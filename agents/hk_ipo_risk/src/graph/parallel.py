from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from src.agents.finance_agent import FinanceAgent
from src.agents.legal_agent import LegalAgent
from src.models.evidence import AgentResult


async def run_finance_legal_parallel(
    doc_id: str,
    *,
    issuer_type: str = "general",
    finance_retrieval_json: Path | str | None = None,
    legal_retrieval_json: Path | str | None = None,
    parse_json: Path | str | None = None,
    llm: Any | None = None,
    finance_llm: Any | None = None,
    legal_llm: Any | None = None,
    top_k: int | None = None,
    finance_run_logger: Any | None = None,
    legal_on_progress: Any | None = None,
    finance_rules_only: bool = False,
    finance_pipeline: bool = False,
    doc_name: str | None = None,
    pdf_name: str | None = None,
) -> dict[str, Any]:
    """财务 ‖ 法务 并行；财务/法务 LLM 可分别注入。"""
    fin_llm = finance_llm if finance_llm is not None else llm
    leg_llm = legal_llm if legal_llm is not None else None
    finance_agent = FinanceAgent(
        llm=fin_llm,
        run_logger=finance_run_logger,
        rules_only=finance_rules_only,
        pipeline=finance_pipeline,
    )
    legal_agent = LegalAgent(llm=leg_llm, on_progress=legal_on_progress)

    fin_task = asyncio.create_task(
        finance_agent.run(
            doc_id,
            issuer_type=issuer_type,
            retrieval_json=finance_retrieval_json,
            parse_json=parse_json,
            top_k=top_k,
            doc_name=doc_name,
            pdf_name=pdf_name,
        )
    )
    provisional_gates = {
        "issuer_type": issuer_type,
        "is_biotech_18a": issuer_type.lower() in {"biotech", "18a", "18c"},
        "skip_3_5": issuer_type.lower() not in {"biotech", "18a", "18c"},
        "skip_3_5_reason": None if issuer_type.lower() in {"biotech", "18a", "18c"} else "non-biotech",
    }
    leg_task = asyncio.create_task(
        legal_agent.run(
            doc_id,
            issuer_type=issuer_type,
            gates=provisional_gates,
            retrieval_json=legal_retrieval_json,
            parse_json=parse_json,
            top_k=top_k,
        )
    )
    finance_result, legal_result = await asyncio.gather(fin_task, leg_task)
    return merge_results(finance_result, legal_result)


def merge_results(finance: AgentResult, legal: AgentResult) -> dict[str, Any]:
    # 参考旧 fusion：fundamental ≈ legal*0.45 + finance*0.55（本阶段附带参考值，非总控正式输出）
    fundamental = min(100.0, legal.risk_score * 0.45 + finance.risk_score * 0.55)
    return {
        "doc_id": finance.doc_id or legal.doc_id,
        "finance": finance.model_dump(),
        "legal": legal.model_dump(),
        "reference_fundamental_score": round(fundamental, 2),
        "cross_agent_features": [],
        "master": None,
        "note": (
            "reference_fundamental_score = legal*0.45 + finance*0.55; "
            "master/cross_agent_features 为本轮占位，总控辩论未启用"
        ),
    }
