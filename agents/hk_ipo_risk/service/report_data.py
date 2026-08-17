"""把总控 + 三专家结果映射为前端 ReportData（v3.4 §8.1）。"""

from __future__ import annotations

from typing import Any


_LEVEL_LABEL = {
    "HIGH": "高风险",
    "MEDIUM": "关注",
    "LOW": "低风险",
    "high": "高风险",
    "medium": "关注",
    "low": "低风险",
}


def _http_level(raw: Any) -> str:
    s = str(raw or "").upper()
    if s in {"HIGH", "MEDIUM", "LOW"}:
        return s
    return "MEDIUM"


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _agent_score(block: dict[str, Any] | None) -> float:
    if not isinstance(block, dict):
        return 0.0
    return _f(block.get("risk_score"))


def build_report_data(
    merged: dict[str, Any],
    *,
    overall_score: int,
    risk_level: str,
    debate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    finance = merged.get("finance") or {}
    legal = merged.get("legal") or {}
    market = merged.get("market") if isinstance(merged.get("market"), dict) else {}
    master = merged.get("master") if isinstance(merged.get("master"), dict) else {}
    judgment = master.get("judgment") or {}
    level = _http_level(risk_level or judgment.get("risk_level_http") or judgment.get("level"))
    fin_s = _agent_score(finance)
    leg_s = _agent_score(legal)
    mkt_s = _agent_score(market) if market else 0.0

    factors_in = master.get("risk_factors") or []
    risk_factors: list[dict[str, Any]] = []
    for i, f in enumerate(factors_in):
        if not isinstance(f, dict):
            continue
        evs = f.get("evidence") or []
        page = None
        excerpt = ""
        if evs and isinstance(evs[0], dict):
            page = evs[0].get("page")
            excerpt = evs[0].get("excerpt") or ""
        risk_factors.append(
            {
                "id": f.get("title") or f"rf-{i+1}",
                "title": f.get("title") or "",
                "sourceAgent": f.get("source_agent") or "",
                "reason": f.get("reason") or "",
                "weight": f.get("weight"),
                "evidencePage": page,
                "evidenceExcerpt": excerpt,
            }
        )

    windows = master.get("predicted_windows") or {}
    risk_timeline = [
        {"window": "day1", "label": "上市首日", "risk": windows.get("ipo_day_break_risk") or "medium"},
        {"window": "d5", "label": "5 日", "risk": windows.get("d5_significant_downside_risk") or "medium"},
        {"window": "d20", "label": "20 日", "risk": windows.get("d20_downside_risk") or "medium"},
        {"window": "d60", "label": "60 日", "risk": windows.get("d60_downside_risk") or "medium"},
    ]

    dimensions = [
        {"id": "legal", "name": "法务合规", "score": round(leg_s, 1)},
        {"id": "financial", "name": "财务穿透", "score": round(fin_s, 1)},
        {"id": "market", "name": "市场情绪", "score": round(mkt_s, 1)},
        {
            "id": "embellishment",
            "name": "文本粉饰",
            "score": _f((master.get("embellishment") or {}).get("score")),
        },
    ]

    debate_msgs = (debate or {}).get("messages") or []
    highlights = [
        {
            "agentId": m.get("agentId"),
            "type": m.get("type"),
            "content": (m.get("content") or "")[:280],
            "category": m.get("category"),
        }
        for m in debate_msgs[:12]
        if isinstance(m, dict)
    ]

    exec_md = str(
        (master.get("report_sections") or {}).get("composite")
        or judgment.get("verdict_reasoning")
        or ""
    )
    if master.get("degraded"):
        exec_md = (exec_md + f"\n\n（降级：{master.get('degraded_reason') or 'degraded'}）").strip()
    if judgment.get("gate_warning"):
        exec_md = (exec_md + f"\n\ngate_warning：{judgment.get('gate_warning')}").strip()

    return {
        "overallScore": int(overall_score),
        "riskLevel": level,
        "riskLabel": _LEVEL_LABEL.get(level, "关注"),
        "dimensions": dimensions,
        "riskFactors": risk_factors,
        "comparableIPOs": [],
        "riskTimeline": risk_timeline,
        "radarData": [
            {"axis": "法务", "value": round(leg_s, 1)},
            {"axis": "财务", "value": round(fin_s, 1)},
            {"axis": "市场", "value": round(mkt_s, 1)},
        ],
        "executiveSummary": exec_md,
        "debateHighlights": highlights,
        "agentScores": {
            "legal": round(leg_s, 1),
            "financial": round(fin_s, 1),
            "market": round(mkt_s, 1),
        },
        "degraded": bool(master.get("degraded")),
        "gateWarning": judgment.get("gate_warning"),
        "referenceFundamentalScore": merged.get("reference_fundamental_score"),
    }
