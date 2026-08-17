from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from src.config import load_master_rules
from src.llm.debate_prompts import FINANCE_DEBATE_REPLY, LEGAL_DEBATE_REPLY, MARKET_DEBATE_REPLY
from src.models.evidence import EvidenceRef
from src.models.master import ClaimUpdate, DebateQuestion
from src.skills.debate_query import (
    DebateSearchStep,
    hit_is_useful,
    looks_like_instruction,
    plan_debate_searches,
)
from src.skills.llm_json import llm_json

logger = logging.getLogger(__name__)

_STATUS = {
    "proposed",
    "challenged",
    "verified",
    "partially_accepted",
    "rejected",
    "unresolved",
}


def _hits_to_evidence(hits: list[dict[str, Any]], limit: int = 4) -> list[EvidenceRef]:
    out: list[EvidenceRef] = []
    for h in hits[:limit]:
        if not isinstance(h, dict):
            continue
        excerpt = str(h.get("excerpt") or h.get("text") or "")[:400]
        page = h.get("page")
        try:
            page_i = int(page) if page is not None else None
        except (TypeError, ValueError):
            page_i = None
        st = h.get("source_type") or "unknown"
        if st not in {"table", "text", "title", "unknown"}:
            st = "unknown"
        out.append(EvidenceRef(page=page_i, excerpt=excerpt, source_type=st))  # type: ignore[arg-type]
    return out


async def _maybe_search(
    *,
    agent: str,
    doc_id: str,
    parse_json: Path | str | None,
    query: str,
    intent: str,
    top_k: int,
    section_hint: list[str] | None = None,
    prefer_pages: list[int] | None = None,
) -> dict[str, Any]:
    if not query.strip():
        return {"ok": False, "hits": [], "query": query, "n": 0}
    t0 = time.time()
    if agent == "finance":
        if not parse_json:
            return {"ok": False, "hits": [], "query": query, "n": 0, "error": "缺少 parse_json"}
        from src.skills.finance_toolbox import search_finance_evidence_standalone

        raw = await search_finance_evidence_standalone(
            doc_id=doc_id,
            query=query,
            intent=intent,
            parse_json=parse_json,
            top_k=top_k,
            section_hint=section_hint,
            prefer_pages=prefer_pages,
        )
    elif agent == "legal":
        if not parse_json:
            return {"ok": False, "hits": [], "query": query, "n": 0, "error": "缺少 parse_json"}
        from src.skills.legal_toolbox import search_legal_evidence_standalone

        raw = await search_legal_evidence_standalone(
            doc_id=doc_id,
            parse_json=parse_json,
            query=query,
            intent=intent,
            top_k=top_k,
            section_hint=section_hint,
            prefer_pages=prefer_pages,
        )
    else:
        from src.skills.market_toolbox import search_market_evidence_standalone

        raw = await search_market_evidence_standalone(doc_id=doc_id, query=query)
    raw["duration_ms"] = int((time.time() - t0) * 1000)
    return raw


async def _run_search_step(
    *,
    agent: str,
    doc_id: str,
    parse_json: Path | str | None,
    step: DebateSearchStep,
    top_k: int,
) -> dict[str, Any]:
    if step.kind == "page":
        if not parse_json:
            return {"ok": False, "hits": [], "query": step.query, "n": 0, "error": "缺少 parse_json"}
        from src.tools.retrieval_tool import hits_from_prefer_pages

        kws = [t for t in (step.query or "").split() if t]
        t0 = time.time()
        hits = hits_from_prefer_pages(
            parse_json,
            list(step.pages),
            keywords=kws or None,
            top_k=top_k,
        )
        return {
            "ok": True,
            "hits": hits,
            "n": len(hits),
            "query": step.query,
            "pages": list(step.pages),
            "duration_ms": int((time.time() - t0) * 1000),
        }
    return await _maybe_search(
        agent=agent,
        doc_id=doc_id,
        parse_json=parse_json,
        query=step.query,
        intent=step.intent,
        top_k=top_k,
        section_hint=step.section_hint or None,
    )


def _coerce_status(raw: Any) -> str:
    s = str(raw or "unresolved").strip()
    return s if s in _STATUS else "unresolved"


def _log_reply(run_logger: Any, **kwargs: Any) -> None:
    if run_logger is None:
        return
    try:
        run_logger.debate_reply(**kwargs)
    except Exception:
        logger.exception("debate_reply log failed")


async def expert_respond_to_controller(
    *,
    agent: str,
    question: DebateQuestion,
    claim_card: dict[str, Any] | None,
    llm: Any,
    doc_id: str,
    parse_json: Path | str | None,
    run_logger: Any | None = None,
    round_no: int = 1,
    demo_market: bool = False,
) -> ClaimUpdate:
    rules = load_master_rules()
    debate_cfg = rules.get("debate") or {}
    max_search = int(debate_cfg.get("max_new_searches_per_question") or 2)
    top_k = int(debate_cfg.get("hits_per_search") or 4)
    max_tokens = int(debate_cfg.get("debate_max_tokens") or 1024)
    effort = str(debate_cfg.get("debate_reasoning_effort") or "low")

    existing_n = int((claim_card or {}).get("n_evidence") or 0)
    queries_done: list[dict[str, Any]] = []
    hits_all: list[dict[str, Any]] = []

    qtext = question.question or ""
    plan = plan_debate_searches(
        agent=agent,
        question_text=qtext,
        theme=question.theme,
        claim_card=claim_card,
        search_hints=question.search_hints,
        max_searches=max_search,
    )
    need_search = bool(plan.pages) or bool(plan.steps) or existing_n < 2 or any(
        k in qtext for k in ("粉饰", "粉飾", "第一", "領先", "领先")
    )
    if agent == "market" and demo_market:
        need_search = True  # standalone 返回空 hits，禁止伪造

    if need_search and max_search > 0:
        for step in plan.steps[:max_search]:
            if looks_like_instruction(step.query) and step.kind != "page":
                continue
            try:
                raw = await _run_search_step(
                    agent=agent,
                    doc_id=doc_id,
                    parse_json=parse_json,
                    step=step,
                    top_k=top_k,
                )
            except Exception as exc:
                logger.warning("debate search failed: %s", exc)
                raw = {"ok": False, "hits": [], "query": step.query, "n": 0, "error": str(exc)}
            raw_hits = [h for h in (raw.get("hits") or []) if isinstance(h, dict)]
            useful = [
                h
                for h in raw_hits
                if hit_is_useful(h, pages=plan.pages, keywords=plan.keywords)
            ]
            n_hits = len(useful)
            queries_done.append(
                {
                    "query": step.query,
                    "intent": step.intent,
                    "kind": step.kind,
                    "pages": list(step.pages),
                    "n": n_hits,
                    "n_raw": len(raw_hits),
                }
            )
            hits_all.extend(useful)
            if run_logger is not None:
                try:
                    run_logger.debate_search(
                        round=round_no,
                        question_id=question.question_id,
                        target_agent=agent,
                        tool_calls=[
                            {
                                "name": f"search_{agent}_evidence_standalone",
                                "arguments": {
                                    "query": step.query,
                                    "intent": step.intent,
                                    "kind": step.kind,
                                    "pages": list(step.pages),
                                },
                            }
                        ],
                        evidence=[
                            {"page": h.get("page"), "excerpt": h.get("excerpt") or h.get("text") or ""}
                            for h in useful[:4]
                        ],
                        duration_ms=raw.get("duration_ms"),
                        search_hit_count=n_hits,
                    )
                except Exception:
                    logger.exception("debate_search log failed")
            if useful:
                break

    evidence_refs = _hits_to_evidence(hits_all)
    hit_n = len(hits_all)

    if agent == "market" and (demo_market or llm is None or not getattr(llm, "available", False)):
        upd = ClaimUpdate(
            question_id=question.question_id,
            target_agent="market",
            clue_id=question.claim_id,
            status="unresolved",
            confidence=0.3,
            reply=(
                "市場情緒 Agent 為 demo stub，本輪無真实行情寬表，"
                "無法用認購/破發率佐證；检索未命中，confidence 封頂。"
            ),
            remaining_uncertainty="等待市場 Agent 正式接入",
            new_queries=queries_done,
            search_hit_count=hit_n,
            evidence=[],
        )
        _log_reply(
            run_logger,
            round=round_no,
            question_id=question.question_id,
            target_agent="market",
            utterance=upd.reply,
            status=upd.status,
            confidence=upd.confidence,
            new_queries=upd.new_queries,
            evidence=[],
        )
        return upd

    if agent == "finance":
        prompt = FINANCE_DEBATE_REPLY
    elif agent == "legal":
        prompt = LEGAL_DEBATE_REPLY
    else:
        prompt = MARKET_DEBATE_REPLY + "\nquestion_id={question_id}\nclaim_id={claim_id}"
    sys_msg = prompt.format(
        question_id=question.question_id,
        claim_id=question.claim_id or "",
    )
    user = (
        f"【总控质询】{question.question}\n"
        f"【己方 claim 已有证据】\n{plan.claimed_evidence}\n"
        f"【己方 claim 卡片】{claim_card or {}}\n"
        f"【本轮检索 hits 数】{hit_n}\n"
        f"【hits 摘要】{[{'page': e.page, 'excerpt': (e.excerpt or '')[:200]} for e in evidence_refs]}\n"
        "请作答。查不到也必须推理并发言，禁止编造页码或数字。"
        "卡片已写明的金额/页码不得改口成未披露；本轮检索失败时维持探查结论并写明未再命中。"
    )
    out = await llm_json(
        llm,
        [{"role": "system", "content": sys_msg}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        reasoning_effort=effort,
    )
    data = out.get("data") or {}
    clue = data.get("updated_clue") if isinstance(data.get("updated_clue"), dict) else {}
    status = _coerce_status(clue.get("status") or data.get("status") or "unresolved")
    try:
        conf = float(
            clue.get("confidence") if clue.get("confidence") is not None else data.get("confidence") or 0.4
        )
    except (TypeError, ValueError):
        conf = 0.4
    if hit_n == 0 and existing_n < 1:
        conf = min(conf, 0.4)
        if status == "verified":
            status = "unresolved"
    reply = str(data.get("reply") or data.get("response") or "").strip()
    if not reply:
        reply = "未能解析模型作答；检索未命中或证据不足，维持原主张待决。"
        status = "unresolved"
        conf = min(conf, 0.4)
    ev_out = list(evidence_refs)
    for e in data.get("evidence") or []:
        if isinstance(e, dict) and (e.get("excerpt") or e.get("page") is not None):
            try:
                page_i = int(e["page"]) if e.get("page") is not None else None
            except (TypeError, ValueError):
                page_i = None
            ev_out.append(
                EvidenceRef(
                    page=page_i,
                    excerpt=str(e.get("excerpt") or "")[:400],
                    source_type="text",
                )
            )
    extra_q = [q for q in (data.get("new_queries") or []) if isinstance(q, dict)]
    upd = ClaimUpdate(
        question_id=question.question_id,
        target_agent=agent,
        clue_id=str(clue.get("clue_id") or question.claim_id or ""),
        status=status,  # type: ignore[arg-type]
        severity=str(clue.get("severity") or "medium"),
        confidence=conf,
        reply=reply,
        revision_reason=str(clue.get("revision_reason") or ""),
        remaining_uncertainty=str(clue.get("remaining_uncertainty") or ""),
        new_queries=queries_done + extra_q,
        search_hit_count=hit_n,
        evidence=ev_out,
    )
    _log_reply(
        run_logger,
        round=round_no,
        question_id=question.question_id,
        target_agent=agent,
        utterance=upd.reply,
        status=upd.status,
        confidence=upd.confidence,
        duration_ms=out.get("duration_ms"),
        reasoning=out.get("reasoning"),
        tool_calls=[{"name": f"search_{agent}_evidence_standalone", "arguments": q} for q in queries_done],
        evidence=[e.model_dump() for e in upd.evidence],
        new_queries=upd.new_queries,
        usage=out.get("usage"),
        model=out.get("model"),
    )
    return upd
