"""
Model picker — recommend and pull an Ollama model based on detected hardware.

Decision logic (RAM-based defaults):
  ≥ 32 GB → qwen2.5-coder:32b
  ≥ 16 GB → qwen2.5-coder:14b  (default)
  ≥  8 GB → qwen2.5-coder:7b
  <  8 GB → warn, suggest cloud alternative

Vision model (qwen3-vl:8b) is offered when ≥ 8 GB RAM is available.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

# ── Model catalogue ────────────────────────────────────────────────────────────

MODELS = [
    {
        "name": "qwen2.5-coder:7b",
        "label": "Small  (7 B)",
        "disk_gb": 4.7,
        "min_ram_gb": 8,
        "description": "Fast, good quality. Best for machines with 8–15 GB RAM.",
    },
    {
        "name": "qwen2.5-coder:14b",
        "label": "Medium (14 B)",
        "disk_gb": 9.0,
        "min_ram_gb": 16,
        "description": "Recommended default. Excellent instruction-following.",
    },
    {
        "name": "qwen2.5-coder:32b",
        "label": "Large  (32 B)",
        "disk_gb": 20.0,
        "min_ram_gb": 32,
        "description": "Best quality. Requires 32 GB+ RAM.",
    },
]

VISION_MODEL = {
    "name": "qwen3-vl:8b",
    "label": "Vision (8 B)",
    "disk_gb": 5.2,
    "min_ram_gb": 8,
    "description": "Enables image classification and descriptive renaming.",
}


def recommend(ram_gb: float) -> dict:
    """Return the best model dict for the given RAM amount."""
    for m in reversed(MODELS):          # largest first
        if ram_gb >= m["min_ram_gb"]:
            return m
    return MODELS[0]                    # floor: 7b even if below minimum


def pick_model(system_info: dict) -> tuple[str, str | None]:
    """
    Interactive model selection.

    Prints a table of options, highlights the recommendation, and lets the
    user choose. Returns (main_model_name, vision_model_name | None).
    """
    ram_gb = system_info["ram_gb"]
    free_disk_gb = system_info["free_disk_gb"]
    rec = recommend(ram_gb)

    if ram_gb < 8:
        console.print(
            "\n[yellow]Warning:[/yellow] Only [bold]{:.1f} GB[/bold] RAM detected. "
            "Local LLMs require at least 8 GB to run reliably.\n"
            "You can still install, but performance may be very slow.".format(ram_gb)
        )

    # Build selection table
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Model")
    table.add_column("Size")
    table.add_column("Min RAM")
    table.add_column("Notes")

    for i, m in enumerate(MODELS, 1):
        tag = " ← recommended" if m["name"] == rec["name"] else ""
        fits_disk = "⚠ low disk" if free_disk_gb < m["disk_gb"] + 2 else ""
        style = "bold green" if m["name"] == rec["name"] else ""
        table.add_row(
            str(i),
            m["name"] + tag,
            f"{m['disk_gb']} GB",
            f"{m['min_ram_gb']} GB",
            m["description"] + (" " + fits_disk if fits_disk else ""),
            style=style,
        )

    console.print("\n[bold]Available models:[/bold]")
    console.print(table)

    default_idx = MODELS.index(rec) + 1
    while True:
        raw = console.input(
            f"[cyan]Choose a model [1-{len(MODELS)}] (default {default_idx}): [/cyan]"
        ).strip()
        if raw == "":
            chosen = rec
            break
        if raw.isdigit() and 1 <= int(raw) <= len(MODELS):
            chosen = MODELS[int(raw) - 1]
            break
        console.print("[red]Invalid choice — enter a number or press Enter for default.[/red]")

    console.print(f"  Selected: [bold]{chosen['name']}[/bold]")

    # Vision model offer
    vision_name: str | None = None
    if ram_gb >= VISION_MODEL["min_ram_gb"]:
        console.print(
            f"\n[bold]Optional vision model:[/bold] {VISION_MODEL['name']} "
            f"({VISION_MODEL['disk_gb']} GB)\n"
            f"  {VISION_MODEL['description']}"
        )
        ans = console.input("[cyan]Install vision model? [y/N]: [/cyan]").strip().lower()
        if ans == "y":
            vision_name = VISION_MODEL["name"]

    return chosen["name"], vision_name
