from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from src.agents.finance_agent import FinanceAgent
from src.agents.legal_agent import LegalAgent
from src.agents.market_agent import MarketAgent
from src.agents.master_agent import MasterAgent
from src.models.evidence import AgentResult
from src.skills.master_cards import market_reference_score, reference_fundamental, reference_score_note

logger = logging.getLogger(__name__)


def _market_score_for_reference(market: AgentResult | None) -> float | None:
    if market is None:
        return None
    score, _meta = market_reference_score(market.model_dump())
    return score


async def _run_finance_legal_experts(
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
    keep_open: bool = True,
    on_finance_done: Any | None = None,
    on_legal_done: Any | None = None,
) -> tuple[AgentResult, AgentResult, FinanceAgent, LegalAgent]:
    """财务 ‖ 法务并行探查，不构造市场 Agent、不跑总控。"""
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
        close_logger=not keep_open,
    )
    legal_agent = LegalAgent(
        llm=leg_llm,
        on_progress=legal_on_progress,
        react=legal_react,
        run_logger=legal_run_logger,
        max_turns=legal_max_turns,
        debate_dir=debate_dir,
        reasoning_effort=legal_reasoning_effort,
        close_logger=not keep_open,
    )

    async def _run_finance() -> AgentResult:
        result = await finance_agent.run(
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
        if on_finance_done is not None:
            try:
                on_finance_done(result)
            except Exception:
                logger.exception("on_finance_done failed")
        return result

    provisional_gates = {
        "issuer_type": issuer_type,
        "is_biotech_18a": issuer_type.lower() in {"biotech", "18a", "18c"},
        "skip_3_5": issuer_type.lower() not in {"biotech", "18a", "18c"},
        "skip_3_5_reason": None if issuer_type.lower() in {"biotech", "18a", "18c"} else "non-biotech",
    }

    async def _run_legal() -> AgentResult:
        result = await legal_agent.run(
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
        if on_legal_done is not None:
            try:
                on_legal_done(result)
            except Exception:
                logger.exception("on_legal_done failed")
        return result

    finance_result, legal_result = await asyncio.gather(_run_finance(), _run_legal())
    finance_agent._last_result = finance_result
    legal_agent._last_result = legal_result
    return finance_result, legal_result, finance_agent, legal_agent


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
    master_llm: Any | None = None,
    top_k: int | None = None,
    finance_run_logger: Any | None = None,
    legal_on_progress: Any | None = None,
    finance_rules_only: bool = False,
    finance_pipeline: bool = False,
    legal_react: bool = False,
    legal_run_logger: Any | None = None,
    market_run_logger: Any | None = None,
    master_run_logger: Any | None = None,
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
    skip_master: bool = False,
    enable_embellishment: bool = True,
    include_market: bool = False,
    on_finance_done: Any | None = None,
    on_legal_done: Any | None = None,
) -> dict[str, Any]:
    """财务 ‖ 法务并行探查，随后总控子图。正式市场请走 run_finance_legal_market_parallel。"""
    del market_run_logger, include_market
    mas_llm = master_llm if master_llm is not None else llm
    finance_result, legal_result, finance_agent, legal_agent = await _run_finance_legal_experts(
        doc_id,
        issuer_type=issuer_type,
        finance_retrieval_json=finance_retrieval_json,
        legal_retrieval_json=legal_retrieval_json,
        parse_json=parse_json,
        llm=llm,
        finance_llm=finance_llm,
        legal_llm=legal_llm,
        top_k=top_k,
        finance_run_logger=finance_run_logger,
        legal_on_progress=legal_on_progress,
        finance_rules_only=finance_rules_only,
        finance_pipeline=finance_pipeline,
        legal_react=legal_react,
        legal_run_logger=legal_run_logger,
        legal_max_turns=legal_max_turns,
        finance_max_turns=finance_max_turns,
        debate_dir=debate_dir,
        client_project_id=client_project_id,
        task_id=task_id,
        analysis_id=analysis_id,
        doc_name=doc_name,
        pdf_name=pdf_name,
        legal_reasoning_effort=legal_reasoning_effort,
        finance_reasoning_effort=finance_reasoning_effort,
        keep_open=not skip_master,
        on_finance_done=on_finance_done,
        on_legal_done=on_legal_done,
    )
    return await merge_results(
        finance_result,
        legal_result,
        market=None,
        skip_master=skip_master,
        enable_embellishment=enable_embellishment,
        master_llm=mas_llm,
        master_run_logger=master_run_logger,
        parse_json=parse_json,
        debate_dir=debate_dir,
        finance_agent=finance_agent,
        legal_agent=legal_agent,
        market_agent=None,
        doc_name=doc_name,
    )


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
    on_market_done: Any | None = None,
    **finance_legal_kwargs: Any,
) -> dict[str, Any]:
    """财务、法务、市场并行；三专家完成后再进总控。"""
    finance_legal_kwargs.pop("include_market", None)
    finance_legal_kwargs.pop("market_run_logger", None)
    skip_master = bool(finance_legal_kwargs.pop("skip_master", False))
    enable_embellishment = bool(finance_legal_kwargs.pop("enable_embellishment", True))
    master_llm = finance_legal_kwargs.pop("master_llm", None)
    master_run_logger = finance_legal_kwargs.pop("master_run_logger", None)
    parse_json = finance_legal_kwargs.get("parse_json")
    debate_dir = finance_legal_kwargs.get("debate_dir")
    doc_name = finance_legal_kwargs.get("doc_name")
    llm = finance_legal_kwargs.get("llm")
    mas_llm = master_llm if master_llm is not None else llm

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
            logger.warning("market agent failed: %s", exc)
            return None, f"{type(exc).__name__}: {exc}"

    async def _run_market_and_notify() -> tuple[AgentResult | None, str | None]:
        result, err = await _run_market_safely()
        if on_market_done is not None:
            try:
                on_market_done(result, err)
            except Exception:
                logger.exception("on_market_done failed")
        return result, err

    experts_task = asyncio.create_task(
        _run_finance_legal_experts(
            doc_id,
            keep_open=not skip_master,
            **finance_legal_kwargs,
        )
    )
    market_task = asyncio.create_task(_run_market_and_notify())
    (finance_result, legal_result, finance_agent, legal_agent), (market_result, market_error) = (
        await asyncio.gather(experts_task, market_task)
    )
    merged = await merge_results(
        finance_result,
        legal_result,
        market=market_result,
        skip_master=skip_master,
        enable_embellishment=enable_embellishment,
        master_llm=mas_llm,
        master_run_logger=master_run_logger,
        parse_json=parse_json,
        debate_dir=debate_dir,
        finance_agent=finance_agent,
        legal_agent=legal_agent,
        market_agent=market_agent if market_result is not None else None,
        doc_name=doc_name,
    )
    merged["market_error"] = market_error
    return merged


async def merge_results(
    finance: AgentResult,
    legal: AgentResult,
    *,
    market: AgentResult | None = None,
    skip_master: bool = False,
    enable_embellishment: bool = True,
    master_llm: Any | None = None,
    master_run_logger: Any | None = None,
    parse_json: Path | str | None = None,
    debate_dir: Path | str | None = None,
    finance_agent: Any | None = None,
    legal_agent: Any | None = None,
    market_agent: Any | None = None,
    doc_name: str | None = None,
) -> dict[str, Any]:
    market_score = _market_score_for_reference(market)
    market_reference_meta: dict[str, Any] = {}
    if market is not None:
        _score, market_reference_meta = market_reference_score(market.model_dump())
    fundamental = reference_fundamental(
        finance.risk_score,
        legal.risk_score,
        market_score,
    )
    out: dict[str, Any] = {
        "doc_id": finance.doc_id or legal.doc_id,
        "finance": finance.model_dump(),
        "legal": legal.model_dump(),
        "reference_fundamental_score": fundamental,
        "market_reference_score": market_score,
        "market_reference_score_meta": market_reference_meta,
        "cross_agent_features": [],
        "master": None,
        "analysis_options": {"embellishment_enabled": bool(enable_embellishment)},
        "note": reference_score_note(has_market=market_score is not None, skip_master=skip_master),
    }
    if market is not None:
        out["market"] = market.model_dump()
    if skip_master:
        return out

    master = MasterAgent(
        llm=master_llm,
        run_logger=master_run_logger,
        debate_dir=debate_dir,
        parse_json=parse_json,
        finance_agent=finance_agent,
        legal_agent=legal_agent,
        market_agent=market_agent,
        enable_embellishment=enable_embellishment,
    )
    master_result = await master.run(
        doc_id=out["doc_id"],
        finance=finance,
        legal=legal,
        market=market,
        parse_json=parse_json,
        doc_name=doc_name,
    )
    out["master"] = master_result.model_dump()
    out["cross_agent_features"] = [
        {
            "theme": c.theme,
            "kind": c.kind,
            "need_discussion": c.need_discussion,
            "description": c.description,
            "claim_ids": c.claim_ids,
        }
        for c in master_result.conflicts
    ]
    return out


def _agent_result_from_saved(raw: Any, *, fallback_agent: str, doc_id: str) -> AgentResult:
    if isinstance(raw, AgentResult):
        return raw
    if isinstance(raw, dict) and raw.get("agent"):
        try:
            return AgentResult.model_validate(raw)
        except Exception:
            pass
    raise ValueError(f"--from-result 缺少可用的 {fallback_agent} AgentResult")


async def run_master_from_saved(
    result_path: Path | str,
    *,
    master_llm: Any | None = None,
    parse_json: Path | str | None = None,
    debate_dir: Path | str | None = None,
    finance_run_logger: Any | None = None,
    legal_run_logger: Any | None = None,
    market_run_logger: Any | None = None,
    master_run_logger: Any | None = None,
    doc_name: str | None = None,
    finance_reasoning_effort: str | None = "low",
    legal_reasoning_effort: str | None = "high",
    enable_embellishment: bool = True,
) -> dict[str, Any]:
    """跳过专家探查：从已有 merged JSON 直接跑总控（辩论补证仍可用 standalone）。"""
    path = Path(result_path)
    if not path.is_file():
        raise FileNotFoundError(f"--from-result 不存在: {path}")
    with path.open(encoding="utf-8") as f:
        saved = json.load(f)
    if not isinstance(saved, dict):
        raise ValueError("--from-result 必须是含 finance/legal 的 merged JSON")
    doc_id = str(saved.get("doc_id") or "")
    finance = _agent_result_from_saved(saved.get("finance"), fallback_agent="finance", doc_id=doc_id)
    legal = _agent_result_from_saved(saved.get("legal"), fallback_agent="legal", doc_id=doc_id)
    doc_id = doc_id or finance.doc_id or legal.doc_id
    market: AgentResult | None = None
    if saved.get("market"):
        market = _agent_result_from_saved(saved.get("market"), fallback_agent="market", doc_id=doc_id)

    finance_agent = FinanceAgent(
        llm=master_llm,
        run_logger=finance_run_logger,
        close_logger=False,
        debate_dir=debate_dir,
        reasoning_effort=finance_reasoning_effort,
    )
    finance_agent._doc_id = finance.doc_id or doc_id
    finance_agent._parse_json = parse_json
    finance_agent._last_result = finance
    legal_agent = LegalAgent(
        llm=master_llm,
        run_logger=legal_run_logger,
        close_logger=False,
        debate_dir=debate_dir,
        reasoning_effort=legal_reasoning_effort,
        react=True,
    )
    legal_agent._doc_id = legal.doc_id or doc_id
    legal_agent._parse_json = parse_json
    legal_agent._last_result = legal
    market_agent = MarketAgent(
        llm=master_llm,
        run_logger=market_run_logger,
    )
    market_agent._doc_id = doc_id
    if market is not None:
        market_agent._last_result = market

    logger.info(
        "skip-experts: load %s finance=%s legal=%s market=%s",
        path,
        finance.risk_score,
        legal.risk_score,
        None if market is None else market.risk_score,
    )
    out = await merge_results(
        finance,
        legal,
        market=market,
        skip_master=False,
        enable_embellishment=enable_embellishment,
        master_llm=master_llm,
        master_run_logger=master_run_logger,
        parse_json=parse_json,
        debate_dir=debate_dir,
        finance_agent=finance_agent,
        legal_agent=legal_agent,
        market_agent=market_agent if market is not None else None,
        doc_name=doc_name,
    )
    out["note"] = (out.get("note") or "") + f"；skip-experts from {path}"
    return out
