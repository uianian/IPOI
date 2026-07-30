from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base import BaseAgent
from src.models.enums import AgentRole, SeverityLevel
from src.models.evidence import EvidenceRef
from src.models.legal import (
    ComplianceFlaw,
    CrossReference,
    LegalAnalysisResult,
    LegalRiskFeature,
)

logger = logging.getLogger(__name__)


class LegalAgent(BaseAgent):
    agent_role = AgentRole.LEGAL

    async def analyze(self, doc_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}

        retrieval_result = await self.call_skill(
            "long_doc_retrieval", doc_id,
            {"action": "retrieve", "query": "诉讼 仲裁 行政处罚 知识产权 VIE 对赌 赎回条款 关联交易 数据合规 环保", "top_k": 20},
        )

        if not retrieval_result.success:
            return LegalAnalysisResult(doc_id=doc_id, summary="检索法律相关段落失败").model_dump()

        chunks_text = ""
        for chunk_data in retrieval_result.data.get("chunks", []):
            chunks_text += f"[第{chunk_data['page_number']}页] {chunk_data['content']}\n\n"

        from src.llm.prompts import LEGAL_RISK_EXTRACTION, LEGAL_SEVERITY_GRADING, LEGAL_CROSS_REFERENCE

        extraction_messages = [
            {"role": "user", "content": LEGAL_RISK_EXTRACTION.format(text=chunks_text[:8000])},
        ]
        extraction_response = await self.llm_call(extraction_messages, step_type=StepType.EXTRACT)

        risk_features = []
        try:
            parsed = json.loads(extraction_response)
            feature_list = parsed.get("risk_features", [])
            for feat in feature_list:
                evidence = []
                if feat.get("evidence_text") and feat["evidence_text"] != "无直接原文支撑":
                    evidence.append(EvidenceRef(
                        page_number=feat.get("_evidence_page", 1),
                        text_excerpt=feat["evidence_text"][:500],
                        confidence=1.0 if feat.get("_evidence_page") else 0.3,
                    ))
                else:
                    evidence.append(EvidenceRef(
                        page_number=1,
                        text_excerpt="无直接原文支撑",
                        confidence=0.2,
                    ))

                severity = SeverityLevel.LOW
                if feat.get("severity") == "high":
                    severity = SeverityLevel.HIGH
                elif feat.get("severity") == "medium":
                    severity = SeverityLevel.MEDIUM

                risk_features.append(LegalRiskFeature(
                    feature_name=feat.get("feature_name", "未知"),
                    description=feat.get("description", ""),
                    severity=severity,
                    legal_basis=feat.get("legal_basis"),
                    evidence=evidence,
                ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Legal extraction parse failed: {e}")

        grading_messages = [
            {"role": "user", "content": LEGAL_SEVERITY_GRADING.format(
                features=json.dumps([f.model_dump() for f in risk_features], ensure_ascii=False)
            )},
        ]
        await self.llm_call(grading_messages, step_type=StepType.VALIDATE)

        needs_full_scan = any(
            f.description and any(kw in f.description for kw in ["VIE", "关联交易", "对赌"])
            for f in risk_features
        )
        if needs_full_scan:
            full_scan_result = await self.call_skill(
                "long_doc_retrieval", doc_id,
                {"action": "retrieve", "query": "VIE架构 关联交易 对赌协议 赎回条款", "top_k": 30},
            )

        high_risk_count = sum(1 for f in risk_features if f.severity == SeverityLevel.HIGH)

        result = LegalAnalysisResult(
            doc_id=doc_id,
            risk_features=risk_features,
            high_risk_count=high_risk_count,
            full_scan_triggered=needs_full_scan,
            summary=f"发现{len(risk_features)}个法律风险特征，其中高危{high_risk_count}个"
            + ("，已触发全文档补充扫描" if needs_full_scan else ""),
        )

        await self._trace_logger.log_step(
            agent_role=self.agent_role,
            step_type=StepType.REPORT,
            output_summary=result.summary,
        )

        return result.model_dump()