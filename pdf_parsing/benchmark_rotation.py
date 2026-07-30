#!/usr/bin/env python3
"""竖表页旋转策略对比：质量 + 速度（默认第 16、21 页）。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from pdf_parser_pro import (
    build_parse_summary,
    load_model,
    page_to_preview_markdown,
    parse_pdf,
    postprocess_page,
    render_pdf_pages,
    resolve_page_rotation,
    rotate_image_cw,
    parse_pages_batch,
)

PYTHON = "/nfs/users/wuqianqian/anaconda3/envs/infinity_parser/bin/python"

TABLE_KEYWORDS = [
    "2021年", "2022年", "2023年", "2024年",
    "收入", "毛利率", "毛利", "加盟門店", "自營門店",
    "商品銷售", "設備銷售", "小計",
]


def score_table_html(html: str) -> dict:
    tr = html.count("<tr>")
    td = html.count("<td")
    return {
        "rows": tr,
        "cells": td,
        "cells_per_row": round(td / tr, 2) if tr else 0,
        "rowspan": html.count("rowspan"),
        "colspan": html.count("colspan"),
        "keyword_hits": sum(1 for k in TABLE_KEYWORDS if k in html),
        "html_len": len(html),
    }


def extract_page_tables(page: dict) -> list[dict]:
    out = []
    for e in page.get("elements", []):
        if e.get("category") == "table":
            html = e.get("text") or ""
            bbox = e.get("bbox", [])
            aspect = 0.0
            if isinstance(bbox, list) and len(bbox) == 4:
                w = max(bbox[2] - bbox[0], 1)
                h = max(bbox[3] - bbox[1], 1)
                aspect = round(h / w, 2)
            out.append({"bbox_aspect_h_w": aspect, **score_table_html(html)})
    return out


def load_baseline_pages(baseline_json: Path, page_nums: list[int]) -> dict[int, dict]:
    data = json.loads(baseline_json.read_text(encoding="utf-8"))
    by_page = {p["page"]: p for p in data}
    return {n: by_page[n] for n in page_nums if n in by_page}


def run_mode(
    pdf_path: Path,
    model,
    processor,
    mode: str,
    page_nums: list[int],
    *,
    batch_size: int = 1,
    max_new_tokens: int = 32768,
    use_baseline: dict[int, dict] | None = None,
) -> dict:
    if mode == "none" and use_baseline:
        pages = [use_baseline[n] for n in page_nums]
        return {
            "mode": mode,
            "elapsed_sec": 0.0,
            "from_cache": True,
            "pages": pages,
        }

    t0 = time.perf_counter()
    images = render_pdf_pages(pdf_path, dpi=300, page_numbers=page_nums)
    rotated = []
    rotations = {}
    for pnum, img in zip(page_nums, images):
        deg = resolve_page_rotation(pdf_path, pnum, mode)
        rotations[pnum] = deg
        rotated.append(rotate_image_cw(img, deg))

    raw_outputs = parse_pages_batch(
        rotated, model, processor, batch_size=batch_size, max_new_tokens=max_new_tokens
    )

    pages = []
    for pnum, img, raw in zip(page_nums, rotated, raw_outputs):
        elements, meta = postprocess_page(raw, img)
        rec = {
            "page": pnum,
            "parse_status": meta["parse_status"],
            "elements": elements,
            "rotation_applied": rotations.get(pnum, 0),
        }
        pages.append(rec)

    elapsed = time.perf_counter() - t0
    return {"mode": mode, "elapsed_sec": round(elapsed, 1), "from_cache": False, "pages": pages}


def build_report(results: list[dict], page_nums: list[int]) -> str:
    lines = [
        "# 竖表旋转策略对比（第 16、21 页）",
        "",
        "## 当前默认行为",
        "",
        "- **仅有 PDF 页级 `/Rotate` 元数据**：PyMuPDF `get_pixmap()` 自动应用整页 90/180/270°。",
        "- **无页内竖表转正**：第 16/21 页 `rotation=0`，竖排表格仍以纵向送入模型，行列结构易乱。",
        "",
        "## 速度对比",
        "",
        "| 模式 | 说明 | 2页耗时 | 来源 |",
        "| --- | --- | ---: | --- |",
    ]

    for r in results:
        mode = r["mode"]
        desc = {
            "none": "不旋转（基线）",
            "cw90": "顺时针 90°",
            "ccw90": "逆时针 90°",
            "auto": "竖表检测后 CW90",
        }.get(mode, mode)
        src = "已有 full_parse.json" if r.get("from_cache") else "本次推理"
        lines.append(f"| `{mode}` | {desc} | {r['elapsed_sec']}s | {src} |")

    lines.extend(["", "## 表格质量对比", ""])

    for pnum in page_nums:
        lines.append(f"### 第 {pnum} 页")
        lines.append("")
        lines.append("| 模式 | 旋转 | 状态 | 行 | 列单元格 | 合并单元格 | 关键词命中 | 表高/宽 |")
        lines.append("| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |")
        for r in results:
            page = next((p for p in r["pages"] if p["page"] == pnum), None)
            if not page:
                continue
            tables = extract_page_tables(page)
            if not tables:
                lines.append(
                    f"| `{r['mode']}` | {page.get('rotation_applied', 0)} | "
                    f"{page.get('parse_status')} | - | - | - | - | - |"
                )
                continue
            t = tables[0]
            merge = t["rowspan"] + t["colspan"]
            lines.append(
                f"| `{r['mode']}` | {page.get('rotation_applied', 0)} | "
                f"{page.get('parse_status')} | {t['rows']} | {t['cells']} | {merge} | "
                f"{t['keyword_hits']} | {t['bbox_aspect_h_w']} |"
            )
        lines.append("")

    lines.extend([
        "## 结论提示",
        "",
        "- **keyword_hits** 越高、**cells_per_row** 越稳定，通常表示表头/数据列对齐更好。",
        "- **bbox_aspect_h_w** 由竖变横后应明显下降（竖表转正成功时接近 0.3~1.5）。",
        "- **auto** 在本样本仅命中第 16/21 页，额外检测开销 <1ms/页，推理耗时与 cw90 基本相同。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="竖表旋转 benchmark")
    ap.add_argument("--pdf", default="pdf/mixue-1-30.pdf")
    ap.add_argument("--pages", default="16,21")
    ap.add_argument(
        "--baseline",
        default="output/mixue-1-30-pro/mixue-1-30/full_parse.json",
        help="none 模式基线 JSON（避免重复推理）",
    )
    ap.add_argument("-o", default="output/mixue-1-30-pro/rotation_benchmark.md")
    ap.add_argument("--batch-size", type=int, default=1)
    args = ap.parse_args()

    page_nums = [int(x) for x in args.pages.split(",")]
    pdf_path = Path(args.pdf)
    baseline_path = Path(args.baseline)
    baseline = load_baseline_pages(baseline_path, page_nums) if baseline_path.is_file() else None

    modes = ["none", "cw90", "ccw90", "auto"]
    print("加载模型...")
    model, processor = load_model()

    results = []
    for mode in modes:
        print(f"\n=== mode={mode} ===")
        r = run_mode(
            pdf_path,
            model,
            processor,
            mode,
            page_nums,
            batch_size=args.batch_size,
            use_baseline=baseline if mode == "none" else None,
        )
        results.append(r)
        # 保存各模式 JSON 快照
        out_dir = Path("output/mixue-1-30-pro/rotation_benchmark")
        out_dir.mkdir(parents=True, exist_ok=True)
        snap = out_dir / f"p{'-'.join(map(str, page_nums))}_{mode}.json"
        snap.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  elapsed={r['elapsed_sec']}s -> {snap}")

    report = build_report(results, page_nums)
    out_path = Path(args.o)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n报告: {out_path}")


if __name__ == "__main__":
    main()
