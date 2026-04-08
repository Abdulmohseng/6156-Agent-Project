#!/usr/bin/env python3
"""File Organization Agent — just run: python run.py"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT         = Path(__file__).parent
VENV         = ROOT / ".venv"
AGENT_DIR    = ROOT / "file-agent"
SETUP_DIR    = ROOT / "setup"
REQUIREMENTS = ROOT / "requirements.txt"
RECENTS_FILE = Path.home() / ".file-agent" / "recents.json"

VENV_PYTHON = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

# ── Cyan theme for questionary ─────────────────────────────────────────────────
QS_STYLE = None  # populated after questionary is importable (inside venv)


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — stdlib-only bootstrap (runs before venv exists)
# ══════════════════════════════════════════════════════════════════════════════

def _inside_venv() -> bool:
    return sys.executable.startswith(str(VENV))


def _deps_installed() -> bool:
    return subprocess.run(
        [str(VENV_PYTHON), "-c", "import rich, questionary"],
        capture_output=True,
    ).returncode == 0


def _bootstrap() -> None:
    """Create .venv, install deps, re-exec inside it. Never returns."""
    if not VENV.exists():
        print("Setting up environment (first time only)...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    if not _deps_installed():
        print("Installing dependencies...")
        subprocess.run(
            [str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)],
            check=True,
        )
    # Re-exec inside the venv, preserving all original CLI flags
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__] + sys.argv[1:])


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — runs inside the venv (rich + questionary available)
# ══════════════════════════════════════════════════════════════════════════════

def _make_style():
    from questionary import Style
    return Style([
        ("qmark",       "fg:#00bcd4 bold"),
        ("question",    "bold"),
        ("answer",      "fg:#00bcd4"),
        ("pointer",     "fg:#00bcd4 bold"),
        ("highlighted", "fg:#00bcd4 bold"),
        ("selected",    "fg:#00bcd4"),
        ("separator",   "fg:#555555"),
        ("instruction", "fg:#555555 italic"),
    ])


# ── Setup detection ────────────────────────────────────────────────────────────

def _needs_setup() -> bool:
    """True if Ollama isn't installed or no models are pulled yet."""
    import shutil
    import requests
    if not shutil.which("ollama"):
        return True
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return len(r.json().get("models", [])) == 0
    except Exception:
        return True


def _run_setup() -> None:
    sys.path.insert(0, str(SETUP_DIR))
    import main as setup_main
    setup_main.main()


# ── Recent folders ─────────────────────────────────────────────────────────────

def _load_recents() -> list[str]:
    try:
        return json.loads(RECENTS_FILE.read_text())
    except Exception:
        return []


def _save_recent(folder: str) -> None:
    recents = [folder] + [r for r in _load_recents() if r != folder]
    RECENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RECENTS_FILE.write_text(json.dumps(recents[:5]))


# ── Interactive prompts ────────────────────────────────────────────────────────

def _ask_folder() -> str:
    import questionary
    from rich.console import Console
    console = Console()

    home = Path.home()
    common = [
        ("Downloads",  home / "Downloads"),
        ("Desktop",    home / "Desktop"),
        ("Documents",  home / "Documents"),
        ("Home",       home),
    ]
    # Only show locations that actually exist
    common_choices = [
        questionary.Choice(f"{label:<12} {path}", value=str(path))
        for label, path in common
        if path.exists()
    ]

    recents = _load_recents()
    recent_choices = [
        questionary.Choice(f"Recent       {r}", value=r)
        for r in recents
        if Path(r).exists() and r not in [c.value for c in common_choices]
    ]

    separator = [questionary.Separator()]
    browse    = [questionary.Choice("Browse...    enter a custom path", value="__browse__")]

    answer = questionary.select(
        "Which folder would you like to organize?",
        choices=recent_choices + (separator if recent_choices else []) + common_choices + separator + browse,
        style=QS_STYLE,
        use_shortcuts=False,
    ).ask()

    if answer is None:
        sys.exit(0)  # user hit Ctrl-C

    if answer == "__browse__":
        raw = questionary.path(
            "Folder path:",
            only_directories=True,
            style=QS_STYLE,
        ).ask()
        if raw is None:
            sys.exit(0)
        answer = str(Path(raw).expanduser().resolve())

    folder = Path(answer)
    if not folder.exists():
        console.print(f"[red]Folder not found:[/red] {folder}")
        sys.exit(1)

    return str(folder)


def _ask_goal() -> str:
    import questionary

    goal = questionary.text(
        "What would you like to do with the files?",
        instruction="e.g. Organize by type, Sort by date, Group photos by location",
        style=QS_STYLE,
    ).ask()

    if goal is None:
        sys.exit(0)

    goal = goal.strip()
    if not goal:
        from rich.console import Console
        Console().print("[red]Goal cannot be empty.[/red]")
        sys.exit(1)

    return goal


def _ask_options(presets: list[str]) -> list[str]:
    """Checkbox for dry-run / safe / verbose. Presets from CLI flags."""
    import questionary

    # If all options already forced via flags, skip the prompt
    if "--dry-run" in presets:
        return presets

    choices = [
        questionary.Choice(
            "Dry run    — preview the plan, no files changed",
            value="--dry-run",
            checked="--dry-run" in presets,
        ),
        questionary.Choice(
            "Safe mode  — confirm each step before executing",
            value="--safe",
            checked="--safe" in presets,
        ),
        questionary.Choice(
            "Verbose    — print full tool output for each step",
            value="--verbose",
            checked="--verbose" in presets,
        ),
    ]

    selected = questionary.checkbox(
        "Run options  (space to toggle, enter to confirm):",
        choices=choices,
        style=QS_STYLE,
    ).ask()

    return selected if selected is not None else []


# ── Agent runner ───────────────────────────────────────────────────────────────

def _run_agent(goal: str, folder: str, flags: list[str]) -> None:
    sys.path.insert(0, str(AGENT_DIR))
    sys.argv = ["agent.py", goal, "--folder", folder] + flags
    import agent
    agent.main()


# ── CLI flags ─────────────────────────────────────────────────────────────────

def _parse_args():
    import argparse
    p = argparse.ArgumentParser(
        prog="run.py",
        description="File Organization Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Override flags:\n"
            "  --reset      Re-run the setup wizard\n"
            "  --test       Use the built-in sample folder (skips folder prompt)\n"
            "  --model NAME Use a specific Ollama model for this run\n"
            "  --dry-run    Force dry-run mode (no files changed)\n"
            "  --safe       Force safe mode (confirm each step)\n"
            "  --verbose    Force verbose output\n"
        ),
    )
    p.add_argument("--reset",    action="store_true", help="Re-run the setup wizard")
    p.add_argument("--test",     action="store_true", help="Use built-in sample folder")
    p.add_argument("--model",    metavar="NAME",      help="Override the Ollama model")
    p.add_argument("--dry-run",  action="store_true", help="Preview plan, no changes")
    p.add_argument("--safe",     action="store_true", help="Confirm each step")
    p.add_argument("--verbose",  action="store_true", help="Full tool output")
    return p.parse_args()


# ── Banner ─────────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich import box
    Console().print(Panel(
        "[bold cyan]File Organization Agent[/bold cyan]\n"
        "[dim]Organize your files using a local AI model[/dim]",
        box=box.ROUNDED,
        border_style="cyan",
        padding=(0, 2),
    ))


# ══════════════════════════════════════════════════════════════════════════════
# Entry
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not _inside_venv():
        _bootstrap()  # never returns

    QS_STYLE = _make_style()

    args = _parse_args()

    _print_banner()

    # ── Setup ──────────────────────────────────────────────────────────────────
    if args.reset:
        from rich.console import Console
        Console().print("[dim]Forcing setup wizard...[/dim]\n")
        _run_setup()
    elif _needs_setup():
        from rich.console import Console
        Console().print(
            "[yellow]Looks like this is your first time — let's get you set up.[/yellow]\n"
        )
        _run_setup()

    # ── Folder ─────────────────────────────────────────────────────────────────
    if args.test:
        folder = str(ROOT / "tests" / "data" / "folder-vision")
        from rich.console import Console
        Console().print(f"[dim]Using test folder:[/dim] {folder}\n")
    else:
        folder = _ask_folder()

    # ── Goal ───────────────────────────────────────────────────────────────────
    goal = _ask_goal()

    # ── Options ────────────────────────────────────────────────────────────────
    preset_flags: list[str] = []
    if args.dry_run: preset_flags.append("--dry-run")
    if args.safe:    preset_flags.append("--safe")
    if args.verbose: preset_flags.append("--verbose")
    if args.model:   preset_flags += ["--model", args.model]

    flags = _ask_options(preset_flags)
    if args.model and "--model" not in flags:
        flags += ["--model", args.model]

    # ── Run ────────────────────────────────────────────────────────────────────
    _save_recent(folder)
    _run_agent(goal, folder, flags)
