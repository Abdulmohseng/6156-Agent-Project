from langchain_core.messages import AIMessage

from state import AgentState
from tools import list_files, read_file, rename_file, create_folder, move_file
from utils.confirm import confirm_step, is_destructive
from utils.logger import log_step_success, log_step_failure, log_step_skipped, log_info

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


def executor_node(state: AgentState) -> dict:
    """
    Executor node: iterates through the plan and executes each step using tools directly.
    On success, advances current_step. On failure, sets last_error for the Reflector.
    """
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    step_results = list(state.get("step_results", []))
    safe_mode = state.get("safe_mode", False)
    verbose = state.get("verbose", False)
    dry_run = state.get("dry_run", False)
    stats = dict(state.get("stats", {}))
    decision = state.get("decision")

    # If reflector decided to skip, advance past the failed step
    if decision == "skip" and state.get("last_error"):
        step = plan[current_step] if current_step < len(plan) else {}
        log_step_skipped(step)
        stats["steps_skipped"] = stats.get("steps_skipped", 0) + 1
        next_step = current_step + 1
        done = next_step >= len(plan)
        return {
            "current_step": next_step,
            "step_results": step_results,
            "last_error": None,
            "decision": None,
            "done": done,
            "stats": stats,
        }

    if current_step >= len(plan):
        log_info("\n[EXECUTOR] All steps completed.")
        return {"done": True, "step_results": step_results, "last_error": None, "stats": stats}

    step = plan[current_step]
    tool_name = step.get("tool", "")
    args = step.get("args", {})

    # Human-in-the-loop: confirm destructive steps in safe mode
    if safe_mode and is_destructive(tool_name) and not dry_run:
        approved = confirm_step(step)
        if not approved:
            log_step_skipped(step)
            stats["steps_skipped"] = stats.get("steps_skipped", 0) + 1
            step_results.append({"step": current_step, "skipped": True, "tool": tool_name})
            return {
                "current_step": current_step + 1,
                "step_results": step_results,
                "last_error": None,
                "stats": stats,
            }

    if dry_run:
        log_info(f"  [DRY RUN] Step {step.get('step', current_step + 1)}: {step.get('description', '')} → {tool_name}({args})")
        step_results.append({"step": current_step, "dry_run": True, "tool": tool_name})
        return {
            "current_step": current_step + 1,
            "step_results": step_results,
            "last_error": None,
            "stats": stats,
        }

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

    try:
        result = tool_fn.invoke(args)
    except Exception as e:
        error = str(e)
        log_step_failure(step, error)
        stats["steps_failed"] = stats.get("steps_failed", 0) + 1
        return {
            "current_step": current_step,
            "step_results": step_results,
            "last_error": error,
            "stats": stats,
        }

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

    step_results.append({
        "step": current_step,
        "tool": tool_name,
        "success": True,
        "message": result.get("message", ""),
    })

    next_step = current_step + 1
    done = next_step >= len(plan)

    return {
        "current_step": next_step,
        "step_results": step_results,
        "last_error": None,
        "done": done,
        "stats": stats,
    }
