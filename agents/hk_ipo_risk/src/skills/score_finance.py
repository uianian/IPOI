"""规则财务打分（fallback）。

主路径已改为 LLM `analyze_finance`；本模块在无 API key / --finance-rules-only / LLM 失败时使用。
"""
from __future__ import annotations

from typing import Any

from src.config import load_score_rules
from src.models.evidence import EvidenceRef, RiskPoint, ScoreBreakdownItem
from src.skills.extract_financials import evidence_refs_for
from src.skills.gates import _series_values


def score_to_level(score: float, rules: dict[str, Any] | None = None) -> str:
    rules = rules or load_score_rules()
    levels = rules.get("levels") or []
    for item in levels:
        if score < float(item.get("max", 100)):
            return str(item.get("level") or "medium")
    return "very_high"


def _gp_margin_drop(metrics: dict[str, dict[str, float | None]]) -> bool:
    series = _series_values(metrics.get("GP_MARGIN"))
    if len(series) < 2:
        return False
    series = [(y, v) for y, v in series if 0 <= v <= 100]
    if len(series) < 2:
        return False
    prev, cur = series[-2][1], series[-1][1]
    return (prev - cur) > 5.0


def _cfo_persistently_negative(metrics: dict[str, dict[str, float | None]]) -> bool:
    series = _series_values(metrics.get("CFO"))
    if not series:
        return False
    tail = series[-2:] if len(series) >= 2 else series
    return all(v < 0 for _, v in tail)


def _latest_metric_value(series: dict[str, float | None] | None) -> float | None:
    """Prefer latest period (incl. interim) then full-year."""
    from src.skills.gates import _period_values

    periods = _period_values(series)
    if periods:
        return periods[-1][1]
    full = _series_values(series)
    if full:
        return full[-1][1]
    return None


def runway_uncertain(
    metrics: dict[str, dict[str, float | None]],
    gates: dict[str, Any],
    cash_burn: dict[str, Any],
) -> bool:
    """未盈利但无法算出跑道（缺 CFO/烧钱）→ 不得仅以 CONTINUOUS_LOSS 定档。"""
    if gates.get("skip_3_4"):
        return False
    if cash_burn.get("skipped"):
        return False
    months = cash_burn.get("CASH_RUNWAY_MONTHS")
    if months is not None:
        return False
    # 已能算出具体跑道档则不算 uncertain
    unprofitable = bool(
        gates.get("is_unprofitable")
        or gates.get("continuous_net_loss")
        or gates.get("profitability_status") in {"unprofitable", "unknown"}
    )
    if not unprofitable:
        return False
    has_cash = _latest_metric_value(
        metrics.get("CASH_EQ") or metrics.get("END_CASH")
    ) is not None or cash_burn.get("END_CASH") is not None
    has_loss = bool(gates.get("continuous_net_loss") or gates.get("latest_full_year_loss"))
    # 缺 CFO 导致 monthly_burn 为空是主因
    cfo_missing = not _series_values(metrics.get("CFO")) and not (
        cash_burn.get("BURN_RATE_MONTHLY")
    )
    return bool((has_cash or has_loss) and (cfo_missing or months is None))


def cv_pref_material(metrics: dict[str, dict[str, float | None]]) -> bool:
    """CV_PREF>0 且相对总资产≥10% 或相对现金≥50% → 表内优先股/赎回负债压力。"""
    pref = _latest_metric_value(metrics.get("CV_PREF"))
    if pref is None or pref <= 0:
        return False
    assets = _latest_metric_value(metrics.get("TOTAL_ASSETS"))
    cash = _latest_metric_value(
        metrics.get("CASH_EQ") or metrics.get("END_CASH")
    )
    if assets is not None and assets > 0 and (pref / assets) >= 0.10:
        return True
    if cash is not None and cash > 0 and (pref / cash) >= 0.50:
        return True
    return False


def _evidence_from_table_meta(
    extracted: dict[str, Any], field_or_table: str
) -> list[EvidenceRef]:
    meta = extracted.get("table_meta") or {}
    info = meta.get(field_or_table) or {}
    if not isinstance(info, dict):
        return []
    page = info.get("page")
    if page is None:
        return []
    try:
        page_i = int(page)
    except (TypeError, ValueError):
        return []
    st = str(info.get("source_type") or info.get("category") or "table")
    if st not in {"table", "text", "title", "unknown"}:
        st = "table"
    return [
        EvidenceRef(
            page=page_i,
            excerpt=str(info.get("excerpt") or "")[:200],
            source_type=st,  # type: ignore[arg-type]
            field_code=str(info.get("field_code") or field_or_table),
        )
    ]


def _resolve_evidence(
    code: str,
    when: str,
    cash_burn: dict[str, Any],
    extracted: dict[str, Any],
) -> list[EvidenceRef]:
    ev_field = "TBL_IS"
    if "CFO" in code:
        ev_field = "TBL_CF"
    elif "CV_PREF" in code or "SOLVENCY" in code:
        ev_field = "TBL_BS"
    elif "CASH" in code or "BURN" in code or "RUNWAY" in code:
        ev_field = "TBL_BS" if cash_burn.get("END_CASH") is not None else "TBL_CF"
    evid = list(evidence_refs_for(ev_field, extracted))
    if not evid and when in {
        "continuous_net_loss",
        "latest_full_year_loss",
        "gp_margin_drop_gt_5pp",
    }:
        evid = list(evidence_refs_for("TBL_IS", extracted))
    if not evid and when == "cv_pref_material":
        evid = list(evidence_refs_for("TBL_BS", extracted)) or list(
            evidence_refs_for("TBL_BS_COMPANY", extracted)
        )
    if not evid:
        for key in (ev_field, "TBL_IS", "TBL_CF", "TBL_BS", "TBL_BS_COMPANY"):
            evid = _evidence_from_table_meta(extracted, key)
            if evid:
                break
    # 指标字段页码兜底
    if not evid:
        for key in ("NET_LOSS", "CFO", "CASH_EQ", "END_CASH", "CV_PREF"):
            evid = _evidence_from_table_meta(extracted, key)
            if evid:
                break
    return evid


def _metric_note_for_rule(
    when: str,
    code: str,
    metrics: dict[str, dict[str, float | None]],
    cash_burn: dict[str, Any],
    flags: dict[str, Any],
) -> tuple[str, Any]:
    """可读说明 + metric_value。"""
    if when == "continuous_net_loss":
        series = _series_values(metrics.get("NET_LOSS"))
        if series:
            parts = ", ".join(f"{y}={v:,.0f}" for y, v in series[-3:])
            return f"業績記錄期連續虧損（NET_LOSS {parts}）", series[-1][1]
        return "業績記錄期連續虧損", True
    if when == "latest_full_year_loss":
        series = _series_values(metrics.get("NET_LOSS"))
        if series:
            y, v = series[-1]
            return f"最近完整年度虧損（{y}={v:,.0f}）", v
        return "最近完整年度虧損", True
    if when == "cfo_persistently_negative":
        series = _series_values(metrics.get("CFO"))
        if series:
            parts = ", ".join(f"{y}={v:,.0f}" for y, v in series[-3:])
            return f"經營活動現金流持續為負（CFO {parts}）", series[-1][1]
        return "經營活動現金流持續為負", True
    if when == "gp_margin_drop_gt_5pp":
        series = [(y, v) for y, v in _series_values(metrics.get("GP_MARGIN")) if 0 <= v <= 100]
        if len(series) >= 2:
            return (
                f"毛利率降幅超過 5 個百分點（{series[-2][1]:.2f}%→{series[-1][1]:.2f}%）",
                series[-1][1],
            )
        return "毛利率降幅超過 5 個百分點", True
    if when == "runway_lt_12":
        m = cash_burn.get("CASH_RUNWAY_MONTHS")
        return f"未盈利且現金跑道 <12 個月（約 {m} 個月）", m
    if when == "runway_12_24":
        m = cash_burn.get("CASH_RUNWAY_MONTHS")
        return f"未盈利且現金跑道 12–24 個月（約 {m} 個月）", m
    if when == "runway_uncertain":
        end_cash = cash_burn.get("END_CASH")
        return (
            "未盈利但無法測算現金跑道（缺 CFO/燒錢序列）；"
            f"END_CASH={end_cash}；禁止僅以連續虧損定檔，需補證或保守抬升",
            end_cash,
        )
    if when == "burn_yoy_up_gt_30":
        g = cash_burn.get("burn_yoy_growth_full") or cash_burn.get("burn_yoy_growth_interim")
        return f"未盈利且燒錢同比上升超過 30%（growth={g}）", g
    if when == "cv_pref_material":
        pref = _latest_metric_value(metrics.get("CV_PREF"))
        return (
            f"表內可轉換可贖回優先股/贖回負債壓力顯著（CV_PREF≈{pref}）",
            pref,
        )
    return f"触发 {when}", flags.get(when)


def _build_negative_findings(
    metrics: dict[str, dict[str, float | None]],
    gates: dict[str, Any],
    cash_burn: dict[str, Any],
    flags: dict[str, Any],
    extracted: dict[str, Any],
) -> list[dict[str, Any]]:
    """财务分为 0 / 低风险时的阴性发现，避免被误解为「未分析」。"""
    findings: list[dict[str, Any]] = []
    ev_is = evidence_refs_for("TBL_IS", extracted)
    ev_cf = evidence_refs_for("TBL_CF", extracted)

    if not gates.get("is_unprofitable"):
        findings.append({
            "code": "PROFITABLE",
            "description": "业绩记录期盈利（期内利润为正），未触发连续亏损规则",
            "rule_ref": "doc§2.1",
            "evidence": [e.model_dump() for e in ev_is[:1]],
        })
    if gates.get("skip_3_4"):
        findings.append({
            "code": "SKIP_CASH_BURN",
            "description": f"跳过 3.4 现金跑道（原因：{gates.get('skip_3_4_reason') or cash_burn.get('reason')}）",
            "rule_ref": "doc§3.4",
            "evidence": [],
        })
    if not flags.get("cfo_persistently_negative"):
        cfo = _series_values(metrics.get("CFO"))
        if cfo and all(v > 0 for _, v in cfo):
            findings.append({
                "code": "CFO_POSITIVE",
                "description": "经营活动现金流（CFO）业绩记录期均为正",
                "rule_ref": "doc§2.3",
                "evidence": [e.model_dump() for e in ev_cf[:1]],
            })
    gp = _series_values(metrics.get("GP_MARGIN"))
    gp_ok = [(y, v) for y, v in gp if 0 <= v <= 100]
    if len(gp_ok) >= 2 and not flags.get("gp_margin_drop_gt_5pp"):
        findings.append({
            "code": "GP_MARGIN_STABLE",
            "description": (
                f"毛利率相对稳定（{_fmt(gp_ok[0][1])}% → {_fmt(gp_ok[-1][1])}%），"
                "未出现 >5pct 恶化"
            ),
            "rule_ref": "doc§2.1",
            "evidence": [e.model_dump() for e in ev_is[:1]],
        })
    return findings


def _fmt(v: float) -> str:
    return f"{v:.2f}"


def build_rules_summary(
    *,
    risk_score: float,
    risk_level: str,
    flags: dict[str, Any],
    breakdown: list[dict[str, Any]],
    metrics: dict[str, Any],
    cash_burn: dict[str, Any],
    gates: dict[str, Any],
) -> str:
    """结构化规则摘要，禁止「财务指标N项 [rules]」模板。"""
    issuer = str(gates.get("issuer_type") or "")
    parts = [
        f"{'18A/生物科技' if gates.get('is_biotech_18a') or issuer.lower() in {'18a','biotech','18c'} else '發行人'}"
        f"規則打分 {risk_score:.1f}（{risk_level}）。"
    ]
    if breakdown:
        codes = []
        for b in breakdown:
            if not isinstance(b, dict):
                continue
            code = b.get("code")
            delta = b.get("delta")
            note = (b.get("note") or "")[:60]
            if code:
                codes.append(f"{code}+{delta}" + (f"（{note}）" if note else ""))
        if codes:
            parts.append("扣分：" + "；".join(codes[:8]) + "。")
    else:
        parts.append("未觸發規則扣分項。")
    if flags.get("runway_uncertain"):
        parts.append(
            "現金跑道無法測算（缺 CFO/燒錢），已計 RUNWAY_UNCERTAIN，建議補 search_finance_evidence。"
        )
    elif cash_burn.get("CASH_RUNWAY_MONTHS") is not None:
        parts.append(f"現金跑道約 {cash_burn.get('CASH_RUNWAY_MONTHS')} 個月。")
    n_metrics = len([k for k, v in metrics.items() if v not in (None, {}, [])])
    parts.append(f"已抽取指標 {n_metrics} 項。")
    return "".join(parts)


def score_finance(
    metrics: dict[str, dict[str, float | None]],
    gates: dict[str, Any],
    cash_burn: dict[str, Any],
    extracted: dict[str, Any],
) -> dict[str, Any]:
    rules_cfg = load_score_rules()
    fin_rules = (rules_cfg.get("finance") or {}).get("rules") or []

    flags = {
        "continuous_net_loss": bool(gates.get("continuous_net_loss")),
        "latest_full_year_loss": bool(gates.get("latest_full_year_loss")) and bool(gates.get("is_unprofitable")),
        "cfo_persistently_negative": _cfo_persistently_negative(metrics),
        "gp_margin_drop_gt_5pp": _gp_margin_drop(metrics),
        "runway_lt_12": (cash_burn.get("CASH_RUNWAY_MONTHS") or 999) < 12 and not cash_burn.get("skipped"),
        "runway_12_24": 12 <= (cash_burn.get("CASH_RUNWAY_MONTHS") or -1) < 24 and not cash_burn.get("skipped"),
        "burn_yoy_up_gt_30": bool(cash_burn.get("burn_yoy_up_gt_30")) and not cash_burn.get("skipped"),
        "cv_pref_material": cv_pref_material(metrics),
        "runway_uncertain": runway_uncertain(metrics, gates, cash_burn),
    }
    # 已有明确跑道档时不再叠 uncertain
    if flags["runway_lt_12"] or flags["runway_12_24"]:
        flags["runway_uncertain"] = False

    breakdown: list[ScoreBreakdownItem] = []
    risk_points: list[RiskPoint] = []
    total = 0.0

    for rule in fin_rules:
        when = rule.get("when")
        if not when or not flags.get(when):
            continue
        if rule.get("require_gate") == "unprofitable" and gates.get("skip_3_4"):
            continue
        # 连续亏损已覆盖单年亏损，避免双计
        if when == "latest_full_year_loss" and flags.get("continuous_net_loss"):
            continue
        # 明确跑道档与 uncertain 互斥（yaml 顺序上 uncertain 在后，双保险）
        if when == "runway_uncertain" and (
            flags.get("runway_lt_12") or flags.get("runway_12_24")
        ):
            continue
        delta = float(rule.get("delta") or 0)
        code = str(rule.get("code"))
        rule_ref = str(rule.get("rule_ref") or "")
        evid = _resolve_evidence(code, when, cash_burn, extracted)
        # 无证据页仍计分（禁止因证据缺失跳过 runway/CFO），页码尽量从 table_meta 补
        note, metric_value = _metric_note_for_rule(when, code, metrics, cash_burn, flags)
        if not evid:
            note = (note or "") + "（证据页待补）"
        total += delta
        page = next((e.page for e in evid if e.page is not None), None)
        item = ScoreBreakdownItem(
            code=code,
            delta=delta,
            rule_ref=rule_ref,
            evidence=evid,
            note=note,
            metric_value=metric_value,
            evidence_page=page,
        )
        breakdown.append(item)
        level = "high" if delta >= 20 else "medium"
        if code == "RUNWAY_UNCERTAIN":
            level = "high"
        risk_points.append(
            RiskPoint(
                code=code,
                level=level,
                rule_ref=rule_ref,
                value=metric_value if metric_value is not None else flags.get(when),
                description=note,
                evidence=evid,
            )
        )

    total = max(0.0, min(100.0, total))
    negative_findings = _build_negative_findings(metrics, gates, cash_burn, flags, extracted)
    level = score_to_level(total, rules_cfg)
    bd_dump = [b.model_dump() for b in breakdown]
    summary = build_rules_summary(
        risk_score=total,
        risk_level=level,
        flags=flags,
        breakdown=bd_dump,
        metrics=metrics,
        cash_burn=cash_burn,
        gates=gates,
    )
    return {
        "risk_score": total,
        "risk_level": level,
        "score_breakdown": bd_dump,
        "risk_points": [r.model_dump() for r in risk_points],
        "flags": flags,
        "negative_findings": negative_findings,
        "summary": summary,
        "reasoning": summary,
    }
