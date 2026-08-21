"""把总控 + 三专家结果映射为前端 ReportData（v3.4 §8.1）。"""

from __future__ import annotations

from typing import Any

from src.skills.embellishment_reporting import embellishment_enabled, embellishment_report_data


_LEVEL_LABEL = {
    "HIGH": "高风险",
    "MEDIUM": "关注",
    "LOW": "低风险",
    "high": "高风险",
    "medium": "关注",
    "low": "低风险",
}

_WINDOW_PREDICTED_FIELD = {
    "D1": "ipo_day_break_risk",
    "D5": "d5_significant_downside_risk",
    "D20": "d20_downside_risk",
    "D60": "d60_downside_risk",
}

_WINDOW_DEFAULT_TEXT = {
    "D1": ("上市首日破发风险中等", "仅有标签级预测，未生成结构化走势文本", "波动风险中等"),
    "D5": ("上市后5个交易日显著下跌风险中等", "仅有标签级预测，未生成结构化走势文本", "波动风险中等"),
    "D20": ("上市后20个交易日下行风险中等", "仅有标签级预测，未生成结构化走势文本", "波动风险中等"),
    "D60": ("上市后60个交易日下行风险中等", "仅有标签级预测，未生成结构化走势文本", "波动风险中等"),
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


def _pct_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _price_path_forecast_items(master: dict[str, Any], windows: dict[str, Any]) -> list[dict[str, Any]]:
    by_window: dict[str, dict[str, Any]] = {}
    for item in master.get("price_path_forecast") or []:
        if not isinstance(item, dict):
            continue
        window = str(item.get("window") or "").upper()
        if window in _WINDOW_PREDICTED_FIELD:
            by_window[window] = item

    out: list[dict[str, Any]] = []
    for window, field in _WINDOW_PREDICTED_FIELD.items():
        item = by_window.get(window) or {}
        direction, pattern, volatility = _WINDOW_DEFAULT_TEXT[window]
        out.append(
            {
                "window": window,
                "riskLabel": item.get("risk_label") or item.get("riskLabel") or windows.get(field) or "medium",
                "expectedDirection": item.get("expected_direction") or item.get("expectedDirection") or direction,
                "expectedPattern": item.get("expected_pattern") or item.get("expectedPattern") or pattern,
                "volatilityView": item.get("volatility_view") or item.get("volatilityView") or volatility,
                "keyDrivers": item.get("key_drivers") or item.get("keyDrivers") or [],
                "confidence": item.get("confidence") or "medium",
            }
        )
    return out


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
    include_embellishment = embellishment_enabled(master)
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
    price_path_forecast = _price_path_forecast_items(master, windows)
    post = master.get("post_listing") if isinstance(master.get("post_listing"), dict) else {}
    post_validation = {
        "status": post.get("status") or "not_available",
        "source": post.get("source") or "",
        "summary": post.get("summary") or "",
        "businessValueScore": _pct_or_none(post.get("business_value_score")),
        "weightedHitScore": _pct_or_none(post.get("weighted_hit_score")),
        "d5PriorityHit": post.get("d5_priority_hit"),
        "forecastAlignmentSummary": post.get("forecast_alignment_summary") or "",
        "weights": post.get("weights") or {},
        "checkpoints": [
            {
                "window": c.get("window"),
                "predictionLabel": c.get("prediction_label"),
                "predictionText": c.get("prediction_text"),
                "actualSeverity": c.get("actual_severity"),
                "hit": c.get("hit"),
                "alignment": c.get("alignment"),
                "observationDate": c.get("observation_date"),
                "belowIssuePrice": c.get("below_issue_price"),
                "cumulativeReturnFromOpen": _pct_or_none(c.get("cumulative_return_from_open")),
                "issuePriceReturn": _pct_or_none(c.get("issue_price_return")),
                "maxDrawdownFromOpen": _pct_or_none(c.get("max_drawdown_from_open")),
                "realizedRiskScore": _pct_or_none(c.get("realized_risk_score")),
                "note": c.get("note") or "",
            }
            for c in (post.get("checkpoints") or [])
            if isinstance(c, dict)
        ],
        "limitations": post.get("limitations") or [],
    }

    dimensions = [
        {"id": "legal", "name": "法务合规", "score": round(leg_s, 1)},
        {"id": "financial", "name": "财务穿透", "score": round(fin_s, 1)},
        {"id": "market", "name": "市场情绪", "score": round(mkt_s, 1)},
    ]
    if include_embellishment:
        dimensions.append(
            {
                "id": "embellishment",
                "name": "文本粉饰",
                "score": _f((master.get("embellishment") or {}).get("score")),
            }
        )

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

    result = {
        "overallScore": int(overall_score),
        "riskLevel": level,
        "riskLabel": _LEVEL_LABEL.get(level, "关注"),
        "dimensions": dimensions,
        "riskFactors": risk_factors,
        "comparableIPOs": [],
        "riskTimeline": risk_timeline,
        "pricePathForecast": price_path_forecast,
        "postListingValidation": post_validation,
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
    if include_embellishment:
        result["embellishmentAnalysis"] = embellishment_report_data(master.get("embellishment"))
    return result
