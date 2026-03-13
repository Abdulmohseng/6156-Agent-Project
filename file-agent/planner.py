import json
import re
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
- When file names are ambiguous or generic (e.g. doc1.txt, stuff.txt, file10.txt),
  you MUST include a read_file step for each file before deciding where to move it
  or what to rename it to
- When renaming, use a short descriptive snake_case name that reflects the actual
  content (e.g. invoice_acme_feb2026.txt, doctor_visit_jan2026.txt)
- Rename BEFORE moving: rename_file first, then move_file with the new path
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
    # Strip markdown code fences if present
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
        # Try to find JSON object within the response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return data.get("steps", [])
            except json.JSONDecodeError:
                pass
    return None


def planner_node(state: AgentState) -> dict:
    """
    Planner node: lists files in the target folder, then calls the LLM to generate
    a JSON step plan. Stores plan in state and resets execution counters.
    """
    log_info("\n[PLANNER] Analyzing folder and generating plan...")

    folder = state["folder"]
    goal = state["goal"]
    model = state.get("model", "qwen3:8b")

    # List files to give the planner context
    file_listing_result = list_files.invoke({"folder": folder})
    files = file_listing_result.get("files", [])

    # Build file summary. For small text files with ambiguous names, include a
    # content preview so the planner can classify and rename without extra read steps.
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
