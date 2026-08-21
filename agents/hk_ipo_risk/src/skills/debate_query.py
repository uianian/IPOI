"""辩论补证：从质询/卡片抽出页码与短关键词，禁止把整段质询丢进检索器。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.config import load_master_rules

_PAGE_RE = re.compile(
    r"(?:第\s*)(\d{1,4})\s*(?:頁|页)|(?:頁|页)\s*[.:：]?\s*(\d{1,4})|(?:(?<![A-Za-z])[pP]\s*)(\d{1,4})",
)
_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:百萬|百万|億|亿)")
_DATE_RE = re.compile(r"20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")
_INSTRUCTION_MARKERS = (
    "總監",
    "总监",
    "並列出",
    "并列出",
    "完整明細",
    "請提供",
    "请提供",
    "請確認",
    "请确认",
    "請法務",
    "请法务",
    "請財務",
    "请财务",
)


@dataclass
class DebateSearchStep:
    query: str
    pages: list[int] = field(default_factory=list)
    intent: str = "business_context"
    section_hint: list[str] = field(default_factory=list)
    kind: str = "keyword"  # page | keyword


@dataclass
class DebateSearchPlan:
    pages: list[int] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    steps: list[DebateSearchStep] = field(default_factory=list)
    claimed_evidence: str = ""


def looks_like_instruction(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if len(t) > 40:
        return True
    if t.startswith(("請", "请")):
        return True
    return any(m in t for m in _INSTRUCTION_MARKERS)


def extract_pages(*texts: str, max_pages: int = 4) -> list[int]:
    found: list[int] = []
    for text in texts:
        for m in _PAGE_RE.finditer(text or ""):
            raw = m.group(1) or m.group(2) or m.group(3)
            try:
                page = int(raw)
            except (TypeError, ValueError):
                continue
            if 1 <= page <= 9999 and page not in found:
                found.append(page)
            if len(found) >= max_pages:
                return found
    return found


def extract_amounts(text: str) -> list[str]:
    out: list[str] = []
    for m in _AMOUNT_RE.finditer(text or ""):
        token = m.group(0).replace(" ", "")
        num = m.group(1)
        for item in (token, num):
            if item and item not in out:
                out.append(item)
    return out


def extract_dates(text: str) -> list[str]:
    out: list[str] = []
    for m in _DATE_RE.finditer(text or ""):
        token = re.sub(r"\s+", "", m.group(0))
        if token not in out:
            out.append(token)
    return out


def format_claimed_evidence(claim_card: dict[str, Any] | None) -> str:
    card = claim_card or {}
    lines: list[str] = []
    if card.get("code"):
        lines.append(f"code={card.get('code')}")
    if card.get("statement"):
        lines.append(str(card.get("statement") or "")[:220])
    for ex in card.get("excerpts") or []:
        if not isinstance(ex, dict):
            continue
        page = ex.get("page")
        excerpt = str(ex.get("excerpt") or "")[:160]
        if page is None and not excerpt:
            continue
        lines.append(f"页{page if page is not None else '—'}: {excerpt}")
    return "\n".join(lines) if lines else "（无）"


def hit_is_useful(
    hit: dict[str, Any],
    *,
    pages: list[int],
    keywords: list[str],
) -> bool:
    if not isinstance(hit, dict):
        return False
    page = hit.get("page")
    try:
        page_i = int(page) if page is not None else None
    except (TypeError, ValueError):
        page_i = None
    if pages and page_i in pages:
        return True
    matched = hit.get("matched_terms") or []
    if matched:
        return True
    excerpt = str(hit.get("excerpt") or hit.get("text") or "")
    blob = excerpt.lower()
    for kw in keywords:
        k = str(kw or "").strip()
        if k and k.lower() in blob:
            return True
    return False


def _theme_cfg(theme: str, search_cfg: dict[str, Any]) -> dict[str, Any]:
    themes = search_cfg.get("themes") or {}
    raw = themes.get(theme) or {}
    return raw if isinstance(raw, dict) else {}


def _code_keywords(code: str, search_cfg: dict[str, Any]) -> list[str]:
    codes = search_cfg.get("codes") or {}
    raw = codes.get(str(code or "").upper()) or []
    return [str(x).strip() for x in raw if str(x).strip()]


def _agent_keywords(agent: str, theme_cfg: dict[str, Any]) -> list[str]:
    key = "finance_keywords" if agent == "finance" else "legal_keywords"
    if agent == "market":
        key = "market_keywords"
    raw = theme_cfg.get(key) or []
    return [str(x).strip() for x in raw if str(x).strip()]


def _short_query(parts: list[str], max_chars: int) -> str:
    out: list[str] = []
    n = 0
    for part in parts:
        p = str(part or "").strip()
        if not p or looks_like_instruction(p):
            continue
        extra = len(p) + (1 if out else 0)
        if n + extra > max_chars:
            break
        out.append(p)
        n += extra
    return " ".join(out)


def plan_debate_searches(
    *,
    agent: str,
    question_text: str,
    theme: str = "",
    claim_card: dict[str, Any] | None = None,
    search_hints: dict[str, Any] | None = None,
    max_searches: int = 2,
) -> DebateSearchPlan:
    rules = load_master_rules()
    search_cfg = (rules.get("debate") or {}).get("debate_search") or {}
    max_pages = int(search_cfg.get("max_pages") or 4)
    max_chars = int(search_cfg.get("query_max_chars") or 32)
    card = claim_card or {}
    hints = search_hints if isinstance(search_hints, dict) else {}

    pages = extract_pages(question_text or "", max_pages=max_pages)
    excerpt_pages: list[Any] = []
    for ex in card.get("excerpts") or []:
        if isinstance(ex, dict) and ex.get("page") is not None:
            excerpt_pages.append(ex.get("page"))
    for raw in list(hints.get("pages") or []) + excerpt_pages:
        try:
            page = int(raw)
        except (TypeError, ValueError):
            continue
        if 1 <= page <= 9999 and page not in pages:
            pages.append(page)
        if len(pages) >= max_pages:
            break

    theme_cfg = _theme_cfg(theme, search_cfg)
    keywords: list[str] = []
    for src in (
        list(hints.get("keywords") or []),
        extract_amounts(question_text or ""),
        _code_keywords(str(card.get("code") or ""), search_cfg),
        _agent_keywords(agent, theme_cfg),
        extract_dates(question_text or ""),
    ):
        for kw in src:
            k = str(kw or "").strip()
            if not k or looks_like_instruction(k) or k in keywords:
                continue
            keywords.append(k)
    for q in card.get("retrieval_queries") or []:
        token = str(q.get("query") if isinstance(q, dict) else q or "").strip()
        if token and not looks_like_instruction(token) and token not in keywords:
            keywords.append(token)

    if agent == "finance":
        intent = str(theme_cfg.get("finance_intent") or "business_context")
    elif agent == "legal":
        intent = str(theme_cfg.get("legal_intent") or "business_context")
    else:
        intent = "business_context"
    section_hint = [str(x) for x in (theme_cfg.get("section_hint") or []) if str(x).strip()]

    steps: list[DebateSearchStep] = []
    if pages:
        steps.append(
            DebateSearchStep(
                query=_short_query(keywords[:3], max_chars) or " ".join(keywords[:2]),
                pages=list(pages),
                intent=intent,
                section_hint=list(section_hint),
                kind="page",
            )
        )
    primary = _short_query(keywords[:3], max_chars)
    used = set(primary.split())
    rest = [k for k in keywords if k not in used] or keywords[3:]
    secondary = _short_query(rest, max_chars)
    for q in (primary, secondary):
        if not q:
            continue
        if any(s.kind == "keyword" and s.query == q for s in steps):
            continue
        steps.append(
            DebateSearchStep(
                query=q,
                pages=[],
                intent=intent,
                section_hint=list(section_hint),
                kind="keyword",
            )
        )
        if len(steps) >= max(1, int(max_searches)):
            break
    steps = [s for s in steps if s.kind == "page" or (s.query and not looks_like_instruction(s.query))]
    steps = steps[: max(1, int(max_searches))]
    # Market debate has no prospectus page anchors; always keep at least one
    # local keyword search so expert_respond can probe dated market evidence.
    if agent == "market" and not steps:
        fallback = _short_query(keywords[:3], max_chars) or _short_query(
            [str(question_text or "").strip()],
            max_chars,
        )
        if fallback and not looks_like_instruction(fallback):
            steps = [
                DebateSearchStep(
                    query=fallback,
                    pages=[],
                    intent=intent,
                    section_hint=list(section_hint),
                    kind="keyword",
                )
            ]
            if fallback not in keywords:
                keywords = list(keywords) + [fallback]
    return DebateSearchPlan(
        pages=pages,
        keywords=keywords,
        steps=steps,
        claimed_evidence=format_claimed_evidence(card),
    )
