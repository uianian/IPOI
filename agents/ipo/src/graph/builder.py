from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from src.graph.state import AgentState
from src.graph.edges import has_conflict, debate_resolved

logger = logging.getLogger(__name__)


class GraphBuilder:
    def __init__(
        self,
        legal_agent: Any,
        finance_agent: Any,
        sentiment_agent: Any,
        debate_protocol: Any,
        fusion_engine: Any,
    ) -> None:
        self._legal_agent = legal_agent
        self._finance_agent = finance_agent
        self._sentiment_agent = sentiment_agent
        self._debate_protocol = debate_protocol
        self._fusion_engine = fusion_engine

    def build(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("task_decomposition", self._task_decomposition)
        graph.add_node("legal_analysis", self._legal_analysis)
        graph.add_node("finance_analysis", self._finance_analysis)
        graph.add_node("sentiment_analysis", self._sentiment_analysis)
        graph.add_node("conflict_detection", self._conflict_detection)
        graph.add_node("debate_round", self._debate_round)
        graph.add_node("cross_modal_fusion", self._cross_modal_fusion)
        graph.add_node("report_generation", self._report_generation)

        graph.set_entry_point("task_decomposition")

        graph.add_edge("task_decomposition", "legal_analysis")
        graph.add_edge("task_decomposition", "finance_analysis")
        graph.add_edge("task_decomposition", "sentiment_analysis")

        graph.add_edge("legal_analysis", "conflict_detection")
        graph.add_edge("finance_analysis", "conflict_detection")
        graph.add_edge("sentiment_analysis", "conflict_detection")

        graph.add_conditional_edges(
            "conflict_detection",
            has_conflict,
            {"debate": "debate_round", "fusion": "cross_modal_fusion"},
        )

        graph.add_conditional_edges(
            "debate_round",
            debate_resolved,
            {"debate": "debate_round", "fusion": "cross_modal_fusion"},
        )

        graph.add_edge("cross_modal_fusion", "report_generation")
        graph.add_edge("report_generation", END)

        return graph

    async def _task_decomposition(self, state: AgentState) -> dict[str, Any]:
        from src.graph.nodes import task_decomposition_node
        return await task_decomposition_node(state)

    async def _legal_analysis(self, state: AgentState) -> dict[str, Any]:
        from src.graph.nodes import legal_analysis_node
        return await legal_analysis_node(state, self._legal_agent)

    async def _finance_analysis(self, state: AgentState) -> dict[str, Any]:
        from src.graph.nodes import finance_analysis_node
        return await finance_analysis_node(state, self._finance_agent)

    async def _sentiment_analysis(self, state: AgentState) -> dict[str, Any]:
        from src.graph.nodes import sentiment_analysis_node
        return await sentiment_analysis_node(state, self._sentiment_agent)

    async def _conflict_detection(self, state: AgentState) -> dict[str, Any]:
        from src.graph.nodes import conflict_detection_node
        return await conflict_detection_node(state, self._debate_protocol)

    async def _debate_round(self, state: AgentState) -> dict[str, Any]:
        from src.graph.nodes import debate_round_node
        return await debate_round_node(state, self._debate_protocol)

    async def _cross_modal_fusion(self, state: AgentState) -> dict[str, Any]:
        from src.graph.nodes import cross_modal_fusion_node
        return await cross_modal_fusion_node(state, self._fusion_engine)

    async def _report_generation(self, state: AgentState) -> dict[str, Any]:
        from src.graph.nodes import report_generation_node
        return await report_generation_node(state)