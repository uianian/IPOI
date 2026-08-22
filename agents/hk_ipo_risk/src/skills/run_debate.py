from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable

from src.config import load_master_rules
from src.llm.master_prompts import (
    MASTER_FOLLOWUP_SYSTEM,
    MASTER_FOLLOWUP_USER,
    MASTER_QUESTIONS_SYSTEM,
)
from src.models.master import ClaimUpdate, DebateQuestion, DebateRoundRecord
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.llm_json import dumps_cards, llm_json
from src.skills.master_cards import find_claim_card

logger = logging.getLogger(__name__)

RespondFn = Callable[..., Awaitable[ClaimUpdate]]


def _parse_questions(raw_list: Any, *, cap: int) -> list[DebateQuestion]:
    out: list[DebateQuestion] = []
    seen: set[str] = set()
    for raw in raw_list or []:
        if not isinstance(raw, dict):
            continue
        qid = str(raw.get("question_id") or f"q{len(out)+1}")
        if qid in seen:
            qid = f"{qid}_{len(out)+1}"
        seen.add(qid)
        target = str(raw.get("target_agent") or "finance").lower()
        if target not in {"finance", "legal", "market"}:
            target = "finance"
        question = str(raw.get("question") or "").strip()
        if not question:
            continue
        required = list(raw.get("required_evidence_types") or [])
        hints = raw.get("search_hints") if isinstance(raw.get("search_hints"), dict) else None
        if target == "market":
            # Enforce the market/prospectus boundary deterministically.
            question = question.replace("招股書或規則層面的證據", "市場字段、證據ID或規則層面的證據")
            question = question.replace("招股书或规则层面的证据", "市场字段、证据ID或规则层面的证据")
            question = question.replace("招股書頁碼", "市場數據來源、字段與截止日")
            question = question.replace("招股书页码", "市场数据来源、字段与截止日")
            required = [x for x in required if x != "page_excerpt"]
            for item in ("market_field", "evidence_id", "as_of_date", "value"):
                if item not in required:
                    required.append(item)
            hints = dict(hints or {})
            hints["pages"] = []
        try:
            out.append(
                DebateQuestion(
                    question_id=qid,
                    target_agent=target,  # type: ignore[arg-type]
                    claim_id=str(raw.get("claim_id") or "") or None,
                    theme=str(raw.get("theme") or ""),
                    question=question,
                    required_evidence_types=required,
                    priority=raw.get("priority") or "medium",
                    search_hints=hints,
                )
            )
        except Exception:
            continue
        if len(out) >= cap:
            break
    return out


def _ensure_real_market_question(
    questions: list[DebateQuestion],
    market_card: dict[str, Any],
    *,
    cap: int,
) -> list[DebateQuestion]:
    """Do not let an active three-expert debate silently omit real market evidence."""
    if any(q.target_agent == "market" for q in questions):
        return questions
    if market_card.get("agent") != "market" or market_card.get("risk_score") is None or market_card.get("demo"):
        return questions
    claims = [c for c in (market_card.get("claims") or []) if isinstance(c, dict)]
    claim_id = str((claims[0] if claims else {}).get("claim_id") or "") or None
    market_q = DebateQuestion(
        question_id="q_market_evidence",
        target_agent="market",
        claim_id=claim_id,
        theme="market_sentiment",
        question=(
            "請解釋原生 risk_score、overall_net_support、deterministic_score 與 LLM 評分之間的口徑及"
            "表面張力，並以不晚於 as_of_date 的上市前市場字段或新聞證據補證首日破發風險結論；"
            "不得使用上市後行情。"
        ),
        required_evidence_types=["market_field", "evidence_id", "as_of_date"],
        priority="high",
        search_hints={
            "pages": [],
            "keywords": ["overall_net_support", "deterministic_score", "risk_score"],
        },
    )
    if len(questions) < cap:
        return [*questions, market_q]
    return [*questions[: max(0, cap - 1)], market_q]


def _round_digest(record: DebateRoundRecord) -> str:
    rows = []
    qmap = {q.question_id: q for q in record.questions}
    for r in record.replies:
        q = qmap.get(r.question_id)
        rows.append(
            {
                "question_id": r.question_id,
                "target_agent": r.target_agent,
                "question": (q.question if q else "")[:180],
                "status": r.status,
                "confidence": r.confidence,
                "reply": (r.reply or "")[:1200],
                "search_hit_count": r.search_hit_count,
                "evidence_pages": [e.page for e in (r.evidence or []) if e.page is not None],
            }
        )
    return json.dumps(rows, ensure_ascii=False)


class RunDebateSkill(BaseSkill):
    skill_name = "master_run_debate"
    version = "0.1.0"
    description = "总控主持质询：本轮打包并行作答，答完再判是否开下一轮（≤3）"

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        p = skill_input.params
        llm = p.get("llm")
        master_logger = p.get("run_logger")
        respond_fn: RespondFn | None = p.get("respond_fn")
        cards = {
            "finance": p.get("finance_cards") or {},
            "legal": p.get("legal_cards") or {},
            "market": p.get("market_cards") or {},
        }
        rules = load_master_rules()
        debate_cfg = rules.get("debate") or {}
        max_rounds = int(p.get("max_rounds") or debate_cfg.get("max_rounds") or 3)
        cap = int(p.get("max_questions_per_round") or debate_cfg.get("max_questions_per_round") or 4)
        q_tokens = int(debate_cfg.get("question_max_tokens") or 800)

        history: list[DebateRoundRecord] = []
        if respond_fn is None:
            return SkillOutput(
                success=True,
                data={"debate_history": [], "skipped": True, "reason": "no_respond_fn"},
                degraded=True,
                degraded_reason="no_respond_fn",
            )

        user_q = (
            f"【冲突研判】{dumps_cards(p.get('conflicts') or [])}\n"
            f"【财务卡片】{dumps_cards(cards['finance'])}\n"
            f"【法务卡片】{dumps_cards(cards['legal'])}\n"
            f"【市场卡片】{dumps_cards(cards['market'])}\n"
            "请一次写出本轮全部质询（打包，不要拆轮）。未点名者不发言。"
        )
        q_out = await llm_json(
            llm,
            [
                {
                    "role": "system",
                    "content": MASTER_QUESTIONS_SYSTEM.format(max_questions=cap),
                },
                {"role": "user", "content": user_q},
            ],
            max_tokens=q_tokens,
        )
        pending = _parse_questions((q_out.get("data") or {}).get("questions"), cap=cap)
        pending = _ensure_real_market_question(pending, cards["market"], cap=cap)
        if master_logger is not None:
            master_logger.master_step(
                event="debate_plan",
                utterance=json.dumps(
                    [q.model_dump() for q in pending], ensure_ascii=False
                ),
                duration_ms=q_out.get("duration_ms"),
                reasoning=q_out.get("reasoning"),
                usage=q_out.get("usage"),
                extra={"ok": q_out.get("ok"), "n_questions": len(pending)},
                model=q_out.get("model"),
            )
        if not pending:
            return SkillOutput(
                success=True,
                data={
                    "debate_history": [],
                    "skipped": True,
                    "reason": "no_questions",
                    "llm_ok": q_out.get("ok"),
                },
                degraded=not q_out.get("ok"),
                degraded_reason=q_out.get("error"),
            )

        round_no = 0
        while pending and round_no < max_rounds:
            round_no += 1
            t0 = time.time()
            questions = pending[:cap]
            for q in questions:
                if master_logger is not None:
                    master_logger.debate_question(
                        round=round_no,
                        question_id=q.question_id,
                        target_agent=q.target_agent,
                        utterance=q.question,
                        claim_id=q.claim_id,
                        theme=q.theme,
                        duration_ms=q_out.get("duration_ms") if round_no == 1 else None,
                        reasoning=q_out.get("reasoning") if round_no == 1 else None,
                        usage=q_out.get("usage") if round_no == 1 else None,
                        model=q_out.get("model") if round_no == 1 else None,
                    )

            async def _one(q: DebateQuestion) -> ClaimUpdate:
                card = find_claim_card(cards.get(q.target_agent), q.claim_id)
                return await respond_fn(q, card, round_no=round_no)

            replies = list(await asyncio.gather(*[_one(q) for q in questions]))
            rec = DebateRoundRecord(
                round=round_no,
                questions=questions,
                replies=replies,
                continue_debate=False,
                duration_ms=int((time.time() - t0) * 1000),
            )
            if master_logger is not None:
                for r in replies:
                    master_logger.debate_reply(
                        round=round_no,
                        question_id=r.question_id,
                        target_agent=r.target_agent,
                        utterance=r.reply,
                        status=r.status,
                        confidence=r.confidence,
                        duration_ms=r.search_hit_count,
                        tool_calls=[{"name": "search_standalone", "arguments": q} for q in r.new_queries],
                        evidence=[e.model_dump() if hasattr(e, "model_dump") else e for e in r.evidence],
                        new_queries=r.new_queries,
                    )
            if round_no >= max_rounds:
                rec.continue_reason = "max_rounds"
                rec.continue_debate = False
                history.append(rec)
                break

            fu = await llm_json(
                llm,
                [
                    {
                        "role": "system",
                        "content": MASTER_FOLLOWUP_SYSTEM.format(max_questions=cap),
                    },
                    {
                        "role": "user",
                        "content": MASTER_FOLLOWUP_USER.format(
                            round=round_no,
                            max_rounds=max_rounds,
                            round_digest=_round_digest(rec),
                        ),
                    },
                ],
                max_tokens=q_tokens,
            )
            data = fu.get("data") or {}
            rec.continue_debate = bool(data.get("continue_debate"))
            rec.continue_reason = str(data.get("reason") or "")
            if master_logger is not None:
                master_logger.master_step(
                    event="debate_followup",
                    utterance=rec.continue_reason,
                    duration_ms=fu.get("duration_ms"),
                    reasoning=fu.get("reasoning"),
                    usage=fu.get("usage"),
                    extra={
                        "continue_debate": rec.continue_debate,
                        "round": round_no,
                    },
                    model=fu.get("model"),
                )
            history.append(rec)
            q_out = fu
            if rec.continue_debate:
                pending = _parse_questions(data.get("questions"), cap=cap)
                if not pending:
                    rec.continue_debate = False
                    rec.continue_reason = rec.continue_reason or "empty_followup_questions"
            else:
                pending = []

        return SkillOutput(
            success=True,
            data={
                "debate_history": [h.model_dump() for h in history],
                "n_rounds": len(history),
            },
        )
