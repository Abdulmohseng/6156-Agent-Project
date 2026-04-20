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
from config_vision import IMAGE_EXTENSIONS, VISION_MODEL

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
- CRITICAL: Every single file in the listing MUST have a move_file step. Never skip any file.
- Always create a destination folder before moving files into it
- Never move files to a folder that hasn't been created yet
- Use full absolute paths in all args (no ~)
- Use EXACTLY the filename as it appears in the file listing — do not invent or guess filenames
- When file names are ambiguous or generic (e.g. doc1.txt, img001.jpg, stuff.txt, file10.txt,
  photo_002.png), you MUST include a read_file step for each file before deciding where to
  move it or what to rename it
- When a file has a generic or non-descriptive name, you MUST rename it to a short descriptive
  snake_case name that reflects the actual content BEFORE moving it. This applies to both text
  files AND image files. Examples:
    doc1.txt        → invoice_acme_feb2026.txt   (based on content preview)
    img001.jpg      → beach_sunset_travel.jpg    (based on image description)
    img004.jpg      → golden_retriever_dog.jpg   (based on image description)
    stuff.txt       → gym_log_mar2026.txt        (based on content preview)
- Rename BEFORE moving: rename_file first, then move_file using the NEW renamed path
- After renaming a file, all subsequent steps that reference that file MUST use the new path
- Group files into meaningful semantic folders (Finance, Health, Work, Travel,
  Personal, Nature, Animals, Food, Education, etc.) — not by extension
- Images (.jpg, .jpeg, .png, etc.) MUST be organized just like any other file — do not skip them

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


def _generate_image_filename(original_name: str, description: str, llm) -> str:
    """
    Ask the LLM to produce a short snake_case filename for an image given its
    description. Returns the new filename (with original extension preserved).
    Falls back to the original name if parsing fails.
    """
    ext = Path(original_name).suffix
    prompt = (
        f"Generate a short, descriptive snake_case filename for an image file.\n"
        f"Original filename: {original_name}\n"
        f"Image description: {description}\n\n"
        f"Rules:\n"
        f"- Maximum 4 words, snake_case, no spaces\n"
        f"- Do NOT include the file extension\n"
        f"- Output ONLY the stem (no extension, no explanation)\n"
        f"Examples: beach_sunset, golden_retriever_dog, mountain_trail, city_skyline_night"
    )
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = re.sub(r"<think>.*?</think>", "", response.content, flags=re.DOTALL).strip()
        # Strip any extension the model may have added, quotes, or extra whitespace
        stem = raw.strip().strip('"\'').split()[0]
        stem = re.sub(r"\.[a-zA-Z]{2,5}$", "", stem)
        stem = re.sub(r"[^\w]", "_", stem).strip("_")
        if stem:
            return stem + ext
    except Exception as e:
        log_warning(f"[PLANNER] Could not generate filename for {original_name}: {e}")
    return original_name


def _inject_image_renames(
    plan: list[dict],
    image_descriptions: dict[str, str],
    folder: str,
    llm,
) -> list[dict]:
    """
    For every image in `image_descriptions` that has no rename_file step in the
    plan, generate a descriptive filename and inject a rename_file step immediately
    before its move_file step (updating the move_file src to use the new path).
    All step numbers are renumbered at the end.
    """
    if not image_descriptions:
        return plan

    # Which images already have a rename step in the plan?
    already_renamed = set()
    for step in plan:
        if step.get("tool") == "rename_file":
            src = step.get("args", {}).get("path", "")
            already_renamed.add(Path(src).name)

    # Build new plan, injecting rename steps where needed
    new_plan = []
    for step in plan:
        tool = step.get("tool", "")
        args = step.get("args", {})

        if tool == "move_file":
            src_path = args.get("src", "")
            src_name = Path(src_path).name
            if src_name in image_descriptions and src_name not in already_renamed:
                description = image_descriptions[src_name]
                new_filename = _generate_image_filename(src_name, description, llm)
                new_path = str(Path(src_path).parent / new_filename)

                log_info(f"[PLANNER] Injecting rename: {src_name} → {new_filename}")

                # Inject rename_file step before this move
                rename_step = {
                    "step": 0,  # renumbered below
                    "description": f"Rename {src_name} to descriptive name {new_filename}",
                    "tool": "rename_file",
                    "args": {"path": src_path, "new_name": new_filename},
                }
                new_plan.append(rename_step)

                # Update move_file to use the new path
                updated_step = {
                    **step,
                    "args": {**args, "src": new_path},
                }
                new_plan.append(updated_step)
                already_renamed.add(src_name)
                continue

        new_plan.append(step)

    # Renumber all steps sequentially
    for i, step in enumerate(new_plan):
        new_plan[i] = {**step, "step": i + 1}

    injected = len(new_plan) - len(plan)
    if injected:
        log_info(f"[PLANNER] Injected {injected} rename step(s) for generic image names.")

    return new_plan


def _append_uncovered_files(
    plan: list[dict],
    files: list[dict],
    image_descriptions: dict[str, str],
    folder: str,
    llm,
) -> list[dict]:
    """
    Find any files that have no move_file step in the plan and append steps for them.

    Coverage logic: a file is considered covered if its original name appears as the
    source of a rename_file step (which always precedes its move), OR directly as the
    src of a move_file step (for files that aren't renamed).
    """
    renamed_originals = {
        Path(s["args"].get("path", "")).name
        for s in plan if s.get("tool") == "rename_file"
    }
    moved_srcs = {
        Path(s["args"].get("src", "")).name
        for s in plan if s.get("tool") == "move_file"
    }
    covered = renamed_originals | moved_srcs

    uncovered = [f for f in files if f["name"] not in covered]
    if not uncovered:
        return plan

    log_warning(f"[PLANNER] {len(uncovered)} file(s) not covered by plan — generating steps...")

    existing_folders = sorted({
        Path(s["args"]["path"]).name
        for s in plan if s.get("tool") == "create_folder"
    })

    uncovered_desc_lines = []
    for f in uncovered:
        size_kb = round(f["size_bytes"] / 1024, 1)
        line = f"  {f['name']} ({f['extension'] or 'no ext'}, {size_kb}KB)"
        if f["name"] in image_descriptions:
            desc = image_descriptions[f["name"]]
            if not desc.startswith("[vision error"):
                line += f"\n    IMAGE DESCRIPTION: {desc}"
        uncovered_desc_lines.append(line)

    fix_prompt = (
        f"/no_think\n"
        f"These files were NOT included in the organization plan. "
        f"Generate JSON steps to organize ALL of them.\n\n"
        f"Target folder: {folder}\n"
        f"Folders already created in the plan: {', '.join(existing_folders) if existing_folders else 'none'}\n\n"
        f"Files to organize:\n" + "\n".join(uncovered_desc_lines) + "\n\n"
        f"Rules:\n"
        f"- Use full absolute paths\n"
        f"- create_folder first if the destination doesn't exist yet\n"
        f"- If the filename is generic (e.g. img001.jpg, doc1.txt), rename it first "
        f"(rename_file), then move with the NEW path\n"
        f"- Group into meaningful folders (Nature, Animals, Food, Travel, etc.)\n\n"
        f"Output ONLY a JSON array of steps (no wrapper object):\n"
        f'[{{"step": 0, "description": "...", "tool": "...", "args": {{...}}}}]'
    )

    try:
        response = llm.invoke([HumanMessage(content=fix_prompt)])
        raw = re.sub(r"<think>.*?</think>", "", response.content, flags=re.DOTALL).strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
        new_steps = json.loads(raw)

        if isinstance(new_steps, list) and new_steps:
            plan = list(plan) + new_steps
            for i, step in enumerate(plan):
                plan[i] = {**step, "step": i + 1}
            log_info(f"[PLANNER] Appended {len(new_steps)} step(s) for {len(uncovered)} uncovered file(s).")
        else:
            log_warning("[PLANNER] Coverage fix returned no steps.")
    except Exception as e:
        log_warning(f"[PLANNER] Could not generate steps for uncovered files: {e}")

    return plan


def planner_node(state: AgentState) -> dict:
    """
    Planner node: lists files in the target folder, then calls the LLM to generate
    a JSON step plan. Validates all source paths against the real filesystem and
    makes a targeted correction call if any are wrong before returning.
    """
    # If a plan was already generated (e.g. for pre-run user confirmation), skip re-planning
    if state.get("plan"):
        log_info("[PLANNER] Plan already exists — skipping re-plan.")
        return {}

    log_info("\n[PLANNER] Analyzing folder and generating plan...")

    folder = state["folder"]
    goal = state["goal"]
    model = state.get("model", "qwen2.5-coder:14b")

    # List files to give the planner context
    file_listing_result = list_files.invoke({"folder": folder})
    files = file_listing_result.get("files", [])

    # Build file summary with inline content previews for ambiguous text files
    # Also collect image descriptions for programmatic rename injection later
    file_summary_lines = []
    image_descriptions: dict[str, str] = {}  # {filename: description}

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
            # Ambiguous text file — read content inline so planner can classify
            from tools import read_file as _read_file
            result = _read_file.invoke({"path": f["full_path"], "max_chars": CONTENT_PREVIEW_MAX_CHARS})
            preview = result.get("content", "").strip().replace("\n", " ↵ ")[:CONTENT_PREVIEW_MAX_CHARS]
            file_summary_lines.append(
                f"  {f['name']} ({f['extension'] or 'no ext'}, {size_kb}KB)\n"
                f"    CONTENT PREVIEW: {preview}"
            )
        elif f["extension"] in IMAGE_EXTENSIONS:
            # Image file — always register so the coverage check can handle missed images.
            # Only call the vision model when the name is ambiguous (needs description for rename).
            from tools import read_file as _read_file
            if is_ambiguous:
                log_info(f"[PLANNER] Describing image via {VISION_MODEL}: {f['name']}")
                result = _read_file.invoke({"path": f["full_path"], "max_chars": CONTENT_PREVIEW_MAX_CHARS})
                preview = result.get("content", "").strip().replace("\n", " ")[:CONTENT_PREVIEW_MAX_CHARS]
                if preview.startswith("[vision error"):
                    log_warning(f"[PLANNER] Vision model unavailable for {f['name']} — image will be moved without description")
                    preview = ""
            else:
                preview = ""
            image_descriptions[f["name"]] = preview  # always track images
            if preview:
                file_summary_lines.append(
                    f"  {f['name']} ({f['extension'] or 'no ext'}, {size_kb}KB)\n"
                    f"    IMAGE DESCRIPTION: {preview}"
                )
            else:
                file_summary_lines.append(f"  {f['name']} ({f['extension'] or 'no ext'}, {size_kb}KB)")
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

    # ── Programmatically inject rename steps for generic-named images ──────────
    if image_descriptions:
        plan = _inject_image_renames(plan, image_descriptions, folder, llm)

    # ── Safety net: append steps for any files the LLM missed entirely ─────────
    if plan and files:
        plan = _append_uncovered_files(plan, files, image_descriptions, folder, llm)

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
