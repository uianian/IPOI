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
    }

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
        delta = float(rule.get("delta") or 0)
        code = str(rule.get("code"))
        rule_ref = str(rule.get("rule_ref") or "")
        ev_field = "TBL_IS"
        if "CFO" in code:
            ev_field = "TBL_CF"
        elif "CV_PREF" in code or "SOLVENCY" in code:
            ev_field = "TBL_BS"
        elif "CASH" in code or "BURN" in code or "RUNWAY" in code:
            ev_field = "TBL_BS" if cash_burn.get("END_CASH") is not None else "TBL_CF"
        if code.startswith("CASH") or code.startswith("BURN"):
            ev_field = "TBL_BS" if cash_burn.get("END_CASH") is not None else "TBL_CF"
        evid = evidence_refs_for(ev_field, extracted)
        if not evid and when in {"continuous_net_loss", "latest_full_year_loss", "gp_margin_drop_gt_5pp"}:
            evid = evidence_refs_for("TBL_IS", extracted)
        if not evid and when == "cv_pref_material":
            evid = evidence_refs_for("TBL_BS", extracted) or evidence_refs_for(
                "TBL_BS_COMPANY", extracted
            )
        if not evid:
            continue
        total += delta
        item = ScoreBreakdownItem(code=code, delta=delta, rule_ref=rule_ref, evidence=evid)
        if when == "cv_pref_material":
            pref = _latest_metric_value(metrics.get("CV_PREF"))
            item.note = (
                f"CV_PREF≈{pref}；表内优先股/赎回负债压力（cross_ref=legal:REDEMPTION）"
            )
        breakdown.append(item)
        level = "high" if delta >= 20 else "medium"
        risk_points.append(
            RiskPoint(
                code=code,
                level=level,
                rule_ref=rule_ref,
                value=flags.get(when),
                description=f"触发 {when}",
                evidence=evid,
            )
        )

    total = max(0.0, min(100.0, total))
    negative_findings = _build_negative_findings(metrics, gates, cash_burn, flags, extracted)
    return {
        "risk_score": total,
        "risk_level": score_to_level(total, rules_cfg),
        "score_breakdown": [b.model_dump() for b in breakdown],
        "risk_points": [r.model_dump() for r in risk_points],
        "flags": flags,
        "negative_findings": negative_findings,
    }
