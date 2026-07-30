from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.models.prospectus import DocumentChunk
from src.retrieval.section_map import SectionMap, build_section_map

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
    section_map: SectionMap | None = None,
) -> tuple[list[DocumentChunk], int, dict[str, Any]]:
    """Convert Infinity full_parse.json into indexable DocumentChunks.

    Skips footer and empty-text figures. Returns (chunks, total_pages, stats).
    """
    pages = load_full_parse(parse_json_path)
    resolved_section_map = section_map or build_section_map(pages)
    chunks: list[DocumentChunk] = []
    skipped_footer = 0
    skipped_empty_figure = 0

    for page_data in pages:
        page_num = int(page_data.get("page", 0) or 0)
        parse_status = page_data.get("parse_status") or "unknown"
        elements = page_data.get("elements") or []
        section_span = resolved_section_map.section_for_page(page_num)

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
                "element_category": category,
                "parse_status": parse_status,
                "elem_index": elem_index,
            }
            if section_span is not None:
                metadata.update(
                    {
                        "section_id": section_span.canonical_section,
                        "section_title": section_span.display_title,
                        "section_level": section_span.level,
                        "section_start_page": section_span.start_page,
                        "section_end_page": section_span.end_page,
                        "section_confidence": section_span.confidence,
                        "page_role": (
                            "appendix"
                            if section_span.canonical_section.startswith("appendix_")
                            else section_span.canonical_section
                        ),
                    }
                )
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
                    section_title=(
                        section_span.canonical_section if section_span is not None else None
                    ),
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
        "section_count": len(resolved_section_map.section_spans),
        "section_map": resolved_section_map.to_dict(),
    }
    logger.info(
        "Parsed %s → %d chunks (skip footer=%d empty_figure=%d)",
        parse_json_path,
        len(chunks),
        skipped_footer,
        skipped_empty_figure,
    )
    return chunks, len(pages), stats
