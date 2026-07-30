#!/usr/bin/env python3
"""表格结构质量评分与置信度（无 torch 依赖，供解析器 / QA / merge 共用）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List

_YEAR_RE = re.compile(r"20\d{2}\s*年")
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
_NUM_RE = re.compile(r"[\d,]{4,}")


def score_table_html(text: str) -> int:
    """单张 HTML 表的质量分：行数 + 数值密度 + 文本长度。"""
    rows = text.count("<tr>")
    nums = len(_NUM_RE.findall(text))
    return rows * 100 + nums * 5 + len(text) // 20


def score_table_quality(elements: List[dict]) -> int:
    """
    表格质量分（页内最佳）。
    用于 auto 旋转回退：旋转版仅表头时分数远低于 none 版。
    """
    best = 0
    for elem in elements:
        if elem.get("category") != "table":
            continue
        best = max(best, score_table_html(elem.get("text") or ""))
    return best


def assess_single_table(
    text: str,
    *,
    rotation_applied: int = 0,
) -> Dict[str, Any]:
    """
    评估单张 HTML 表结构置信度。
    返回: confidence (high|medium|low), score, notes
    """
    text = text or ""
    rows = text.count("<tr>")
    nums = len(_NUM_RE.findall(text))
    years = _YEAR_RE.findall(text)
    colspan = text.count("colspan")
    score = score_table_html(text)
    notes: List[str] = []

    if not text.strip().startswith("<"):
        return {"confidence": "low", "score": score, "notes": ["not_html_table"]}

    if rows <= 4 and nums < 3:
        notes.append("truncated_or_header_only")
        return {"confidence": "low", "score": score, "notes": notes}

    if rotation_applied and colspan >= 2:
        notes.append("rotated_table_structure_unstable")
    if colspan >= 4 and len(set(years)) < 2 and nums >= 10:
        notes.append("colspan_year_mismatch")
    if colspan >= 3 and rows <= 8 and nums >= 15 and len(set(years)) <= 2:
        notes.append("possible_vertical_table")

    if notes:
        return {"confidence": "low", "score": score, "notes": notes}

    if rows <= 4 or (nums < 8 and rows < 8):
        notes.append("sparse_table")
        return {"confidence": "medium", "score": score, "notes": notes}

    if colspan >= 6 and len(set(years)) >= 2:
        notes.append("complex_colspan_header")
        return {"confidence": "medium", "score": score, "notes": notes}

    return {"confidence": "high", "score": score, "notes": notes}


def annotate_table_confidence(
    elements: List[dict],
    *,
    rotation_applied: int = 0,
) -> Dict[str, Any]:
    """
    给 table 元素写入 table_structure_confidence / table_quality_score，
    并返回页级聚合（取最差置信度；分数取最佳）。
    """
    page_conf = None
    page_score = 0
    all_notes: List[str] = []

    for elem in elements:
        if elem.get("category") != "table":
            continue
        info = assess_single_table(
            elem.get("text") or "",
            rotation_applied=rotation_applied,
        )
        elem["table_structure_confidence"] = info["confidence"]
        elem["table_quality_score"] = info["score"]
        if info["notes"]:
            elem["table_quality_notes"] = info["notes"]
            all_notes.extend(info["notes"])

        page_score = max(page_score, info["score"])
        if page_conf is None or _CONFIDENCE_RANK[info["confidence"]] < _CONFIDENCE_RANK[page_conf]:
            page_conf = info["confidence"]

    if page_conf is None:
        return {}

    out: Dict[str, Any] = {
        "table_structure_confidence": page_conf,
        "table_quality_score": page_score,
    }
    seen = set()
    uniq_notes = []
    for n in all_notes:
        if n not in seen:
            seen.add(n)
            uniq_notes.append(n)
    if uniq_notes:
        out["table_quality_notes"] = uniq_notes
    return out
