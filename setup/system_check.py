"""
System detection — OS, available RAM, disk space, GPU presence.
Used by model_picker.py to recommend an appropriate Ollama model.
"""

import platform
import shutil
import subprocess

import psutil


def get_os() -> str:
    """Return the OS name: 'Darwin', 'Linux', or 'Windows'."""
    return platform.system()


def get_ram_gb() -> float:
    return psutil.virtual_memory().total / (1024 ** 3)


def get_free_disk_gb() -> float:
    root = "C:\\" if platform.system() == "Windows" else "/"
    return psutil.disk_usage(root).free / (1024 ** 3)


def get_gpu_info() -> dict:
    """
    Detect the best available GPU.

    Returns a dict with keys:
      type  — 'apple_silicon' | 'nvidia' | 'amd' | 'cpu'
      name  — human-readable label
      vram_gb — approximate VRAM (None when unknown)
    """
    # Apple Silicon — Ollama uses Metal automatically
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        chip = _apple_chip_name()
        return {"type": "apple_silicon", "name": chip, "vram_gb": None}

    # NVIDIA via nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                parts = out.stdout.strip().splitlines()[0].split(", ")
                name = parts[0].strip()
                vram_gb = round(int(parts[1].strip()) / 1024, 1) if len(parts) > 1 else None
                return {"type": "nvidia", "name": name, "vram_gb": vram_gb}
        except Exception:
            pass

    # AMD via rocm-smi
    if shutil.which("rocm-smi"):
        return {"type": "amd", "name": "AMD GPU (ROCm)", "vram_gb": None}

    return {"type": "cpu", "name": "CPU only", "vram_gb": None}


def get_system_info() -> dict:
    """Return a summary dict of the current machine's specs."""
    return {
        "os": get_os(),
        "arch": platform.machine(),
        "ram_gb": get_ram_gb(),
        "free_disk_gb": get_free_disk_gb(),
        "gpu": get_gpu_info(),
    }


# ── helpers ────────────────────────────────────────────────────────────────────

def _apple_chip_name() -> str:
    """Try to return the M-series chip name (e.g. 'Apple M2 Pro')."""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=3,
        )
        name = out.stdout.strip()
        if name:
            return name
    except Exception:
        pass
    return "Apple Silicon"
