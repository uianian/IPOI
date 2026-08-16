"""总控子图：detect → (debate?) → embellish → decide → report。专家探查不进本图。"""

from __future__ import annotations

from typing import Any, TypedDict


class MasterGraphState(TypedDict, total=False):
    doc_id: str
    need_debate: bool
    conflicts: list[dict[str, Any]]
    debate_history: list[dict[str, Any]]
    embellishment: dict[str, Any]
    judgment: dict[str, Any]
    degraded: bool
    degraded_reasons: list[str]


def _route_after_detect(state: MasterGraphState) -> str:
    return "debate" if state.get("need_debate") else "embellish"


async def run_master_subgraph(master: Any, state: dict[str, Any]) -> dict[str, Any]:
    from langgraph.graph import END, START, StateGraph

    async def detect(s: dict[str, Any]) -> dict[str, Any]:
        return await master.step_detect(s)

    async def debate(s: dict[str, Any]) -> dict[str, Any]:
        return await master.step_debate(s)

    async def embellish(s: dict[str, Any]) -> dict[str, Any]:
        return await master.step_embellish(s)

    async def decide(s: dict[str, Any]) -> dict[str, Any]:
        return await master.step_decide(s)

    async def report(s: dict[str, Any]) -> dict[str, Any]:
        return await master.step_report(s)

    g = StateGraph(dict)
    g.add_node("detect", detect)
    g.add_node("debate", debate)
    g.add_node("embellish", embellish)
    g.add_node("decide", decide)
    g.add_node("report", report)
    g.add_edge(START, "detect")
    g.add_conditional_edges(
        "detect",
        _route_after_detect,
        {"debate": "debate", "embellish": "embellish"},
    )
    g.add_edge("debate", "embellish")
    g.add_edge("embellish", "decide")
    g.add_edge("decide", "report")
    g.add_edge("report", END)
    app = g.compile()
    return await app.ainvoke(state)
