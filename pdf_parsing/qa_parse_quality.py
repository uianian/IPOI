#!/usr/bin/env python3
"""
解析质量门禁：扫描 full_parse.json，输出需重跑/复核的问题页列表。

检测标签：
  - parse_failed / truncated / empty_page
  - missing_table_high_numeric（高数值密度 text、无 table — 附录财务页典型）
  - vertical_table_low_structure（竖表结构低置信）
  - table_structure_low / table_structure_medium
  - empty_bbox

用法：
  python qa_parse_quality.py output/mixue/full_parse.json
  python qa_parse_quality.py output/mixue/full_parse.json -o output/mixue/qa_report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

# 允许从同目录 import pdf_parser_pro 的评估函数（可选增强）
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

try:
    from table_quality import annotate_table_confidence
except ImportError:
    annotate_table_confidence = None  # type: ignore


_NUM_RE = re.compile(r"[\d,]{4,}")
_APPENDIX_MARKERS = ("附錄", "附录", "會計師報告", "会计师报告", "人民幣千元", "人民币千元")


def _page_text_blob(page: dict) -> str:
    parts = []
    for e in page.get("elements", []):
        if e.get("category") in ("text", "title", "header", "table_caption"):
            parts.append(e.get("text") or "")
    return "\n".join(parts)


def _looks_like_raw_json_dump(text: str) -> bool:
    t = (text or "").strip()
    return '"bbox"' in t and '"category"' in t and t.startswith(("[", "{", "\n["))


def _ensure_confidence(page: dict) -> dict:
    """若旧 JSON 无置信度字段，现场补算（就地写入 page）。"""
    if page.get("table_structure_confidence"):
        return page
    if annotate_table_confidence is None:
        return page
    elems = page.get("elements") or []
    has_table = any(e.get("category") == "table" for e in elems)
    if not has_table:
        return page
    meta = annotate_table_confidence(
        elems, rotation_applied=page.get("rotation_applied") or 0
    )
    page.update(meta)
    return page


def scan_page(page: dict) -> List[Dict[str, Any]]:
    """返回该页命中的 issue 列表（可为空）。"""
    issues: List[Dict[str, Any]] = []
    pnum = page.get("page")
    status = page.get("parse_status", "ok")
    elems = page.get("elements") or []

    if status not in (None, "ok", "unknown"):
        issues.append(
            {
                "page": pnum,
                "tag": "parse_failed",
                "severity": "high",
                "detail": f"parse_status={status}",
            }
        )

    if page.get("truncated"):
        issues.append(
            {
                "page": pnum,
                "tag": "truncated",
                "severity": "medium",
                "detail": "模型输出被截断修复",
            }
        )

    if not elems:
        issues.append(
            {
                "page": pnum,
                "tag": "empty_page",
                "severity": "high",
                "detail": "elements 为空",
            }
        )
        return issues

    # 旧版 raw-json 兜底
    if len(elems) == 1:
        e0 = elems[0]
        if not e0.get("bbox") and _looks_like_raw_json_dump(e0.get("text") or ""):
            issues.append(
                {
                    "page": pnum,
                    "tag": "parse_failed",
                    "severity": "high",
                    "detail": "整页 raw JSON 兜底，无有效 bbox",
                }
            )

    empty_bbox = sum(
        1 for e in elems if not (isinstance(e.get("bbox"), list) and len(e["bbox"]) == 4)
    )
    if empty_bbox:
        issues.append(
            {
                "page": pnum,
                "tag": "empty_bbox",
                "severity": "medium" if empty_bbox < len(elems) else "high",
                "detail": f"{empty_bbox}/{len(elems)} 元素缺少 bbox",
            }
        )

    page = _ensure_confidence(page)
    elems = page.get("elements") or []
    has_table = any(e.get("category") == "table" for e in elems)
    blob = _page_text_blob(page)
    nums = len(_NUM_RE.findall(blob))
    lines = [ln for ln in blob.splitlines() if ln.strip()]
    appendix_hint = any(m in blob for m in _APPENDIX_MARKERS) or any(
        m in (e.get("text") or "")
        for e in elems
        for m in ("附錄", "附录")
        if e.get("category") == "header"
    )

    # 无 table 但高数值密度（附录财务报表典型回归）
    if not has_table and nums >= 30 and len(lines) >= 15:
        issues.append(
            {
                "page": pnum,
                "tag": "missing_table_high_numeric",
                "severity": "high",
                "detail": f"无 table，text 中约 {nums} 个数值字段、{len(lines)} 行",
                "suggest_reparse": True,
            }
        )
    elif (
        not has_table
        and appendix_hint
        and nums >= 15
        and ("人民幣千元" in blob or "人民币千元" in blob)
    ):
        issues.append(
            {
                "page": pnum,
                "tag": "missing_table_high_numeric",
                "severity": "high",
                "detail": f"附录页疑似财务表丢失 table 结构（nums={nums}）",
                "suggest_reparse": True,
            }
        )

    conf = page.get("table_structure_confidence")
    notes = page.get("table_quality_notes") or []
    if conf == "low":
        tag = "vertical_table_low_structure" if any(
            n in notes
            for n in (
                "rotated_table_structure_unstable",
                "possible_vertical_table",
                "colspan_year_mismatch",
                "truncated_or_header_only",
            )
        ) else "table_structure_low"
        issues.append(
            {
                "page": pnum,
                "tag": tag,
                "severity": "high" if tag == "vertical_table_low_structure" else "medium",
                "detail": f"score={page.get('table_quality_score')}, notes={notes}",
                "suggest_reparse": tag == "vertical_table_low_structure",
            }
        )
    elif conf == "medium":
        issues.append(
            {
                "page": pnum,
                "tag": "table_structure_medium",
                "severity": "low",
                "detail": f"score={page.get('table_quality_score')}, notes={notes}",
            }
        )

    return issues


def build_report(doc: List[dict]) -> Dict[str, Any]:
    all_issues: List[Dict[str, Any]] = []
    for page in doc:
        _ensure_confidence(page)
        all_issues.extend(scan_page(page))

    by_tag = Counter(i["tag"] for i in all_issues)
    reparse_pages = sorted(
        {
            i["page"]
            for i in all_issues
            if i.get("suggest_reparse")
            or i["tag"] in ("parse_failed", "empty_page", "missing_table_high_numeric")
        }
    )
    review_pages = sorted(
        {
            i["page"]
            for i in all_issues
            if i["tag"]
            in (
                "vertical_table_low_structure",
                "table_structure_low",
                "truncated",
                "empty_bbox",
            )
        }
    )

    conf_pages = Counter(
        p.get("table_structure_confidence")
        for p in doc
        if p.get("table_structure_confidence")
    )

    return {
        "total_pages": len(doc),
        "issue_count": len(all_issues),
        "issues_by_tag": dict(by_tag),
        "table_structure_confidence_pages": dict(conf_pages),
        "reparse_pages": reparse_pages,
        "reparse_pages_csv": ",".join(str(p) for p in reparse_pages),
        "review_pages": review_pages,
        "issues": all_issues,
    }


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        description="扫描 full_parse.json，生成解析质量 QA 报告",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("input", help="full_parse.json 路径")
    ap.add_argument(
        "-o",
        "--output",
        default=None,
        help="qa_report.json 输出路径（默认与 input 同目录）",
    )
    ap.add_argument(
        "--markdown",
        action="store_true",
        help="额外写出 qa_report.md 摘要",
    )
    ap.add_argument(
        "--write-confidence",
        action="store_true",
        help="将补算的 table_structure_confidence 写回 full_parse.json（原地更新）",
    )
    args = ap.parse_args(argv)

    in_path = Path(args.input)
    doc = json.loads(in_path.read_text(encoding="utf-8"))
    if not isinstance(doc, list):
        raise SystemExit("期望 full_parse.json 为页数组")

    report = build_report(doc)

    if args.write_confidence:
        in_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已写回置信度字段: {in_path}")

    out_path = Path(args.output) if args.output else in_path.parent / "qa_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"总页数: {report['total_pages']}")
    print(f"问题条数: {report['issue_count']}")
    print(f"按标签: {report['issues_by_tag']}")
    print(f"表格置信度页数: {report['table_structure_confidence_pages']}")
    print(f"建议重跑页 ({len(report['reparse_pages'])}): {report['reparse_pages_csv'] or '(无)'}")
    print(f"报告: {out_path}")

    if args.markdown:
        md_path = out_path.with_suffix(".md")
        lines = [
            "# 解析质量 QA 报告",
            "",
            f"- 输入: `{in_path}`",
            f"- 总页数: {report['total_pages']}",
            f"- 问题条数: {report['issue_count']}",
            f"- 建议重跑: `{report['reparse_pages_csv'] or '无'}`",
            "",
            "## 按标签统计",
            "",
            "| 标签 | 次数 |",
            "| --- | ---: |",
        ]
        for tag, cnt in sorted(report["issues_by_tag"].items(), key=lambda x: -x[1]):
            lines.append(f"| `{tag}` | {cnt} |")
        lines.extend(["", "## 问题明细", ""])
        for iss in report["issues"]:
            lines.append(
                f"- **p{iss['page']}** `{iss['tag']}` [{iss['severity']}] {iss.get('detail', '')}"
            )
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()
