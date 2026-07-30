"""Evidence pack expansion + table role tagging for IPO prospectus retrieval.

Policies (agreed):
- Expand: find table OR finish same page; stop at next title; no fill-n page turn.
- table_caption is unreliable — do not use for naming/role.
- table_role: summary | appendix | discussion | other (from headers / cues).
- Row-label channel: match line items inside category=table HTML/text.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.models.prospectus import DocumentChunk

_SKIP_CATS = frozenset({"header", "footer"})
_EXPAND_CATS = frozenset({"text", "table", "table_footnote"})

# Role priority for financial extraction (higher = better as final source)
ROLE_PRIORITY = {
    "appendix": 3,
    "summary": 2,
    "discussion": 1,
    "other": 0,
}

ROLE_SCORE_BONUS = {
    "appendix": 0.06,
    "summary": 0.035,
    "discussion": 0.015,
    "other": 0.0,
}

_CONTINUATION_RE = re.compile(r"[（(]\s*續\s*[)）]|[（(]\s*续\s*[)）]|（续）|\(continued\)", re.I)


@dataclass
class PageRoleMap:
    """page → table_role inferred from headers / section cues."""

    roles: dict[int, str] = field(default_factory=dict)
    appendix_range: tuple[int, int] | None = None
    summary_pages: list[int] = field(default_factory=list)
    discussion_range: tuple[int, int] | None = None

    def role_of(self, page: int) -> str:
        return self.roles.get(page, "other")


@dataclass
class ExpandResult:
    anchor: DocumentChunk
    members: list[DocumentChunk]
    stop_reason: str
    found_table: DocumentChunk | None = None

    @property
    def primary(self) -> DocumentChunk:
        return self.found_table or self.anchor


def _cat(chunk: DocumentChunk) -> str:
    return str((chunk.metadata or {}).get("category") or chunk.chunk_type or "text")


def _elem_index(chunk: DocumentChunk) -> int:
    meta = chunk.metadata or {}
    if "elem_index" in meta:
        return int(meta["elem_index"])
    return int(chunk.paragraph_index or 0)


def _norm_header(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def build_page_role_map(chunks: Iterable[DocumentChunk]) -> PageRoleMap:
    """Infer summary / discussion / appendix page roles from indexed chunks."""
    headers: dict[int, list[str]] = defaultdict(list)
    titles: dict[int, list[str]] = defaultdict(list)
    texts: dict[int, list[str]] = defaultdict(list)
    pages: set[int] = set()

    for c in chunks:
        page = int(c.page_number)
        pages.add(page)
        cat = _cat(c)
        content = c.content or ""
        if cat == "header":
            headers[page].append(content)
        elif cat == "title":
            titles[page].append(content)
        elif cat == "text":
            texts[page].append(content[:200])

    roles: dict[int, str] = {}
    appendix_pages: list[int] = []
    summary_pages: list[int] = []
    discussion_pages: list[int] = []

    for page in sorted(pages):
        h = _norm_header("".join(headers.get(page, [])))
        title_blob = "".join(titles.get(page, []))
        text_blob = "".join(texts.get(page, []))

        # Appendix I (accountant report) wins over other markers
        if "附錄一" in h or "附录一" in h:
            roles[page] = "appendix"
            appendix_pages.append(page)
            continue

        if "財務資料" in h or "财务资料" in h:
            # exclude unaudited pro forma appendix headers if any slip through
            if "備考" in h or "备考" in h:
                roles[page] = "other"
            else:
                roles[page] = "discussion"
                discussion_pages.append(page)
            continue

        if (
            "歷史財務資料概要" in title_blob
            or "历史财务资料概要" in title_blob
            or h in ("概要",)
            or ("概要" in h and page < 80)
        ):
            roles[page] = "summary"
            summary_pages.append(page)
            continue

        if ("下表" in text_blob or "下表載列" in text_blob) and "概要" in text_blob:
            roles[page] = "summary"
            summary_pages.append(page)
            continue

        roles[page] = "other"

    appendix_range = None
    if appendix_pages:
        appendix_range = (min(appendix_pages), max(appendix_pages))
    discussion_range = None
    if discussion_pages:
        discussion_range = (min(discussion_pages), max(discussion_pages))

    return PageRoleMap(
        roles=roles,
        appendix_range=appendix_range,
        summary_pages=sorted(set(summary_pages)),
        discussion_range=discussion_range,
    )


def build_page_index(
    chunks: list[DocumentChunk],
) -> dict[int, list[DocumentChunk]]:
    """page → chunks sorted by elem_index (skip empty)."""
    by_page: dict[int, list[DocumentChunk]] = defaultdict(list)
    for c in chunks:
        by_page[int(c.page_number)].append(c)
    for page in by_page:
        by_page[page].sort(key=_elem_index)
    return dict(by_page)


def expand_anchor(
    anchor: DocumentChunk,
    page_index: dict[int, list[DocumentChunk]],
    *,
    allow_continuation: bool = True,
) -> ExpandResult:
    """Same-page expand: collect text/table until table found or next title / page end.

    Does NOT turn pages to fill a quota. Optional single-page continuation only when
    the current page ends mid-table and the next page starts with （續） / table.
    """
    cat = _cat(anchor)
    page = int(anchor.page_number)
    page_chunks = page_index.get(page) or []

    if cat == "table":
        members = [anchor]
        # include immediate footnotes after this table until next title/table
        start = None
        for i, c in enumerate(page_chunks):
            if c.chunk_id == anchor.chunk_id:
                start = i
                break
        if start is not None:
            for c in page_chunks[start + 1 :]:
                ccat = _cat(c)
                if ccat in _SKIP_CATS:
                    continue
                if ccat == "title":
                    break
                if ccat == "table":
                    break
                if ccat == "table_footnote":
                    members.append(c)
                elif ccat == "text":
                    break
        return ExpandResult(
            anchor=anchor,
            members=members,
            stop_reason="already_table",
            found_table=anchor,
        )

    # Locate anchor position
    start_idx = 0
    for i, c in enumerate(page_chunks):
        if c.chunk_id == anchor.chunk_id:
            start_idx = i + 1
            break

    members: list[DocumentChunk] = []
    found_table: DocumentChunk | None = None
    stop_reason = "same_page_exhausted"

    for c in page_chunks[start_idx:]:
        ccat = _cat(c)
        if ccat in _SKIP_CATS:
            continue
        if ccat == "title":
            stop_reason = "next_title"
            break
        if ccat not in _EXPAND_CATS:
            continue
        members.append(c)
        if ccat == "table":
            found_table = c
            stop_reason = "found_table"
            break

    # Continuation: only if we ended the page without a table, last member
    # suggests continuation, OR we found a table that may continue (skip — we already have table).
    if (
        allow_continuation
        and found_table is None
        and stop_reason == "same_page_exhausted"
        and members
    ):
        last = members[-1]
        last_text = last.content or ""
        if _CONTINUATION_RE.search(last_text) or _cat(last) == "table_footnote":
            next_page = page_index.get(page + 1) or []
            for c in next_page:
                ccat = _cat(c)
                if ccat in _SKIP_CATS:
                    continue
                if ccat == "title":
                    break
                if ccat == "table":
                    members.append(c)
                    found_table = c
                    stop_reason = "found_table_continuation"
                    break
                if ccat == "text":
                    if _CONTINUATION_RE.search(c.content or ""):
                        members.append(c)
                        continue
                    break

    if found_table is None and not members:
        stop_reason = "narrative_only" if cat in ("title", "text") else stop_reason

    if found_table is None and members and all(_cat(m) == "text" for m in members):
        if cat == "title":
            stop_reason = "narrative_only"

    return ExpandResult(
        anchor=anchor,
        members=members,
        stop_reason=stop_reason,
        found_table=found_table,
    )


def table_has_row_label(content: str, label: str) -> bool:
    """True if label appears as a table cell / row name (not merely substring noise)."""
    if not content or not label:
        return False
    # HTML cell exact-ish
    pat = re.compile(
        rf"<td[^>]*>\s*{re.escape(label)}\s*</td>",
        re.IGNORECASE,
    )
    if pat.search(content):
        return True
    # Soft: cell with label then optional note markers
    pat2 = re.compile(
        rf"<td[^>]*>\s*{re.escape(label)}\s*[（(0-9注註\*]*\s*</td>",
        re.IGNORECASE,
    )
    if pat2.search(content):
        return True
    # Plain-text row start
    if re.search(rf"(?:^|\n)\s*{re.escape(label)}\s*(?:\t|\s{{2,}}|$)", content):
        return True
    return False


def row_label_search(
    chunks: list[DocumentChunk],
    row_labels: list[str],
    *,
    top_k: int = 20,
    role_map: PageRoleMap | None = None,
) -> list[tuple[DocumentChunk, float, list[str]]]:
    """Grep only category=table chunks for financial line-item labels."""
    if not row_labels:
        return []
    labels = [str(x) for x in row_labels if x]
    scored: list[tuple[DocumentChunk, float, list[str]]] = []
    for c in chunks:
        if _cat(c) != "table":
            continue
        content = c.content or ""
        matched = [lb for lb in labels if table_has_row_label(content, lb)]
        if not matched:
            continue
        score = float(len(matched))
        if role_map is not None:
            score += ROLE_SCORE_BONUS.get(role_map.role_of(int(c.page_number)), 0.0) * 10
        # Prefer tables that also look like statements (multi period headers)
        if "截至" in content or "12月31日" in content or "附註" in content or "附注" in content:
            score += 0.5
        scored.append((c, score, matched))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def role_score_bonus(role: str) -> float:
    return ROLE_SCORE_BONUS.get(role, 0.0)


def short_title_penalty(chunk: DocumentChunk, expanded: ExpandResult | None) -> float:
    """Downweight bare short titles that did not expand to a table."""
    if _cat(chunk) != "title":
        return 0.0
    if expanded and expanded.found_table is not None:
        return 0.0
    text = (chunk.content or "").strip()
    if len(text) <= 20 and not re.search(r"\d", text):
        return -0.025
    return -0.01
