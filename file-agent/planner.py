import json
import re
from pathlib import Path
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from state import AgentState
from tools import list_files
from utils.logger import log_info, log_warning
from config import (
    PLANNER_NUM_PREDICT,
    TEXT_EXTENSIONS,
    AMBIGUOUS_STEMS,
    AMBIGUOUS_MAX_STEM_LEN,
    CONTENT_PREVIEW_MAX_CHARS,
    CONTENT_PREVIEW_MAX_BYTES,
)

SYSTEM_PROMPT = """/no_think
You are a file organization planner. You will receive:
1. The user's goal in natural language
2. A listing of files in the target folder (with their contents if provided)

Your job is to produce a precise, ordered JSON plan.
Each step must specify exactly one tool to call and its arguments.

Available tools:
- list_files(folder): List files in a folder
- read_file(path, max_chars): Read file content for classification
- create_folder(path): Create a folder (mkdir -p)
- move_file(src, dest_folder): Move a file to a folder
- rename_file(path, new_name): Rename a file

Rules:
- Always create a destination folder before moving files into it
- Never move files to a folder that hasn't been created yet
- Use full absolute paths in all args (no ~)
- Use EXACTLY the filename as it appears in the file listing — do not invent or guess filenames
- When file names are ambiguous or generic (e.g. doc1.txt, stuff.txt, file10.txt),
  you MUST include a read_file step for each file before deciding where to move it
  or what to rename it to
- When renaming, use a short descriptive snake_case name that reflects the actual
  content (e.g. invoice_acme_feb2026.txt, doctor_visit_jan2026.txt)
- Rename BEFORE moving: rename_file first, then move_file using the NEW renamed path
- After renaming a file, all subsequent steps that reference that file MUST use the new path
- Group files into meaningful semantic folders (Finance, Health, Work, Travel,
  Personal, Education, etc.) — not by extension

Output ONLY valid JSON, no explanation, no markdown fences, no extra text.

Output schema:
{
  "goal": "...",
  "steps": [
    {
      "step": 1,
      "description": "...",
      "tool": "create_folder",
      "args": { "path": "/absolute/path/to/folder" }
    },
    {
      "step": 2,
      "description": "...",
      "tool": "move_file",
      "args": { "src": "/absolute/path/to/file.pdf", "dest_folder": "/absolute/path/to/folder" }
    }
  ]
}"""


def _parse_plan(raw: str) -> list[dict] | None:
    """Extract and parse JSON from LLM output, handling markdown fences."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    # Remove <think>...</think> blocks (qwen3 chain-of-thought)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    try:
        data = json.loads(raw)
        return data.get("steps", [])
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return data.get("steps", [])
            except json.JSONDecodeError:
                pass
    return None


def _simulate_plan(plan: list[dict], files: list[dict]) -> list[tuple]:
    """
    Walk the plan step-by-step against a simulated filesystem to find steps
    whose source file won't exist when they execute.

    Returns a list of (step_index, step, bad_path) for every broken step.
    """
    # Simulated filesystem: name -> full_path
    simulated = {f["name"]: f["full_path"] for f in files}
    broken = []

    for i, step in enumerate(plan):
        tool = step.get("tool", "")
        args = step.get("args", {})

        if tool == "rename_file":
            src_path = args.get("path", "")
            src_name = Path(src_path).name
            if src_name not in simulated:
                broken.append((i, step, src_path))
            else:
                # Simulate the rename so downstream steps see the new name
                new_name_arg = args.get("new_name", "")
                src_suffix = Path(src_path).suffix
                new_name = (new_name_arg + src_suffix
                            if not Path(new_name_arg).suffix
                            else new_name_arg)
                old_full = simulated.pop(src_name)
                new_full = str(Path(old_full).parent / new_name)
                simulated[new_name] = new_full

        elif tool == "move_file":
            src_path = args.get("src", "")
            src_name = Path(src_path).name
            if src_name not in simulated:
                broken.append((i, step, src_path))
            else:
                simulated.pop(src_name)

    return broken


def _fix_broken_steps(plan: list[dict], broken: list[tuple],
                      files: list[dict], folder: str, llm) -> list[dict]:
    """
    Make a targeted LLM call to correct only the steps with bad source paths.
    Returns the corrected plan (in-place mutations on a copy).
    """
    if not broken:
        return plan

    # Which original files are referenced correctly vs not
    correctly_referenced = set()
    for i, step in enumerate(plan):
        if i in {b[0] for b in broken}:
            continue
        tool = step.get("tool", "")
        args = step.get("args", {})
        if tool == "rename_file":
            correctly_referenced.add(Path(args.get("path", "")).name)
        elif tool == "move_file":
            correctly_referenced.add(Path(args.get("src", "")).name)

    unassigned = [
        f for f in files
        if f["name"] not in correctly_referenced
    ]

    if not unassigned:
        log_warning("[PLANNER] Validation: broken steps found but no unassigned files to map them to.")
        return plan

    broken_desc = "\n".join(
        f'  Step {s.get("step", i + 1)}: {s.get("description", "")} | '
        f'tool={s.get("tool", "")} | bad_path={bad}'
        for i, s, bad in broken
    )
    unassigned_desc = "\n".join(
        f'  {f["name"]}  (full path: {f["full_path"]})'
        for f in unassigned
    )

    fix_prompt = (
        f"The following plan steps reference source files that do not exist in the folder:\n"
        f"{broken_desc}\n\n"
        f"The actual files that have not yet been assigned in the plan are:\n"
        f"{unassigned_desc}\n\n"
        f"For each broken step, identify the correct source file from the unassigned list "
        f"and output ONLY a JSON array:\n"
        f'[{{"step": <step_number>, "correct_path": "<full_absolute_path_from_list_above>"}}]\n'
        f"Output only the JSON array. No explanation."
    )

    try:
        response = llm.invoke([HumanMessage(content=fix_prompt)])
        raw = re.sub(r"<think>.*?</think>", "", response.content, flags=re.DOTALL).strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
        corrections = json.loads(raw)

        plan = [dict(s) for s in plan]  # shallow copy
        step_index_map = {s.get("step", i + 1): i for i, s in enumerate(plan)}

        for correction in corrections:
            step_num = correction.get("step")
            correct_path = correction.get("correct_path", "")
            if step_num not in step_index_map or not correct_path:
                continue
            idx = step_index_map[step_num]
            tool = plan[idx].get("tool", "")
            args = dict(plan[idx].get("args", {}))
            if tool == "rename_file":
                args["path"] = correct_path
            elif tool == "move_file":
                args["src"] = correct_path
            plan[idx] = {**plan[idx], "args": args}

        log_info(f"[PLANNER] Corrected {len(corrections)} step(s) with wrong source paths.")

    except Exception as e:
        log_warning(f"[PLANNER] Could not apply path corrections: {e}")

    return plan


def planner_node(state: AgentState) -> dict:
    """
    Planner node: lists files in the target folder, then calls the LLM to generate
    a JSON step plan. Validates all source paths against the real filesystem and
    makes a targeted correction call if any are wrong before returning.
    """
    log_info("\n[PLANNER] Analyzing folder and generating plan...")

    folder = state["folder"]
    goal = state["goal"]
    model = state.get("model", "qwen2.5-coder:14b")

    # List files to give the planner context
    file_listing_result = list_files.invoke({"folder": folder})
    files = file_listing_result.get("files", [])

    # Build file summary with inline content previews for ambiguous text files
    file_summary_lines = []
    for f in files:
        size_kb = round(f["size_bytes"] / 1024, 1)
        stem = f["name"].rstrip("0123456789_- ").lower().split(".")[0]
        is_ambiguous = (
            any(stem.startswith(a) for a in AMBIGUOUS_STEMS)
            or len(stem) <= AMBIGUOUS_MAX_STEM_LEN
        )

        if (f["extension"] in TEXT_EXTENSIONS
                and is_ambiguous
                and f["size_bytes"] < CONTENT_PREVIEW_MAX_BYTES):
            from tools import read_file as _read_file
            result = _read_file.invoke({"path": f["full_path"], "max_chars": CONTENT_PREVIEW_MAX_CHARS})
            preview = result.get("content", "").strip().replace("\n", " ↵ ")[:CONTENT_PREVIEW_MAX_CHARS]
            file_summary_lines.append(
                f"  {f['name']} ({f['extension'] or 'no ext'}, {size_kb}KB)\n"
                f"    CONTENT PREVIEW: {preview}"
            )
        else:
            file_summary_lines.append(f"  {f['name']} ({f['extension'] or 'no ext'}, {size_kb}KB)")

    file_summary = "\n".join(file_summary_lines) if file_summary_lines else "  (folder is empty)"

    user_content = (
        f"Goal: {goal}\n\n"
        f"Target folder: {folder}\n\n"
        f"Files in folder ({len(files)} total):\n{file_summary}"
    )

    llm = ChatOllama(model=model, temperature=0, num_predict=PLANNER_NUM_PREDICT)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    response = llm.invoke(messages)
    raw_output = response.content

    plan = _parse_plan(raw_output)

    if plan is None:
        log_warning("[PLANNER] Failed to parse plan JSON. Raw output:")
        log_warning(raw_output[:2000])
        plan = []

    # ── Validate source paths against actual filesystem ────────────────────────
    if plan and files:
        broken = _simulate_plan(plan, files)
        if broken:
            log_warning(
                f"[PLANNER] {len(broken)} step(s) reference files that don't exist — fixing..."
            )
            plan = _fix_broken_steps(plan, broken, files, folder, llm)

    log_info(f"[PLANNER] Generated {len(plan)}-step plan.")

    stats = state.get("stats", {})
    stats["plan_steps"] = len(plan)

    return {
        "file_listing": files,
        "plan": plan,
        "current_step": 0,
        "step_results": [],
        "last_error": None,
        "decision": None,
        "done": False,
        "stats": stats,
        "retry_counts": {},
    }
