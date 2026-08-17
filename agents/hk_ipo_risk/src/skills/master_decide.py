from __future__ import annotations

import json
from typing import Any

from src.config import load_master_rules
from src.llm.master_prompts import (
    MASTER_DECIDE_SYSTEM,
    MASTER_DECIDE_USER,
    MASTER_REVISE_SYSTEM,
    MASTER_REVISE_USER,
)
from src.models.evidence import EvidenceRef
from src.models.master import CompositeJudgment, PredictedWindows, RiskFactorItem
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.llm_json import dumps_cards, json_payload_usable, llm_json
from src.skills.master_cards import checklist_text, high_risk_codes_present

_DECIDE_JSON_KEYS = ("overall_score", "level")


def compact_debate_digest(history: Any, *, reply_chars: int = 280) -> str:
    """终裁只用短问答，禁止把 evidence HTML / 全文质询塞进 prompt。"""
    rows: list[dict[str, Any]] = []
    for rnd in history or []:
        if not isinstance(rnd, dict):
            continue
        qmap = {
            str(q.get("question_id")): q
            for q in (rnd.get("questions") or [])
            if isinstance(q, dict)
        }
        qa: list[dict[str, Any]] = []
        for r in rnd.get("replies") or []:
            if not isinstance(r, dict):
                continue
            q = qmap.get(str(r.get("question_id") or "")) or {}
            pages: list[Any] = []
            for e in r.get("evidence") or []:
                if isinstance(e, dict) and e.get("page") is not None and e.get("page") not in pages:
                    pages.append(e.get("page"))
            qa.append(
                {
                    "id": r.get("question_id"),
                    "agent": r.get("target_agent"),
                    "theme": q.get("theme"),
                    "q": str(q.get("question") or "")[:180],
                    "status": r.get("status"),
                    "conf": r.get("confidence"),
                    "hits": r.get("search_hit_count"),
                    "pages": pages[:8],
                    "a": str(r.get("reply") or "")[:reply_chars],
                }
            )
        rows.append(
            {
                "round": rnd.get("round"),
                "continue": rnd.get("continue_debate"),
                "qa": qa,
            }
        )
    return json.dumps(rows, ensure_ascii=False) if rows else "[]"


def _sections_from_judgment(judgment: CompositeJudgment, debate_digest: str) -> dict[str, Any]:
    return {
        "composite": judgment.verdict_reasoning,
        "embellishment": "",
        "debate_summary": debate_digest[:800],
        "confidence_note": judgment.score_explanation,
    }


def _level_to_http(level: str) -> str:
    m = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
    return m.get(str(level).lower(), "LOW")


def _parse_judgment(data: dict[str, Any]) -> tuple[CompositeJudgment, list[RiskFactorItem], PredictedWindows, dict[str, Any]]:
    try:
        score = float(data.get("overall_score") if data.get("overall_score") is not None else 0)
    except (TypeError, ValueError):
        score = 0.0
    # 模型偶发按 0–1 输出；终裁标尺是 0–100。
    if 0.0 < score <= 1.0:
        score *= 100.0
    score = max(0.0, min(100.0, score))
    level = str(data.get("level") or "low").lower()
    if level not in {"high", "medium", "low"}:
        level = "low"
    conf = str(data.get("confidence") or "medium").lower()
    if conf not in {"high", "medium", "low"}:
        conf = "medium"
    judgment = CompositeJudgment(
        overall_score=score,
        level=level,  # type: ignore[arg-type]
        risk_level_http=_level_to_http(level),
        confidence=conf,  # type: ignore[arg-type]
        triggered_gates=[str(x) for x in (data.get("triggered_gates") or [])],
        verdict_reasoning=str(data.get("verdict_reasoning") or ""),
        score_explanation=str(data.get("score_explanation") or ""),
    )
    factors: list[RiskFactorItem] = []
    for raw in data.get("risk_factors") or []:
        if not isinstance(raw, dict):
            continue
        ev = []
        if raw.get("excerpt") or raw.get("page") is not None:
            try:
                page = int(raw["page"]) if raw.get("page") is not None else None
            except (TypeError, ValueError):
                page = None
            ev = [EvidenceRef(page=page, excerpt=str(raw.get("excerpt") or ""), source_type="text")]
        factors.append(
            RiskFactorItem(
                title=str(raw.get("title") or ""),
                source_agent=str(raw.get("source_agent") or ""),
                reason=str(raw.get("reason") or ""),
                evidence=ev,
            )
        )
    pw_raw = data.get("predicted_windows") if isinstance(data.get("predicted_windows"), dict) else {}
    windows = PredictedWindows(
        ipo_day_break_risk=str(pw_raw.get("ipo_day_break_risk") or "medium"),
        d5_significant_downside_risk=str(pw_raw.get("d5_significant_downside_risk") or "medium"),
        d20_downside_risk=str(pw_raw.get("d20_downside_risk") or "medium"),
        d60_downside_risk=str(pw_raw.get("d60_downside_risk") or "medium"),
    )
    sections = data.get("report_sections") if isinstance(data.get("report_sections"), dict) else {}
    return judgment, factors, windows, sections


def _degraded_from_cards(
    *,
    reference_score: float,
    high_codes: list[str],
    embellish_score: int,
) -> tuple[CompositeJudgment, list[RiskFactorItem], PredictedWindows, dict[str, Any]]:
    """无 LLM 时：对照分 + 第五章清单脚本。禁止在有 LLM 时走这条。"""
    level = "low"
    gates: list[str] = []
    if high_codes:
        level = "high"
        gates = list(high_codes)
    elif embellish_score >= 7:
        level = "medium"
        gates = ["EMBELLISHMENT_HIGH"]
    elif reference_score >= 60:
        level = "high"
    elif reference_score >= 30:
        level = "medium"
    judgment = CompositeJudgment(
        overall_score=float(reference_score),
        level=level,  # type: ignore[arg-type]
        risk_level_http=_level_to_http(level),
        confidence="low",
        triggered_gates=gates,
        verdict_reasoning="規則降級：LLM 不可用，採用對照加權分與第五章清單。",
        score_explanation="degraded_rules_fallback",
    )
    return judgment, [], PredictedWindows(), {"composite": judgment.verdict_reasoning}


class MasterDecideSkill(BaseSkill):
    skill_name = "master_decide"
    version = "0.1.0"
    description = "总控终裁：证据权衡、综合分与等级；漏用高风险清单则再修订一次"

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        p = skill_input.params
        llm = p.get("llm")
        logger_ = p.get("run_logger")
        rules = load_master_rules()
        debate_cfg = rules.get("debate") or {}
        max_tokens = int(debate_cfg.get("decide_max_tokens") or 4096)
        reasoning_max_tokens = int(debate_cfg.get("decide_reasoning_max_tokens") or 512)
        finance = p.get("finance") or {}
        legal = p.get("legal") or {}
        market = p.get("market") or {}
        ref = p.get("reference_score")
        high_codes = high_risk_codes_present(finance, legal)
        emb = p.get("embellishment") or {}
        debate_digest = compact_debate_digest(p.get("debate_history") or [])
        user = MASTER_DECIDE_USER.format(
            reference_score=ref,
            checklist=checklist_text(),
            finance_score=(finance.get("risk_score") if isinstance(finance, dict) else None)
            or (p.get("finance_cards") or {}).get("risk_score"),
            finance_level=(finance.get("risk_level") if isinstance(finance, dict) else None)
            or (p.get("finance_cards") or {}).get("risk_level"),
            finance_cards=dumps_cards(p.get("finance_cards") or {}),
            legal_score=(legal.get("risk_score") if isinstance(legal, dict) else None)
            or (p.get("legal_cards") or {}).get("risk_score"),
            legal_level=(legal.get("risk_level") if isinstance(legal, dict) else None)
            or (p.get("legal_cards") or {}).get("risk_level"),
            legal_cards=dumps_cards(p.get("legal_cards") or {}),
            market_score=(market.get("risk_score") if isinstance(market, dict) else None) or 50,
            market_level=(market.get("risk_level") if isinstance(market, dict) else None) or "medium",
            market_demo=bool((market.get("features") or {}).get("demo")) if isinstance(market, dict) else True,
            market_cards=dumps_cards(p.get("market_cards") or {}),
            embellish_score=emb.get("score"),
            embellish_reason=emb.get("reason") or "",
            debate_digest=debate_digest,
        )
        out = await llm_json(
            llm,
            [
                {"role": "system", "content": MASTER_DECIDE_SYSTEM},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            reasoning_max_tokens=reasoning_max_tokens,
            required_keys=_DECIDE_JSON_KEYS,
        )
        llm_calls = 1 + int(out.get("retries") or 0)
        usable = json_payload_usable(out.get("data") or {}, required_keys=_DECIDE_JSON_KEYS) and bool(out.get("ok"))
        degraded = not usable
        if degraded:
            judgment, factors, windows, sections = _degraded_from_cards(
                reference_score=float(ref or 0),
                high_codes=high_codes,
                embellish_score=int(emb.get("score") or 0),
            )
            sections = _sections_from_judgment(judgment, debate_digest)
            if logger_ is not None:
                logger_.master_step(
                    event="fusion",
                    utterance=judgment.verdict_reasoning,
                    duration_ms=out.get("duration_ms"),
                    reasoning=out.get("reasoning"),
                    usage=out.get("usage"),
                    extra={
                        "degraded": True,
                        "high_codes": high_codes,
                        "retries": out.get("retries"),
                        "finish_reason": out.get("finish_reason"),
                        "error": out.get("error"),
                    },
                    model=out.get("model"),
                )
            return SkillOutput(
                success=True,
                data={
                    "judgment": judgment.model_dump(),
                    "risk_factors": [f.model_dump() for f in factors],
                    "predicted_windows": windows.model_dump(),
                    "report_sections": sections,
                    "llm_calls": llm_calls,
                    "high_risk_codes": high_codes,
                    "retries": out.get("retries") or 0,
                },
                degraded=True,
                degraded_reason=out.get("error") or "empty_json",
            )

        judgment, factors, windows, sections = _parse_judgment(out.get("data") or {})
        gate_warning = None
        if high_codes and judgment.level == "low":
            gate_warning = (
                "卡片含高风险码 " + ",".join(high_codes) + f" 但终裁 level={judgment.level}"
            )
            prev = {
                "overall_score": judgment.overall_score,
                "level": judgment.level,
                "confidence": judgment.confidence,
                "triggered_gates": judgment.triggered_gates,
                "verdict_reasoning": judgment.verdict_reasoning,
                "score_explanation": judgment.score_explanation,
            }
            rev = await llm_json(
                llm,
                [
                    {"role": "system", "content": MASTER_REVISE_SYSTEM},
                    {
                        "role": "user",
                        "content": MASTER_REVISE_USER.format(
                            codes=",".join(high_codes),
                            prev_level=judgment.level,
                            prev_json=json.dumps(prev, ensure_ascii=False),
                        ),
                    },
                ],
                max_tokens=max_tokens,
                reasoning_max_tokens=reasoning_max_tokens,
                required_keys=_DECIDE_JSON_KEYS,
            )
            llm_calls += 1 + int(rev.get("retries") or 0)
            if json_payload_usable(rev.get("data") or {}, required_keys=_DECIDE_JSON_KEYS) and rev.get("ok"):
                judgment, factors, windows, sections = _parse_judgment(rev.get("data") or {})
                judgment.revised = True
                out = rev
            # 禁止 Python 直接改 riskLevel；保留总控（修订后）输出
            judgment.gate_warning = gate_warning

        if not (isinstance(sections, dict) and (sections.get("composite") or sections.get("debate_summary"))):
            sections = {**_sections_from_judgment(judgment, debate_digest), **(sections or {})}

        if logger_ is not None:
            logger_.master_step(
                event="fusion",
                utterance=judgment.verdict_reasoning,
                duration_ms=out.get("duration_ms"),
                reasoning=out.get("reasoning"),
                usage=out.get("usage"),
                extra={
                    "level": judgment.level,
                    "overall_score": judgment.overall_score,
                    "gate_warning": gate_warning,
                    "revised": judgment.revised,
                    "llm_calls": llm_calls,
                    "high_risk_codes": high_codes,
                },
                model=out.get("model"),
            )
        return SkillOutput(
            success=True,
            data={
                "judgment": judgment.model_dump(),
                "risk_factors": [f.model_dump() for f in factors],
                "predicted_windows": windows.model_dump(),
                "report_sections": sections,
                "llm_calls": llm_calls,
                "high_risk_codes": high_codes,
                "decide_user": user,
            },
            degraded=False,
        )
