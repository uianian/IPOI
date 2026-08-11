"""Simulate Finance / Legal Agent hybrid retrieval over a built FAISS index.

Finance 2.1/2.2/2.3 (recall_unit=table):
  Grep∪BM25∪Vector∪row_label → expand → **appendix-only** whole statement packs
  (cross-page for CF; text-as-table when parse drops table tags) → Top-K per type.
  Core line-item ``row_labels`` gate precision (esp. TBL_BS vs tax notes).

Finance 2.4 / Legal (recall_unit=field, default):
  Per field_code candidate recall (optional row_label for legacy field profiles).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.models.prospectus import DocumentChunk
from src.retrieval.evidence_expand import (
    ExpandResult,
    PageRoleMap,
    build_page_index,
    build_page_role_map,
    collect_cross_page_pack,
    consolidated_title_bonus,
    expand_anchor,
    infer_statement_kind,
    matched_row_labels,
    must_have_groups_ok,
    page_title_blob,
    role_score_bonus,
    row_label_search,
    short_title_penalty,
    statement_body_score,
    statement_kind_compatible,
)
from src.retrieval.hybrid import SearchHit
from src.retrieval.store import DocumentIndexStore

logger = logging.getLogger(__name__)

_PROFILES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "agent_retrieval_profiles.yaml"
)

# Sections gated for non-biotech issuers.
# issuer_type biotech / 18a / 18c 门控等价（对应前端 isBiotech=true）。
_BIOTECH_SECTIONS = {"2.4", "3.5"}

# Whole-table recall: keep full HTML/text (downstream extraction needs rows intact)
_TABLE_EXCERPT_MAX = 50000


@dataclass
class AgentHit:
    chunk_id: str
    page: int
    bbox: list[float]
    category: str
    chunk_type: str
    excerpt: str
    score: float
    match_sources: list[str]
    matched_queries: list[str] = field(default_factory=list)
    agent: str = ""
    query_label: str = ""
    section: str = ""
    field_code: str = ""
    table_type: str = ""
    table_role: str = "other"
    stop_reason: str = ""
    expanded_from: str = ""
    pack_chunk_ids: list[str] = field(default_factory=list)
    pack_pages: list[int] = field(default_factory=list)
    covers_fields: list[str] = field(default_factory=list)
    matched_row_labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "agent": self.agent,
            "section": self.section,
            "field_code": self.field_code,
            "query_label": self.query_label,
            "chunk_id": self.chunk_id,
            "page": self.page,
            "bbox": self.bbox,
            "category": self.category,
            "chunk_type": self.chunk_type,
            "excerpt": self.excerpt,
            "score": round(self.score, 6),
            "match_sources": self.match_sources,
            "matched_queries": self.matched_queries,
            "table_role": self.table_role,
            "stop_reason": self.stop_reason,
        }
        if self.table_type:
            d["table_type"] = self.table_type
        if self.covers_fields:
            d["covers_fields"] = list(self.covers_fields)
        if self.expanded_from:
            d["expanded_from"] = self.expanded_from
        if self.pack_chunk_ids:
            d["pack_chunk_ids"] = self.pack_chunk_ids
        if self.pack_pages:
            d["pack_pages"] = list(self.pack_pages)
        if self.matched_row_labels:
            d["matched_row_labels"] = list(self.matched_row_labels)
        return d


def load_profiles(path: Path | None = None) -> dict[str, Any]:
    p = path or _PROFILES_PATH
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _normalize_excerpt(text: str, n: int = 80) -> str:
    s = re.sub(r"\s+", "", text or "")
    return s[:n]


def _category_of(chunk: DocumentChunk) -> str:
    return str((chunk.metadata or {}).get("category") or chunk.chunk_type)


def _prefer_categories(prefer: list[str] | None) -> list[str]:
    """Drop unreliable table_caption from prefer list."""
    if not prefer:
        return []
    return [c for c in prefer if c != "table_caption"]


def _excerpt_for_chunk(chunk: DocumentChunk, *, whole_table: bool) -> str:
    content = chunk.content or ""
    if whole_table and _category_of(chunk) in ("table", "text"):
        return content[:_TABLE_EXCERPT_MAX]
    return content[:400]


def _title_hint_bonus(text: str, title_hints: list[str]) -> float:
    """单条标题是否命中表名白名单。

    匹配顺序：精确相等 → 前缀（允许 —續/(續)）→ 包含 hint → 去「表」词干前缀
    （「綜合損益表」可命中「綜合損益及其他全面開支表」）。
    """
    if not title_hints or not text:
        return 0.0
    blob = re.sub(r"\s+", "", text)
    for hint in title_hints:
        h = re.sub(r"\s+", "", str(hint))
        if not h:
            continue
        if blob == h:
            return 0.04
        if blob.startswith(h) and (
            len(blob) == len(h)
            or blob[len(h) : len(h) + 1] in "—－–-﹣(（"
            or blob[len(h) :].startswith("續")
            or blob[len(h) :].startswith("续")
        ):
            return 0.04
        if len(h) >= 5 and h in blob:
            return 0.04
        # 词干：去掉末尾「表」后，标题以词干起头且后续为表/及/其他…
        stem = h[:-1] if h.endswith("表") and len(h) >= 5 else ""
        if stem and blob.startswith(stem):
            rest = blob[len(stem) :]
            if (not rest) or rest.startswith(("表", "及", "和其他", "其他", "—", "－", "(")):
                return 0.04
    return 0.0


def _page_has_title_hint(
    page_index: dict[int, list[DocumentChunk]],
    page: int,
    title_hints: list[str] | None,
) -> bool:
    """逐条 title/table_caption 匹配，避免同页多标题拼接导致 startswith 失败。

    部分招股书把「綜合損益及其他全面收益表」标成 table_caption 而非 title。
    """
    if not title_hints:
        return False
    for c in page_index.get(int(page)) or []:
        if _category_of(c) not in {"title", "table_caption"}:
            continue
        if _title_hint_bonus(c.content or "", title_hints) > 0:
            return True
    return False


def _page_title_hint_bonus(
    page_index: dict[int, list[DocumentChunk]],
    page: int,
    title_hints: list[str] | None,
) -> float:
    if not title_hints:
        return 0.0
    best = 0.0
    for c in page_index.get(int(page)) or []:
        if _category_of(c) not in {"title", "table_caption"}:
            continue
        best = max(best, _title_hint_bonus(c.content or "", title_hints))
    return best


def _hit_from_chunk(
    chunk: DocumentChunk,
    *,
    score: float,
    match_sources: list[str],
    agent: str,
    query_name: str,
    query_label: str,
    prefer_categories: list[str] | None,
    section: str = "",
    field_code: str = "",
    table_type: str = "",
    covers_fields: list[str] | None = None,
    category_bonus: float = 0.002,
    score_scale: float = 1.0,
    table_role: str = "other",
    stop_reason: str = "",
    expanded_from: str = "",
    pack_chunk_ids: list[str] | None = None,
    pack_pages: list[int] | None = None,
    matched_row_labels: list[str] | None = None,
    whole_table: bool = False,
    title_hints: list[str] | None = None,
    excerpt_override: str | None = None,
) -> AgentHit:
    meta = chunk.metadata or {}
    category = _category_of(chunk)
    final = float(score) * score_scale
    prefs = _prefer_categories(prefer_categories)
    if prefs and category in prefs:
        try:
            rank = prefs.index(category)
            final += category_bonus * (len(prefs) - rank)
        except ValueError:
            pass
    final += role_score_bonus(table_role)
    if whole_table and category in ("table", "text"):
        final += 0.03
        final += _title_hint_bonus(chunk.content or "", title_hints or [])
    excerpt = excerpt_override if excerpt_override is not None else _excerpt_for_chunk(
        chunk, whole_table=whole_table
    )
    return AgentHit(
        chunk_id=chunk.chunk_id,
        page=chunk.page_number,
        bbox=list(meta.get("bbox") or []),
        category=category,
        chunk_type=chunk.chunk_type,
        excerpt=excerpt,
        score=final,
        match_sources=list(match_sources),
        matched_queries=[query_name],
        agent=agent,
        query_label=query_label,
        section=section,
        field_code=field_code,
        table_type=table_type,
        table_role=table_role,
        stop_reason=stop_reason,
        expanded_from=expanded_from,
        pack_chunk_ids=list(pack_chunk_ids or []),
        pack_pages=list(pack_pages or []),
        covers_fields=list(covers_fields or []),
        matched_row_labels=list(matched_row_labels or []),
    )


def _hit_from_search(
    hit: SearchHit,
    *,
    agent: str,
    query_name: str,
    query_label: str,
    prefer_categories: list[str] | None,
    section: str = "",
    field_code: str = "",
    table_type: str = "",
    covers_fields: list[str] | None = None,
    category_bonus: float = 0.002,
    score_scale: float = 1.0,
    table_role: str = "other",
    whole_table: bool = False,
    title_hints: list[str] | None = None,
) -> AgentHit:
    return _hit_from_chunk(
        hit.chunk,
        score=float(hit.score),
        match_sources=list(hit.match_sources),
        agent=agent,
        query_name=query_name,
        query_label=query_label,
        prefer_categories=prefer_categories,
        section=section,
        field_code=field_code,
        table_type=table_type,
        covers_fields=covers_fields,
        category_bonus=category_bonus,
        score_scale=score_scale,
        table_role=table_role,
        stop_reason="",
        whole_table=whole_table,
        title_hints=title_hints,
    )


def _merge_by_chunk_id(hits: list[AgentHit]) -> list[AgentHit]:
    by_id: dict[str, AgentHit] = {}
    for h in hits:
        prev = by_id.get(h.chunk_id)
        if prev is None:
            by_id[h.chunk_id] = h
            continue
        if h.score > prev.score:
            h.match_sources = sorted(set(prev.match_sources) | set(h.match_sources))
            h.matched_queries = sorted(set(prev.matched_queries) | set(h.matched_queries))
            if not h.stop_reason and prev.stop_reason:
                h.stop_reason = prev.stop_reason
            if not h.expanded_from and prev.expanded_from:
                h.expanded_from = prev.expanded_from
            if not h.pack_chunk_ids and prev.pack_chunk_ids:
                h.pack_chunk_ids = prev.pack_chunk_ids
            if h.table_role == "other" and prev.table_role != "other":
                h.table_role = prev.table_role
            if not h.covers_fields and prev.covers_fields:
                h.covers_fields = prev.covers_fields
            if not h.table_type and prev.table_type:
                h.table_type = prev.table_type
            by_id[h.chunk_id] = h
        else:
            prev.match_sources = sorted(set(prev.match_sources) | set(h.match_sources))
            prev.matched_queries = sorted(set(prev.matched_queries) | set(h.matched_queries))
            if not prev.stop_reason and h.stop_reason:
                prev.stop_reason = h.stop_reason
            if not prev.expanded_from and h.expanded_from:
                prev.expanded_from = h.expanded_from
            if not prev.pack_chunk_ids and h.pack_chunk_ids:
                prev.pack_chunk_ids = h.pack_chunk_ids
    return sorted(by_id.values(), key=lambda x: x.score, reverse=True)


def _dedupe_same_page_field(hits: list[AgentHit]) -> list[AgentHit]:
    """Same page + field_code + similar excerpt → keep highest score."""
    buckets: dict[tuple[str, int, str], AgentHit] = {}
    for h in hits:
        key = (h.field_code, h.page, _normalize_excerpt(h.excerpt))
        prev = buckets.get(key)
        if prev is None or h.score > prev.score:
            if prev is not None:
                h.match_sources = sorted(set(prev.match_sources) | set(h.match_sources))
                h.matched_queries = sorted(set(prev.matched_queries) | set(h.matched_queries))
            buckets[key] = h
        else:
            prev.match_sources = sorted(set(prev.match_sources) | set(h.match_sources))
            prev.matched_queries = sorted(set(prev.matched_queries) | set(h.matched_queries))
    return sorted(buckets.values(), key=lambda x: x.score, reverse=True)


def _rank_key(h: AgentHit) -> tuple:
    """appendix body > summary; text-as-statement == table; then score / pack span."""
    role_rank = {"appendix": 3, "summary": 2, "discussion": 1, "other": 0}.get(h.table_role, 0)
    # Parser may emit statement body as text (e.g. mixue BS p430); do not demote vs HTML table.
    is_body = 1 if h.category in ("table", "text") else 0
    pack_span = len(h.pack_pages or [h.page])
    return (is_body, role_rank, h.score, pack_span)


def _section_page_range(
    chunks: list[DocumentChunk], section_id: str
) -> tuple[int, int] | None:
    pages = [
        int(chunk.page_number)
        for chunk in chunks
        if str((chunk.metadata or {}).get("section_id") or chunk.section_title or "")
        == section_id
    ]
    return (min(pages), max(pages)) if pages else None


def _collapse_overlapping_packs(hits: list[AgentHit]) -> list[AgentHit]:
    """Keep one hit per overlapping pack cluster (prefer earliest seed + longest span)."""
    if len(hits) <= 1:
        return hits
    n = len(hits)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    page_sets = [set(h.pack_pages or [h.page]) for h in hits]
    for i in range(n):
        for j in range(i + 1, n):
            if page_sets[i] & page_sets[j]:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    out: list[AgentHit] = []
    for idxs in groups.values():
        union_pages: set[int] = set()
        for i in idxs:
            union_pages |= page_sets[i]
        min_page = min(union_pages) if union_pages else 0

        def pick_key(i: int) -> tuple:
            h = hits[i]
            pages = page_sets[i]
            starts_at_head = 1 if pages and min(pages) == min_page else 0
            return (starts_at_head, len(pages), h.score)

        best_i = max(idxs, key=pick_key)
        out.append(hits[best_i])
    return sorted(out, key=_rank_key, reverse=True)


def _gate_queries(
    queries: list[dict[str, Any]],
    *,
    issuer_type: str,
    biotech_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (active_queries, skipped_meta)."""
    # biotech ≡ 18a ≡ 18c（前端 isBiotech=true 通常写入 biotech）
    is_biotech = str(issuer_type).strip().lower() in {"biotech", "18a", "18c"}
    active: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for q in queries:
        section = str(q.get("section") or "")
        gated = section in _BIOTECH_SECTIONS
        if not gated or is_biotech:
            qq = dict(q)
            qq["_score_scale"] = 1.0
            active.append(qq)
            continue
        if biotech_mode == "skip":
            skipped.append(
                {
                    "section": section,
                    "field_code": q.get("field_code") or q.get("name"),
                    "label": q.get("label"),
                    "reason": f"issuer_type={issuer_type}: skip biotech section {section}",
                }
            )
            continue
        qq = dict(q)
        qq["_score_scale"] = float(q.get("non_biotech_score_scale", 0.15))
        qq["_gated"] = "downweight"
        active.append(qq)
    return active, skipped


def _apply_expand_and_role(
    raw_hits: list[AgentHit],
    *,
    chunks_by_id: dict[str, DocumentChunk],
    page_index: dict[int, list[DocumentChunk]],
    role_map: PageRoleMap,
    agent: str,
    query_name: str,
    query_label: str,
    prefer: list[str],
    section: str,
    field_code: str,
    score_scale: float,
    table_type: str = "",
    covers_fields: list[str] | None = None,
    whole_table: bool = False,
    title_hints: list[str] | None = None,
    row_labels: list[str] | None = None,
    allow_text_as_table: bool = False,
    min_row_label_hits: int = 0,
    appendix_only: bool = False,
    cross_page_continue: bool = False,
    max_continue_pages: int = 4,
    must_have_groups: list[list[str]] | None = None,
    require_title_hint: bool = False,
    allowed_page_range: tuple[int, int] | None = None,
) -> list[AgentHit]:
    """Expand anchors to statement bodies; optional cross-page pack + row-label gate."""
    labels = list(row_labels or [])
    groups = list(must_have_groups or [])
    out: list[AgentHit] = []
    for h in raw_hits:
        chunk = chunks_by_id.get(h.chunk_id)
        if chunk is None:
            h.table_role = role_map.role_of(h.page)
            out.append(h)
            continue

        if appendix_only and whole_table and role_map.role_of(int(chunk.page_number)) != "appendix":
            continue

        expanded: ExpandResult = expand_anchor(
            chunk,
            page_index,
            row_labels=labels,
            allow_text_as_table=allow_text_as_table,
            min_row_label_hits=min_row_label_hits,
        )
        role = role_map.role_of(int(chunk.page_number))
        h.table_role = role
        h.stop_reason = expanded.stop_reason
        h.pack_chunk_ids = [m.chunk_id for m in expanded.members]
        h.score += short_title_penalty(chunk, expanded)

        body = expanded.found_table
        if body is None:
            if not whole_table:
                out.append(h)
            continue

        if appendix_only and role_map.role_of(int(body.page_number)) != "appendix":
            continue

        pack_members = [body]
        pack_stop = expanded.stop_reason
        if whole_table and cross_page_continue:
            pack = collect_cross_page_pack(
                body,
                page_index,
                role_map,
                max_pages=max_continue_pages,
                appendix_only=appendix_only,
                row_labels=labels,
                min_row_label_hits=min_row_label_hits,
                table_type=table_type,
                allowed_page_range=allowed_page_range,
            )
            pack_members = pack.members
            pack_stop = pack.stop_reason

        merged_excerpt = ""
        if whole_table and len(pack_members) > 1:
            parts = []
            for m in pack_members:
                if _category_of(m) in ("table", "text"):
                    parts.append(m.content or "")
            merged_excerpt = "\n\n<!-- page_break -->\n\n".join(parts)[:_TABLE_EXCERPT_MAX]
        elif whole_table:
            merged_excerpt = _excerpt_for_chunk(body, whole_table=True)

        blob_for_labels = merged_excerpt or (body.content or "")
        matched = matched_row_labels(blob_for_labels, labels) if labels else []
        if whole_table and labels and min_row_label_hits > 0:
            if len(matched) < min_row_label_hits:
                continue
        if whole_table and not must_have_groups_ok(blob_for_labels, groups):
            continue

        body_page = int(body.page_number)
        titles = page_title_blob(page_index.get(body_page) or [])
        # Prefer title on the pack's earliest page (statement head)
        pack_title_pages = sorted({int(m.page_number) for m in pack_members})
        head_titles = page_title_blob(page_index.get(pack_title_pages[0]) or []) if pack_title_pages else titles
        kind = infer_statement_kind(blob_for_labels, head_titles or titles)
        if whole_table and not statement_kind_compatible(table_type, kind):
            continue

        if whole_table and require_title_hint and title_hints:
            title_ok = False
            for pn in pack_title_pages[:2]:
                if _page_has_title_hint(page_index, pn, title_hints):
                    title_ok = True
                    break
            if not title_ok:
                continue

        sources = sorted(set(h.match_sources) | {"expand"})
        body_score = max(h.score, 0.01) + 0.02
        if matched:
            body_score += 0.015 * len(matched)
            sscore, _ = statement_body_score(blob_for_labels, labels)
            body_score += 0.01 * min(sscore, 5)

        if whole_table and title_hints:
            body_score += _page_title_hint_bonus(page_index, body_page, title_hints)
            body_score += _title_hint_bonus(body.content or "", title_hints)
            if pack_title_pages:
                body_score += _page_title_hint_bonus(
                    page_index, pack_title_pages[0], title_hints
                )
        if whole_table:
            body_score += consolidated_title_bonus(head_titles or titles, table_type)
            if pack_title_pages and _page_has_title_hint(
                page_index, pack_title_pages[0], title_hints
            ):
                body_score += 0.05

        # Prefer earliest pack page as the reported seed when title lives there
        report_body = body
        if whole_table and pack_title_pages:
            head_page = pack_title_pages[0]
            if title_hints and _page_has_title_hint(page_index, head_page, title_hints):
                for m in pack_members:
                    if int(m.page_number) == head_page and _category_of(m) in ("table", "text"):
                        report_body = m
                        break

        table_hit = _hit_from_chunk(
            report_body,
            score=body_score,
            match_sources=sources,
            agent=agent,
            query_name=query_name,
            query_label=query_label,
            prefer_categories=prefer,
            section=section,
            field_code=field_code,
            table_type=table_type,
            covers_fields=covers_fields,
            score_scale=score_scale,
            table_role=role_map.role_of(int(report_body.page_number)),
            stop_reason=pack_stop,
            expanded_from=h.chunk_id if report_body.chunk_id != chunk.chunk_id else "",
            pack_chunk_ids=[m.chunk_id for m in pack_members],
            pack_pages=sorted({int(m.page_number) for m in pack_members}),
            matched_row_labels=matched,
            whole_table=whole_table,
            title_hints=title_hints,
            excerpt_override=merged_excerpt or None,
        )
        if matched:
            table_hit.matched_queries = sorted(
                set(table_hit.matched_queries) | {f"row:{m}" for m in matched}
            )
        out.append(table_hit)
        if not whole_table and body.chunk_id != chunk.chunk_id:
            h.score -= 0.015
            out.append(h)
    return out


class AgentRetrievalSimulator:
    def __init__(self, store: DocumentIndexStore, profiles: dict[str, Any] | None = None) -> None:
        self._store = store
        self._profiles = profiles or load_profiles()
        self._page_index_cache: dict[str, dict[int, list[DocumentChunk]]] = {}
        self._role_map_cache: dict[str, PageRoleMap] = {}
        self._chunks_by_id_cache: dict[str, dict[str, DocumentChunk]] = {}

    async def _doc_nav(self, doc_id: str) -> tuple[
        dict[int, list[DocumentChunk]],
        PageRoleMap,
        dict[str, DocumentChunk],
        list[DocumentChunk],
    ]:
        loaded = await self._store.ensure_loaded(doc_id)
        if doc_id not in self._page_index_cache:
            self._page_index_cache[doc_id] = build_page_index(loaded.chunks)
            self._role_map_cache[doc_id] = build_page_role_map(loaded.chunks)
            self._chunks_by_id_cache[doc_id] = {c.chunk_id: c for c in loaded.chunks}
        return (
            self._page_index_cache[doc_id],
            self._role_map_cache[doc_id],
            self._chunks_by_id_cache[doc_id],
            loaded.chunks,
        )

    async def run_agent(
        self,
        agent: str,
        doc_id: str,
        *,
        top_k: int | None = None,
        query_names: list[str] | None = None,
        issuer_type: str = "general",
        biotech_mode: str | None = None,
    ) -> dict[str, Any]:
        """Run retrieval: table-unit for finance statements; field-unit otherwise."""
        profile = self._profiles.get(agent)
        if not profile:
            raise KeyError(f"Unknown agent profile: {agent}. Available: {list(self._profiles)}")

        default_field_k = int(
            top_k
            or profile.get("top_k_per_field")
            or profile.get("top_k_per_query", 5)
        )
        default_table_k = int(
            top_k
            or profile.get("top_k_per_table")
            or profile.get("top_k_per_field")
            or profile.get("top_k_per_query", 5)
        )
        mode = biotech_mode or profile.get("non_biotech_gate", "skip")
        if mode not in ("skip", "downweight"):
            mode = "skip"

        queries = list(profile.get("queries") or [])
        if query_names:
            allowed = set(query_names)
            queries = [q for q in queries if q.get("name") in allowed]

        queries, skipped = _gate_queries(
            queries, issuer_type=issuer_type, biotech_mode=mode
        )

        page_index, role_map, chunks_by_id, all_chunks = await self._doc_nav(doc_id)

        by_key: dict[str, list[AgentHit]] = {}
        evidence_by_table: dict[str, list[AgentHit]] = {}
        field_table_map: dict[str, str] = {}
        per_query_stats: list[dict[str, Any]] = []

        for q in queries:
            name = q.get("name") or "unnamed"
            label = q.get("label") or name
            section = str(q.get("section") or "")
            field_code = str(q.get("field_code") or name)
            table_type = str(q.get("table_type") or "")
            recall_unit = str(q.get("recall_unit") or "field")
            whole_table = recall_unit == "table"
            covers_fields = [str(x) for x in (q.get("covers_fields") or [])]
            title_hints = [str(x) for x in (q.get("title_hints") or [])]
            query = q.get("query") or ""
            grep_terms = list(q.get("grep_terms") or [])
            prefer = list(q.get("prefer_categories") or [])
            row_labels = list(q.get("row_labels") or [])
            score_scale = float(q.get("_score_scale", 1.0))
            per_k = default_table_k if whole_table else default_field_k
            appendix_only = bool(
                q.get("appendix_only", profile.get("appendix_only", False))
            ) if whole_table else False
            appendix_section_range = (
                _section_page_range(all_chunks, "appendix_one")
                if whole_table and appendix_only
                else None
            )
            # New indexes use the chapter tree as the hard gate.  PageRoleMap
            # remains the fallback for legacy indexes without section metadata.
            appendix_role_fallback = appendix_only and appendix_section_range is None
            allow_text_as_table = bool(q.get("allow_text_as_table", False))
            min_row_label_hits = int(q.get("min_row_label_hits") or 0)
            cross_page_continue = bool(q.get("cross_page_continue", False))
            max_continue_pages = int(q.get("max_continue_pages") or 4)
            must_have_groups = [
                [str(x) for x in group]
                for group in (q.get("must_have_groups") or [])
                if group
            ]
            require_title_hint = bool(q.get("require_title_hint", False))

            # 先写入者优先：合并 TBL_BS 不被后续 TBL_BS_COMPANY 覆盖集团字段映射
            for fc in covers_fields:
                field_table_map.setdefault(fc, field_code)

            hits = await self._store.search(
                doc_id=doc_id,
                query=query,
                top_k=max(per_k * 4, per_k),
                grep_terms=grep_terms,
                page_range=appendix_section_range,
                weights=profile.get("weights"),
                grep_boost_rank=profile.get("grep_boost_rank"),
            )
            agent_hits = [
                _hit_from_search(
                    h,
                    agent=agent,
                    query_name=name,
                    query_label=label,
                    prefer_categories=prefer,
                    section=section,
                    field_code=field_code,
                    table_type=table_type,
                    covers_fields=covers_fields,
                    score_scale=score_scale,
                    table_role=role_map.role_of(h.chunk.page_number),
                    whole_table=whole_table,
                    title_hints=title_hints,
                )
                for h in hits
            ]

            # Row-label channel: tables (+ optional text) — used for both field and table units
            if row_labels:
                for chunk, score, matched in row_label_search(
                    all_chunks,
                    row_labels,
                    top_k=max(per_k * 4, 20),
                    role_map=role_map,
                    appendix_only=appendix_role_fallback,
                    allow_text=allow_text_as_table or whole_table,
                    page_range=appendix_section_range,
                ):
                    agent_hits.append(
                        _hit_from_chunk(
                            chunk,
                            score=0.08 + float(score) * 0.02,
                            match_sources=["row_label"],
                            agent=agent,
                            query_name=name,
                            query_label=label,
                            prefer_categories=prefer,
                            section=section,
                            field_code=field_code,
                            table_type=table_type,
                            covers_fields=covers_fields,
                            score_scale=score_scale,
                            table_role=role_map.role_of(int(chunk.page_number)),
                            stop_reason="row_label",
                            matched_row_labels=matched,
                            whole_table=whole_table,
                            title_hints=title_hints,
                        )
                    )
                    agent_hits[-1].matched_queries = sorted(
                        set(agent_hits[-1].matched_queries) | {f"row:{m}" for m in matched}
                    )

            merged = _merge_by_chunk_id(agent_hits)
            if agent == "finance" or whole_table:
                expanded = _apply_expand_and_role(
                    merged,
                    chunks_by_id=chunks_by_id,
                    page_index=page_index,
                    role_map=role_map,
                    agent=agent,
                    query_name=name,
                    query_label=label,
                    prefer=prefer,
                    section=section,
                    field_code=field_code,
                    score_scale=score_scale,
                    table_type=table_type,
                    covers_fields=covers_fields,
                    whole_table=whole_table,
                    title_hints=title_hints,
                    row_labels=row_labels,
                    allow_text_as_table=allow_text_as_table,
                    min_row_label_hits=min_row_label_hits,
                    appendix_only=appendix_role_fallback,
                    cross_page_continue=cross_page_continue,
                    max_continue_pages=max_continue_pages,
                    must_have_groups=must_have_groups,
                    require_title_hint=require_title_hint,
                    allowed_page_range=appendix_section_range,
                )
                field_hits = _dedupe_same_page_field(_merge_by_chunk_id(expanded))
                if whole_table:
                    keep: list[AgentHit] = []
                    for h in field_hits:
                        if appendix_role_fallback and h.table_role != "appendix":
                            continue
                        if h.category in ("table", "text"):
                            keep.append(h)
                    field_hits = keep or [
                        h
                        for h in field_hits
                        if not appendix_role_fallback or h.table_role == "appendix"
                    ]
                    field_hits = _collapse_overlapping_packs(field_hits)
                field_hits = sorted(field_hits, key=_rank_key, reverse=True)[:per_k]
            else:
                for h in merged:
                    h.table_role = role_map.role_of(h.page)
                    h.stop_reason = h.stop_reason or "no_expand"
                field_hits = _dedupe_same_page_field(merged)[:per_k]

            by_key[field_code] = field_hits
            if whole_table:
                evidence_by_table[field_code] = field_hits

            roles = sorted({h.table_role for h in field_hits})
            stops = sorted({h.stop_reason for h in field_hits if h.stop_reason})
            pack_pages = sorted({p for ah in field_hits for p in (ah.pack_pages or [ah.page])})
            per_query_stats.append(
                {
                    "name": name,
                    "section": section,
                    "field_code": field_code,
                    "table_type": table_type or None,
                    "recall_unit": recall_unit,
                    "label": label,
                    "query": query,
                    "covers_fields": covers_fields,
                    "title_hints": title_hints,
                    "row_labels": row_labels,
                    "appendix_only": appendix_only,
                    "appendix_gate": (
                        "section_span" if appendix_section_range else "page_role_fallback"
                    )
                    if appendix_only
                    else None,
                    "appendix_section_range": (
                        list(appendix_section_range) if appendix_section_range else None
                    ),
                    "cross_page_continue": cross_page_continue,
                    "extract_fields": q.get("extract_fields") or covers_fields,
                    "gated": q.get("_gated"),
                    "score_scale": score_scale,
                    "hit_count": len(field_hits),
                    "top_pages": [ah.page for ah in field_hits],
                    "pack_pages": pack_pages,
                    "table_roles": roles,
                    "stop_reasons": stops,
                    "sources": sorted({s for ah in field_hits for s in ah.match_sources}),
                    "role": "table_recall" if whole_table else "candidate_recall",
                }
            )
            logger.info(
                "[%s] %s/%s unit=%s keep=%d pages=%s pack=%s roles=%s appendix_only=%s",
                agent,
                section,
                field_code,
                recall_unit,
                len(field_hits),
                [ah.page for ah in field_hits],
                pack_pages,
                roles,
                appendix_only,
            )

        evidence_by_field = {
            fc: [h.to_dict() for h in hits] for fc, hits in by_key.items()
        }
        evidence_by_table_out = {
            tc: [h.to_dict() for h in hits] for tc, hits in evidence_by_table.items()
        }
        flat: list[AgentHit] = []
        for fc in sorted(by_key.keys()):
            flat.extend(by_key[fc])

        has_table = bool(evidence_by_table)
        fusion_strategy = (
            "per table_type (2.1/2.2/2.3): Grep∪BM25∪Vector∪row_label → expand "
            "→ appendix-only statement pack (cross-page) → core row_labels gate → Top-K. "
            "Other sections: per field_code Top-K."
            if has_table
            else (
                "per field_code: Grep∪BM25∪Vector → expand → table_role boost → Top-K per field"
            )
        )

        return {
            "agent": agent,
            "description": profile.get("description", ""),
            "doc_chapter": profile.get("doc_chapter", ""),
            "doc_id": doc_id,
            "issuer_type": issuer_type,
            "biotech_gate": mode,
            "skipped_fields": skipped,
            "page_roles": {
                "appendix_range": list(role_map.appendix_range)
                if role_map.appendix_range
                else None,
                "discussion_range": list(role_map.discussion_range)
                if role_map.discussion_range
                else None,
                "summary_page_count": len(role_map.summary_pages),
            },
            "fusion": {
                "strategy": fusion_strategy,
                "weights": profile.get("weights") or {},
                "top_k_per_table": default_table_k,
                "top_k_per_field": default_field_k,
                "output": "evidence_by_table + evidence_by_field + field_table_map",
                "expand": "appendix_only_statement_pack",
                "table_roles": ["appendix", "summary", "discussion", "other"],
                "recall_note": (
                    "2.1/2.2/2.3: appendix-only whole statements; "
                    "cross-page CF pack; BS gated by 2.2 core row_labels"
                ),
                "appendix_only": True,
            },
            "per_query": per_query_stats,
            "evidence_by_table": evidence_by_table_out,
            "field_table_map": field_table_map,
            "evidence_by_field": evidence_by_field,
            "total_unique_hits": len(flat),
            "field_count": len(by_key),
            "table_count": len(evidence_by_table),
            "evidence": [h.to_dict() for h in flat],
        }

    async def run_finance(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        return await self.run_agent("finance", doc_id, **kwargs)

    async def run_legal(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        return await self.run_agent("legal", doc_id, **kwargs)

    async def run_all(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        finance = await self.run_finance(doc_id, **kwargs)
        legal = await self.run_legal(doc_id, **kwargs)
        return {
            "doc_id": doc_id,
            "issuer_type": kwargs.get("issuer_type", "general"),
            "finance": finance,
            "legal": legal,
            "summary": {
                "finance_fields": finance["field_count"],
                "finance_tables": finance.get("table_count", 0),
                "legal_fields": legal["field_count"],
                "finance_hits": finance["total_unique_hits"],
                "legal_hits": legal["total_unique_hits"],
                "finance_skipped": [s["field_code"] for s in finance.get("skipped_fields", [])],
                "legal_skipped": [s["field_code"] for s in legal.get("skipped_fields", [])],
                "finance_pages": sorted({e["page"] for e in finance["evidence"]}),
                "legal_pages": sorted({e["page"] for e in legal["evidence"]}),
                "finance_appendix_range": (finance.get("page_roles") or {}).get("appendix_range"),
                "field_table_map": finance.get("field_table_map") or {},
            },
        }
