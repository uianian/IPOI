from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.llm.prompts import FINANCE_ANALYZE, FINANCE_SYSTEM
from src.models.evidence import EvidenceRef, RiskPoint, ScoreBreakdownItem
from src.skills.score_finance import score_to_level

logger = logging.getLogger(__name__)


def _derive_ratios(metrics: dict[str, dict[str, float | None]]) -> dict[str, Any]:
    """轻量派生：资产负债率等，供 LLM 参考（不另开 Skill）。"""
    out: dict[str, Any] = {}
    ta = metrics.get("TOTAL_ASSETS") or {}
    tl = metrics.get("TOTAL_LIAB") or {}
    leverage: dict[str, float | None] = {}
    for y, assets in ta.items():
        liab = tl.get(y)
        if assets and liab is not None and abs(float(assets)) > 1e-9:
            leverage[str(y)] = round(float(liab) / float(assets) * 100.0, 2)
        else:
            leverage[str(y)] = None
    if leverage:
        out["DEBT_TO_ASSET_PCT"] = leverage
    return out


def _evidence_blob(extracted: dict[str, Any], max_chars: int = 6000) -> str:
    parts: list[str] = []
    meta = extracted.get("table_meta") or {}
    for code, info in meta.items():
        page = info.get("page")
        excerpt = (info.get("excerpt") or "")[:400]
        parts.append(f"[{code} p{page}] {excerpt}")
    evidence = extracted.get("evidence") or {}
    for code, items in evidence.items():
        if code in meta:
            continue
        for it in (items or [])[:1]:
            parts.append(f"[{code} p{it.get('page')}] {(it.get('excerpt') or '')[:300]}")
    text = "\n".join(parts)
    return text[:max_chars] if text else "（无表证据摘录）"


def _normalize_breakdown(items: list[Any], extracted: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        try:
            delta = float(it.get("delta") or 0)
        except (TypeError, ValueError):
            delta = 0.0
        page = it.get("evidence_page")
        evid: list[EvidenceRef] = []
        if page is not None:
            evid.append(
                EvidenceRef(
                    page=int(page) if str(page).isdigit() else None,
                    excerpt=str(it.get("note") or "")[:200],
                    source_type="table",
                    field_code=str(it.get("code") or ""),
                )
            )
        item = ScoreBreakdownItem(
            code=str(it.get("code") or "LLM_ITEM"),
            delta=delta,
            rule_ref=str(it.get("rule_ref") or "llm"),
            evidence=evid,
            note=str(it.get("note") or "") or None,
            metric_value=it.get("metric_value"),
            evidence_page=int(page) if page is not None and str(page).isdigit() else None,
        )
        out.append(item.model_dump())
    return out


def _normalize_risk_points(items: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        level = str(it.get("level") or "medium").lower().strip()
        if level in {"critical", "very_high", "severe"}:
            level = "high"
        elif level in {"moderate", "mid"}:
            level = "medium"
        elif level not in {"high", "medium", "low"}:
            level = "medium"
        page = it.get("evidence_page")
        evid = []
        if page is not None:
            evid.append(
                EvidenceRef(
                    page=int(page) if str(page).isdigit() else None,
                    excerpt=str(it.get("description") or "")[:200],
                    source_type="text",
                    field_code=str(it.get("code") or ""),
                )
            )
        rp = RiskPoint(
            code=str(it.get("code") or "LLM_RISK"),
            level=level,  # type: ignore[arg-type]
            rule_ref=str(it.get("rule_ref") or "llm"),
            value=it.get("metric_value"),
            description=str(it.get("description") or ""),
            evidence=evid,
        )
        out.append(rp.model_dump())
    return out


def compose_from_llm(
    data: dict[str, Any],
    *,
    extracted: dict[str, Any],
    model_think: str | None = None,
    reasoning_details: Any = None,
) -> dict[str, Any]:
    """把 LLM JSON 规范成 Agent 打分结构。"""
    breakdown = _normalize_breakdown(data.get("score_breakdown") or [], extracted)
    total = sum(float(b.get("delta") or 0) for b in breakdown)
    if data.get("risk_score") is not None:
        try:
            total = float(data["risk_score"])
        except (TypeError, ValueError):
            pass
    total = max(0.0, min(100.0, total))
    # 等级始终由最终分数映射，避免 LLM 自称 low 而托底分已升至 medium
    level = score_to_level(total)

    return {
        "scoring_mode": data.get("scoring_mode") or "llm",
        "risk_score": total,
        "risk_level": level,
        "score_breakdown": breakdown,
        "risk_points": _normalize_risk_points(data.get("risk_points") or []),
        "negative_findings": data.get("negative_findings") or [],
        "dimensions": data.get("dimensions") or [],
        "reasoning": data.get("reasoning") or "",
        "summary": data.get("summary") or "",
        "llm_analysis": data,
        "model_think": model_think,
        "reasoning_details": reasoning_details or [],
        "think_status": "ok" if model_think else "reasoning_missing",
    }


async def analyze_finance_llm(
    llm: Any,
    *,
    doc_id: str,
    issuer_type: str,
    metrics: dict[str, Any],
    gates: dict[str, Any],
    cash_burn: dict[str, Any],
    extracted: dict[str, Any],
    run_logger: Any | None = None,
) -> dict[str, Any]:
    """单次 LLM 四维财务分析。失败抛异常，由上层 fallback。"""
    derived = _derive_ratios(
        {k: v for k, v in metrics.items() if isinstance(v, dict) and k != "cash_burn"}
    )
    metrics_for_prompt = {
        k: v
        for k, v in metrics.items()
        if k != "cash_burn" and isinstance(v, dict)
    }
    if derived:
        metrics_for_prompt = {**metrics_for_prompt, **derived}

    gates_slim = {
        k: gates[k]
        for k in gates
        if k
        in {
            "is_unprofitable",
            "continuous_net_loss",
            "latest_full_year_loss",
            "skip_3_4",
            "skip_3_4_reason",
            "skip_2_4",
            "issuer_type",
            "is_biotech_18a",
        }
    }

    user = FINANCE_ANALYZE.format(
        doc_id=doc_id,
        issuer_type=issuer_type,
        gates_json=json.dumps(gates_slim, ensure_ascii=False),
        cash_burn_json=json.dumps(cash_burn, ensure_ascii=False, default=str),
        metrics_json=json.dumps(metrics_for_prompt, ensure_ascii=False, default=str),
        evidence_text=_evidence_blob(extracted),
    )
    messages = [
        {"role": "system", "content": FINANCE_SYSTEM},
        {"role": "user", "content": user},
    ]

    t0 = time.time()
    resp = await llm.chat_json(
        messages,
        enable_reasoning=True,
        reasoning_effort="low",
        max_tokens=2048,
        reasoning_max_tokens=256,
    )
    duration_ms = int((time.time() - t0) * 1000)

    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    model_think = resp.get("reasoning")
    reasoning_details = resp.get("reasoning_details") or []

    if run_logger is not None:
        run_logger.llm_turn(
            model=getattr(llm, "settings", {}).get("chat_model") if hasattr(llm, "settings") else None,
            prompt_chars=len(user) + len(FINANCE_SYSTEM),
            content=resp.get("content"),
            reasoning=model_think,
            reasoning_details=reasoning_details,
            structured_reasoning=(data or {}).get("reasoning"),
            duration_ms=duration_ms,
            usage=resp.get("usage"),
            status="ok" if data else "empty_json",
        )

    if not data:
        raise RuntimeError("LLM returned empty JSON for finance analysis")

    composed = compose_from_llm(
        data,
        extracted=extracted,
        model_think=model_think,
        reasoning_details=reasoning_details,
    )
    composed["derived_ratios"] = derived
    composed["llm_duration_ms"] = duration_ms
    composed["llm_usage"] = resp.get("usage")
    return composed
