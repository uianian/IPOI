#!/usr/bin/env python3
"""将 full_parse.json 转为 Markdown / HTML，便于审阅解析质量。"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CATEGORY_LABELS = {
    "header": "页眉",
    "title": "标题",
    "text": "正文",
    "figure": "图片",
    "table": "表格",
    "formula": "公式",
    "figure_caption": "图注",
    "table_caption": "表注",
    "table_footnote": "表脚注",
    "page_footnote": "页脚注",
    "footer": "页脚",
}

CATEGORY_COLORS = {
    "header": "#6b7280",
    "title": "#2563eb",
    "text": "#111827",
    "figure": "#d97706",
    "table": "#059669",
    "formula": "#7c3aed",
    "figure_caption": "#92400e",
    "table_caption": "#047857",
    "table_footnote": "#065f46",
    "page_footnote": "#4b5563",
    "footer": "#9ca3af",
}


class HtmlTableParser(HTMLParser):
    """将 <table> HTML 解析为 markdown 表格。"""

    def __init__(self):
        super().__init__()
        self.rows = []
        self._current_row = []
        self._current_cell = []
        self._in_cell = False
        self._cell_attrs = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []
            self._cell_attrs = attrs
        elif tag == "br":
            self._current_cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            text = "".join(self._current_cell).strip()
            colspan = int(self._cell_attrs.get("colspan", 1))
            rowspan = int(self._cell_attrs.get("rowspan", 1))
            self._current_row.append({
                "text": text,
                "colspan": colspan,
                "rowspan": rowspan,
            })
            self._in_cell = False
        elif tag == "tr" and self._current_row:
            self.rows.append(self._current_row)

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell.append(data)


def html_table_to_markdown(table_html: str) -> str:
    parser = HtmlTableParser()
    try:
        parser.feed(table_html)
    except Exception:
        return table_html

    rows = parser.rows
    if not rows:
        return table_html

    max_cols = max(sum(cell["colspan"] for cell in row) for row in rows)
    grid = [["" for _ in range(max_cols)] for _ in range(len(rows))]

    for r, row in enumerate(rows):
        c = 0
        for cell in row:
            while c < max_cols and grid[r][c]:
                c += 1
            text = cell["text"].replace("|", "\\|").replace("\n", " ")
            grid[r][c] = text
            c += cell["colspan"]

    lines = []
    for i, row in enumerate(grid):
        lines.append("| " + " | ".join(row) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * len(row)) + " |")
    return "\n".join(lines)


def bbox_str(bbox: list) -> str:
    if not bbox:
        return "[]"
    return "[" + ", ".join(str(int(v)) for v in bbox) + "]"


def is_parse_failure(elements: list) -> bool:
    return len(elements) == 1 and not elements[0].get("bbox")


def try_recover_nested_json(text: str) -> Optional[List[dict]]:
    text = text.strip()
    if not text.startswith("[") and not text.startswith("{"):
        match = re.search(r"\[\s*\{", text)
        if match:
            text = text[match.start():]
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return None


def collect_stats(doc_result: list) -> dict:
    category_counts = Counter()
    failed_pages = []
    empty_text_counts = Counter()

    for page_data in doc_result:
        page = page_data["page"]
        elements = page_data["elements"]
        if is_parse_failure(elements):
            failed_pages.append(page)
        for elem in elements:
            cat = elem.get("category", "unknown")
            category_counts[cat] += 1
            if not (elem.get("text") or "").strip():
                empty_text_counts[cat] += 1

    return {
        "total_pages": len(doc_result),
        "total_elements": sum(category_counts.values()),
        "category_counts": dict(category_counts.most_common()),
        "failed_pages": failed_pages,
        "empty_text_counts": dict(empty_text_counts),
    }


def format_element_md(elem: dict, hide_header_footer: bool) -> Optional[str]:
    category = elem.get("category", "text")
    if hide_header_footer and category in ("header", "footer"):
        return None

    text = (elem.get("text") or "").strip()
    bbox = elem.get("bbox", [])
    label = CATEGORY_LABELS.get(category, category)
    meta = f"**[{label}]** `{bbox_str(bbox)}`"

    if category == "title":
        body = f"# {text}" if text else "> *(空标题)*"
    elif category == "header":
        body = f"#### {text}" if text else "> *(空页眉)*"
    elif category == "footer":
        body = f"*{text}*" if text else "> *(空页脚)*"
    elif category == "figure":
        body = "> 🖼️ *[图片区域 — 未提取 OCR 文本]*"
    elif category == "table":
        if text.startswith("<table"):
            body = html_table_to_markdown(text)
        else:
            body = text or "> *(空表格)*"
    elif category in ("figure_caption", "table_caption"):
        body = f"*{text}*" if text else "> *(空注释)*"
    elif category in ("page_footnote", "table_footnote"):
        body = f"> 注：{text}" if text else "> *(空脚注)*"
    elif category == "formula":
        body = f"$$\n{text}\n$$" if text else "> *(空公式)*"
    else:
        body = text or "> *(空文本)*"

    return f"{meta}\n\n{body}\n"


def format_element_html(elem: dict, hide_header_footer: bool) -> Optional[str]:
    category = elem.get("category", "text")
    if hide_header_footer and category in ("header", "footer"):
        return None

    text = elem.get("text") or ""
    bbox = elem.get("bbox", [])
    label = CATEGORY_LABELS.get(category, category)
    color = CATEGORY_COLORS.get(category, "#374151")
    meta = (
        f'<div class="meta">'
        f'<span class="badge" style="background:{color}">{html.escape(label)}</span>'
        f'<code>{html.escape(bbox_str(bbox))}</code>'
        f"</div>"
    )

    if category == "title":
        body = f"<h2>{html.escape(text)}</h2>" if text else "<p><em>(空标题)</em></p>"
    elif category == "header":
        body = f'<p class="header-text">{html.escape(text)}</p>' if text else "<p><em>(空页眉)</em></p>"
    elif category == "footer":
        body = f'<p class="footer-text">{html.escape(text)}</p>' if text else "<p><em>(空页脚)</em></p>"
    elif category == "figure":
        body = '<div class="figure-box">🖼️ 图片区域 — 未提取 OCR 文本</div>'
    elif category == "table":
        if text.startswith("<table"):
            body = f'<div class="table-wrap">{text}</div>'
        else:
            body = f"<pre>{html.escape(text)}</pre>"
    elif category in ("figure_caption", "table_caption"):
        body = f'<p class="caption">{html.escape(text)}</p>' if text else "<p><em>(空注释)</em></p>"
    elif category in ("page_footnote", "table_footnote"):
        body = f'<p class="footnote">{html.escape(text)}</p>' if text else "<p><em>(空脚注)</em></p>"
    elif category == "formula":
        body = f"<pre class=\"formula\">{html.escape(text)}</pre>" if text else "<p><em>(空公式)</em></p>"
    else:
        body = f"<p>{html.escape(text)}</p>" if text else "<p><em>(空文本)</em></p>"

    return f'<div class="element cat-{category}">{meta}{body}</div>'


def render_page_elements(page_data: dict, hide_header_footer: bool, fmt: str) -> Tuple[str, bool]:
    page = page_data["page"]
    elements = page_data["elements"]
    failed = is_parse_failure(elements)

    if failed:
        recovered = try_recover_nested_json(elements[0].get("text", ""))
        if recovered:
            elements = recovered
            failed = False

    formatter = format_element_md if fmt == "md" else format_element_html
    parts = []
    for elem in elements:
        block = formatter(elem, hide_header_footer)
        if block:
            parts.append(block)

    return "\n".join(parts), failed


def build_summary_md(stats: dict, source_name: str) -> str:
    lines = [
        f"# PDF 解析审阅：{source_name}",
        "",
        "## 统计摘要",
        "",
        f"- 总页数：**{stats['total_pages']}**",
        f"- 总元素数：**{stats['total_elements']}**",
        f"- 解析失败页：{stats['failed_pages'] or '无'}",
        "",
        "### 元素类型分布",
        "",
        "| 类型 | 数量 | 空文本数 |",
        "| --- | ---: | ---: |",
    ]
    for cat, count in stats["category_counts"].items():
        label = CATEGORY_LABELS.get(cat, cat)
        empty = stats["empty_text_counts"].get(cat, 0)
        lines.append(f"| {label} (`{cat}`) | {count} | {empty} |")
    lines.append("")
    return "\n".join(lines)


def build_summary_html(stats: dict, source_name: str) -> str:
    rows = ""
    for cat, count in stats["category_counts"].items():
        label = CATEGORY_LABELS.get(cat, cat)
        empty = stats["empty_text_counts"].get(cat, 0)
        color = CATEGORY_COLORS.get(cat, "#374151")
        rows += (
            f"<tr><td><span class='badge' style='background:{color}'>{html.escape(label)}</span>"
            f" <code>{html.escape(cat)}</code></td>"
            f"<td>{count}</td><td>{empty}</td></tr>"
        )
    failed = ", ".join(str(p) for p in stats["failed_pages"]) or "无"
    return f"""
<section class="summary">
  <h1>PDF 解析审阅：{html.escape(source_name)}</h1>
  <ul>
    <li>总页数：<strong>{stats['total_pages']}</strong></li>
    <li>总元素数：<strong>{stats['total_elements']}</strong></li>
    <li>解析失败页：{html.escape(failed)}</li>
  </ul>
  <h2>元素类型分布</h2>
  <table class="stats-table">
    <thead><tr><th>类型</th><th>数量</th><th>空文本数</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: "PingFang SC", "Noto Sans CJK SC", sans-serif; max-width: 980px; margin: 0 auto; padding: 24px; line-height: 1.6; color: #111827; background: #f9fafb; }}
  .summary {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; }}
  .page {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; }}
  .page.failed {{ border-color: #fca5a5; background: #fff7f7; }}
  .page h2 {{ margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
  .element {{ margin: 14px 0; padding: 12px; border-left: 4px solid #e5e7eb; background: #fcfcfd; border-radius: 0 8px 8px 0; }}
  .meta {{ margin-bottom: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
  .badge {{ color: #fff; font-size: 12px; padding: 2px 8px; border-radius: 999px; }}
  .header-text {{ color: #6b7280; font-weight: 600; margin: 0; }}
  .footer-text {{ color: #9ca3af; text-align: center; margin: 0; }}
  .caption {{ color: #374151; font-style: italic; margin: 0; }}
  .footnote {{ color: #4b5563; font-size: 14px; margin: 0; padding-left: 12px; border-left: 3px solid #d1d5db; }}
  .figure-box {{ border: 2px dashed #f59e0b; background: #fffbeb; color: #92400e; padding: 24px; text-align: center; border-radius: 8px; }}
  .table-wrap {{ overflow-x: auto; }}
  .table-wrap table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  .table-wrap td, .table-wrap th {{ border: 1px solid #d1d5db; padding: 6px 8px; vertical-align: top; }}
  .stats-table {{ width: 100%; border-collapse: collapse; }}
  .stats-table th, .stats-table td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; }}
  .warn {{ color: #b91c1c; font-weight: 600; }}
  .cat-title {{ border-left-color: #2563eb; }}
  .cat-table {{ border-left-color: #059669; }}
  .cat-figure {{ border-left-color: #d97706; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def convert_to_markdown(
    doc_result: list,
    source_name: str,
    hide_header_footer: bool = False,
    page_range: Optional[Tuple[int, int]] = None,
) -> str:
    stats = collect_stats(doc_result)
    parts = [build_summary_md(stats, source_name)]

    for page_data in doc_result:
        page = page_data["page"]
        if page_range and not (page_range[0] <= page <= page_range[1]):
            continue

        content, failed = render_page_elements(page_data, hide_header_footer, "md")
        parts.append(f"\n---\n\n## 第 {page} 页")
        if failed:
            parts.append("\n> ⚠️ **本页 JSON 解析失败，以下为原始输出**\n")
        parts.append(content)

    return "\n".join(parts) + "\n"


def convert_to_html(
    doc_result: list,
    source_name: str,
    hide_header_footer: bool = False,
    page_range: Optional[Tuple[int, int]] = None,
) -> str:
    stats = collect_stats(doc_result)
    body_parts = [build_summary_html(stats, source_name)]

    for page_data in doc_result:
        page = page_data["page"]
        if page_range and not (page_range[0] <= page <= page_range[1]):
            continue

        content, failed = render_page_elements(page_data, hide_header_footer, "html")
        cls = "page failed" if failed else "page"
        warn = '<p class="warn">⚠️ 本页 JSON 解析失败，以下为原始/恢复输出</p>' if failed else ""
        body_parts.append(
            f'<section class="{cls}"><h2>第 {page} 页</h2>{warn}{content}</section>'
        )

    body = "\n".join(body_parts)
    return HTML_TEMPLATE.format(title=f"Parse Review - {source_name}", body=body)


def parse_page_range(value: str) -> Tuple[int, int]:
    if "-" in value:
        start, end = value.split("-", 1)
        return int(start), int(end)
    page = int(value)
    return page, page


def main():
    parser = argparse.ArgumentParser(description="将 full_parse.json 转为 Markdown / HTML 审阅报告")
    parser.add_argument("json_path", help="full_parse.json 路径")
    parser.add_argument(
        "--format", choices=["md", "html", "both"], default="both", help="输出格式"
    )
    parser.add_argument(
        "--hide-header-footer", action="store_true", help="隐藏页眉/页脚，便于阅读正文"
    )
    parser.add_argument(
        "--page-range", type=str, default=None, help="仅导出指定页，如 1-20 或 5"
    )
    parser.add_argument(
        "-o", "--output-dir", type=str, default=None, help="输出目录，默认与 JSON 同目录"
    )
    args = parser.parse_args()

    json_path = Path(args.json_path)
    out_dir = Path(args.output_dir) if args.output_dir else json_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(json_path, encoding="utf-8") as f:
        doc_result = json.load(f)

    source_name = json_path.parent.name or json_path.stem
    page_range = parse_page_range(args.page_range) if args.page_range else None
    suffix = ""
    if page_range:
        suffix = f"_p{page_range[0]}-{page_range[1]}"

    if args.format in ("md", "both"):
        md_path = out_dir / f"full_parse_review{suffix}.md"
        md_content = convert_to_markdown(
            doc_result, source_name, args.hide_header_footer, page_range
        )
        md_path.write_text(md_content, encoding="utf-8")
        print(f"Markdown: {md_path}")

    if args.format in ("html", "both"):
        html_path = out_dir / f"full_parse_review{suffix}.html"
        html_content = convert_to_html(
            doc_result, source_name, args.hide_header_footer, page_range
        )
        html_path.write_text(html_content, encoding="utf-8")
        print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
