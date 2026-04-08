#!/usr/bin/env python3
"""
File Agent Setup — guided installer for new users.

Walks through:
  1. System detection (RAM, disk, GPU)
  2. Ollama install + service start
  3. Model selection based on your hardware
  4. Model pull

Note: the virtual environment and Python deps are managed by run.py,
which bootstraps itself before calling this module.

Usage (via run.py — preferred):
  python run.py setup
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

# Allow importing sibling modules whether invoked via run.py or directly
sys.path.insert(0, str(Path(__file__).parent))

from system_check import get_system_info
from ollama_setup import ensure_ollama, pull_model
from model_picker import pick_model

console = Console()


def main() -> None:
    console.print(Panel.fit(
        "[bold cyan]File Organization Agent — Setup[/bold cyan]\n"
        "[dim]This wizard installs everything you need to run the agent locally.[/dim]",
        border_style="cyan",
    ))

    # ── Step 1: System info ────────────────────────────────────────────────────
    _step("1", "Detecting your system")
    info = get_system_info()
    _print_system_table(info)

    # ── Step 2: Ollama ─────────────────────────────────────────────────────────
    _step("2", "Checking Ollama")
    ready = ensure_ollama()
    if not ready:
        console.print(
            "\n[red]Setup could not complete — Ollama is required.[/red]\n"
            "Install it from [link=https://ollama.com]https://ollama.com[/link] and re-run setup."
        )
        sys.exit(1)

    # ── Step 3: Model selection ────────────────────────────────────────────────
    _step("3", "Selecting a model")
    main_model, vision_model = pick_model(info)

    # ── Step 4: Pull models ────────────────────────────────────────────────────
    _step("4", "Pulling model(s)")
    if not pull_model(main_model):
        console.print("[red]Could not pull the selected model. Check your internet connection.[/red]")
        sys.exit(1)

    if vision_model:
        if not pull_model(vision_model):
            console.print("[yellow]Could not pull vision model — continuing without it.[/yellow]")
            vision_model = None

    # ── Done ───────────────────────────────────────────────────────────────────
    _print_success(main_model, vision_model)


# ── helpers ────────────────────────────────────────────────────────────────────

def _step(number: str, label: str) -> None:
    console.print(f"\n[bold cyan]Step {number}:[/bold cyan] {label}")
    console.rule(style="dim")


def _print_system_table(info: dict) -> None:
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("Key", style="dim")
    t.add_column("Value")

    gpu = info["gpu"]
    gpu_label = gpu["name"]
    if gpu.get("vram_gb"):
        gpu_label += f" ({gpu['vram_gb']} GB VRAM)"

    t.add_row("OS", f"{info['os']} ({info['arch']})")
    t.add_row("RAM", f"{info['ram_gb']:.1f} GB")
    t.add_row("Free disk", f"{info['free_disk_gb']:.1f} GB")
    t.add_row("GPU", gpu_label)
    console.print(t)


def _print_success(main_model: str, vision_model: str | None) -> None:
    lines = [
        "[bold green]Setup complete![/bold green]",
        "",
        f"Main model   : [cyan]{main_model}[/cyan]",
    ]
    if vision_model:
        lines.append(f"Vision model : [cyan]{vision_model}[/cyan]")
    console.print(Panel("\n".join(lines), border_style="green"))


if __name__ == "__main__":
    main()
