#!/usr/bin/env python3
"""Build a section map and compare it with the source full_parse.json."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.section_map import (  # noqa: E402
    build_section_map,
    save_section_map,
)


def _raw_anchor_evidence(
    pages: list[dict[str, Any]], page_no: int
) -> list[dict[str, Any]]:
    page = next((item for item in pages if int(item.get("page") or 0) == page_no), {})
    evidence: list[dict[str, Any]] = []
    for idx, element in enumerate(page.get("elements") or []):
        if element.get("category") not in {"header", "title"}:
            continue
        text = str(element.get("text") or "").strip()
        if text:
            evidence.append(
                {
                    "element_index": idx,
                    "category": element.get("category"),
                    "text": text,
                    "bbox": element.get("bbox") or [],
                }
            )
    return evidence


def build_quality_payload(
    pages: list[dict[str, Any]], doc_name: str
) -> tuple[dict[str, Any], Any]:
    section_map = build_section_map(pages)
    span_by_id = {span.canonical_section: span for span in section_map.section_spans}
    aligned = []
    offsets = []
    unresolved = []
    for entry in section_map.toc_entries:
        span = span_by_id.get(entry.canonical_section or "")
        raw_numeric = (
            int(entry.target_page_raw) if entry.target_page_raw.isdigit() else None
        )
        if span and raw_numeric is not None:
            offset = span.start_page - raw_numeric
            offsets.append(offset)
            aligned.append(
                {
                    "title": entry.title,
                    "canonical_section": entry.canonical_section,
                    "toc_page": raw_numeric,
                    "actual_pdf_page": span.start_page,
                    "offset": offset,
                }
            )
        elif not entry.canonical_section:
            unresolved.append(
                {
                    "title": entry.title,
                    "target_page_raw": entry.target_page_raw,
                    "source_page": entry.source_page,
                }
            )

    expected = {
        "summary",
        "risk_factors",
        "business",
        "financial_information",
        "appendix_one",
    }
    found = expected & set(span_by_id)
    anchor_samples = []
    ranked = sorted(
        section_map.section_spans,
        key=lambda span: (-span.confidence, span.start_page),
    )
    for span in ranked[:8]:
        anchor_samples.append(
            {
                "canonical_section": span.canonical_section,
                "start_page": span.start_page,
                "end_page": span.end_page,
                "confidence": span.confidence,
                "raw_elements": _raw_anchor_evidence(pages, span.start_page),
            }
        )

    payload = {
        "doc_name": doc_name,
        "source_page_count": len(pages),
        "section_map_version": section_map.version,
        "toc": {
            "pages": section_map.toc_pages,
            "entry_count": len(section_map.toc_entries),
            "canonicalized_count": sum(
                1 for entry in section_map.toc_entries if entry.canonical_section
            ),
            "resolved_page_count": sum(
                1 for entry in section_map.toc_entries if entry.target_page is not None
            ),
            "unresolved_entries": unresolved,
        },
        "alignment": {
            "matched_count": len(aligned),
            "page_offset_median": (
                statistics.median(offsets) if offsets else None
            ),
            "page_offset_min": min(offsets) if offsets else None,
            "page_offset_max": max(offsets) if offsets else None,
            "entries": aligned,
        },
        "coverage": {
            "required_sections": sorted(expected),
            "found_sections": sorted(found),
            "missing_sections": sorted(expected - found),
            "required_coverage": round(len(found) / len(expected), 4),
            "all_span_count": len(section_map.section_spans),
        },
        "conflicts": section_map.conflicts,
        "anchor_samples_from_full_parse": anchor_samples,
        "section_spans": [
            {
                "canonical_section": span.canonical_section,
                "display_title": span.display_title,
                "start_page": span.start_page,
                "end_page": span.end_page,
                "confidence": span.confidence,
                "anchor_source": span.anchor_source,
            }
            for span in section_map.section_spans
        ],
    }
    return payload, section_map


def render_markdown(payload: dict[str, Any]) -> str:
    toc = payload["toc"]
    coverage = payload["coverage"]
    alignment = payload["alignment"]
    lines = [
        f"# {payload['doc_name']} — 章节映射质量报告",
        "",
        "## 总览",
        "",
        f"- 原始 `full_parse.json` 页数：{payload['source_page_count']}",
        f"- 目录页：{toc['pages'] or '未识别'}",
        f"- 目录项：{toc['entry_count']}；canonical 命中：{toc['canonicalized_count']}；页码已解析：{toc['resolved_page_count']}",
        f"- 核心章节覆盖率：{coverage['required_coverage']:.0%}",
        f"- 章节 span 数：{coverage['all_span_count']}",
        f"- 目录页码→PDF页偏移中位数：{alignment['page_offset_median']}",
        f"- 冲突数：{len(payload['conflicts'])}",
        "",
        "## 章节区间",
        "",
        "| canonical section | 原始标题 | PDF页区间 | 置信度 | 锚点来源 |",
        "|---|---|---:|---:|---|",
    ]
    for span in payload["section_spans"]:
        lines.append(
            f"| {span['canonical_section']} | {span['display_title']} | "
            f"{span['start_page']}–{span['end_page']} | {span['confidence']:.2f} | "
            f"{span['anchor_source']} |"
        )
    lines.extend(["", "## 目录与实际标题页对齐", ""])
    if alignment["entries"]:
        lines.extend(
            [
                "| 目录标题 | canonical section | 目录页码 | PDF页码 | 偏移 |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for item in alignment["entries"]:
            lines.append(
                f"| {item['title']} | {item['canonical_section']} | "
                f"{item['toc_page']} | {item['actual_pdf_page']} | {item['offset']} |"
            )
    else:
        lines.append("_没有可对齐的数字目录页码。_")
    lines.extend(["", "## 原始 JSON 锚点抽样", ""])
    for sample in payload["anchor_samples_from_full_parse"]:
        lines.append(
            f"### {sample['canonical_section']}（p{sample['start_page']}，"
            f"confidence={sample['confidence']:.2f}）"
        )
        for element in sample["raw_elements"]:
            text = str(element["text"]).replace("|", "/").replace("\n", " ")
            lines.append(
                f"- `{element['category']}` element={element['element_index']}: {text}"
            )
        lines.append("")
    if payload["conflicts"]:
        lines.extend(["## 冲突/待复核", "", "```json"])
        lines.append(json.dumps(payload["conflicts"], ensure_ascii=False, indent=2))
        lines.extend(["```", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze prospectus section mapping")
    parser.add_argument("--parse", required=True, type=Path)
    parser.add_argument("--doc-name", default="")
    parser.add_argument("--out-dir", type=Path, default=Path(".runtime/section_maps"))
    args = parser.parse_args()

    with args.parse.open(encoding="utf-8") as handle:
        pages = json.load(handle)
    if not isinstance(pages, list):
        raise ValueError("full_parse.json top-level must be a list")
    doc_name = args.doc_name or args.parse.parent.name
    payload, section_map = build_quality_payload(pages, doc_name)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.parse.parent.name
    map_path = save_section_map(section_map, args.out_dir / f"{stem}_section_map.json")
    json_path = args.out_dir / f"{stem}_section_quality.json"
    md_path = args.out_dir / f"{stem}_section_quality.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(f"section_map={map_path}")
    print(f"quality_json={json_path}")
    print(f"quality_md={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
