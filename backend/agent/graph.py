"""The LangGraph state graph (docs/spec.md S6.3, S6.5)."""

from typing import Any

from langgraph.graph import END, START, StateGraph

from agent import nodes
from agent.state import AgentDeps, AgentState

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


def build_graph(deps: AgentDeps) -> Any:
    """Compile the graph with the nodes bound to `deps`."""
    g = StateGraph(AgentState)
    g.add_node("survey", lambda s: nodes.survey(s, deps))
    g.add_node("plan", lambda s: nodes.plan(s, deps))
    g.add_node("inspect", lambda s: nodes.inspect(s, deps))
    g.add_node("verify", lambda s: nodes.verify(s, deps))
    g.add_node("report", lambda s: nodes.report(s, deps))
    g.add_edge(START, "survey")
    g.add_edge("survey", "plan")
    g.add_conditional_edges("plan", after_plan, {"inspect": "inspect", "report": "report"})
    g.add_edge("inspect", "verify")
    g.add_conditional_edges("verify", after_verify, {"plan": "plan", "report": "report"})
    g.add_edge("report", END)
    return g.compile()
