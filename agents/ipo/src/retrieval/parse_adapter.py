from __future__ import annotations

import json
import logging
from pathlib import Path

from src.models.prospectus import DocumentChunk

logger = logging.getLogger(__name__)


def load_full_parse(parse_json_path: str | Path) -> list[dict]:
    path = Path(parse_json_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"full_parse.json not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected list of pages in {path}")
    return data


def should_skip_element(category: str, text: str) -> bool:
    if category == "footer":
        return True
    if category == "figure" and not text.strip():
        return True
    return False


def full_parse_to_chunks(
    parse_json_path: str | Path,
    doc_id: str,
) -> tuple[list[DocumentChunk], int, dict[str, int]]:
    """Convert Infinity full_parse.json into indexable DocumentChunks.

    Skips footer and empty-text figures. Returns (chunks, total_pages, stats).
    """
    pages = load_full_parse(parse_json_path)
    chunks: list[DocumentChunk] = []
    skipped_footer = 0
    skipped_empty_figure = 0

    for page_data in pages:
        page_num = int(page_data.get("page", 0) or 0)
        parse_status = page_data.get("parse_status") or "unknown"
        elements = page_data.get("elements") or []

        for elem_index, elem in enumerate(elements):
            category = elem.get("category") or "text"
            text = elem.get("text") or ""
            bbox = elem.get("bbox") if isinstance(elem.get("bbox"), list) else []

            if category == "footer":
                skipped_footer += 1
                continue
            if category == "figure" and not text.strip():
                skipped_empty_figure += 1
                continue
            if not text.strip():
                # skip other empty elements (cannot satisfy DocumentChunk.min_length)
                continue

            chunk_type = "table" if category == "table" else "text"
            chunk_id = f"{doc_id}_p{page_num}_e{elem_index}"
            metadata = {
                "bbox": bbox,
                "category": category,
                "parse_status": parse_status,
                "elem_index": elem_index,
            }
            image_path = elem.get("image_path")
            if image_path:
                metadata["image_path"] = image_path
            if not bbox:
                metadata["parse_degraded"] = True

            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    page_number=max(page_num, 1),
                    paragraph_index=elem_index,
                    section_title=None,
                    content=text,
                    token_count=max(1, len(text) // 2),
                    chunk_type=chunk_type,
                    metadata=metadata,
                )
            )

    stats = {
        "skipped_footer": skipped_footer,
        "skipped_empty_figure": skipped_empty_figure,
        "chunk_count": len(chunks),
    }
    logger.info(
        "Parsed %s → %d chunks (skip footer=%d empty_figure=%d)",
        parse_json_path,
        len(chunks),
        skipped_footer,
        skipped_empty_figure,
    )
    return chunks, len(pages), stats
