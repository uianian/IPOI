from __future__ import annotations

import logging
from typing import Any

from rank_bm25 import BM25Okapi

from src.config import settings
from src.models.prospectus import DocumentChunk

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(self, indexer: Any) -> None:
        self._indexer = indexer
        self._bm25: BM25Okapi | None = None
        self._bm25_chunks: list[DocumentChunk] = []

    def build_bm25(self, chunks: list[DocumentChunk]) -> None:
        self._bm25_chunks = chunks
        tokenized = [list(c.content) for c in chunks]
        self._bm25 = BM25Okapi(tokenized)

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        section_filter: str | None = None,
        page_range: tuple[int, int] | None = None,
    ) -> list[tuple[DocumentChunk, float]]:
        vector_available = getattr(self._indexer, "vector_available", True)

        vector_dict: dict[str, tuple[DocumentChunk, float]] = {}
        if vector_available:
            try:
                vector_results = await self._indexer.search(query, top_k=top_k * 2)
                for chunk, score in vector_results:
                    vector_dict[chunk.chunk_id] = (chunk, score)
            except Exception as e:
                logger.warning(f"向量检索失败，降级为纯 BM25: {e}")

        if not vector_dict:
            logger.info("向量检索无结果，使用纯 BM25 检索")

        bm25_dict: dict[str, float] = {}
        if self._bm25 is not None:
            tokenized_query = list(query)
            bm25_scores = self._bm25.get_scores(tokenized_query)
            top_indices = bm25_scores.argsort()[::-1][: top_k * 2]
            for idx in top_indices:
                if idx < len(self._bm25_chunks):
                    chunk = self._bm25_chunks[idx]
                    bm25_dict[chunk.chunk_id] = float(bm25_scores[idx])

        all_chunk_ids = set(vector_dict.keys()) | set(bm25_dict.keys())

        use_vector = bool(vector_dict)
        v_weight = settings.retrieval.vector_weight if use_vector else 0.0
        b_weight = settings.retrieval.bm25_weight if use_vector else 1.0
        rrf_k = settings.retrieval.rrf_k

        vector_ranked = {cid: rank + 1 for rank, (cid, _) in enumerate(
            sorted(vector_dict.items(), key=lambda x: x[1][1], reverse=True)
        )}
        bm25_ranked = {cid: rank + 1 for rank, cid in enumerate(
            sorted(bm25_dict.keys(), key=lambda c: bm25_dict.get(c, 0), reverse=True)
        )}

        fused_scores: list[tuple[str, float]] = []
        for cid in all_chunk_ids:
            v_score = 1.0 / (rrf_k + vector_ranked.get(cid, len(all_chunk_ids) + 1))
            b_score = 1.0 / (rrf_k + bm25_ranked.get(cid, len(all_chunk_ids) + 1))
            fused = v_weight * v_score + b_weight * b_score
            fused_scores.append((cid, fused))

        fused_scores.sort(key=lambda x: x[1], reverse=True)
        top_ids = [cid for cid, _ in fused_scores[:top_k]]

        results: list[tuple[DocumentChunk, float]] = []
        for cid in top_ids:
            if cid in vector_dict:
                chunk, _ = vector_dict[cid]
            elif cid in bm25_dict:
                idx = next(i for i, c in enumerate(self._bm25_chunks) if c.chunk_id == cid)
                chunk = self._bm25_chunks[idx]
            else:
                continue

            if section_filter and chunk.section_title and section_filter not in chunk.section_title:
                continue
            if page_range and not (page_range[0] <= chunk.page_number <= page_range[1]):
                continue

            fused_val = next(s for c, s in fused_scores if c == cid)
            results.append((chunk, fused_val))

        return results[:top_k]