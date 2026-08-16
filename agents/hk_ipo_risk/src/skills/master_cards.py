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
        "n_evidence": len(refs),
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


def reference_fundamental(finance_score: float, legal_score: float) -> float:
    rules = load_master_rules()
    w = rules.get("reference_weights") or {}
    legal_w = float(w.get("legal") or 0.45)
    fin_w = float(w.get("finance") or 0.55)
    return round(min(100.0, float(legal_score) * legal_w + float(finance_score) * fin_w), 2)


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


def checklist_text() -> str:
    rules = load_master_rules()
    ch5 = rules.get("chapter5_checklist") or {}
    lines = ["高风险触发（任一）："]
    for item in ch5.get("high") or []:
        lines.append(f"- {item.get('code')}: {item.get('label')}")
    lines.append("中风险触发（任一）：")
    for item in ch5.get("medium") or []:
        lines.append(f"- {item.get('code')}: {item.get('label')}")
    lines.append((rules.get("confidence_rubric") or "").strip())
    return "\n".join(lines)
