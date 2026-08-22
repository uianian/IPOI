from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import load_master_rules
from src.models.debate import DebateClaim, DebateDossier, load_dossier


THEME_CODE_HINTS: list[tuple[str, str]] = [
    ("redemption", "CV_PREF,REDEMPTION,RIGHTS_CLEANUP"),
    ("cash_runway", "CASH_RUNWAY,BURN_YOY,RUNWAY"),
    ("concentration", "CONCENTRATION,TOP1,TOP5,CUSTOMER,SUPPLIER"),
    ("related_party", "RELATED_PARTY"),
    ("valuation", "VALUATION"),
    ("franchise", "FRANCHISE"),
    ("supply_chain", "SUPPLY"),
    ("pipeline", "PIPELINE,IP_"),
    ("embellishment", "EMBELLISH"),
]


def theme_hint_for_code(code: str) -> str:
    c = (code or "").upper()
    for theme, needles in THEME_CODE_HINTS:
        for n in needles.split(","):
            if n and n in c:
                return theme
    return "other"


def _trunc(text: str, n: int) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def claim_to_card(claim: DebateClaim | dict[str, Any], *, excerpt_max: int = 200) -> dict[str, Any]:
    if isinstance(claim, DebateClaim):
        d = claim.model_dump()
    else:
        d = dict(claim)
    refs = d.get("evidence_refs") or []
    evidence_ids = [str(x) for x in (d.get("evidence_ids") or []) if str(x).strip()]
    excerpts = []
    for r in refs[:2]:
        if not isinstance(r, dict):
            continue
        excerpts.append(
            {
                "page": r.get("page"),
                "excerpt": _trunc(str(r.get("excerpt") or ""), excerpt_max),
                "source_type": r.get("source_type") or "unknown",
            }
        )
    code = str(d.get("code") or "")
    return {
        "claim_id": d.get("claim_id"),
        "agent": d.get("agent"),
        "code": code,
        "level": d.get("level"),
        "confidence": d.get("confidence"),
        "statement": _trunc(str(d.get("statement") or ""), 220),
        "theme_hint": theme_hint_for_code(code),
        "excerpts": excerpts,
        # Market claims are backed by structured evidence IDs rather than PDF
        # pages. Counting only evidence_refs made a fully audited market score
        # look like an evidence-free claim to the controller.
        "evidence_ids": evidence_ids[:24],
        "n_evidence": len(refs) + len([x for x in evidence_ids if x not in {
            str((r or {}).get("field_code") or "") for r in refs if isinstance(r, dict)
        }]),
        "retrieval_queries": (d.get("retrieval_queries") or [])[:2],
    }


def dossier_to_cards(dossier: DebateDossier | dict[str, Any] | None, *, excerpt_max: int = 200) -> dict[str, Any]:
    if dossier is None:
        return {"agent": None, "risk_score": 0, "risk_level": "", "summary": "", "claims": []}
    if isinstance(dossier, dict):
        try:
            dossier = DebateDossier(**dossier)
        except Exception:
            return {
                "agent": dossier.get("agent"),
                "risk_score": dossier.get("risk_score"),
                "risk_level": dossier.get("risk_level"),
                "summary": _trunc(str(dossier.get("summary") or ""), 280),
                "claims": [claim_to_card(c, excerpt_max=excerpt_max) for c in (dossier.get("claims") or [])[:12]],
            }
    return {
        "agent": dossier.agent,
        "risk_score": dossier.risk_score,
        "risk_level": dossier.risk_level,
        "summary": _trunc(dossier.summary or "", 280),
        "claims": [claim_to_card(c, excerpt_max=excerpt_max) for c in (dossier.claims or [])[:12]],
    }


def load_dossier_optional(path: str | None) -> DebateDossier | None:
    if not path:
        return None
    try:
        return load_dossier(path)
    except Exception:
        return None


def agent_result_dossier_path(agent_result: dict[str, Any] | None) -> str | None:
    if not agent_result:
        return None
    feats = agent_result.get("features") or {}
    trace = agent_result.get("trace") or {}
    return feats.get("debate_dossier_path") or trace.get("debate_dossier_path")


def reference_weights() -> dict[str, float]:
    rules = load_master_rules()
    w = rules.get("reference_weights") or {}
    return {
        "legal": float(w.get("legal") if w.get("legal") is not None else 0.55),
        "finance": float(w.get("finance") if w.get("finance") is not None else 0.45),
        "fundamental": float(w.get("fundamental") if w.get("fundamental") is not None else 0.65),
        "market": float(w.get("market") if w.get("market") is not None else 0.35),
    }


def market_reference_score(market: dict[str, Any] | None) -> tuple[float | None, dict[str, Any]]:
    """Return the market Agent's audited 0-100 break-risk score for reference.

    Net support describes direction rather than risk magnitude. It is retained
    in metadata for qualitative judgment, but never replaces ``risk_score`` in
    the controller's reference formula.
    """
    if not market:
        return None, {"source": "missing_market"}
    features = market.get("features") if isinstance(market.get("features"), dict) else {}
    if features.get("demo"):
        return None, {"source": "demo_market"}
    sentiment = features.get("sentiment_analysis") if isinstance(features.get("sentiment_analysis"), dict) else {}
    raw_support = sentiment.get("overall_net_support")
    try:
        net_support = float(raw_support)
    except (TypeError, ValueError):
        net_support = None
    try:
        score = float(market.get("risk_score"))
    except (TypeError, ValueError):
        return None, {"source": "missing_market_score"}
    if net_support is not None:
        if abs(net_support) > 1.0:
            net_support = net_support / 100.0
        net_support = max(-1.0, min(1.0, net_support))
    return max(0.0, min(100.0, score)), {
        "source": "market_risk_score",
        "overall_net_support": net_support,
        "net_support_scale": "-100%..+100%",
        "note": "risk_score enters the reference formula; net support is qualitative context only.",
    }


def reference_fundamental(
    finance_score: float,
    legal_score: float,
    market_score: float | None = None,
) -> float:
    w = reference_weights()
    fundamental = min(
        100.0,
        float(legal_score) * w["legal"] + float(finance_score) * w["finance"],
    )
    if market_score is None:
        return round(fundamental, 2)
    combined = fundamental * w["fundamental"] + float(market_score) * w["market"]
    return round(min(100.0, combined), 2)


def reference_score_note(*, has_market: bool, skip_master: bool = False) -> str:
    w = reference_weights()
    base = f"legal*{w['legal']} + finance*{w['finance']}"
    if has_market:
        text = (
            f"reference_fundamental_score = ({base})*{w['fundamental']} + market_risk_score*{w['market']} 为对照分；"
            "正式等级以总控终裁为准"
        )
    else:
        text = (
            f"reference_fundamental_score = {base} 为对照分（无市场结果，未计入市场分）；"
            "正式等级以总控终裁为准"
        )
    if skip_master:
        text = (
            f"reference_fundamental_score = "
            + (f"({base})*{w['fundamental']} + market_risk_score*{w['market']}" if has_market else base)
            + "；--skip-master，总控未运行"
        )
    return text


def reference_formula_label(*, has_market: bool) -> str:
    w = reference_weights()
    base = f"legal×{w['legal']} + finance×{w['finance']}"
    if has_market:
        return f"({base})×{w['fundamental']} + market_risk_score×{w['market']}"
    return base


def high_risk_codes_present(finance: dict[str, Any], legal: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for src in (finance, legal):
        for b in src.get("score_breakdown") or []:
            if isinstance(b, dict) and b.get("code"):
                codes.append(str(b["code"]).upper())
        for p in src.get("risk_points") or []:
            if isinstance(p, dict) and p.get("code"):
                codes.append(str(p["code"]).upper())
    uniq = []
    for c in codes:
        if c not in uniq:
            uniq.append(c)
    high_needles = (
        "CASH_RUNWAY_LT_12",
        "REDEMPTION_HIGH",
        "CONCENTRATION_HIGH",
        "VALUATION_INVERSION",
    )
    found = []
    blob = " ".join(uniq)
    for n in high_needles:
        if n in blob or any(n in u for u in uniq):
            found.append(n)
    return found


def first_pages_text(
    parse_json: Path | str | None,
    *,
    n_pages: int = 5,
    page_char_cap: int = 1200,
) -> str:
    """压缩招股书前 N 页原文，供粉饰 Prompt（禁止编造页码）。"""
    if not parse_json:
        return ""
    path = Path(parse_json)
    if not path.is_file():
        return ""
    import json

    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""
    pages: list[dict[str, Any]] = []
    if isinstance(data, list):
        pages = [p for p in data if isinstance(p, dict)]
    elif isinstance(data, dict):
        raw = data.get("pages") or data.get("content") or []
        if isinstance(raw, list):
            pages = [p for p in raw if isinstance(p, dict)]
    blocks: list[str] = []
    for p in pages:
        try:
            page_no = int(p.get("page") or p.get("page_number") or 0)
        except (TypeError, ValueError):
            page_no = 0
        if page_no <= 0:
            page_no = len(blocks) + 1
        if page_no > n_pages and len(blocks) >= n_pages:
            continue
        if page_no > n_pages:
            continue
        parts: list[str] = []
        for el in p.get("elements") or p.get("items") or []:
            if isinstance(el, dict):
                t = str(el.get("text") or el.get("content") or el.get("html") or "")
                if t.strip():
                    parts.append(t.strip())
        if not parts:
            blob = str(p.get("text") or p.get("content") or "")
            if blob.strip():
                parts.append(blob.strip())
        text = _trunc(" ".join(parts), page_char_cap)
        if text:
            blocks.append(f"[第{page_no}页] {text}")
        if len(blocks) >= n_pages:
            break
    return "\n".join(blocks)


def find_claim_card(cards: dict[str, Any] | None, claim_id: str | None) -> dict[str, Any] | None:
    claims = (cards or {}).get("claims") or []
    if claim_id:
        for c in claims:
            if isinstance(c, dict) and str(c.get("claim_id")) == str(claim_id):
                return c
    return claims[0] if claims and isinstance(claims[0], dict) else None


def checklist_text(*, exclude_codes: set[str] | None = None) -> str:
    rules = load_master_rules()
    excluded = {str(code).upper() for code in (exclude_codes or set())}
    ch5 = rules.get("chapter5_checklist") or {}
    lines = ["高风险触发（任一）："]
    for item in ch5.get("high") or []:
        if str(item.get("code") or "").upper() not in excluded:
            lines.append(f"- {item.get('code')}: {item.get('label')}")
    lines.append("中风险触发（任一）：")
    for item in ch5.get("medium") or []:
        if str(item.get("code") or "").upper() not in excluded:
            lines.append(f"- {item.get('code')}: {item.get('label')}")
    lines.append((rules.get("confidence_rubric") or "").strip())
    return "\n".join(lines)
