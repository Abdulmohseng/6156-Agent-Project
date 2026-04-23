"""
Rich terminal report and JSON comparison aggregation for eval results.
"""

import json
from datetime import datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

RESULTS_DIR = Path(__file__).parent / "results"
console = Console()


def _color(value: float, good: float = 0.8, ok: float = 0.6) -> str:
    if value >= good:
        return "green"
    elif value >= ok:
        return "yellow"
    return "red"


def print_comparison_table(results: list[dict]):
    table = Table(
        title="File Organization Agent — Evaluation Results",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("Model", style="bold cyan", min_width=22)
    table.add_column("Coverage", justify="center")
    table.add_column("Placement Acc.", justify="center")
    table.add_column("Judge Score", justify="center")
    table.add_column("Folder Quality", justify="center")
    table.add_column("Files Moved", justify="center")
    table.add_column("Replans", justify="center")
    table.add_column("Duration (s)", justify="center")
    table.add_column("Run ID", style="dim")

    for r in results:
        if "error" in r:
            table.add_row(
                r.get("model", "unknown"),
                "[red]ERROR[/red]", "-", "-", "-", "-", "-", "-",
                r.get("error", "")[:50],
            )
            continue

        struct = r.get("structural", {})
        judge = r.get("judge", {})
        summary = r.get("agent_summary", {})

        coverage = struct.get("coverage", 0.0)
        placement = struct.get("placement_accuracy", 0.0)
        score = judge.get("score")
        folder_q = judge.get("folder_quality", "-")

        cov_str = f"[{_color(coverage)}]{coverage:.0%}[/]"
        plc_str = f"[{_color(placement)}]{placement:.0%}[/]"

        if isinstance(score, (int, float)):
            score_color = _color(score / 10)
            score_str = f"[{score_color}]{score}/10[/]"
        else:
            score_str = "-"

        table.add_row(
            r.get("model", "unknown"),
            cov_str,
            plc_str,
            score_str,
            folder_q,
            str(summary.get("files_moved", "-")),
            str(summary.get("replans", "-")),
            str(round(summary.get("duration_seconds", 0), 1)),
            r.get("run_id", ""),
        )

    console.print()
    console.print(table)

    for r in results:
        if "structural" in r and r["structural"].get("per_file"):
            _print_per_file(r)
            break


def _print_per_file(result: dict):
    table = Table(
        title=f"Per-File Placement — {result.get('model', '')} ({result.get('run_id', '')})",
        box=box.SIMPLE,
    )
    table.add_column("Original File")
    table.add_column("Expected Folder")
    table.add_column("Actual Folder")
    table.add_column("Placed?", justify="center")
    table.add_column("Match?", justify="center")

    for r in result["structural"]["per_file"]:
        placed = "[green]Yes[/]" if r["placed"] else "[red]No[/]"
        match = "[green]Yes[/]" if r["folder_match"] else "[red]No[/]"
        actual = r.get("actual_folder") or "[dim]not moved[/dim]"
        table.add_row(
            r["original_name"],
            r["expected_folder"],
            actual,
            placed,
            match,
        )

    console.print()
    console.print(table)

    if result.get("judge", {}).get("reasoning"):
        console.print(f"\n[bold]Judge reasoning:[/bold] {result['judge']['reasoning']}")
        if result["judge"].get("weaknesses"):
            console.print(f"[bold]Weaknesses:[/bold] {', '.join(result['judge']['weaknesses'])}")


def _compute_aggregate(results: list[dict]) -> dict:
    by_model: dict[str, list] = {}
    for r in results:
        if "error" in r:
            continue
        by_model.setdefault(r["model"], []).append(r)

    agg = {}
    for model, runs in by_model.items():
        coverages = [r["structural"]["coverage"] for r in runs]
        placements = [r["structural"]["placement_accuracy"] for r in runs]
        scores = [r["judge"]["score"] for r in runs
                  if isinstance(r.get("judge", {}).get("score"), (int, float))]
        durations = [r["agent_summary"]["duration_seconds"] for r in runs]

        agg[model] = {
            "num_runs": len(runs),
            "avg_coverage": round(sum(coverages) / len(coverages), 3),
            "avg_placement_accuracy": round(sum(placements) / len(placements), 3),
            "avg_judge_score": round(sum(scores) / len(scores), 2) if scores else None,
            "avg_duration_seconds": round(sum(durations) / len(durations), 1),
        }
    return agg


def save_comparison(results: list[dict]) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = RESULTS_DIR / f"comparison_{timestamp}.json"
    output = {
        "timestamp": timestamp,
        "results": results,
        "aggregate": _compute_aggregate(results),
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    return path
