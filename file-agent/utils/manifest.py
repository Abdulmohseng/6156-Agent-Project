"""
Run manifest — captures the full plan, per-step execution records, and
summary statistics for every agent run.

Saved to: ~/.file-agent/runs/<run_id>/manifest.json

Schema
------
{
  "version": "1.0",
  "run_id": "2026-03-12_17-11-47",
  "metadata": {
    "timestamp": "2026-03-12T17:11:47",
    "goal": "...",
    "folder": "...",
    "model": "...",
    "mode": "plan-and-act",
    "dry_run": false,
    "safe_mode": false
  },
  "plan": [
    {"step": 1, "description": "...", "tool": "create_folder", "args": {...}}
  ],
  "execution": [
    {
      "step_index": 0,
      "step_number": 1,
      "description": "...",
      "tool": "create_folder",
      "args": {...},
      "status": "success",       // success | failed | skipped | user_skipped | dry_run
      "message": "Created Finance/",
      "duration_seconds": 0.02
    }
  ],
  "summary": {
    "plan_steps": 12,
    "steps_completed": 11,
    "steps_failed": 0,
    "steps_skipped": 1,
    "replans": 0,
    "files_moved": 8,
    "folders_created": 3,
    "files_renamed": 2,
    "duration_seconds": 42.3
  }
}
"""

import json
from pathlib import Path

from config import RUNS_DIR

MANIFEST_VERSION = "1.0"


def build_manifest(
    run_id: str,
    goal: str,
    folder: str,
    model: str,
    mode: str,
    dry_run: bool,
    safe_mode: bool,
    plan: list,
    step_results: list,
    stats: dict,
) -> dict:
    """Assemble the manifest dict from run state."""
    return {
        "version": MANIFEST_VERSION,
        "run_id": run_id,
        "metadata": {
            "timestamp": stats.get("timestamp", ""),
            "goal": goal,
            "folder": folder,
            "model": model,
            "mode": mode,
            "dry_run": dry_run,
            "safe_mode": safe_mode,
        },
        "plan": [
            {
                "step": s.get("step", i + 1),
                "description": s.get("description", ""),
                "tool": s.get("tool", ""),
                "args": s.get("args", {}),
            }
            for i, s in enumerate(plan or [])
        ],
        "execution": step_results,
        "summary": {
            "plan_steps": stats.get("plan_steps", 0),
            "steps_completed": stats.get("steps_completed", 0),
            "steps_failed": stats.get("steps_failed", 0),
            "steps_skipped": stats.get("steps_skipped", 0),
            "replans": stats.get("replans", 0),
            "files_moved": stats.get("files_moved", 0),
            "folders_created": stats.get("folders_created", 0),
            "files_renamed": stats.get("files_renamed", 0),
            "duration_seconds": stats.get("duration_seconds", 0.0),
        },
    }


def save_manifest(manifest: dict) -> Path:
    """Write manifest JSON to ~/.file-agent/runs/<run_id>/manifest.json."""
    run_dir = RUNS_DIR / manifest["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    return path
