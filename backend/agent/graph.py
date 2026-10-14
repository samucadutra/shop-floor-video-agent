"""The LangGraph state graph (docs/spec.md S6.3, S6.5)."""

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent import nodes
from agent.state import AgentDeps, AgentState
from config.logging import log_context

RECURSION_LIMIT = 50


def after_plan(state: AgentState) -> str:
    return "inspect" if state["windows"] else "report"


def after_verify(state: AgentState) -> str:
    # The verify node already set stop_reason when a limit was hit (routers cannot write state).
    if state["stop_reason"]:
        return "report"
    if any(c["status"] == "open" for c in state["candidates"]):
        return "plan"
    return "report"


def _bind(name: str, node: Callable[[AgentState, AgentDeps], dict], deps: AgentDeps) -> Callable:
    """Bind the node to `deps`; its log lines carry the node name."""

    def run(state: AgentState) -> dict[str, Any]:
        with log_context(node=name):
            return node(state, deps)

    return run


def build_graph(deps: AgentDeps) -> Any:
    """Compile the graph with the nodes bound to `deps`."""
    g = StateGraph(AgentState)
    for name in ("survey", "plan", "inspect", "verify", "report"):
        g.add_node(name, _bind(name, getattr(nodes, name), deps))
    g.add_edge(START, "survey")
    g.add_edge("survey", "plan")
    g.add_conditional_edges("plan", after_plan, {"inspect": "inspect", "report": "report"})
    g.add_edge("inspect", "verify")
    g.add_conditional_edges("verify", after_verify, {"plan": "plan", "report": "report"})
    g.add_edge("report", END)
    return g.compile()
