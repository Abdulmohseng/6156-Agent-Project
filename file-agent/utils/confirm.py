from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

console = Console()

DESTRUCTIVE_TOOLS = {"move_file", "rename_file"}


def show_plan_and_confirm(plan: list[dict]) -> bool:
    """
    Displays the full plan in a formatted table and asks for y/n confirmation.
    Returns True if user approves, False otherwise.
    """
    console.print()
    table = Table(title="[bold cyan]PLAN REVIEW[/bold cyan]", show_header=True, header_style="bold white")
    table.add_column("Step", style="cyan", justify="center", width=6)
    table.add_column("Description", style="white", min_width=40)
    table.add_column("Tool", style="yellow", width=16)

    for step in plan:
        step_num = str(step.get("step", "?"))
        description = step.get("description", "")
        tool_name = step.get("tool", "")
        table.add_row(step_num, description, tool_name)

    console.print(table)
    console.print()
    return Confirm.ask(f"[bold]Proceed with {len(plan)} steps?[/bold]", default=True)


def confirm_step(step: dict) -> bool:
    """
    Prompts before a single destructive step. Returns True to proceed, False to skip.
    """
    tool_name = step.get("tool", "")
    description = step.get("description", "")
    args = step.get("args", {})

    console.print(f"\n[yellow]  Step {step.get('step', '?')}:[/yellow] {description}")
    console.print(f"  [dim]Tool:[/dim] {tool_name}  [dim]Args:[/dim] {args}")
    return Confirm.ask("  Execute this step?", default=True)


def is_destructive(tool_name: str) -> bool:
    return tool_name in DESTRUCTIVE_TOOLS
