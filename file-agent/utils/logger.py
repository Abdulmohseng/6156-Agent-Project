import time
from datetime import datetime

from rich.console import Console

from config import RUNS_DIR

console = Console()


def init_stats(goal: str, model: str) -> dict:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
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


def print_summary(stats: dict, manifest_path: str = None):
    console.print()
    console.print("[bold cyan]─── Summary ───────────────────────────────────[/bold cyan]")
    console.print(f"  Steps completed : [green]{stats['steps_completed']}[/green]")
    if stats.get("steps_failed"):
        console.print(f"  Steps failed    : [red]{stats['steps_failed']}[/red]")
    if stats.get("steps_skipped"):
        console.print(f"  Steps skipped   : [yellow]{stats['steps_skipped']}[/yellow]")
    if stats.get("replans"):
        console.print(f"  Replans         : {stats['replans']}")
    console.print(f"  Files moved     : {stats.get('files_moved', 0)}")
    console.print(f"  Folders created : {stats.get('folders_created', 0)}")
    console.print(f"  Files renamed   : {stats.get('files_renamed', 0)}")
    console.print(f"  Duration        : {stats.get('duration_seconds', 0.0)}s")
    if manifest_path:
        console.print(f"  Manifest        : [dim]{manifest_path}[/dim]")
    console.print("[bold cyan]────────────────────────────────────────────────[/bold cyan]")
