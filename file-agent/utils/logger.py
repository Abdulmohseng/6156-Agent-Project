import json
import os
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console

console = Console()

LOG_DIR = Path.home() / ".file-agent" / "logs"


def init_stats(goal: str, model: str) -> dict:
    return {
        "timestamp": datetime.now().isoformat(),
        "goal": goal,
        "model": model,
        "plan_steps": 0,
        "steps_completed": 0,
        "steps_failed": 0,
        "steps_skipped": 0,
        "replans": 0,
        "files_moved": 0,
        "folders_created": 0,
        "files_renamed": 0,
        "duration_seconds": 0.0,
        "start_time": time.time(),
    }


def finalize_stats(stats: dict) -> dict:
    stats["duration_seconds"] = round(time.time() - stats.pop("start_time", time.time()), 2)
    return stats


def save_log(stats: dict) -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = LOG_DIR / f"{ts}.json"
    with open(log_path, "w") as f:
        json.dump(stats, f, indent=2)
    return str(log_path)


def log_step_success(step: dict, result: dict, verbose: bool = False):
    description = step.get("description", "")
    console.print(f"  [green]✓[/green] {description}")
    if verbose and result:
        console.print(f"    [dim]{result.get('message', '')}[/dim]")


def log_step_failure(step: dict, error: str):
    description = step.get("description", "")
    console.print(f"  [red]✗[/red] {description}")
    console.print(f"    [red dim]{error}[/red dim]")


def log_step_skipped(step: dict):
    description = step.get("description", "")
    console.print(f"  [yellow]⊘[/yellow] {description} [dim](skipped)[/dim]")


def log_info(msg: str):
    console.print(f"[cyan]{msg}[/cyan]")


def log_warning(msg: str):
    console.print(f"[yellow]{msg}[/yellow]")


def log_error(msg: str):
    console.print(f"[red]{msg}[/red]")


def print_summary(stats: dict, log_path: str = None):
    console.print()
    console.print("[bold cyan]─── Summary ───────────────────────────────────[/bold cyan]")
    console.print(f"  Steps completed : [green]{stats['steps_completed']}[/green]")
    if stats["steps_failed"]:
        console.print(f"  Steps failed    : [red]{stats['steps_failed']}[/red]")
    if stats["steps_skipped"]:
        console.print(f"  Steps skipped   : [yellow]{stats['steps_skipped']}[/yellow]")
    if stats["replans"]:
        console.print(f"  Replans         : {stats['replans']}")
    console.print(f"  Files moved     : {stats['files_moved']}")
    console.print(f"  Folders created : {stats['folders_created']}")
    console.print(f"  Files renamed   : {stats['files_renamed']}")
    console.print(f"  Duration        : {stats['duration_seconds']}s")
    if log_path:
        console.print(f"  Log saved to    : [dim]{log_path}[/dim]")
    console.print("[bold cyan]────────────────────────────────────────────────[/bold cyan]")
