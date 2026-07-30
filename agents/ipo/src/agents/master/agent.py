from __future__ import annotations

import logging
import uuid
from typing import Any

from src.agents.base import BaseAgent
from src.agents.legal.agent import LegalAgent
from src.agents.finance.agent import FinanceAgent
from src.agents.sentiment.agent import SentimentAgent
from src.config import settings
from src.graph.builder import GraphBuilder
from src.graph.state import AgentState
from src.models.enums import AgentRole
from src.models.report import RiskReport
from src.protocols.debate import DebateProtocol
from src.protocols.fusion import CrossModalFusion
from src.skills.registry import SkillRegistry
from src.tracing.logger import TraceAuditLogger

logger = logging.getLogger(__name__)


class MasterOrchestrator:
    def __init__(
        self,
        vllm_client: Any,
        skill_registry: SkillRegistry,
        trace_logger: TraceAuditLogger,
    ) -> None:
        self._vllm = vllm_client
        self._skill_registry = skill_registry
        self._trace_logger = trace_logger

        self._legal_agent = LegalAgent(vllm_client, skill_registry, trace_logger)
        self._finance_agent = FinanceAgent(vllm_client, skill_registry, trace_logger)
        self._sentiment_agent = SentimentAgent(vllm_client, skill_registry, trace_logger)

        self._debate_protocol = DebateProtocol(vllm_client, max_rounds=settings.debate.max_rounds)
        self._fusion_engine = CrossModalFusion()

        self._graph_builder = GraphBuilder(
            legal_agent=self._legal_agent,
            finance_agent=self._finance_agent,
            sentiment_agent=self._sentiment_agent,
            debate_protocol=self._debate_protocol,
            fusion_engine=self._fusion_engine,
        )

        self._compiled_graph = None

    def _get_compiled_graph(self):
        if self._compiled_graph is None:
            graph = self._graph_builder.build()
            self._compiled_graph = graph.compile()
        return self._compiled_graph

    async def decompose_task(self, doc_id: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = params or {}
        sub_tasks = [
            {"agent": "legal", "doc_id": doc_id},
            {"agent": "finance", "doc_id": doc_id},
            {"agent": "sentiment", "doc_id": doc_id},
        ]
        return sub_tasks

    async def detect_conflicts(
        self,
        legal_result: dict[str, Any],
        finance_result: dict[str, Any],
        sentiment_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        conflicts = await self._debate_protocol.detect_conflicts(
            legal_result, finance_result, sentiment_result
        )
        return [c.model_dump() for c in conflicts]

    async def orchestrate_debate(
        self,
        conflicts: list[dict[str, Any]],
        agent_results: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results = []
        for conflict_data in conflicts:
            from src.models.conflict import ConflictItem
            conflict = ConflictItem(**conflict_data)
            debate_result = await self._debate_protocol.run_debate(conflict, agent_results)
            results.append(debate_result.model_dump())
        return results

    async def fuse_results(
        self,
        legal_result: dict[str, Any],
        finance_result: dict[str, Any],
        sentiment_result: dict[str, Any],
    ) -> dict[str, Any]:
        fused = self._fusion_engine.fuse_and_rate(legal_result, finance_result, sentiment_result)
        return fused.model_dump()

    async def run_full_analysis(
        self,
        doc_id: str,
        file_path: str | None = None,
        company_name: str | None = None,
        stock_code: str | None = None,
        industry: str | None = None,
    ) -> RiskReport:
        logger.info(f"Starting full analysis for doc_id={doc_id}")

        initial_state: AgentState = {
            "doc_id": doc_id,
            "file_path": file_path or "",
            "company_name": company_name or "",
            "stock_code": stock_code or "",
            "industry": industry or "",
        }

        compiled = self._get_compiled_graph()

        final_state = await compiled.ainvoke(initial_state)

        report_data = final_state.get("final_report", {})
        fused_data = final_state.get("fused_result", {})

        report = RiskReport(
            report_id=report_data.get("report_id", str(uuid.uuid4())),
            doc_id=doc_id,
            company_name=company_name or "",
            risk_assessment=None,
            conflicts=report_data.get("conflicts", []),
            debate_results=report_data.get("debate_results", []),
            summary=report_data.get("summary", ""),
        )

        if fused_data:
            from src.models.report import FusedRiskAssessment
            try:
                report.risk_assessment = FusedRiskAssessment(**fused_data)
            except Exception as e:
                logger.warning(f"Failed to parse fused result: {e}")

        return report