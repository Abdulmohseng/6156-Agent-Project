"""
Folder-based evaluator — no agent manifest required.

Walks an already-organized folder, maps each file to its parent subfolder,
and scores against ground truth. Use this to evaluate any organizer (Claude Code,
manual, rule-based, etc.) that doesn't produce an agent manifest.

Usage:
  python eval/eval_folder.py --folder <path-to-organized-folder> --dataset model_test
  python eval/eval_folder.py --folder ~/Desktop/my_organized/ --dataset sample_flat
"""

import argparse
import json
from pathlib import Path

from compare import _folder_matches, load_ground_truth


def build_map_from_folder(folder: Path) -> dict[str, dict]:
    """
    Walk a folder and map each file to the subfolder it lives in.

    Files in the root of `folder` (not in any subfolder) get final_folder=None.
    Returns {filename: {final_name, final_folder}}.
    """
    result: dict[str, dict] = {}
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(folder)
        parts = relative.parts
        if len(parts) == 1:
            # File is still at root — not organized
            final_folder = None
        else:
            # First path component is the subfolder name
            final_folder = parts[0]
        result[path.name] = {
            "final_name": path.name,
            "final_folder": final_folder,
        }
    return result


def score_folder(folder: Path, ground_truth: dict, name_map: dict | None = None) -> dict:
    """
    Score an organized folder against ground truth labels.

    name_map: optional {original_filename: renamed_filename} for when the
    organizer also renamed files (e.g. Claude Code). Without it, matching
    is by exact filename.
    """
    gt_files = ground_truth["files"]
    file_map = build_map_from_folder(folder)
    name_map = name_map or {}

    per_file = []
    for original_name, gt_entry in gt_files.items():
        # Look up by renamed name first, then fall back to original name
        lookup_name = name_map.get(original_name, original_name)
        destination = file_map.get(lookup_name, {})

        actual_folder = destination.get("final_folder") if destination else None
        final_name = destination.get("final_name", original_name) if destination else original_name

        placed = actual_folder is not None
        matched = _folder_matches(actual_folder, gt_entry)

        per_file.append({
            "original_name": original_name,
            "final_name": final_name,
            "expected_folder": gt_entry["expected_folder"],
            "actual_folder": actual_folder or "(root — not moved)",
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


def print_results(scores: dict, folder: Path, dataset: str, organizer: str):
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box

        console = Console()
        console.print(f"\n[bold cyan]Folder Evaluation Results[/bold cyan]")
        console.print(f"  Organizer : [bold]{organizer}[/bold]")
        console.print(f"  Folder    : {folder}")
        console.print(f"  Dataset   : {dataset}")

        cov = scores["coverage"]
        acc = scores["placement_accuracy"]
        cov_color = "green" if cov >= 0.8 else "yellow" if cov >= 0.6 else "red"
        acc_color = "green" if acc >= 0.8 else "yellow" if acc >= 0.6 else "red"

        console.print(f"\n  Coverage          : [{cov_color}]{cov*100:.0f}%[/{cov_color}] "
                      f"({scores['files_placed']}/{scores['total_files']} files moved)")
        console.print(f"  Placement Accuracy: [{acc_color}]{acc*100:.0f}%[/{acc_color}] "
                      f"({scores['files_folder_matched']}/{scores['total_files']} correct folder)")

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("File", style="dim")
        table.add_column("Expected")
        table.add_column("Actual")
        table.add_column("Match")

        for r in scores["per_file"]:
            match_icon = "[green]✓[/green]" if r["folder_match"] else (
                "[yellow]~[/yellow]" if r["placed"] else "[red]✗[/red]"
            )
            table.add_row(
                r["original_name"],
                r["expected_folder"],
                r["actual_folder"],
                match_icon,
            )

        console.print(table)

    except ImportError:
        print(f"\nOrganizer : {organizer}")
        print(f"Folder    : {folder}")
        print(f"Dataset   : {dataset}")
        print(f"Coverage          : {scores['coverage']*100:.0f}%")
        print(f"Placement Accuracy: {scores['placement_accuracy']*100:.0f}%")
        for r in scores["per_file"]:
            mark = "✓" if r["folder_match"] else ("~" if r["placed"] else "✗")
            print(f"  {mark} {r['original_name']:15} → {r['actual_folder']:20} (expected: {r['expected_folder']})")


def main():
    parser = argparse.ArgumentParser(description="Evaluate an organized folder against ground truth")
    parser.add_argument("--folder",   required=True, help="Path to the organized folder to evaluate")
    parser.add_argument("--dataset",  default="model_test", help="Ground truth dataset name (default: model_test)")
    parser.add_argument("--organizer", default="external", help="Label for who organized the folder (e.g. 'claude-code')")
    parser.add_argument("--name-map", metavar="FILE",
                        help="JSON file mapping original filenames to renamed filenames "
                             "(use when the organizer also renamed files)")
    parser.add_argument("--save",     action="store_true", help="Save results JSON to eval/results/")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists():
        print(f"Error: folder not found: {folder}")
        raise SystemExit(1)

    name_map = {}
    if args.name_map:
        with open(args.name_map) as f:
            name_map = json.load(f)

    ground_truth = load_ground_truth(args.dataset)
    scores = score_folder(folder, ground_truth, name_map=name_map)
    print_results(scores, folder, args.dataset, args.organizer)

    if args.save:
        out_dir = Path(__file__).parent / "results"
        out_dir.mkdir(exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = out_dir / f"folder_eval_{ts}_{args.organizer}.json"
        with open(out_path, "w") as f:
            json.dump({
                "organizer": args.organizer,
                "folder": str(folder),
                "dataset": args.dataset,
                **scores,
            }, f, indent=2)
        print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
