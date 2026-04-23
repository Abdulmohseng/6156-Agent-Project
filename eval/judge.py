"""
LLM-as-judge for file organization quality using a local Ollama model.

Sends the original file list, agent's actual output, and ground truth to the
model and asks for a structured JSON quality score (1-10).
"""

import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "file-agent"))
from config import OLLAMA_BASE_URL, DEFAULT_MODEL

DEFAULT_JUDGE_MODEL = DEFAULT_MODEL
JUDGE_NUM_PREDICT = 1024

SYSTEM_PROMPT = """You are an expert evaluator for file organization quality.
You will receive the original file list, what a file organization agent produced, and the expected ground-truth organization.

Score the organization on a 1–10 scale and output ONLY valid JSON matching this schema exactly:
{
  "score": <integer 1-10>,
  "reasoning": "<2-3 sentence explanation>",
  "strengths": ["<strength>"],
  "weaknesses": ["<weakness>"],
  "folder_quality": "<poor|fair|good|excellent>",
  "naming_quality": "<poor|fair|good|excellent>",
  "coverage_assessment": "<brief note on whether all files were handled>"
}

Scoring rubric:
1-3: Major failures — many files left unorganized, completely wrong categories
4-5: Below average — some correct but significant misclassifications or missed files
6-7: Good — most files correctly categorized, minor issues
8-9: Very good — all files placed correctly, intuitive structure
10: Excellent — perfect placement, ideal semantics, descriptive naming throughout

Do not output anything outside the JSON object."""

USER_TEMPLATE = """ORIGINAL FILES (before organization):
{original_files}

AGENT OUTPUT STRUCTURE:
{actual_structure}

EXPECTED GROUND TRUTH:
{ground_truth_structure}

PROGRAMMATIC SCORES:
- Coverage: {coverage_pct}% ({files_placed}/{total_files} files moved out of root)
- Placement Accuracy: {placement_pct}% ({files_matched}/{total_files} files in correct folder)

Evaluate the quality of this organization."""


def _format_actual_structure(file_map: dict) -> str:
    by_folder: dict[str, list[str]] = {}
    for original, info in file_map.items():
        folder = info.get("final_folder") or "__root__ (not moved)"
        name = info.get("final_name", original)
        by_folder.setdefault(folder, []).append(name)
    lines = []
    for folder, files in sorted(by_folder.items()):
        lines.append(f"{folder}/")
        for f in sorted(files):
            lines.append(f"  {f}")
    return "\n".join(lines) if lines else "(no files were moved)"


def _format_ground_truth_structure(gt: dict) -> str:
    by_folder: dict[str, list[str]] = {}
    for fname, entry in gt["files"].items():
        folder = entry["expected_folder"]
        by_folder.setdefault(folder, []).append(fname)
    lines = []
    for folder, files in sorted(by_folder.items()):
        lines.append(f"{folder}/")
        for f in sorted(files):
            lines.append(f"  {f}")
    return "\n".join(lines)


def _strip_think_tags(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def judge_run(
    original_files: list[str],
    file_map: dict,
    ground_truth: dict,
    structural_scores: dict,
    judge_model: str = DEFAULT_JUDGE_MODEL,
) -> dict:
    """
    Call local Ollama model to semantically score the organization result.
    Returns parsed judge response dict.
    """
    actual_structure = _format_actual_structure(file_map)
    gt_structure = _format_ground_truth_structure(ground_truth)
    original_list = "\n".join(f"  {f}" for f in sorted(original_files))

    total = structural_scores["total_files"]
    placed = structural_scores["files_placed"]
    matched = structural_scores["files_folder_matched"]

    user_content = USER_TEMPLATE.format(
        original_files=original_list,
        actual_structure=actual_structure,
        ground_truth_structure=gt_structure,
        coverage_pct=round(structural_scores["coverage"] * 100),
        placement_pct=round(structural_scores["placement_accuracy"] * 100),
        files_placed=placed,
        files_matched=matched,
        total_files=total,
    )

    prompt = f"{SYSTEM_PROMPT}\n\n{user_content}"

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": judge_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": JUDGE_NUM_PREDICT,
                    "temperature": 0,
                },
            },
            timeout=300,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
    except Exception as e:
        return {"score": None, "error": str(e), "judge_model": judge_model}

    raw = _strip_think_tags(raw)
    raw = _extract_json(raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"score": None, "reasoning": f"Parse error: {raw[:300]}", "error": True}

    parsed["judge_model"] = judge_model
    return parsed
