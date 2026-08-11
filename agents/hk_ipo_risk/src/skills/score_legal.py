from __future__ import annotations

from typing import Any

from src.config import load_score_rules
from src.models.evidence import EvidenceRef, RiskPoint, ScoreBreakdownItem
from src.skills.score_finance import score_to_level


def _ev_list(feature: dict[str, Any]) -> list[EvidenceRef]:
    out: list[EvidenceRef] = []
    for e in feature.get("evidence") or []:
        if isinstance(e, EvidenceRef):
            out.append(e)
        elif isinstance(e, dict):
            out.append(EvidenceRef(**{k: e[k] for k in e if k in EvidenceRef.model_fields}))
    return out


def score_legal(features: dict[str, Any], gates: dict[str, Any] | None = None) -> dict[str, Any]:
    gates = gates or {}
    rules_cfg = load_score_rules()
    legal_cfg = rules_cfg.get("legal") or {}
    rules = legal_cfg.get("rules") or []
    disclosure_base = legal_cfg.get("disclosure_base") or {}

    f31 = features.get("3.1") or {}
    f32 = features.get("3.2") or {}
    f33 = features.get("3.3") or {}
    f35 = features.get("3.5") or {}
    f36 = features.get("3.6") or {}

    flags = {
        "redemption_high": bool(f31.get("redemption_high")),
        "redemption_medium": bool(f31.get("redemption_medium")),
        "related_party_ratio_gt_30": bool(f32.get("related_party_ratio_gt_30")),
        "related_party_rising": bool(f32.get("related_party_rising")),
        "concentration_high": bool(f33.get("concentration_high")),
        "pipeline_high": bool(f35.get("pipeline_high")),
        "valuation_inversion": bool(f36.get("valuation_inversion")),
    }

    breakdown: list[ScoreBreakdownItem] = []
    risk_points: list[RiskPoint] = []
    total = 0.0
    applied_codes: set[str] = set()

    def add(code: str, delta: float, rule_ref: str, evid: list[EvidenceRef], note: str | None = None) -> None:
        nonlocal total
        if not evid:
            return
        if code in applied_codes:
            return
        applied_codes.add(code)
        total += delta
        breakdown.append(
            ScoreBreakdownItem(code=code, delta=delta, rule_ref=rule_ref, evidence=evid, note=note)
        )
        risk_points.append(
            RiskPoint(
                code=code,
                level="high" if delta >= 20 else "medium",
                rule_ref=rule_ref,
                description=note or code,
                evidence=evid,
            )
        )

    for rule in rules:
        when = rule.get("when")
        if not when or not flags.get(when):
            continue
        if rule.get("require_gate") == "biotech" and gates.get("skip_3_5"):
            continue
        evid_src = f31 if "redemption" in when else f32 if "related" in when else f33 if "concentration" in when else f35 if "pipeline" in when else f36
        add(str(rule["code"]), float(rule["delta"]), str(rule["rule_ref"]), _ev_list(evid_src))

    # disclosure base if no high/medium rule fired for that theme
    if f31.get("exists") and "REDEMPTION_HIGH" not in applied_codes and "REDEMPTION_MEDIUM" not in applied_codes:
        add(
            "REDEMPTION_DISCLOSURE",
            float(disclosure_base.get("exists_redemption") or 18),
            "doc§3.1",
            _ev_list(f31),
            note="存在赎回/优先股相关披露",
        )
    if f32.get("exists") and "RELATED_PARTY_HIGH" not in applied_codes:
        add(
            "RELATED_PARTY_DISCLOSURE",
            float(disclosure_base.get("exists_related_party") or 15),
            "doc§3.2",
            _ev_list(f32),
            note="存在关联交易披露",
        )
    if f33.get("exists") and "CONCENTRATION_HIGH" not in applied_codes:
        add(
            "CONCENTRATION_DISCLOSURE",
            float(disclosure_base.get("exists_concentration_disclosure") or 12),
            "doc§3.3",
            _ev_list(f33),
            note="存在客户/供应商集中度披露",
        )
    if (
        f35.get("exists")
        and not f35.get("skipped")
        and not gates.get("skip_3_5")
        and "PIPELINE_HIGH" not in applied_codes
    ):
        add(
            "PIPELINE_DISCLOSURE",
            float(disclosure_base.get("exists_pipeline") or 12),
            "doc§3.5",
            _ev_list(f35),
            note="存在核心产品/管线进度披露",
        )

    total = round(max(0.0, min(100.0, total)), 1)
    return {
        "risk_score": total,
        "risk_level": score_to_level(total, rules_cfg),
        "score_breakdown": [b.model_dump() for b in breakdown],
        "risk_points": [r.model_dump() for r in risk_points],
        "flags": flags,
    }
