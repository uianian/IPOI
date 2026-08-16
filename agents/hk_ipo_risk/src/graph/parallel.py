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
from src.skills.master_cards import reference_fundamental

logger = logging.getLogger(__name__)


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
    include_market: bool = True,
) -> dict[str, Any]:
    """财务 ‖ 法务 ‖ 市场(demo) 并行探查，随后总控子图。"""
    fin_llm = finance_llm if finance_llm is not None else llm
    leg_llm = legal_llm if legal_llm is not None else None
    mas_llm = master_llm if master_llm is not None else llm
    keep_open = not skip_master
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
    market_agent = MarketAgent(
        llm=None,
        run_logger=market_run_logger,
        debate_dir=debate_dir,
        demo=True,
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
    tasks: list[asyncio.Task] = [fin_task, leg_task]
    if include_market:
        tasks.append(
            asyncio.create_task(
                market_agent.run(
                    doc_id,
                    issuer_type=issuer_type,
                    parse_json=parse_json,
                    doc_name=doc_name,
                    pdf_name=pdf_name,
                    client_project_id=client_project_id,
                    task_id=task_id or doc_id,
                    analysis_id=analysis_id,
                )
            )
        )
    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    finance_result = gathered[0]
    legal_result = gathered[1]
    if isinstance(finance_result, Exception):
        raise finance_result
    if isinstance(legal_result, Exception):
        raise legal_result
    market_result: AgentResult | None = None
    if include_market:
        raw_m = gathered[2]
        if isinstance(raw_m, Exception):
            logger.warning("market demo failed, using fallback: %s", raw_m)
            market_result = MarketAgent.fallback_result(doc_id)
        else:
            market_result = raw_m

    return await merge_results(
        finance_result,
        legal_result,
        market=market_result,
        skip_master=skip_master,
        master_llm=mas_llm,
        master_run_logger=master_run_logger,
        parse_json=parse_json,
        debate_dir=debate_dir,
        finance_agent=finance_agent,
        legal_agent=legal_agent,
        market_agent=market_agent,
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
        run_finance_legal_parallel(doc_id, include_market=False, **finance_legal_kwargs)
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


async def merge_results(
    finance: AgentResult,
    legal: AgentResult,
    *,
    market: AgentResult | None = None,
    skip_master: bool = False,
    master_llm: Any | None = None,
    master_run_logger: Any | None = None,
    parse_json: Path | str | None = None,
    debate_dir: Path | str | None = None,
    finance_agent: Any | None = None,
    legal_agent: Any | None = None,
    market_agent: Any | None = None,
    doc_name: str | None = None,
) -> dict[str, Any]:
    fundamental = reference_fundamental(finance.risk_score, legal.risk_score)
    out: dict[str, Any] = {
        "doc_id": finance.doc_id or legal.doc_id,
        "finance": finance.model_dump(),
        "legal": legal.model_dump(),
        "reference_fundamental_score": fundamental,
        "cross_agent_features": [],
        "master": None,
        "note": (
            "reference_fundamental_score = legal*0.45 + finance*0.55 为对照分；"
            "正式等级以总控终裁为准"
        ),
    }
    if market is not None:
        out["market"] = market.model_dump()
    if skip_master:
        out["note"] = (
            "reference_fundamental_score = legal*0.45 + finance*0.55; "
            "--skip-master，总控未运行"
        )
        return out

    master = MasterAgent(
        llm=master_llm,
        run_logger=master_run_logger,
        debate_dir=debate_dir,
        parse_json=parse_json,
        finance_agent=finance_agent,
        legal_agent=legal_agent,
        market_agent=market_agent,
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
    if fallback_agent == "market":
        return MarketAgent.fallback_result(doc_id)
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
    if saved.get("market"):
        market = _agent_result_from_saved(saved.get("market"), fallback_agent="market", doc_id=doc_id)
    else:
        market = MarketAgent.fallback_result(doc_id)

    finance_agent = FinanceAgent(
        llm=master_llm,
        run_logger=finance_run_logger,
        close_logger=False,
        debate_dir=debate_dir,
        reasoning_effort=finance_reasoning_effort,
    )
    finance_agent._doc_id = finance.doc_id or doc_id
    finance_agent._parse_json = parse_json
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
    market_agent = MarketAgent(
        llm=None,
        run_logger=market_run_logger,
        debate_dir=debate_dir,
        demo=True,
    )
    market_agent._doc_id = doc_id
    market_agent._parse_json = parse_json

    logger.info("skip-experts: load %s finance=%s legal=%s", path, finance.risk_score, legal.risk_score)
    out = await merge_results(
        finance,
        legal,
        market=market,
        skip_master=False,
        master_llm=master_llm,
        master_run_logger=master_run_logger,
        parse_json=parse_json,
        debate_dir=debate_dir,
        finance_agent=finance_agent,
        legal_agent=legal_agent,
        market_agent=market_agent,
        doc_name=doc_name,
    )
    out["note"] = (
        (out.get("note") or "")
        + f"；skip-experts from {path}"
    )
    return out
