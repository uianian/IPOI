from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.models.prospectus import DocumentChunk

logger = logging.getLogger(__name__)


@dataclass
class IndexMeta:
    doc_id: str
    doc_name: str
    parse_json_path: str
    company_name: str = ""
    stock_code: str = ""
    listing_date: str = ""
    embedding_model: str = ""
    embedding_source: str = ""
    dim: int = 0
    chunk_count: int = 0
    total_pages: int = 0
    created_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "parse_json_path": self.parse_json_path,
            "company_name": self.company_name,
            "stock_code": self.stock_code,
            "listing_date": self.listing_date,
            "embedding_model": self.embedding_model,
            "embedding_source": self.embedding_source,
            "dim": self.dim,
            "chunk_count": self.chunk_count,
            "total_pages": self.total_pages,
            "created_at": self.created_at or datetime.now().isoformat(timespec="seconds"),
        }
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IndexMeta":
        known = {
            "doc_id",
            "doc_name",
            "parse_json_path",
            "company_name",
            "stock_code",
            "listing_date",
            "embedding_model",
            "embedding_source",
            "dim",
            "chunk_count",
            "total_pages",
            "created_at",
            "extra",
        }
        extra = dict(data.get("extra") or {})
        for k, v in data.items():
            if k not in known:
                extra[k] = v
        return cls(
            doc_id=str(data["doc_id"]),
            doc_name=str(data.get("doc_name") or ""),
            parse_json_path=str(data.get("parse_json_path") or ""),
            company_name=str(data.get("company_name") or ""),
            stock_code=str(data.get("stock_code") or ""),
            listing_date=str(data.get("listing_date") or ""),
            embedding_model=str(data.get("embedding_model") or ""),
            embedding_source=str(data.get("embedding_source") or ""),
            dim=int(data.get("dim") or 0),
            chunk_count=int(data.get("chunk_count") or 0),
            total_pages=int(data.get("total_pages") or 0),
            created_at=str(data.get("created_at") or ""),
            extra=extra,
        )


def index_dir_for(index_root: Path, doc_id: str) -> Path:
    return Path(index_root) / doc_id


def index_exists(index_root: Path, doc_id: str) -> bool:
    d = index_dir_for(index_root, doc_id)
    return (d / "index.faiss").is_file() and (d / "chunks.jsonl").is_file() and (d / "meta.json").is_file()


def save_index(
    index_dir: Path,
    faiss_index: Any,
    chunks: list[DocumentChunk],
    meta: IndexMeta,
) -> None:
    import faiss

    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(faiss_index, str(index_dir / "index.faiss"))

    with open(index_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json() + "\n")

    meta.chunk_count = len(chunks)
    if not meta.created_at:
        meta.created_at = datetime.now().isoformat(timespec="seconds")
    with open(index_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)

    logger.info("Saved FAISS index to %s (%d chunks, dim=%d)", index_dir, len(chunks), meta.dim)


def load_meta(index_dir: Path) -> IndexMeta:
    with open(index_dir / "meta.json", encoding="utf-8") as f:
        return IndexMeta.from_dict(json.load(f))


def load_chunks(index_dir: Path) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    with open(index_dir / "chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunks.append(DocumentChunk.model_validate_json(line))
    return chunks


def load_faiss_index(index_dir: Path) -> Any:
    import faiss

    return faiss.read_index(str(index_dir / "index.faiss"))


def build_faiss_from_embeddings(embeddings: np.ndarray) -> Any:
    import faiss

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        raise ValueError("embeddings must be a non-empty 2D array")
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings.astype(np.float32))
    return index


def normalize_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return mat / norms
