from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def grep_parse_json(
    parse_json: Path | str,
    keywords: list[str],
    *,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """在 full_parse.json / risk_chunks.json 上做关键词召回（新工具，不改上游）。"""
    path = Path(parse_json)
    if not path.is_file():
        logger.warning("parse json missing: %s", path)
        return []

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    chunks: list[dict[str, Any]] = []
    if isinstance(data, list):
        chunks = data
    elif isinstance(data, dict):
        # full_parse.json: pages -> elements
        pages = data.get("pages") or data.get("content") or []
        if isinstance(pages, list):
            for page in pages:
                page_no = page.get("page") or page.get("page_number") or page.get("page_idx")
                for el in page.get("elements") or page.get("items") or []:
                    text = el.get("text") or el.get("content") or el.get("html") or ""
                    if not text:
                        continue
                    chunks.append(
                        {
                            "page": page_no if page_no is not None else el.get("page"),
                            "excerpt": text,
                            "category": el.get("category") or el.get("type") or "text",
                            "content": text,
                        }
                    )
        # also allow risk_chunks-like under key
        for key in ("risk_chunks", "chunks", "elements"):
            if isinstance(data.get(key), list):
                chunks.extend(data[key])

    hits: list[dict[str, Any]] = []
    for ch in chunks:
        text = ch.get("content") or ch.get("excerpt") or ch.get("text") or ""
        matched = [k for k in keywords if k in text]
        if not matched:
            continue
        hits.append(
            {
                "page": ch.get("page") or ch.get("page_number"),
                "excerpt": text[:500],
                "content": text[:500],
                "category": ch.get("type") or ch.get("category") or "text",
                "match_sources": ["parse_grep"],
                "matched_keywords": matched,
                "score": float(len(matched)),
            }
        )
    hits.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return hits[:top_k]


def merge_hits(*groups: list[dict[str, Any]], top_k: int = 12) -> list[dict[str, Any]]:
    seen: set[tuple[Any, str]] = set()
    out: list[dict[str, Any]] = []
    for group in groups:
        for h in group:
            key = (h.get("page"), (h.get("excerpt") or "")[:60])
            if key in seen:
                continue
            seen.add(key)
            out.append(h)
    return out[:top_k]
