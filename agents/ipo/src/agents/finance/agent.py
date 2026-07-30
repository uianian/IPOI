from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base import BaseAgent
from src.models.enums import AgentRole, SeverityLevel
from src.models.evidence import EvidenceRef
from src.models.finance import (
    BurnRateResult,
    ComparisonResult,
    FinanceAnalysisResult,
    FinancialIndicator,
    ManipulationSignal,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class FinanceAgent(BaseAgent):
    agent_role = AgentRole.FINANCE

    async def analyze(self, doc_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}

        retrieval_result = await self.call_skill(
            "long_doc_retrieval", doc_id,
            {"action": "retrieve", "query": "营业收入 净利润 毛利率 现金流 资产负债 研发费用", "top_k": 20},
        )

        if not retrieval_result.success:
            return FinanceAnalysisResult(doc_id=doc_id, summary="检索财务段落失败").model_dump()

        chunks_text = ""
        for chunk_data in retrieval_result.data.get("chunks", []):
            chunks_text += f"[第{chunk_data['page_number']}页] {chunk_data['content']}\n\n"

        from src.llm.prompts import FINANCIAL_INDICATOR_EXTRACTION, FINANCIAL_VALIDATION, FINANCIAL_MANIPULATION_DETECTION

        extraction_messages = [
            {"role": "user", "content": FINANCIAL_INDICATOR_EXTRACTION.format(text=chunks_text[:8000])},
        ]
        extraction_response = await self.llm_call(extraction_messages, step_type=StepType.EXTRACT)

        indicators: list[FinancialIndicator] = []
        try:
            parsed = json.loads(extraction_response)
            for ind in parsed.get("indicators", []):
                indicators.append(FinancialIndicator(
                    name=ind.get("name", ""),
                    value=ind.get("value", ""),
                    unit=ind.get("unit"),
                    period=ind.get("period"),
                    source_page=ind.get("source_page"),
                ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Financial indicator extraction failed: {e}")

        burn_rate_result = await self.call_skill(
            "cash_flow_calculation", doc_id,
            {
                "action": "sensitivity",
                "operating_cash_outflow": params.get("operating_cash_outflow", 0.0),
                "months": params.get("months", 12),
                "cash_reserve": params.get("cash_reserve", 0.0),
            },
        )

        burn_rate_results: list[BurnRateResult] = []
        if burn_rate_result.success:
            for scenario in burn_rate_result.data.get("scenarios", []):
                burn_rate_results.append(BurnRateResult(**scenario))

        peer_result = await self.call_skill(
            "peer_comparison", doc_id,
            {
                "action": "compare",
                "industry": params.get("industry", ""),
                "issuer_metrics": params.get("issuer_metrics", {}),
            },
        )

        comparison_results: list[ComparisonResult] = []
        if peer_result.success:
            for comp in peer_result.data.get("comparison_results", []):
                comparison_results.append(ComparisonResult(
                    metric_name=comp.get("metric_name", ""),
                    issuer_value=comp.get("issuer_value"),
                    industry_mean=comp.get("industry_mean"),
                    industry_median=comp.get("industry_median"),
                    z_score=comp.get("z_score"),
                    is_significant=comp.get("is_significant", False),
                    peer_count=comp.get("peer_count", 0),
                    peer_sample_limited=comp.get("peer_sample_limited", False),
                ))

        manipulation_messages = [
            {"role": "user", "content": FINANCIAL_MANIPULATION_DETECTION.format(
                financial_data=chunks_text[:6000]
            )},
        ]
        manipulation_response = await self.llm_call(manipulation_messages, step_type=StepType.ANALYZE)

        manipulation_signals: list[ManipulationSignal] = []
        try:
            parsed = json.loads(manipulation_response)
            for sig in parsed.get("manipulation_signals", []):
                severity = SeverityLevel.LOW
                if sig.get("severity") == "high":
                    severity = SeverityLevel.HIGH
                elif sig.get("severity") == "medium":
                    severity = SeverityLevel.MEDIUM

                manipulation_signals.append(ManipulationSignal(
                    signal_name=sig.get("signal_name", ""),
                    description=sig.get("description", ""),
                    severity=severity,
                    cross_evidence_count=sig.get("cross_evidence_count", 0),
                ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Manipulation detection parse failed: {e}")

        validation_messages = [
            {"role": "user", "content": FINANCIAL_VALIDATION.format(
                indicators=json.dumps([i.model_dump() for i in indicators], ensure_ascii=False),
                peer_data=json.dumps([c.model_dump() for c in comparison_results], ensure_ascii=False),
            )},
        ]
        validation_response = await self.llm_call(validation_messages, step_type=StepType.VALIDATE)

        validation_results: list[ValidationResult] = []
        try:
            parsed = json.loads(validation_response)
            for v in parsed.get("validation_results", []):
                validation_results.append(ValidationResult(
                    indicator_name=v.get("indicator_name", ""),
                    check_type=v.get("check_type", ""),
                    passed=v.get("passed", True),
                    deviation=v.get("deviation"),
                    note=v.get("note"),
                ))
        except (json.JSONDecodeError, KeyError):
            pass

        failed_validations = sum(1 for v in validation_results if not v.passed)
        high_severity_signals = sum(1 for s in manipulation_signals if s.severity == SeverityLevel.HIGH)

        result = FinanceAnalysisResult(
            doc_id=doc_id,
            indicators=indicators,
            validation_results=validation_results,
            manipulation_signals=manipulation_signals,
            burn_rate_results=burn_rate_results,
            comparison_results=comparison_results,
            summary=f"抽取{len(indicators)}个财务指标，校验不通过{failed_validations}项，"
            f"操纵信号{len(manipulation_signals)}个（高危{high_severity_signals}），"
            f"现金流测算{len(burn_rate_results)}组场景",
        )

        await self._trace_logger.log_step(
            agent_role=self.agent_role,
            step_type=StepType.REPORT,
            output_summary=result.summary,
        )

        return result.model_dump()