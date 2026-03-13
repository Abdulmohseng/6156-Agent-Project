import re
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from state import AgentState
from utils.logger import log_info, log_warning
from config import (
    REFLECTOR_NUM_PREDICT, MAX_RETRIES_PER_STEP, MAX_REPLANS, SKIP_ERROR_PATTERNS,
)

SYSTEM_PROMPT = """/no_think
You are a file organization agent error handler.
You will receive:
1. The original goal
2. Steps completed so far
3. The failed step and the error message

Your job is to decide how to recover. Output exactly ONE word (no punctuation, no explanation):
- retry   → the step can succeed if tried again with corrected args (e.g. the folder wasn't created yet)
- skip    → the step is not critical and can be safely skipped
- replan  → the error is serious enough that the entire plan needs to be reconsidered

Output only the single word: retry, skip, or replan"""


def _parse_decision(raw: str) -> str:
    raw = raw.strip().lower()
    # Remove thinking tags
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    for word in ("retry", "skip", "replan"):
        if word in raw:
            return word
    return "skip"  # safe default




def reflector_node(state: AgentState) -> dict:
    """
    Reflector node: called only when a step fails.
    Makes a lightweight LLM call and returns retry/skip/replan.
    """
    goal = state["goal"]
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    step_results = state.get("step_results", [])
    last_error = state.get("last_error", "Unknown error")
    model = state.get("model", "qwen3:8b")
    stats = dict(state.get("stats", {}))
    retry_counts = dict(state.get("retry_counts", {}))

    # Deterministic override: errors that retrying can never fix
    error_lower = last_error.lower()
    if any(pat in error_lower for pat in SKIP_ERROR_PATTERNS):
        log_info(f"[REFLECTOR] Auto-skip (unretryable error): {last_error[:80]}")
        return {"decision": "skip", "stats": stats, "retry_counts": retry_counts}

    # Per-step retry cap: force skip if retried too many times
    step_key = str(current_step)
    retries = retry_counts.get(step_key, 0)
    if retries >= MAX_RETRIES_PER_STEP:
        log_warning(f"[REFLECTOR] Step {current_step + 1} exceeded retry limit — forcing skip.")
        retry_counts[step_key] = 0
        return {"decision": "skip", "stats": stats, "retry_counts": retry_counts}

    failed_step = plan[current_step] if current_step < len(plan) else {}
    completed_count = len([r for r in step_results if r.get("success")])

    completed_summary = "\n".join(
        f"  Step {r['step'] + 1}: {r.get('message', 'completed')}"
        for r in step_results
        if r.get("success")
    ) or "  (none)"

    user_content = (
        f"Goal: {goal}\n\n"
        f"Steps completed ({completed_count}):\n{completed_summary}\n\n"
        f"Failed step: {failed_step.get('description', 'unknown')}\n"
        f"Tool: {failed_step.get('tool', 'unknown')}\n"
        f"Args: {failed_step.get('args', {})}\n"
        f"Error: {last_error}"
    )

    log_info(f"[REFLECTOR] Analyzing failure: {last_error[:80]}...")

    llm = ChatOllama(model=model, temperature=0, num_predict=REFLECTOR_NUM_PREDICT)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    response = llm.invoke(messages)
    decision = _parse_decision(response.content)

    log_info(f"[REFLECTOR] Decision: {decision}")

    if decision == "replan":
        stats["replans"] = stats.get("replans", 0) + 1
    elif decision == "retry":
        retry_counts[step_key] = retries + 1
    else:
        retry_counts[step_key] = 0  # reset on skip

    return {"decision": decision, "stats": stats, "retry_counts": retry_counts}


def route_after_reflect(state: AgentState) -> str:
    """
    Conditional edge function: routes based on reflector decision.
    - retry  → executor (re-attempt same step)
    - skip   → executor (but executor will advance the step index)
    - replan → planner
    """
    decision = state.get("decision", "skip")
    replans = state.get("stats", {}).get("replans", 0)

    # Guard: prevent infinite replan loops
    if decision == "replan" and replans > MAX_REPLANS:
        log_warning("[REFLECTOR] Too many replans — forcing skip.")
        decision = "skip"

    if decision == "retry":
        return "executor"
    elif decision == "replan":
        return "planner"
    else:
        # skip — advance step in executor by clearing last_error
        return "executor"
