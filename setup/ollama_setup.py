"""
Ollama installer — detect if Ollama is installed, install if missing,
verify the service is running, and pull the chosen model.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import time

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn

console = Console()

OLLAMA_API = "http://localhost:11434"
_INSTALL_URLS = {
    "Darwin": "https://ollama.com/download/Ollama-darwin.zip",
    "Linux": "curl -fsSL https://ollama.com/install.sh | sh",
    "Windows": "https://ollama.com/download/OllamaSetup.exe",
}


# ── public API ─────────────────────────────────────────────────────────────────

def ensure_ollama() -> bool:
    """
    Check that Ollama is installed and the service is running.
    Guides the user through installation if either is missing.
    Returns True if ready, False if the user chose to skip.
    """
    if not _is_installed():
        ok = _install_ollama()
        if not ok:
            return False

    if not _is_running():
        ok = _start_service()
        if not ok:
            return False

    console.print("[green]✓ Ollama is running.[/green]")
    return True


def pull_model(model_name: str) -> bool:
    """
    Pull a model via `ollama pull`. Streams progress to the terminal.
    Returns True on success.
    """
    if _model_already_pulled(model_name):
        console.print(f"[green]✓ Model [bold]{model_name}[/bold] already available.[/green]")
        return True

    console.print(f"\nPulling [bold]{model_name}[/bold] — this may take several minutes...")

    try:
        proc = subprocess.Popen(
            ["ollama", "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task(f"Pulling {model_name}", total=None)
            for line in proc.stdout:
                line = line.strip()
                if line:
                    progress.update(task, description=line[:80])

        proc.wait()
        if proc.returncode != 0:
            console.print(f"[red]Failed to pull {model_name}.[/red]")
            return False
    except FileNotFoundError:
        console.print("[red]'ollama' command not found. Please restart your terminal after install.[/red]")
        return False

    console.print(f"[green]✓ {model_name} pulled successfully.[/green]")
    return True


# ── internals ──────────────────────────────────────────────────────────────────

def _is_installed() -> bool:
    return shutil.which("ollama") is not None


def _is_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_API}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _model_already_pulled(model_name: str) -> bool:
    try:
        r = requests.get(f"{OLLAMA_API}/api/tags", timeout=3)
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        base = model_name.split(":")[0]
        return any(m.split(":")[0] == base for m in models)
    except Exception:
        return False


def _install_ollama() -> bool:
    os_name = platform.system()
    console.print("\n[yellow]Ollama is not installed.[/yellow]")

    if os_name == "Darwin":
        if shutil.which("brew"):
            console.print("Installing via Homebrew...")
            result = subprocess.run(["brew", "install", "ollama"], check=False)
            if result.returncode == 0:
                return True
        # Homebrew not available — guide manual install
        console.print(
            "\nPlease download and install Ollama manually:\n"
            f"  [link]{_INSTALL_URLS['Darwin']}[/link]\n\n"
            "Then re-run this setup."
        )
        return False

    elif os_name == "Linux":
        console.print("Installing via official install script...")
        result = subprocess.run(
            "curl -fsSL https://ollama.com/install.sh | sh",
            shell=True, check=False,
        )
        return result.returncode == 0

    else:  # Windows or unknown
        console.print(
            "\nPlease download and install Ollama manually:\n"
            f"  [link]{_INSTALL_URLS.get(os_name, 'https://ollama.com')}[/link]\n\n"
            "Then re-run this setup."
        )
        return False


def _start_service() -> bool:
    """Attempt to start `ollama serve` and wait for it to become ready."""
    console.print("Starting Ollama service...")

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        console.print("[red]'ollama' binary not found. Please restart your terminal and try again.[/red]")
        return False

    # Poll until ready (up to 15 s)
    for _ in range(15):
        time.sleep(1)
        if _is_running():
            return True

    console.print(
        "[red]Ollama did not start within 15 seconds.[/red]\n"
        "Try running [bold]ollama serve[/bold] in a separate terminal, then re-run setup."
    )
    return False
