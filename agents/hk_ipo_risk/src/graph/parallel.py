from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from src.agents.finance_agent import FinanceAgent
from src.agents.legal_agent import LegalAgent
from src.agents.market_agent import MarketAgent
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
    legal_react: bool = False,
    legal_run_logger: Any | None = None,
    legal_max_turns: int = 10,
    finance_max_turns: int = 10,
    debate_dir: Path | str | None = None,
    client_project_id: str | None = None,
    task_id: str | None = None,
    analysis_id: str | None = None,
    doc_name: str | None = None,
    pdf_name: str | None = None,
    legal_reasoning_effort: str | None = "high",
    finance_reasoning_effort: str | None = "low",
) -> dict[str, Any]:
    """财务 ‖ 法务 并行；财务/法务 LLM 可分别注入。

    legal_react：service 默认由调用方开启；无 LLM 时 LegalAgent 自行回退规则链。
    """
    fin_llm = finance_llm if finance_llm is not None else llm
    leg_llm = legal_llm if legal_llm is not None else None
    finance_agent = FinanceAgent(
        llm=fin_llm,
        run_logger=finance_run_logger,
        rules_only=finance_rules_only,
        pipeline=finance_pipeline,
        max_turns=finance_max_turns,
        debate_dir=debate_dir,
        reasoning_effort=finance_reasoning_effort,
    )
    legal_agent = LegalAgent(
        llm=leg_llm,
        on_progress=legal_on_progress,
        react=legal_react,
        run_logger=legal_run_logger,
        max_turns=legal_max_turns,
        debate_dir=debate_dir,
        reasoning_effort=legal_reasoning_effort,
    )

    fin_task = asyncio.create_task(
        finance_agent.run(
            doc_id,
            issuer_type=issuer_type,
            retrieval_json=finance_retrieval_json,
            parse_json=parse_json,
            top_k=top_k,
            doc_name=doc_name,
            pdf_name=pdf_name,
            client_project_id=client_project_id,
            task_id=task_id or doc_id,
            analysis_id=analysis_id,
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
            doc_name=doc_name,
            pdf_name=pdf_name,
            client_project_id=client_project_id,
            task_id=task_id or doc_id,
            analysis_id=analysis_id,
        )
    )
    finance_result, legal_result = await asyncio.gather(fin_task, leg_task)
    return merge_results(finance_result, legal_result)


async def run_finance_legal_market_parallel(
    doc_id: str,
    *,
    stock_code: str,
    market_llm: Any | None = None,
    market_settings: dict[str, Any] | None = None,
    firecrawl_settings: dict[str, Any] | None = None,
    sina_settings: dict[str, Any] | None = None,
    market_run_logger: Any | None = None,
    market_on_progress: Any | None = None,
    market_max_turns: int | None = None,
    market_features_csv: Path | str | None = None,
    market_news_dir: Path | str | None = None,
    **finance_legal_kwargs: Any,
) -> dict[str, Any]:
    """财务、法务、市场并行；市场结果独立返回，不改变基本面参考分。"""

    market_agent = MarketAgent(
        llm=market_llm,
        market_settings=market_settings,
        firecrawl_settings=firecrawl_settings,
        sina_settings=sina_settings,
        run_logger=market_run_logger,
        on_progress=market_on_progress,
        max_turns=market_max_turns,
    )

    async def _run_market_safely() -> tuple[AgentResult | None, str | None]:
        try:
            result = await market_agent.run(
                doc_id,
                stock_code=stock_code,
                features_csv=market_features_csv,
                news_dir=market_news_dir,
            )
            return result, None
        except Exception as exc:  # 市场失败不应中断财务/法务结果
            return None, f"{type(exc).__name__}: {exc}"

    fundamental_task = asyncio.create_task(
        run_finance_legal_parallel(doc_id, **finance_legal_kwargs)
    )
    market_task = asyncio.create_task(_run_market_safely())
    merged, (market_result, market_error) = await asyncio.gather(
        fundamental_task,
        market_task,
    )
    merged["market"] = market_result.model_dump() if market_result is not None else None
    merged["market_error"] = market_error
    merged["note"] = (
        str(merged.get("note") or "")
        + "; market 为独立上市首日破发风险，不计入 reference_fundamental_score"
    )
    return merged


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
