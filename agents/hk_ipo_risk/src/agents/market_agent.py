from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.models.evidence import AgentResult
from src.models.master import ClaimUpdate, DebateQuestion
from src.skills.debate_reply import expert_respond_to_controller
from src.skills.market_toolbox import submit_market_demo_dossier

logger = logging.getLogger(__name__)


class MarketAgent:
    """可替换 demo：中性分≈50，默认不调 LLM；respond_to_controller 模板声明无行情证据。"""

    def __init__(
        self,
        llm: Any | None = None,
        *,
        run_logger: Any | None = None,
        debate_dir: Path | str | None = None,
        demo: bool = True,
    ) -> None:
        self._llm = llm
        self._run_logger = run_logger
        self._debate_dir = debate_dir
        self._demo = demo
        self._doc_id = ""
        self._parse_json: Path | str | None = None

    async def run(
        self,
        doc_id: str,
        *,
        issuer_type: str = "general",
        parse_json: Path | str | None = None,
        doc_name: str | None = None,
        pdf_name: str | None = None,
        client_project_id: str | None = None,
        task_id: str | None = None,
        analysis_id: str | None = None,
        **_: Any,
    ) -> AgentResult:
        self._doc_id = doc_id
        self._parse_json = parse_json
        summary = "市場情緒 Agent 為 demo stub，未接入認購倍數/破發率寬表；風險分中性 50。"
        if self._run_logger is not None:
            self._run_logger.step(
                "market_demo",
                kind="skill",
                status="ok",
                output={"demo": True, "risk_score": 50},
            )
        dossier_path = submit_market_demo_dossier(
            doc_id=doc_id,
            debate_dir=self._debate_dir,
            doc_name=doc_name,
            summary=summary,
        )
        log_paths = self._run_logger.paths if self._run_logger is not None else {}
        return AgentResult(
            agent="market",
            doc_id=doc_id,
            risk_score=50.0,
            risk_level="medium",
            features={
                "demo": True,
                "scoring_mode": "demo_stub",
                "debate_dossier_path": dossier_path,
                "run_log": log_paths,
            },
            gates={"issuer_type": issuer_type},
            evidence_summary={"snippets": []},
            trace={
                "demo": True,
                "debate_dossier_path": dossier_path,
                "client_project_id": client_project_id,
                "task_id": task_id,
                "analysis_id": analysis_id,
                "pdf_name": pdf_name,
            },
            summary=summary,
        )

    async def respond_to_controller(
        self,
        question: DebateQuestion,
        claim_card: dict[str, Any] | None = None,
        *,
        round_no: int = 1,
        doc_id: str | None = None,
        parse_json: Path | str | None = None,
    ) -> ClaimUpdate:
        return await expert_respond_to_controller(
            agent="market",
            question=question,
            claim_card=claim_card,
            llm=self._llm,
            doc_id=doc_id or self._doc_id,
            parse_json=parse_json or self._parse_json,
            run_logger=self._run_logger,
            round_no=round_no,
            demo_market=self._demo,
        )

    @staticmethod
    def fallback_result(doc_id: str) -> AgentResult:
        return AgentResult(
            agent="market",
            doc_id=doc_id,
            risk_score=50.0,
            risk_level="medium",
            features={"demo": True, "scoring_mode": "demo_stub", "error": "market_failed"},
            summary="市場情緒 Agent demo 失敗，使用中性分 50。",
        )
