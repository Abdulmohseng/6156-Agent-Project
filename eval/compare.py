"""
Structural comparison between agent output and ground truth.

Reads the manifest execution trace to reconstruct which original file
ended up in which folder, then scores each file against ground truth labels.
"""

import json
from pathlib import Path
from typing import Optional


def build_original_to_final_map(manifest: dict) -> dict[str, dict]:
    """
    Parse the manifest execution trace to reconstruct:
      {original_filename: {final_name: str, final_folder: str | None}}

    Handles rename chains: if file A was renamed to B then moved to folder F,
    original "A" maps to {final_name: "B", final_folder: "F"}.
    """
    rename_map: dict[str, str] = {}  # current_name -> original_name (reverse lookup)
    file_destinations: dict[str, dict] = {}  # original_name -> {final_name, final_folder}

    for step in manifest.get("execution", []):
        if step.get("status") != "success":
            continue
        tool = step.get("tool", "")
        args = step.get("args", {})

        if tool == "rename_file":
            src_name = Path(args.get("path", "")).name
            new_name = args.get("new_name", src_name)
            original = rename_map.get(src_name, src_name)
            rename_map[new_name] = original
            entry = file_destinations.setdefault(original, {"final_name": src_name, "final_folder": None})
            entry["final_name"] = new_name

        elif tool == "move_file":
            src_name = Path(args.get("src", "")).name
            dest_folder = Path(args.get("dest_folder", "")).name
            original = rename_map.get(src_name, src_name)
            entry = file_destinations.setdefault(original, {"final_name": src_name, "final_folder": None})
            entry["final_folder"] = dest_folder

    return file_destinations


def _folder_matches(actual_folder: Optional[str], gt_entry: dict) -> bool:
    if not actual_folder:
        return False
    expected = gt_entry["expected_folder"]
    aliases = [expected] + gt_entry.get("folder_aliases", [])
    aliases_lower = {a.lower() for a in aliases}
    return actual_folder.lower() in aliases_lower


def compute_structural_scores(manifest: dict, ground_truth: dict) -> dict:
    """
    Score agent output against ground truth labels.

    Returns:
      total_files, files_placed, files_folder_matched,
      coverage (placed/total), placement_accuracy (matched/total),
      per_file list with per-file details.
    """
    gt_files = ground_truth["files"]
    file_map = build_original_to_final_map(manifest)

    per_file = []
    for original_name, gt_entry in gt_files.items():
        destination = file_map.get(original_name, {})
        actual_folder = destination.get("final_folder")
        final_name = destination.get("final_name", original_name)

        placed = actual_folder is not None
        matched = _folder_matches(actual_folder, gt_entry)

        per_file.append({
            "original_name": original_name,
            "final_name": final_name,
            "expected_folder": gt_entry["expected_folder"],
            "actual_folder": actual_folder,
            "placed": placed,
            "folder_match": matched,
        })

    total = len(per_file)
    placed_count = sum(1 for r in per_file if r["placed"])
    matched_count = sum(1 for r in per_file if r["folder_match"])

    return {
        "total_files": total,
        "files_placed": placed_count,
        "files_folder_matched": matched_count,
        "coverage": round(placed_count / total, 3) if total else 0.0,
        "placement_accuracy": round(matched_count / total, 3) if total else 0.0,
        "per_file": per_file,
    }


def load_ground_truth(dataset: str) -> dict:
    gt_path = Path(__file__).parent / "ground_truth" / f"{dataset}.json"
    with open(gt_path) as f:
        return json.load(f)


def load_manifest(run_id: str) -> dict:
    runs_dir = Path.home() / ".file-agent" / "runs"
    path = runs_dir / run_id / "manifest.json"
    with open(path) as f:
        return json.load(f)
