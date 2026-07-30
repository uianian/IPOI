from __future__ import annotations

from src.graph.state import AgentState


def has_conflict(state: AgentState) -> str:
    conflicts = state.get("conflicts", [])
    if conflicts and len(conflicts) > 0:
        return "debate"
    return "fusion"


def debate_resolved(state: AgentState) -> str:
    debate_results = state.get("debate_results", [])
    conflicts = state.get("conflicts", [])

    if not conflicts:
        return "fusion"

    all_resolved = all(d.get("final_resolved", False) for d in debate_results)
    max_rounds_reached = any(
        d.get("total_rounds", 0) >= 3 for d in debate_results
    )

    if all_resolved:
        return "fusion"
    if max_rounds_reached:
        return "fusion"

    return "debate"