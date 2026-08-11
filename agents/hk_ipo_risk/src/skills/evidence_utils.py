"""法务/财务共用：命中去重、observation 截断、queries_used 规范化。

纯规则字符串切片，不用 LLM 摘要。完整证据仍留在 state / dossier。
"""

from __future__ import annotations

from typing import Any


def hit_pages(hits: list[dict[str, Any]]) -> set[int]:
    pages: set[int] = set()
    for h in hits:
        p = h.get("page") or h.get("page_number") or h.get("evidence_page")
        try:
            if p is not None:
                pages.add(int(p))
        except (TypeError, ValueError):
            continue
    return pages


def dedupe_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同页同摘录前缀去重。"""
    seen: set[tuple[Any, str]] = set()
    out: list[dict[str, Any]] = []
    for h in hits:
        excerpt = h.get("excerpt") or h.get("content") or ""
        key = (h.get("page"), str(excerpt)[:80])
        if key in seen or not str(excerpt).strip():
            continue
        seen.add(key)
        item = dict(h)
        item.setdefault("excerpt", excerpt)
        out.append(item)
    return out


def compact_hits(
    hits: list[dict[str, Any]],
    *,
    excerpt_chars: int = 120,
) -> list[dict[str, Any]]:
    """ReAct observation 用短摘录（规则截断）。"""
    compact: list[dict[str, Any]] = []
    for h in hits:
        compact.append(
            {
                "page": h.get("page"),
                "section_id": h.get("section_id"),
                "source_type": h.get("source_type"),
                "score": h.get("score"),
                "matched_terms": h.get("matched_terms") or [],
                "excerpt": str(h.get("excerpt") or h.get("content") or "")[:excerpt_chars],
            }
        )
    return compact


def normalize_query_record(
    *,
    tool: str,
    intent: str | None = None,
    query: str | None = None,
    section_hint: Any = None,
    hits: int | list | None = None,
    pages: list[int] | set[int] | None = None,
    skill: str | None = None,
) -> dict[str, Any]:
    """统一 retrieval_queries / queries_used 结构。"""
    n_hits = hits if isinstance(hits, int) else len(hits or [])
    page_list = sorted(pages) if pages is not None else []
    rec: dict[str, Any] = {
        "tool": tool,
        "intent": intent,
        "query": query,
        "section_hint": section_hint,
        "hits": n_hits,
        "pages": page_list,
    }
    if skill:
        rec["skill"] = skill
    return rec
