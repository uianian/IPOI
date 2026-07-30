"""preview.md 清洗 + ParseStats 映射。"""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

# ![figure](figures/p0144_fig001.png) → 占位文本
_FIGURE_MD_RE = re.compile(
    r"!\[figure\]\((?:figures/)?p(\d+)_fig\d+\.png\)",
    re.IGNORECASE,
)
# 更宽的防御：任意 figures/ 或本地路径的 figure 图片
_ANY_FIGURE_RE = re.compile(
    r"!\[([^\]]*)\]\((?:figures/|[./]*figures/)([^)]+)\)",
    re.IGNORECASE,
)


def clean_preview_markdown(text: str, *, anchors: bool = False) -> str:
    """幂等清洗：去掉图片路径引用，可选加页锚点。"""

    def _repl_named(m: re.Match[str]) -> str:
        page = int(m.group(1))
        return f"> 图表 — 第 {page} 页（图像未随结果返回）"

    out = _FIGURE_MD_RE.sub(_repl_named, text)
    out = _ANY_FIGURE_RE.sub("> 图表（图像未随结果返回）", out)

    if anchors:
        out = re.sub(
            r"(?m)^(## 第 (\d+) 页)\s*$",
            r'<a id="page-\2"></a>\n\n\1',
            out,
        )
    return out


def summary_to_parse_stats(summary: Dict[str, Any]) -> Dict[str, int]:
    """parse_summary.json → 契约 ParseStats。textChunkCount = 正文块数。"""
    cats = summary.get("categories") or {}
    total = int(summary.get("total_pages") or 0)
    failed = set(summary.get("failed_pages") or [])
    empty = set(summary.get("empty_pages") or [])
    bad = failed | empty
    text_n = int(cats.get("text") or 0)
    title_n = int(cats.get("title") or 0)
    return {
        "totalPages": total,
        "parsedPages": max(total - len(bad), 0),
        "chartCount": int(cats.get("figure") or 0),
        "tableCount": int(cats.get("table") or 0),
        "textChunkCount": text_n + title_n,
    }


def slice_markdown_by_pages(
    markdown: str, page_from: int | None, page_to: int | None
) -> str:
    """按 `## 第 N 页` 切段；两端闭区间。"""
    if page_from is None and page_to is None:
        return markdown
    parts = re.split(r"(?m)(?=^## 第 \d+ 页\s*$)", markdown)
    kept: list[str] = []
    for part in parts:
        m = re.match(r"^## 第 (\d+) 页\s*$", part, re.MULTILINE)
        if not m:
            if not kept and part.strip():
                # 文首前言
                if page_from is None or page_from <= 1:
                    kept.append(part)
            continue
        n = int(m.group(1))
        if page_from is not None and n < page_from:
            continue
        if page_to is not None and n > page_to:
            continue
        kept.append(part)
    return "".join(kept).lstrip("\n")


def build_result_payload(
    *,
    task_id: str,
    project_id: str,
    summary: Dict[str, Any],
    preview_md: str,
    completed_at: str,
    timing: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    markdown = clean_preview_markdown(preview_md)
    return {
        "taskId": task_id,
        "projectId": project_id,
        "mode": "expert",
        "status": "completed",
        "stats": summary_to_parse_stats(summary),
        "markdown": markdown,
        "parseSummary": summary,
        "timing": timing or {},
        "completedAt": completed_at,
    }
