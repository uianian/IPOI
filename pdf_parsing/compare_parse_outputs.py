#!/usr/bin/env python3
"""对比两份 full_parse.json（同页），生成 markdown 报告。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def load_pages(path: Path, max_pages: int | None = None) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if max_pages is not None:
        return data[:max_pages]
    return data


def page_stats(page: dict) -> dict:
    elems = page.get("elements", [])
    cats = Counter(e.get("category", "?") for e in elems)
    text_chars = sum(len(e.get("text") or "") for e in elems)
    tables = [e for e in elems if e.get("category") == "table"]
    html_tables = sum(1 for t in tables if (t.get("text") or "").strip().startswith("<"))
    return {
        "elements": len(elems),
        "categories": dict(cats),
        "text_chars": text_chars,
        "tables": len(tables),
        "html_tables": html_tables,
        "parse_status": page.get("parse_status", "unknown"),
    }


def compare_pages(a_pages: List[dict], b_pages: List[dict], label_a: str, label_b: str) -> str:
    n = min(len(a_pages), len(b_pages))
    lines = [
        f"# 解析输出同页对比",
        "",
        f"- **A ({label_a})**：{len(a_pages)} 页",
        f"- **B ({label_b})**：{len(b_pages)} 页",
        f"- **对比范围**：前 {n} 页",
        "",
        "## 全书摘要",
        "",
        "| 指标 | A | B |",
        "| --- | ---: | ---: |",
    ]

    def agg(pages: List[dict]) -> dict:
        elems = sum(len(p.get("elements", [])) for p in pages)
        failed = [p["page"] for p in pages if p.get("parse_status") not in (None, "ok", "unknown")]
        # legacy: no parse_status field means ok
        failed_legacy = []
        for p in pages:
            if "parse_status" in p and p["parse_status"] != "ok":
                failed_legacy.append(p["page"])
            elif len(p.get("elements", [])) == 1:
                e = p["elements"][0]
                if not e.get("bbox") and _looks_like_raw_json(e.get("text", "")):
                    failed_legacy.append(p["page"])
        tables = sum(
            1 for p in pages for e in p.get("elements", [])
            if e.get("category") == "table"
        )
        html_tables = sum(
            1 for p in pages for e in p.get("elements", [])
            if e.get("category") == "table" and (e.get("text") or "").strip().startswith("<")
        )
        return {
            "pages": len(pages),
            "elements": elems,
            "failed": failed_legacy,
            "tables": tables,
            "html_tables": html_tables,
        }

    sa, sb = agg(a_pages), agg(b_pages)
    lines.extend([
        f"| 总页数 | {sa['pages']} | {sb['pages']} |",
        f"| 总元素 | {sa['elements']} | {sb['elements']} |",
        f"| 表格数 | {sa['tables']} | {sb['tables']} |",
        f"| HTML 表格 | {sa['html_tables']} | {sb['html_tables']} |",
        f"| 失败/异常页 | {sa['failed'] or '无'} | {sb['failed'] or '无'} |",
        "",
        "## 逐页差异（元素数 / 表格 / 状态）",
        "",
        "| 页 | A元素 | B元素 | A表 | B表 | A状态 | B状态 | 备注 |",
        "| ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ])

    for i in range(n):
        pa, pb = a_pages[i], b_pages[i]
        sa_p, sb_p = page_stats(pa), page_stats(pb)
        notes = []
        if sa_p["elements"] != sb_p["elements"]:
            notes.append("元素数不同")
        if sa_p["tables"] != sb_p["tables"]:
            notes.append("表格数不同")
        if sa_p["parse_status"] != sb_p["parse_status"]:
            notes.append("状态不同")
        lines.append(
            f"| {pa['page']} | {sa_p['elements']} | {sb_p['elements']} | "
            f"{sa_p['tables']} | {sb_p['tables']} | {sa_p['parse_status']} | "
            f"{sb_p['parse_status']} | {'; '.join(notes) or '-'} |"
        )

    lines.extend(["", "## 典型页抽样", ""])
    sample_pages = [1, 4, 7, 15, 16]
    for pnum in sample_pages:
        if pnum > n:
            continue
        pa, pb = a_pages[pnum - 1], b_pages[pnum - 1]
        lines.append(f"### 第 {pnum} 页")
        lines.append("")
        lines.append(_sample_page_block(pa, label_a))
        lines.append("")
        lines.append(_sample_page_block(pb, label_b))
        lines.append("")

    return "\n".join(lines)


def _looks_like_raw_json(text: str) -> bool:
    t = text.strip()
    return t.startswith("[{") and '"bbox"' in t


def _sample_page_block(page: dict, label: str) -> str:
    lines = [f"**{label}** — 元素 {len(page.get('elements', []))}，状态 `{page.get('parse_status', 'legacy')}`"]
    for e in page.get("elements", [])[:5]:
        cat = e.get("category", "?")
        text = (e.get("text") or "").replace("\n", " ")[:120]
        bbox = e.get("bbox", [])
        lines.append(f"- `{cat}` {bbox}: {text}...")
    tables = [e for e in page.get("elements", []) if e.get("category") == "table"]
    if tables:
        t0 = (tables[0].get("text") or "")[:200]
        fmt = "HTML" if t0.strip().startswith("<") else "Markdown/其他"
        lines.append(f"- 首表格式: **{fmt}** — `{t0[:100]}...`")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="对比两份 PDF 解析 JSON 输出")
    ap.add_argument("--a", required=True, help="新输出 full_parse.json")
    ap.add_argument("--b", required=True, help="基准 full_parse.json")
    ap.add_argument("--label-a", default="pdf_parser_pro")
    ap.add_argument("--label-b", default="parse_prospectus")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("-o", "--output", required=True, help="对比报告 markdown 路径")
    args = ap.parse_args()

    a_pages = load_pages(Path(args.a), args.max_pages)
    b_pages = load_pages(Path(args.b), args.max_pages)
    report = compare_pages(a_pages, b_pages, args.label_a, args.label_b)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"对比报告: {out}")


if __name__ == "__main__":
    main()
