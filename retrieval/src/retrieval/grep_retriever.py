from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from src.models.prospectus import DocumentChunk

logger = logging.getLogger(__name__)

_LEXICON_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "grep_lexicon.yaml"


def load_default_lexicon() -> list[str]:
    if not _LEXICON_PATH.exists():
        return []
    with open(_LEXICON_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    terms = data.get("terms") or []
    return [str(t) for t in terms if t]


def _collect_terms(query: str, grep_terms: list[str] | None, use_lexicon: bool) -> list[str]:
    terms: list[str] = []
    if grep_terms:
        terms.extend(grep_terms)
    # split query on whitespace / punctuation for short keyword hits
    for part in re.split(r"[\s,，;；|/]+", query or ""):
        part = part.strip()
        if len(part) >= 2:
            terms.append(part)
    # lexicon: only terms that actually appear in the query (avoid polluting semantic search)
    if use_lexicon and query:
        for lex in load_default_lexicon():
            if lex and lex in query:
                terms.append(lex)
    # dedupe preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def grep_search(
    chunks: list[DocumentChunk],
    query: str,
    grep_terms: list[str] | None = None,
    use_lexicon: bool = True,
    top_k: int = 40,
) -> list[tuple[DocumentChunk, float, list[str]]]:
    """Substring Grep over chunk content. Returns (chunk, score, matched_terms)."""
    terms = _collect_terms(query, grep_terms, use_lexicon)
    if not terms:
        return []

    scored: list[tuple[DocumentChunk, float, list[str]]] = []
    for chunk in chunks:
        content = chunk.content
        matched = [t for t in terms if t in content]
        if matched:
            scored.append((chunk, float(len(matched)), matched))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
