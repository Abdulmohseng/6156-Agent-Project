from typing import TypedDict, List, Optional


class AgentState(TypedDict):
    goal: str                        # User's natural language instruction
    folder: str                      # Target folder path
    file_listing: List[dict]         # Output of list_files tool
    plan: Optional[List[dict]]       # Step list from Planner
    current_step: int                # Index into plan
    step_results: List[dict]         # Accumulated results
    last_error: Optional[str]        # Error from failed step
    decision: Optional[str]          # Reflector output: retry/skip/replan
    done: bool                       # Terminal condition
    safe_mode: bool                  # Confirm each destructive step individually
    verbose: bool                    # Print full tool outputs
    dry_run: bool                    # Plan only, no execution
    mode: str                        # plan-and-act | reactive | direct
    model: str                       # Ollama model name
    messages: List[dict]             # Message history for executor LLM calls
    stats: dict                      # Runtime statistics for logging
    retry_counts: dict               # {step_index: retry_count} — per-step retry tracking
