from langgraph.graph import StateGraph, END

from state import AgentState
from planner import planner_node
from executor import executor_node
from reflector import reflector_node, route_after_reflect


def _route_after_executor(state: AgentState) -> str:
    if state.get("done"):
        return "end"
    if state.get("last_error"):
        return "reflector"
    return "executor"  # loop back to process next step


def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("reflector", reflector_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "executor")

    builder.add_conditional_edges(
        "executor",
        _route_after_executor,
        {"reflector": "reflector", "executor": "executor", "end": END},
    )

    builder.add_conditional_edges(
        "reflector",
        route_after_reflect,
        {"executor": "executor", "planner": "planner", "end": END},
    )

    return builder.compile()


def build_reactive_graph() -> StateGraph:
    """
    Reactive mode: no planning phase — executor acts step by step without a pre-generated plan.
    The planner node is used once at the start only to list files; plan is built incrementally.
    In practice, we reuse the same graph structure but skip the plan confirmation.
    """
    return build_graph()


# Singleton
graph = build_graph()
