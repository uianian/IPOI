from __future__ import annotations

import logging
from typing import Any

import numpy as np

from src.config import settings
from src.models.prospectus import DocumentChunk

logger = logging.getLogger(__name__)


class DocumentIndexer:
    def __init__(self, vllm_client: Any) -> None:
        self._vllm = vllm_client
        self._index: Any = None
        self._chunks: list[DocumentChunk] = []
        self._embeddings: np.ndarray | None = None
        self._embed_source: str | None = None
        self._vector_available: bool = True

    @property
    def vector_available(self) -> bool:
        return self._vector_available

    async def build_index(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            logger.warning("No chunks to index")
            return

        self._chunks = chunks
        texts = [c.content for c in chunks]

        batch_size = 32
        all_embeddings: list[list[float]] = []
        embed_failed = False

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                embs = await self._vllm.embed(batch)
                all_embeddings.extend(embs)
            except Exception as e:
                logger.error(f"Embedding batch {i} failed: {e}")
                embed_failed = True
                break

        if embed_failed or not all_embeddings:
            logger.warning("Embedding 全部失败，向量检索不可用，将降级为纯 BM25 检索")
            self._vector_available = False
            self._embeddings = None
            self._index = None
            return

        self._embed_source = getattr(self._vllm, "embedding_source", None)
        self._vector_available = True

        self._embeddings = np.array(all_embeddings, dtype=np.float32)

        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        self._embeddings = self._embeddings / norms

        try:
            import faiss

            dim = self._embeddings.shape[1]
            self._index = faiss.IndexFlatIP(dim)
            self._index.add(self._embeddings)
            logger.info(f"FAISS index built with {len(chunks)} chunks, dim={dim}")
        except ImportError:
            logger.warning("FAISS not available, using numpy fallback")
            self._index = None

    async def search(self, query: str, top_k: int = 10) -> list[tuple[DocumentChunk, float]]:
        if not self._chunks:
            return []

        if not self._vector_available:
            return []

        current_source = getattr(self._vllm, "embedding_source", None)
        if self._embed_source is not None and current_source != self._embed_source:
            logger.warning(
                f"Embedding 来源变化 ({self._embed_source} -> {current_source})，"
                "自动重建索引以保证维度一致性"
            )
            await self.build_index(self._chunks)

        try:
            query_emb = await self._vllm.embed([query])
        except Exception as e:
            logger.error(f"Query embedding failed: {e}，向量检索不可用")
            self._vector_available = False
            return []

        query_vec = np.array(query_emb, dtype=np.float32)
        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec = query_vec / norm

        if self._index is not None:
            import faiss

            scores, indices = self._index.search(query_vec, top_k)
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx < len(self._chunks):
                    results.append((self._chunks[idx], float(score)))
            return results
        else:
            scores = np.dot(self._embeddings, query_vec.T).flatten()
            top_indices = np.argsort(scores)[::-1][:top_k]
            return [(self._chunks[i], float(scores[i])) for i in top_indices]

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)