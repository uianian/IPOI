from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from rank_bm25 import BM25Okapi

from src.config import settings
from src.models.prospectus import DocumentChunk
from src.retrieval.grep_retriever import grep_search

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    try:
        import jieba

        tokens = [t.strip() for t in jieba.lcut(text) if t.strip()]
        return tokens or list(text)
    except Exception:
        return list(text)


@dataclass
class SearchHit:
    chunk: DocumentChunk
    score: float
    match_sources: list[str] = field(default_factory=list)

    def to_dict(self, content_limit: int | None = 500) -> dict[str, Any]:
        content = self.chunk.content
        if content_limit is not None:
            content = content[:content_limit]
        meta = self.chunk.metadata or {}
        return {
            "chunk_id": self.chunk.chunk_id,
            "page_number": self.chunk.page_number,
            "section_title": self.chunk.section_title,
            "section_id": meta.get("section_id", self.chunk.section_title),
            "section_display_title": meta.get("section_title"),
            "chunk_type": self.chunk.chunk_type,
            "category": meta.get("category", self.chunk.chunk_type),
            "bbox": meta.get("bbox", []),
            "content": content,
            "score": self.score,
            "match_sources": self.match_sources,
        }


class HybridRetriever:
    """Grep ∪ jieba-BM25 ∪ vector → weighted RRF."""

    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._bm25_chunks: list[DocumentChunk] = []

    def build_bm25(self, chunks: list[DocumentChunk]) -> None:
        self._bm25_chunks = chunks
        tokenized = [_tokenize(c.content) for c in chunks]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    async def retrieve(
        self,
        query: str,
        chunks: list[DocumentChunk],
        vector_search: Any,
        top_k: int = 10,
        grep_terms: list[str] | None = None,
        page_range: tuple[int, int] | None = None,
        category_filter: str | None = None,
        section_filter: str | None = None,
        weights: dict[str, float] | None = None,
        grep_boost_rank: int | None = None,
        use_lexicon: bool | None = None,
    ) -> list[SearchHit]:
        # Filtering happens after the three recall channels are fused.  Pull a
        # wider candidate pool for section/page-constrained searches so a
        # globally common term does not crowd out the target chapter.
        candidate_k = (
            max(top_k * 8, 100)
            if section_filter or page_range or category_filter
            else max(top_k * 2, 20)
        )
        rrf_k = settings.retrieval.rrf_k
        w = weights or {}
        v_weight = float(w.get("vector", settings.retrieval.vector_weight))
        b_weight = float(w.get("bm25", settings.retrieval.bm25_weight))
        g_weight = float(w.get("grep", getattr(settings.retrieval, "grep_weight", 0.2)))
        grep_boost = int(
            grep_boost_rank
            if grep_boost_rank is not None
            else getattr(settings.retrieval, "grep_boost_rank", 3)
        )
        # Explicit grep_terms → do not inject global lexicon (avoids bare「贖回」noise)
        lexicon_on = use_lexicon if use_lexicon is not None else not bool(grep_terms)

        # --- Grep ---
        grep_results = grep_search(
            chunks, query, grep_terms=grep_terms, use_lexicon=lexicon_on, top_k=candidate_k
        )
        grep_ranked = {
            c.chunk_id: rank + 1
            for rank, (c, _, _) in enumerate(grep_results)
        }
        grep_matched_terms = {c.chunk_id: terms for c, _, terms in grep_results}

        # --- Vector ---
        vector_ranked: dict[str, int] = {}
        vector_chunks: dict[str, DocumentChunk] = {}
        try:
            vector_hits = await vector_search(query, top_k=candidate_k)
            for rank, (chunk, _score) in enumerate(vector_hits):
                vector_ranked[chunk.chunk_id] = rank + 1
                vector_chunks[chunk.chunk_id] = chunk
        except Exception as e:
            logger.warning("Vector search failed: %s", e)

        # --- BM25 ---
        bm25_ranked: dict[str, int] = {}
        if self._bm25 is not None and self._bm25_chunks:
            tokenized_query = _tokenize(query)
            scores = self._bm25.get_scores(tokenized_query)
            top_indices = scores.argsort()[::-1][:candidate_k]
            rank = 0
            for idx in top_indices:
                if idx < len(self._bm25_chunks) and scores[idx] > 0:
                    rank += 1
                    bm25_ranked[self._bm25_chunks[idx].chunk_id] = rank

        chunk_by_id = {c.chunk_id: c for c in chunks}
        chunk_by_id.update(vector_chunks)

        all_ids = set(grep_ranked) | set(bm25_ranked) | set(vector_ranked)
        if not all_ids:
            return []

        fused: list[tuple[str, float]] = []
        for cid in all_ids:
            g = 1.0 / (rrf_k + grep_ranked[cid]) if cid in grep_ranked else 0.0
            b = 1.0 / (rrf_k + bm25_ranked[cid]) if cid in bm25_ranked else 0.0
            v = 1.0 / (rrf_k + vector_ranked[cid]) if cid in vector_ranked else 0.0
            score = g_weight * g + b_weight * b + v_weight * v
            # Grep boost: ensure grep hits stay competitive
            if cid in grep_ranked and grep_ranked[cid] <= grep_boost:
                score += 1.0 / (rrf_k + 1)
            fused.append((cid, score))

        fused.sort(key=lambda x: x[1], reverse=True)

        hits: list[SearchHit] = []
        for cid, score in fused:
            chunk = chunk_by_id.get(cid)
            if chunk is None:
                continue
            if section_filter:
                section_id = str(
                    (chunk.metadata or {}).get("section_id")
                    or chunk.section_title
                    or ""
                )
                display_title = str((chunk.metadata or {}).get("section_title") or "")
                if not section_id and not display_title:
                    continue
                if section_filter != section_id and section_filter not in display_title:
                    continue
            if page_range and not (page_range[0] <= chunk.page_number <= page_range[1]):
                continue
            if category_filter:
                cat = (chunk.metadata or {}).get("category", chunk.chunk_type)
                if cat != category_filter:
                    continue

            sources: list[str] = []
            if cid in grep_ranked:
                sources.append("grep")
            if cid in bm25_ranked:
                sources.append("bm25")
            if cid in vector_ranked:
                sources.append("vector")

            hits.append(SearchHit(chunk=chunk, score=score, match_sources=sources))
            if len(hits) >= top_k:
                break

        return hits
