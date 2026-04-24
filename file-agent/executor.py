import time

from state import AgentState
from tools import list_files, read_file, rename_file, create_folder, move_file
from utils.confirm import confirm_step
from utils.logger import log_step_success, log_step_failure, log_step_skipped, log_info
from config import DESTRUCTIVE_TOOLS, MAX_RUN_SECONDS

TOOL_MAP = {
    "list_files": list_files,
    "read_file": read_file,
    "rename_file": rename_file,
    "create_folder": create_folder,
    "move_file": move_file,
}


def _update_stats(stats: dict, tool_name: str, result: dict):
    if not result.get("success"):
        return
    if tool_name == "move_file":
        stats["files_moved"] = stats.get("files_moved", 0) + 1
    elif tool_name == "create_folder" and result.get("created"):
        stats["folders_created"] = stats.get("folders_created", 0) + 1
    elif tool_name == "rename_file":
        stats["files_renamed"] = stats.get("files_renamed", 0) + 1


def _step_record(step_index: int, step: dict, status: str, message: str = "",
                 duration: float = 0.0) -> dict:
    """Build a normalized step result entry for manifest and step_results."""
    return {
        "step_index": step_index,
        "step_number": step.get("step", step_index + 1),
        "description": step.get("description", ""),
        "tool": step.get("tool", ""),
        "args": step.get("args", {}),
        "status": status,
        "message": message,
        "duration_seconds": round(duration, 3),
    }


def executor_node(state: AgentState) -> dict:
    """
    Executor node: runs one plan step per invocation and loops itself via
    the graph's conditional edge. On success, advances current_step. On
    failure, sets last_error so the Reflector can decide what to do next.
    """
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    step_results = list(state.get("step_results", []))
    safe_mode = state.get("safe_mode", False)
    verbose = state.get("verbose", False)
    dry_run = state.get("dry_run", False)
    stats = dict(state.get("stats", {}))
    decision = state.get("decision")
    last_error = state.get("last_error")

    # ── Reflector decided to skip the failed step ──────────────────────────────
    if decision == "skip" and last_error:
        step = plan[current_step] if current_step < len(plan) else {}
        log_step_skipped(step)
        stats["steps_skipped"] = stats.get("steps_skipped", 0) + 1
        step_results.append(_step_record(
            current_step, step, status="skipped", message=last_error
        ))
        next_step = current_step + 1
        return {
            "current_step": next_step,
            "step_results": step_results,
            "last_error": None,
            "decision": None,
            "done": next_step >= len(plan),
            "stats": stats,
        }

    # ── Wall-clock timeout ─────────────────────────────────────────────────────
    elapsed = time.time() - stats.get("start_time", time.time())
    if elapsed >= MAX_RUN_SECONDS:
        remaining = len(plan) - current_step
        log_info(
            f"\n[EXECUTOR] [bold red]Time limit reached[/bold red] "
            f"({elapsed:.0f}s ≥ {MAX_RUN_SECONDS}s) — stopping with {remaining} step(s) remaining."
        )
        stats["steps_skipped"] = stats.get("steps_skipped", 0) + remaining
        stats["timed_out"] = True
        return {"done": True, "step_results": step_results, "last_error": None, "stats": stats}

    # ── All steps done ─────────────────────────────────────────────────────────
    if current_step >= len(plan):
        log_info("\n[EXECUTOR] All steps completed.")
        return {"done": True, "step_results": step_results, "last_error": None, "stats": stats}

    step = plan[current_step]
    tool_name = step.get("tool", "")
    args = step.get("args", {})

    # ── Safe mode: confirm destructive steps before running ────────────────────
    if safe_mode and tool_name in DESTRUCTIVE_TOOLS and not dry_run:
        approved = confirm_step(step)
        if not approved:
            log_step_skipped(step)
            stats["steps_skipped"] = stats.get("steps_skipped", 0) + 1
            step_results.append(_step_record(
                current_step, step, status="user_skipped", message="Declined by user"
            ))
            return {
                "current_step": current_step + 1,
                "step_results": step_results,
                "last_error": None,
                "stats": stats,
            }

    # ── Dry run: log intent without touching files ─────────────────────────────
    if dry_run:
        log_info(
            f"  [DRY RUN] Step {step.get('step', current_step + 1)}: "
            f"{step.get('description', '')} → {tool_name}({args})"
        )
        step_results.append(_step_record(
            current_step, step, status="dry_run",
            message=f"Would call {tool_name} with {args}"
        ))
        return {
            "current_step": current_step + 1,
            "step_results": step_results,
            "last_error": None,
            "stats": stats,
        }

    # ── Unknown tool ───────────────────────────────────────────────────────────
    tool_fn = TOOL_MAP.get(tool_name)
    if tool_fn is None:
        error = f"Unknown tool: {tool_name}"
        log_step_failure(step, error)
        stats["steps_failed"] = stats.get("steps_failed", 0) + 1
        return {
            "current_step": current_step,
            "step_results": step_results,
            "last_error": error,
            "stats": stats,
        }

    # ── Execute tool ───────────────────────────────────────────────────────────
    t0 = time.monotonic()
    try:
        result = tool_fn.invoke(args)
    except Exception as e:
        duration = time.monotonic() - t0
        error = str(e)
        log_step_failure(step, error)
        stats["steps_failed"] = stats.get("steps_failed", 0) + 1
        return {
            "current_step": current_step,
            "step_results": step_results,
            "last_error": error,
            "stats": stats,
        }
    duration = time.monotonic() - t0

    if not result.get("success", False):
        error = result.get("message", "Unknown error")
        log_step_failure(step, error)
        stats["steps_failed"] = stats.get("steps_failed", 0) + 1
        return {
            "current_step": current_step,
            "step_results": step_results,
            "last_error": error,
            "stats": stats,
        }

    log_step_success(step, result, verbose)
    _update_stats(stats, tool_name, result)
    stats["steps_completed"] = stats.get("steps_completed", 0) + 1

    step_results.append(_step_record(
        current_step, step, status="success",
        message=result.get("message", ""),
        duration=duration,
    ))

    next_step = current_step + 1
    return {
        "current_step": next_step,
        "step_results": step_results,
        "last_error": None,
        "done": next_step >= len(plan),
        "stats": stats,
    }
