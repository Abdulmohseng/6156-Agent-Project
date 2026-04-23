#!/usr/bin/env python3
"""
File Organization Agent — terminal entry point.

Usage:
  python agent.py "Organize my downloads by file type"
  python agent.py "Sort by date" --folder ~/Desktop/Projects
  python agent.py "Clean up" --safe
  python agent.py "Organize" --dry-run
  python agent.py "Organize" --verbose
  python agent.py "Organize" --mode reactive
  python agent.py "Organize" --model qwen3-vl:8b
"""

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import requests
from rich.console import Console

from config import DEFAULT_MODEL, OLLAMA_BASE_URL, TEST_FOLDER
import config_vision

console = Console()


def _check_ollama(model: str):
    """Ping Ollama and verify the model is available. Fail fast with helpful errors."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        console.print("[red]Error: Ollama is not running.[/red]")
        console.print("Start it with: [bold]ollama serve[/bold]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error connecting to Ollama: {e}[/red]")
        sys.exit(1)

    available = [m["name"] for m in resp.json().get("models", [])]
    model_base = model.split(":")[0]
    matched = any(m.split(":")[0] == model_base for m in available)

    if not matched:
        console.print(f"[red]Error: Model '{model}' is not pulled.[/red]")
        console.print(f"Run: [bold]ollama pull {model}[/bold]")
        console.print(f"\nAvailable models: {', '.join(available)}")
        sys.exit(1)


def _run_plan_and_act(args, folder: str, run_id: str):
    from graph import build_graph
    from utils.confirm import show_plan_and_confirm
    from utils.logger import init_stats, finalize_stats, print_summary, log_info
    from utils.manifest import build_manifest, save_manifest
    from planner import planner_node

    graph = build_graph()
    stats = init_stats(goal=args.goal, model=args.model)

    initial_state = {
        "goal": args.goal,
        "folder": folder,
        "file_listing": [],
        "plan": None,
        "current_step": 0,
        "step_results": [],
        "last_error": None,
        "decision": None,
        "done": False,
        "safe_mode": args.safe,
        "verbose": args.verbose,
        "dry_run": args.dry_run,
        "mode": args.mode,
        "model": args.model,
        "messages": [],
        "stats": stats,
        "retry_counts": {},
    }

    # Run planner first to get the plan before asking for confirmation
    planned_state = {**initial_state}
    planner_result = planner_node(planned_state)
    planned_state.update(planner_result)

    plan = planned_state.get("plan", [])
    if not plan:
        console.print("[red]Planner produced an empty plan. Exiting.[/red]")
        sys.exit(1)

    if args.dry_run:
        console.print("\n[bold cyan][DRY RUN — plan only, no files will be changed][/bold cyan]")

    approved = show_plan_and_confirm(plan)
    if not approved:
        console.print("[yellow]Aborted by user.[/yellow]")
        sys.exit(0)

    console.print("\n[cyan][EXECUTING — dry run][/cyan]" if args.dry_run else "\n[cyan][EXECUTING][/cyan]")

    final_state = graph.invoke(planned_state)

    final_stats = finalize_stats(final_state.get("stats", stats))

    manifest = build_manifest(
        run_id=run_id,
        goal=args.goal,
        folder=folder,
        model=args.model,
        mode=args.mode,
        dry_run=args.dry_run,
        safe_mode=args.safe,
        plan=plan,
        step_results=final_state.get("step_results", []),
        stats=final_stats,
    )
    manifest_path = save_manifest(manifest)

    print_summary(final_stats, manifest_path=str(manifest_path))


def _run_direct(args, folder: str):
    """Direct mode: single LLM call, no tools — just describes what it would do."""
    from langchain_ollama import ChatOllama
    from langchain_core.messages import HumanMessage, SystemMessage
    from tools import list_files

    console.print("\n[cyan][DIRECT MODE — single LLM call, no tools][/cyan]")

    listing = list_files.invoke({"folder": folder})
    files = listing.get("files", [])
    file_summary = "\n".join(
        f"  {f['name']} ({f['extension']}, {round(f['size_bytes'] / 1024, 1)}KB)"
        for f in files
    )

    llm = ChatOllama(model=args.model, temperature=0, think=False)
    response = llm.invoke([
        SystemMessage(content=(
            "You are a file organization assistant. Describe exactly what actions "
            "you would take to achieve the user's goal, step by step."
        )),
        HumanMessage(content=f"Goal: {args.goal}\n\nFolder: {folder}\n\nFiles:\n{file_summary}"),
    ])
    console.print(response.content)


def main():
    parser = argparse.ArgumentParser(
        description="File Organization Agent — organizes files using a local LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("goal", help="Natural language instruction for organizing files")
    parser.add_argument("--folder", default=None,
                        help="Target folder to organize (default: uses --test-run with the built-in sample folder)")
    parser.add_argument("--safe", action="store_true",
                        help="Confirm each destructive step individually before executing")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan only — do not execute any file operations")
    parser.add_argument("--verbose", action="store_true",
                        help="Print full tool output for each step")
    parser.add_argument("--mode", choices=["plan-and-act", "reactive", "direct"],
                        default="plan-and-act",
                        help="Agent mode (default: plan-and-act)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Ollama model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--vision-model", default=None,
                        help="Ollama model for image descriptions (default: config_vision.VISION_MODEL)")
    parser.add_argument("--test-run", action="store_true",
                        help=(
                            "Copy the built-in sample folder into data/output/run_TIMESTAMP/ "
                            "and run the agent on that copy. Originals are never modified."
                        ))

    args = parser.parse_args()

    # Generate a run ID from timestamp — shared by the manifest and test-run folder name
    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # No --folder specified: default to --test-run with the built-in sample folder
    if args.folder is None:
        args.test_run = True

    # --test-run: copy sample → data/output/run_<timestamp>/ and operate on the copy
    if args.test_run:
        here = Path(__file__).parent
        source_folder = here.parent / "tests" / "data" / TEST_FOLDER
        if not source_folder.exists():
            console.print(f"[red]Error: Sample folder not found at tests/data/{TEST_FOLDER}/[/red]")
            sys.exit(1)
        dest_folder = here.parent / "data" / "output" / f"run_{run_id}"
        dest_folder.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(source_folder), str(dest_folder), dirs_exist_ok=True)
        console.print(f"[dim]Test copy created: {dest_folder}[/dim]")
        args.folder = str(dest_folder)

    folder = os.path.expanduser(args.folder)

    if not Path(folder).exists():
        console.print(f"[red]Error: Folder does not exist: {folder}[/red]")
        sys.exit(1)

    if args.vision_model:
        config_vision.VISION_MODEL = args.vision_model
    _check_ollama(args.model)

    console.print(f"\n[bold cyan]File Organization Agent[/bold cyan]")
    console.print(f"  Goal        : {args.goal}")
    console.print(f"  Folder      : {folder}")
    console.print(f"  Model       : {args.model}")
    console.print(f"  Vision model: {config_vision.VISION_MODEL}")
    console.print(f"  Mode        : {args.mode}")
    console.print(f"  Run ID      : {run_id}")
    if args.dry_run:
        console.print(f"  [yellow]Dry run — no changes will be made[/yellow]")
    if args.safe:
        console.print(f"  [yellow]Safe mode — will confirm each destructive step[/yellow]")

    if args.mode == "direct":
        _run_direct(args, folder)
    else:
        _run_plan_and_act(args, folder, run_id)


if __name__ == "__main__":
    main()
