"""
Planner node — two-phase approach to eliminate hallucination:

  Phase 1 (LLM): output a mapping  {filename → {folder, rename}}
  Phase 2 (code): convert mapping to deterministic step list

The LLM only outputs keys that correspond to filenames it was given.
Step generation is pure Python, so no hallucinated filenames can appear
in the final plan — they're filtered out in _validate_mapping before
any steps are built.
"""

import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

import config_vision
from config import (
    AMBIGUOUS_MAX_STEM_LEN,
    AMBIGUOUS_STEMS,
    CONTENT_PREVIEW_MAX_BYTES,
    CONTENT_PREVIEW_MAX_CHARS,
    DOCUMENT_EXTENSIONS,
    PLANNER_NUM_PREDICT,
    TEXT_EXTENSIONS,
)
from config_vision import IMAGE_EXTENSIONS
from state import AgentState
from tools import list_files
from utils.logger import log_info, log_warning

SYSTEM_PROMPT = """/no_think
You are a file organization assistant. Given a list of files, output a JSON object that maps each filename to its destination.

Output schema — one key per file, exactly:
{
  "<exact_filename_from_listing>": {
    "folder": "<SemanticFolderName>",
    "rename": "<new_stem_no_extension_or_null>"
  }
}

Rules:
- Output a key for EVERY file in the listing. No more, no less. Never invent filenames.
- folder: short, meaningful name (Finance, Health, Work, Travel, Personal, Photos, Data, etc.)
- rename: snake_case stem only, NO file extension — set only when the filename is generic
  (e.g. doc1, file2, img001, stuff, data, temp). For descriptive names, use null.
- Use CONTENT and IMAGE descriptions provided to classify accurately.
- Group related files into the same folder.

Output ONLY valid JSON. No markdown, no explanation."""


# ── File info collection ───────────────────────────────────────────────────────

def _is_ambiguous(name: str) -> bool:
    stem = Path(name).stem.rstrip("0123456789_- ").lower()
    return any(stem.startswith(a) for a in AMBIGUOUS_STEMS) or len(stem) <= AMBIGUOUS_MAX_STEM_LEN


def _collect_file_info(files: list[dict]) -> tuple[list[str], dict[str, str]]:
    """
    Build per-file summary lines with inline content/image previews.
    Returns (summary_lines, image_descriptions).
    """
    from tools import read_file as _read_file

    lines: list[str] = []
    image_descriptions: dict[str, str] = {}

    for f in files:
        size_kb = round(f["size_bytes"] / 1024, 1)
        ambiguous = _is_ambiguous(f["name"])

        if (f["extension"] in TEXT_EXTENSIONS
                and ambiguous
                and f["size_bytes"] < CONTENT_PREVIEW_MAX_BYTES):
            result = _read_file.invoke({"path": f["full_path"], "max_chars": CONTENT_PREVIEW_MAX_CHARS})
            preview = result.get("content", "").strip().replace("\n", " ↵ ")[:CONTENT_PREVIEW_MAX_CHARS]
            lines.append(
                f'  "{f["name"]}" ({f["extension"] or "no ext"}, {size_kb}KB)\n'
                f"    CONTENT: {preview}"
            )

        elif f["extension"] in DOCUMENT_EXTENSIONS and ambiguous:
            log_info(f"[PLANNER] Extracting content from document: {f['name']}")
            result = _read_file.invoke({"path": f["full_path"], "max_chars": CONTENT_PREVIEW_MAX_CHARS})
            preview = result.get("content", "").strip().replace("\n", " ↵ ")[:CONTENT_PREVIEW_MAX_CHARS]
            if preview:
                lines.append(
                    f'  "{f["name"]}" ({f["extension"]}, {size_kb}KB)\n'
                    f"    CONTENT: {preview}"
                )
            else:
                lines.append(f'  "{f["name"]}" ({f["extension"]}, {size_kb}KB)')

        elif f["extension"] in DOCUMENT_EXTENSIONS:
            lines.append(f'  "{f["name"]}" ({f["extension"]}, {size_kb}KB)')

        elif f["extension"] in IMAGE_EXTENSIONS:
            if ambiguous:
                log_info(f"[PLANNER] Describing image: {f['name']} via {config_vision.VISION_MODEL}")
                result = _read_file.invoke({"path": f["full_path"], "max_chars": CONTENT_PREVIEW_MAX_CHARS})
                preview = result.get("content", "").strip().replace("\n", " ")[:CONTENT_PREVIEW_MAX_CHARS]
                if preview.startswith("[vision error"):
                    log_warning(f"[PLANNER] Vision unavailable for {f['name']}")
                    preview = ""
                image_descriptions[f["name"]] = preview
                if preview:
                    lines.append(
                        f'  "{f["name"]}" ({f["extension"]}, {size_kb}KB)\n'
                        f"    IMAGE: {preview}"
                    )
                else:
                    lines.append(f'  "{f["name"]}" ({f["extension"]}, {size_kb}KB)')
            else:
                image_descriptions[f["name"]] = ""
                lines.append(f'  "{f["name"]}" ({f["extension"]}, {size_kb}KB)')

        else:
            lines.append(f'  "{f["name"]}" ({f["extension"] or "no ext"}, {size_kb}KB)')

    return lines, image_descriptions


# ── Mapping parsing and validation ─────────────────────────────────────────────

def _parse_mapping(raw: str) -> dict | None:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
    return None


def _validate_mapping(mapping: dict, files: list[dict]) -> dict:
    """
    Strip hallucinated keys (not in real file listing).
    Fill in any files the LLM missed with folder='Other'.
    """
    real_names = {f["name"] for f in files}

    cleaned = {k: v for k, v in mapping.items() if k in real_names}
    dropped = len(mapping) - len(cleaned)
    if dropped:
        log_warning(f"[PLANNER] Dropped {dropped} hallucinated filename(s) from mapping.")

    missing = real_names - set(cleaned)
    if missing:
        log_warning(f"[PLANNER] {len(missing)} file(s) missing from mapping — assigning to 'Other'.")
        for name in missing:
            cleaned[name] = {"folder": "Other", "rename": None}

    return cleaned


# ── Step generation ────────────────────────────────────────────────────────────

def _mapping_to_plan(mapping: dict, files: list[dict], folder: str) -> list[dict]:
    """
    Convert a validated {filename: {folder, rename}} mapping to an ordered step list.
    All source paths come from the real file listing — zero hallucination possible.
    """
    file_index = {f["name"]: f["full_path"] for f in files}

    # Collect destination folders in order of first appearance
    seen_folders: set[str] = set()
    ordered_folders: list[str] = []
    for entry in mapping.values():
        dest = entry.get("folder") or "Other"
        if dest not in seen_folders:
            ordered_folders.append(dest)
            seen_folders.add(dest)

    steps: list[dict] = []
    n = 1

    # Create all folders first
    for folder_name in ordered_folders:
        steps.append({
            "step": n,
            "description": f"Create {folder_name}/ folder",
            "tool": "create_folder",
            "args": {"path": str(Path(folder) / folder_name)},
        })
        n += 1

    # Rename (if needed) then move each file
    for fname, entry in mapping.items():
        src_path = file_index.get(fname)
        if not src_path:
            continue  # already impossible after _validate_mapping, but be safe

        dest_name = entry.get("folder") or "Other"
        dest_folder_path = str(Path(folder) / dest_name)
        rename_stem = entry.get("rename") or None

        if rename_stem:
            ext = Path(fname).suffix
            # Strip extension if model accidentally included it in the stem
            stem = re.sub(re.escape(ext) + r"$", "", rename_stem, flags=re.IGNORECASE).strip()
            new_name = stem + ext
            new_path = str(Path(src_path).parent / new_name)

            steps.append({
                "step": n,
                "description": f"Rename {fname} → {new_name}",
                "tool": "rename_file",
                "args": {"path": src_path, "new_name": new_name},
            })
            n += 1
            steps.append({
                "step": n,
                "description": f"Move {new_name} → {dest_name}/",
                "tool": "move_file",
                "args": {"src": new_path, "dest_folder": dest_folder_path},
            })
        else:
            steps.append({
                "step": n,
                "description": f"Move {fname} → {dest_name}/",
                "tool": "move_file",
                "args": {"src": src_path, "dest_folder": dest_folder_path},
            })
        n += 1

    return steps


# ── Planner node ───────────────────────────────────────────────────────────────

def planner_node(state: AgentState) -> dict:
    """
    Planner node: asks the LLM for a filename→folder/rename mapping, then
    converts it to a deterministic step list in Python.

    On replan (decision == "replan"), bypasses the early-exit guard so a
    fresh plan is generated from the current folder state.
    """
    is_replan = state.get("decision") == "replan"

    if state.get("plan") and not is_replan:
        log_info("[PLANNER] Plan already exists — skipping re-plan.")
        return {}

    if is_replan:
        log_info("\n[PLANNER] Replanning from current folder state...")
    else:
        log_info("\n[PLANNER] Analyzing folder and generating plan...")

    folder = state["folder"]
    goal = state["goal"]
    model = state.get("model", "qwen2.5-coder:14b")

    file_listing_result = list_files.invoke({"folder": folder})
    files = file_listing_result.get("files", [])

    if not files:
        log_warning("[PLANNER] Folder is empty — nothing to do.")
        stats = state.get("stats", {})
        stats["plan_steps"] = 0
        return {
            "file_listing": [], "plan": [], "current_step": 0,
            "step_results": [], "last_error": None, "decision": None,
            "done": True, "stats": stats, "retry_counts": {},
        }

    summary_lines, _ = _collect_file_info(files)
    file_summary = "\n".join(summary_lines)

    user_content = (
        f"Goal: {goal}\n\n"
        f"Target folder: {folder}\n\n"
        f"Files ({len(files)} total — use EXACTLY these filenames as keys, no others):\n"
        f"{file_summary}"
    )

    llm = ChatOllama(model=model, temperature=0, num_predict=PLANNER_NUM_PREDICT, think=False)
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content)]

    response = llm.invoke(messages)
    raw = re.sub(r"<think>.*?</think>", "", response.content, flags=re.DOTALL).strip()
    mapping = _parse_mapping(raw)

    if mapping is None:
        log_warning("[PLANNER] Failed to parse mapping — retrying once...")
        response = llm.invoke(messages)
        raw = re.sub(r"<think>.*?</think>", "", response.content, flags=re.DOTALL).strip()
        mapping = _parse_mapping(raw)

    if mapping is None:
        log_warning("[PLANNER] Mapping parse failed after retry — all files → Other.")
        mapping = {}

    mapping = _validate_mapping(mapping, files)
    plan = _mapping_to_plan(mapping, files, folder)

    log_info(f"[PLANNER] {len(files)} file(s) → {len(plan)}-step plan.")

    stats = dict(state.get("stats", {}))
    stats["plan_steps"] = len(plan)

    return {
        "file_listing": files,
        "plan": plan,
        "current_step": 0,
        "step_results": list(state.get("step_results", [])),
        "last_error": None,
        "decision": None,
        "done": False,
        "stats": stats,
        "retry_counts": {},
    }
