from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from src.config import settings
from src.models.prospectus import DocumentChunk
from src.retrieval.faiss_index import (
    IndexMeta,
    build_faiss_from_embeddings,
    index_dir_for,
    index_exists,
    load_chunks,
    load_faiss_index,
    load_meta,
    normalize_rows,
    save_index,
)
from src.retrieval.hybrid import HybridRetriever, SearchHit
from src.retrieval.parse_adapter import full_parse_to_chunks

logger = logging.getLogger(__name__)


class IndexNotFound(Exception):
    pass


class IndexMetaMismatch(Exception):
    pass


@dataclass
class BuildResult:
    doc_id: str
    doc_name: str
    reused: bool
    chunk_count: int
    total_pages: int
    index_path: str
    embedding_source: str = ""
    embedding_model: str = ""
    skipped_footer: int = 0
    skipped_empty_figure: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "reused": self.reused,
            "chunk_count": self.chunk_count,
            "total_pages": self.total_pages,
            "index_path": self.index_path,
            "embedding_source": self.embedding_source,
            "embedding_model": self.embedding_model,
            "skipped_footer": self.skipped_footer,
            "skipped_empty_figure": self.skipped_empty_figure,
            **self.extra,
        }


@dataclass
class LoadedIndex:
    doc_id: str
    chunks: list[DocumentChunk]
    faiss_index: Any
    meta: IndexMeta
    retriever: HybridRetriever
    vector_available: bool = True


class DocumentIndexStore:
    """Process-level FAISS index store: build once, load once, search many."""

    def __init__(self, vllm_client: Any, index_root: str | Path | None = None) -> None:
        self._vllm = vllm_client
        root = index_root or getattr(settings.retrieval, "index_root", ".runtime/indexes")
        self._index_root = Path(root)
        if not self._index_root.is_absolute():
            # resolve relative to agents/ipo package root
            pkg_root = Path(__file__).resolve().parent.parent.parent
            self._index_root = (pkg_root / self._index_root).resolve()
        self._cache: dict[str, LoadedIndex] = {}
        self._path_to_doc: dict[str, str] = {}  # absolute parse path -> doc_id
        self._build_count = 0
        self._embed_call_count = 0

    @property
    def index_root(self) -> Path:
        return self._index_root

    @property
    def build_count(self) -> int:
        return self._build_count

    @property
    def embed_call_count(self) -> int:
        return self._embed_call_count

    def exists(self, doc_id: str) -> bool:
        return index_exists(self._index_root, doc_id)

    def resolve_by_parse_path(self, parse_json_path: str) -> str | None:
        abs_path = str(Path(parse_json_path).resolve())
        if abs_path in self._path_to_doc:
            return self._path_to_doc[abs_path]
        # scan meta files
        if not self._index_root.exists():
            return None
        for meta_file in self._index_root.glob("*/meta.json"):
            try:
                meta = load_meta(meta_file.parent)
            except Exception:
                continue
            if str(Path(meta.parse_json_path).resolve()) == abs_path:
                self._path_to_doc[abs_path] = meta.doc_id
                return meta.doc_id
        return None

    async def build_from_parse(
        self,
        doc_id: str,
        parse_json_path: str,
        *,
        company_name: str = "",
        stock_code: str = "",
        listing_date: str = "",
        doc_name: str | None = None,
        force: bool = False,
    ) -> BuildResult:
        abs_path = str(Path(parse_json_path).resolve())
        resolved_name = doc_name or Path(abs_path).parent.name
        index_dir = index_dir_for(self._index_root, doc_id)

        if not force and index_exists(self._index_root, doc_id):
            meta = load_meta(index_dir)
            if str(Path(meta.parse_json_path).resolve()) == abs_path:
                self._path_to_doc[abs_path] = doc_id
                await self.ensure_loaded(doc_id)
                return BuildResult(
                    doc_id=doc_id,
                    doc_name=meta.doc_name or resolved_name,
                    reused=True,
                    chunk_count=meta.chunk_count,
                    total_pages=meta.total_pages,
                    index_path=str(index_dir),
                    embedding_source=meta.embedding_source,
                    embedding_model=meta.embedding_model,
                )

        chunks, total_pages, stats = full_parse_to_chunks(abs_path, doc_id)
        if not chunks:
            raise ValueError(f"No indexable chunks from {abs_path}")

        embeddings, emb_source, emb_model, dim = await self._embed_all([c.content for c in chunks])
        faiss_index = build_faiss_from_embeddings(embeddings)

        meta = IndexMeta(
            doc_id=doc_id,
            doc_name=resolved_name,
            parse_json_path=abs_path,
            company_name=company_name,
            stock_code=stock_code,
            listing_date=listing_date,
            embedding_model=emb_model,
            embedding_source=emb_source,
            dim=dim,
            chunk_count=len(chunks),
            total_pages=total_pages,
        )
        save_index(index_dir, faiss_index, chunks, meta)
        self._path_to_doc[abs_path] = doc_id
        self._build_count += 1

        retriever = HybridRetriever()
        retriever.build_bm25(chunks)
        self._cache[doc_id] = LoadedIndex(
            doc_id=doc_id,
            chunks=chunks,
            faiss_index=faiss_index,
            meta=meta,
            retriever=retriever,
            vector_available=True,
        )

        return BuildResult(
            doc_id=doc_id,
            doc_name=resolved_name,
            reused=False,
            chunk_count=len(chunks),
            total_pages=total_pages,
            index_path=str(index_dir),
            embedding_source=emb_source,
            embedding_model=emb_model,
            skipped_footer=stats.get("skipped_footer", 0),
            skipped_empty_figure=stats.get("skipped_empty_figure", 0),
        )

    async def ensure_loaded(self, doc_id: str) -> LoadedIndex:
        if doc_id in self._cache:
            return self._cache[doc_id]

        if not index_exists(self._index_root, doc_id):
            raise IndexNotFound(f"No FAISS index for doc_id={doc_id} under {self._index_root}")

        index_dir = index_dir_for(self._index_root, doc_id)
        meta = load_meta(index_dir)
        chunks = load_chunks(index_dir)
        faiss_index = load_faiss_index(index_dir)

        # Validate embedding compatibility (do NOT rebuild on mismatch)
        current_source = getattr(self._vllm, "embedding_source", None)
        if meta.embedding_source and current_source and meta.embedding_source != current_source:
            logger.warning(
                "Index embedding_source=%s differs from runtime=%s; "
                "query embedding must match index. Prefer rebuilding with same model.",
                meta.embedding_source,
                current_source,
            )

        retriever = HybridRetriever()
        retriever.build_bm25(chunks)
        loaded = LoadedIndex(
            doc_id=doc_id,
            chunks=chunks,
            faiss_index=faiss_index,
            meta=meta,
            retriever=retriever,
            vector_available=True,
        )
        self._cache[doc_id] = loaded
        if meta.parse_json_path:
            self._path_to_doc[str(Path(meta.parse_json_path).resolve())] = doc_id
        logger.info("Loaded index doc_id=%s chunks=%d dim=%s", doc_id, len(chunks), meta.dim)
        return loaded

    async def search(
        self,
        doc_id: str,
        query: str,
        top_k: int = 10,
        grep_terms: list[str] | None = None,
        page_range: tuple[int, int] | None = None,
        category_filter: str | None = None,
        section_filter: str | None = None,
        weights: dict[str, float] | None = None,
        grep_boost_rank: int | None = None,
        use_lexicon: bool | None = None,
    ) -> list[SearchHit]:
        loaded = await self.ensure_loaded(doc_id)

        async def _vector_search(q: str, top_k: int = 10) -> list[tuple[DocumentChunk, float]]:
            if not loaded.vector_available:
                return []
            try:
                emb = await self._vllm.embed([q])
                self._embed_call_count += 1
            except Exception as e:
                logger.error("Query embed failed: %s", e)
                return []
            vec = np.array(emb, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            scores, indices = loaded.faiss_index.search(vec, top_k)
            results: list[tuple[DocumentChunk, float]] = []
            for score, idx in zip(scores[0], indices[0]):
                if 0 <= idx < len(loaded.chunks):
                    results.append((loaded.chunks[idx], float(score)))
            return results

        return await loaded.retriever.retrieve(
            query=query,
            chunks=loaded.chunks,
            vector_search=_vector_search,
            top_k=top_k,
            grep_terms=grep_terms,
            page_range=page_range,
            category_filter=category_filter,
            section_filter=section_filter,
            weights=weights,
            grep_boost_rank=grep_boost_rank,
            use_lexicon=use_lexicon,
        )

    async def _embed_all(
        self, texts: list[str], batch_size: int = 32
    ) -> tuple[np.ndarray, str, str, int]:
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embs = await self._vllm.embed(batch)
            self._embed_call_count += 1
            all_embeddings.extend(embs)

        if not all_embeddings:
            raise RuntimeError("Embedding produced no vectors")

        mat = normalize_rows(np.array(all_embeddings, dtype=np.float32))
        source = getattr(self._vllm, "embedding_source", None) or "unknown"
        if source == "remote":
            model = settings.llm.embedding_model
        elif source == "local":
            model = settings.llm.fallback_embedding_model
        else:
            model = settings.llm.embedding_model
        return mat, source, model, int(mat.shape[1])
