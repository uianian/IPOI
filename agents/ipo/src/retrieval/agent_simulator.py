"""Simulate Finance / Legal Agent hybrid retrieval over a built FAISS index.

Finance 2.1/2.2/2.3 (recall_unit=table):
  Grep∪BM25∪Vector → expand to table → keep whole tables → Top-K **per table type**.
  Field codes (REV/CFO/…) are covered by the parent statement; no per-field Top-K
  and no row-label slicing at retrieval time (table parse completeness < 100%).

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
    expand_anchor,
    role_score_bonus,
    row_label_search,
    short_title_penalty,
)
from src.retrieval.hybrid import SearchHit
from src.retrieval.store import DocumentIndexStore

logger = logging.getLogger(__name__)

_PROFILES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "agent_retrieval_profiles.yaml"
)

# Sections gated for non-biotech / non-18A issuers
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
    covers_fields: list[str] = field(default_factory=list)

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
    if whole_table and _category_of(chunk) == "table":
        return content[:_TABLE_EXCERPT_MAX]
    return content[:400]


def _title_hint_bonus(text: str, title_hints: list[str]) -> float:
    if not title_hints or not text:
        return 0.0
    blob = re.sub(r"\s+", "", text)
    for hint in title_hints:
        h = re.sub(r"\s+", "", str(hint))
        if h and h in blob:
            return 0.04
    return 0.0


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
    whole_table: bool = False,
    title_hints: list[str] | None = None,
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
    if whole_table and category == "table":
        final += 0.03
        final += _title_hint_bonus(chunk.content or "", title_hints or [])
    return AgentHit(
        chunk_id=chunk.chunk_id,
        page=chunk.page_number,
        bbox=list(meta.get("bbox") or []),
        category=category,
        chunk_type=chunk.chunk_type,
        excerpt=_excerpt_for_chunk(chunk, whole_table=whole_table),
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
        covers_fields=list(covers_fields or []),
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
    """appendix table > summary table > other; then score."""
    role_rank = {"appendix": 3, "summary": 2, "discussion": 1, "other": 0}.get(h.table_role, 0)
    is_table = 1 if h.category == "table" else 0
    return (is_table, role_rank, h.score)


def _gate_queries(
    queries: list[dict[str, Any]],
    *,
    issuer_type: str,
    biotech_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (active_queries, skipped_meta)."""
    is_biotech = issuer_type == "biotech"
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
) -> list[AgentHit]:
    """Expand title/text anchors to tables; annotate roles; demote bare titles."""
    out: list[AgentHit] = []
    for h in raw_hits:
        chunk = chunks_by_id.get(h.chunk_id)
        if chunk is None:
            h.table_role = role_map.role_of(h.page)
            out.append(h)
            continue

        expanded: ExpandResult = expand_anchor(chunk, page_index)
        role = role_map.role_of(int(chunk.page_number))
        h.table_role = role
        h.stop_reason = expanded.stop_reason
        h.pack_chunk_ids = [m.chunk_id for m in expanded.members]
        h.score += short_title_penalty(chunk, expanded)
        if whole_table:
            h.excerpt = _excerpt_for_chunk(chunk, whole_table=True)
            h.table_type = table_type or h.table_type
            h.covers_fields = list(covers_fields or h.covers_fields)
            h.score += _title_hint_bonus(chunk.content or "", title_hints or [])

        if expanded.found_table is not None and expanded.found_table.chunk_id != chunk.chunk_id:
            table = expanded.found_table
            table_role = role_map.role_of(int(table.page_number))
            sources = sorted(set(h.match_sources) | {"expand"})
            table_hit = _hit_from_chunk(
                table,
                score=max(h.score, 0.01) + 0.02,
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
                table_role=table_role,
                stop_reason=expanded.stop_reason,
                expanded_from=h.chunk_id,
                pack_chunk_ids=[m.chunk_id for m in expanded.members],
                whole_table=whole_table,
                title_hints=title_hints,
            )
            # Same-page title hint: boost if nearby title matches
            if whole_table and title_hints:
                page_chunks = page_index.get(int(table.page_number)) or []
                page_blob = " ".join(
                    (c.content or "") for c in page_chunks if _category_of(c) in ("title", "text")
                )
                table_hit.score += _title_hint_bonus(page_blob, title_hints)
            out.append(table_hit)
            if not whole_table:
                h.score -= 0.015
                out.append(h)
            # whole_table mode: drop bare title/text anchors — only keep tables
        elif whole_table and _category_of(chunk) == "table":
            out.append(h)
        elif not whole_table:
            out.append(h)
        # whole_table + non-table with no expand → drop
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

            for fc in covers_fields:
                field_table_map[fc] = field_code

            hits = await self._store.search(
                doc_id=doc_id,
                query=query,
                top_k=max(per_k * 4, per_k),
                grep_terms=grep_terms,
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

            # Field-unit only: optional row-label Grep (legacy / 2.4 atypical)
            if (not whole_table) and row_labels:
                for chunk, score, matched in row_label_search(
                    all_chunks,
                    row_labels,
                    top_k=max(per_k * 3, 15),
                    role_map=role_map,
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
                            score_scale=score_scale,
                            table_role=role_map.role_of(int(chunk.page_number)),
                            stop_reason="row_label",
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
                )
                field_hits = _dedupe_same_page_field(_merge_by_chunk_id(expanded))
                if whole_table:
                    # Keep tables only; demote leftover non-tables if any slipped in
                    tables = [h for h in field_hits if h.category == "table"]
                    if tables:
                        field_hits = tables
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
                    "row_labels": row_labels if not whole_table else [],
                    "extract_fields": q.get("extract_fields") or covers_fields,
                    "gated": q.get("_gated"),
                    "score_scale": score_scale,
                    "hit_count": len(field_hits),
                    "top_pages": [ah.page for ah in field_hits],
                    "table_roles": roles,
                    "stop_reasons": stops,
                    "sources": sorted({s for ah in field_hits for s in ah.match_sources}),
                    "role": "table_recall" if whole_table else "candidate_recall",
                }
            )
            logger.info(
                "[%s] %s/%s unit=%s keep=%d pages=%s roles=%s covers=%s",
                agent,
                section,
                field_code,
                recall_unit,
                len(field_hits),
                [ah.page for ah in field_hits],
                roles,
                covers_fields or None,
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
            "per table_type (2.1/2.2/2.3): Grep∪BM25∪Vector → expand(find table) "
            "→ whole table Top-K; field codes via covers_fields / field_table_map. "
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
                "expand": "find_table_or_same_page",
                "table_roles": ["appendix", "summary", "discussion", "other"],
                "recall_note": (
                    "2.1/2.2/2.3 return whole tables; do not row-slice at retrieval"
                ),
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
