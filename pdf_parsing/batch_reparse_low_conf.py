#!/usr/bin/env python3
"""
对 samples_batch 中表结构置信度非 high 的页面定向重跑（rotate-mode=auto + rotate-fallback），
合并回全书并产出前后质量对比总览。

流程（每份 PDF）：
  1) 扫描 full_parse.json → 收集 confidence 为 medium/low 的页
  2) 备份 qa_report / full_parse（首次）
  3) 定向重跑 → merge 覆盖目标页
  4) 重生成 preview / risk_chunks / parse_summary
  5) 重跑 QA，写入 qa_report.json 与 per-doc 对比

用法（pdf_parsing/ 下，infinity_parser 环境）：
  python batch_reparse_low_conf.py --dry-run
  python batch_reparse_low_conf.py --gpus 2,3,4,5,6 --page-workers 2 --batch-size 2
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

DEFAULT_SAMPLES = _REPO_ROOT / "dataset" / "samples"
DEFAULT_OUTPUT = _THIS_DIR / "output" / "samples_batch"

from batch_parse_samples import (  # noqa: E402
    assign_pdfs_to_gpus,
    parse_pdf_sharded,
    run_qa,
)
from merge_parse_pages import load_pages, merge  # noqa: E402
from qa_parse_quality import build_report  # noqa: E402


def _conf_counter(doc: List[dict]) -> Counter:
    return Counter(
        p.get("table_structure_confidence")
        for p in doc
        if p.get("table_structure_confidence")
    )


def _metrics_from_report(report: Dict[str, Any]) -> Dict[str, Any]:
    conf = report.get("table_structure_confidence_pages") or {}
    return {
        "total_pages": report.get("total_pages", 0),
        "issue_count": report.get("issue_count", 0),
        "issues_by_tag": dict(report.get("issues_by_tag") or {}),
        "table_structure_confidence_pages": dict(conf),
        "reparse_pages_n": len(report.get("reparse_pages") or []),
    }


def collect_non_high_pages(doc: List[dict]) -> List[int]:
    """返回需重跑的页码（table_structure_confidence 为 medium 或 low）。"""
    pages: List[int] = []
    for page in doc:
        conf = page.get("table_structure_confidence")
        if conf in ("medium", "low"):
            pages.append(int(page["page"]))
    return sorted(pages)


def ensure_baseline_snapshots(out_dir: Path, full_parse: Path) -> Dict[str, Any]:
    """首次运行时备份 baseline QA；返回 baseline 指标。"""
    qa_before_path = out_dir / "qa_report.before_reparse.json"
    fp_backup = out_dir / "full_parse.pre_reparse_low_conf.bak"

    doc = json.loads(full_parse.read_text(encoding="utf-8"))
    if not qa_before_path.is_file():
        report = build_report(doc)
        qa_before_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        md = out_dir / "qa_report.before_reparse.md"
        _write_qa_md(md, full_parse, report, title_suffix="（重跑前 baseline）")
    else:
        report = json.loads(qa_before_path.read_text(encoding="utf-8"))

    if not fp_backup.is_file():
        shutil.copy2(full_parse, fp_backup)

    return _metrics_from_report(report)


def _write_qa_md(
    path: Path, full_parse: Path, report: Dict[str, Any], *, title_suffix: str = ""
) -> None:
    lines = [
        f"# 解析质量 QA 报告{title_suffix}",
        "",
        f"- 输入: `{full_parse}`",
        f"- 总页数: {report['total_pages']}",
        f"- 问题条数: {report['issue_count']}",
        f"- 建议重跑: `{report.get('reparse_pages_csv') or '无'}`",
        "",
        "## 表结构置信度（页）",
        "",
        "| 等级 | 页数 |",
        "| --- | ---: |",
    ]
    for k in ("high", "medium", "low"):
        v = (report.get("table_structure_confidence_pages") or {}).get(k, 0)
        lines.append(f"| `{k}` | {v} |")
    lines.extend(["", "## 按标签统计", "", "| 标签 | 次数 |", "| --- | ---: |"])
    for tag, cnt in sorted(
        (report.get("issues_by_tag") or {}).items(), key=lambda x: -x[1]
    ):
        lines.append(f"| `{tag}` | {cnt} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def regenerate_derived_outputs(out_dir: Path, doc: List[dict]) -> None:
    from pdf_parser_pro import (
        build_parse_summary,
        extract_risk_chunks,
        page_to_preview_markdown,
    )

    preview_md = "\n\n---\n\n".join(
        page_to_preview_markdown(int(p["page"]), p.get("elements") or [])
        for p in doc
    )
    (out_dir / "preview.md").write_text(preview_md, encoding="utf-8")
    (out_dir / "risk_chunks.json").write_text(
        json.dumps(extract_risk_chunks(doc), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "parse_summary.json").write_text(
        json.dumps(build_parse_summary(doc), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def confidence_transitions(
    before_pages: Dict[int, dict], after_pages: Dict[int, dict], target_pages: List[int]
) -> Dict[str, int]:
    trans: Counter = Counter()
    for pnum in target_pages:
        b = before_pages.get(pnum, {}).get("table_structure_confidence") or "none"
        a = after_pages.get(pnum, {}).get("table_structure_confidence") or "none"
        trans[f"{b}->{a}"] += 1
    return dict(trans)


def process_one_reparse(
    pdf_path: Path,
    *,
    output_root: Path,
    samples_dir: Path,
    page_numbers: List[int],
    batch_size: int,
    dpi: int,
    max_new_tokens: int,
    page_workers: int,
    gpu_ids: List[int],
    model_name: str,
    workdir: str,
) -> Dict[str, Any]:
    stem = pdf_path.stem
    out_dir = output_root / stem
    full_parse = out_dir / "full_parse.json"
    record: Dict[str, Any] = {
        "pdf": str(pdf_path),
        "stem": stem,
        "out_dir": str(out_dir),
        "target_pages_n": len(page_numbers),
        "gpu_ids": gpu_ids,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    t0 = time.time()

    if not page_numbers:
        record["status"] = "skipped"
        record["reason"] = "no_non_high_pages"
        return record

    baseline = ensure_baseline_snapshots(out_dir, full_parse)
    record["baseline"] = baseline

    base_pages = load_pages(full_parse)
    before_subset = {p: dict(base_pages[p]) for p in page_numbers if p in base_pages}

    reparse_dir = out_dir / "_reparse_low_conf"
    if reparse_dir.exists():
        shutil.rmtree(reparse_dir)
    reparse_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[{stem}] 重跑 {len(page_numbers)} 页 "
        f"(rotate=auto, fallback=on, gpus={gpu_ids})",
        flush=True,
    )
    patch_doc = parse_pdf_sharded(
        pdf_path,
        gpu_ids=gpu_ids,
        out_dir=reparse_dir,
        page_workers=page_workers,
        workdir=workdir,
        model_name=model_name,
        batch_size=batch_size,
        dpi=dpi,
        max_new_tokens=max_new_tokens,
        rotate_mode="auto",
        rotate_fallback=True,
        save_figures=True,
        page_numbers=page_numbers,
    )
    patch_map = {int(p["page"]): p for p in patch_doc}

    merged, changelog = merge(
        base_pages,
        patch_map,
        set(page_numbers),
        prefer_higher_table_score=False,
        parse_pass="reparse_rotate_low_conf",
    )
    full_parse.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    regenerate_derived_outputs(out_dir, merged)
    qa_after = run_qa(full_parse, suffix="")

    after_pages = load_pages(full_parse)
    transitions = confidence_transitions(before_subset, after_pages, page_numbers)
    replaced = sum(1 for c in changelog if c["action"] in ("replace", "insert"))

    compare = {
        "baseline": baseline,
        "after": _metrics_from_report(qa_after),
        "target_pages_n": len(page_numbers),
        "merged_pages_n": replaced,
        "confidence_transitions": transitions,
        "improved_to_high": sum(
            v for k, v in transitions.items() if k.endswith("->high")
        ),
    }
    compare_path = out_dir / "reparse_low_conf_compare.json"
    compare_path.write_text(
        json.dumps(compare, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    changelog_path = out_dir / "reparse_low_conf_changelog.json"
    changelog_path.write_text(
        json.dumps(
            {
                "pdf": str(pdf_path),
                "target_pages": page_numbers,
                "changelog": changelog,
                "compare": compare,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    record.update(
        {
            "status": "ok",
            "compare": compare,
            "elapsed_sec": round(time.time() - t0, 1),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    print(
        f"[{stem}] 完成: merged={replaced}, "
        f"conf high {baseline['table_structure_confidence_pages'].get('high',0)}"
        f"→{compare['after']['table_structure_confidence_pages'].get('high',0)}, "
        f"improved_to_high={compare['improved_to_high']}",
        flush=True,
    )
    return record


def _worker_process(gpu_id: int, jobs: List[Tuple[str, str]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    os.chdir(cfg["workdir"])
    if cfg["workdir"] not in sys.path:
        sys.path.insert(0, cfg["workdir"])

    records: List[Dict[str, Any]] = []
    for pdf_s, pages_csv in jobs:
        pdf = Path(pdf_s)
        page_numbers = [int(x) for x in pages_csv.split(",") if x.strip()]
        print(f"\n[GPU {gpu_id}] ===== {pdf.name} ({len(page_numbers)} pages) =====", flush=True)
        try:
            rec = process_one_reparse(
                pdf,
                output_root=Path(cfg["output_root"]),
                samples_dir=Path(cfg["samples_dir"]),
                page_numbers=page_numbers,
                batch_size=cfg["batch_size"],
                dpi=cfg["dpi"],
                max_new_tokens=cfg["max_new_tokens"],
                page_workers=cfg["page_workers"],
                gpu_ids=[gpu_id],
                model_name=cfg["model"],
                workdir=cfg["workdir"],
            )
            rec["gpu_id"] = gpu_id
        except Exception as e:
            print(f"[GPU {gpu_id}][失败] {pdf.name}: {e}", flush=True)
            traceback.print_exc()
            rec = {
                "pdf": str(pdf),
                "stem": pdf.stem,
                "gpu_id": gpu_id,
                "status": "failed",
                "error": str(e),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
        records.append(rec)
    return records


def scan_jobs(
    samples_dir: Path, output_root: Path
) -> List[Tuple[Path, List[int]]]:
    jobs: List[Tuple[Path, List[int]]] = []
    for pdf in sorted(samples_dir.glob("*.pdf")):
        full_parse = output_root / pdf.stem / "full_parse.json"
        if not full_parse.is_file():
            continue
        doc = json.loads(full_parse.read_text(encoding="utf-8"))
        # 确保页级置信度已标注
        build_report(doc)
        pages = collect_non_high_pages(doc)
        if pages:
            jobs.append((pdf, pages))
    return jobs


def write_batch_compare(output_root: Path, records: List[Dict[str, Any]]) -> None:
    ok = [r for r in records if r.get("status") == "ok"]
    skipped = [r for r in records if r.get("status") == "skipped"]
    failed = [r for r in records if r.get("status") == "failed"]

    def _sum_conf(key: str, which: str) -> int:
        total = 0
        for r in ok:
            src = r.get("compare", {}).get(which, {})
            total += (src.get("table_structure_confidence_pages") or {}).get(key, 0)
        return total

    def _sum_tag(tag: str, which: str) -> int:
        total = 0
        for r in ok:
            src = r.get("compare", {}).get(which, {})
            total += (src.get("issues_by_tag") or {}).get(tag, 0)
        return total

    batch = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_docs": len(records),
        "ok": len(ok),
        "skipped": len(skipped),
        "failed": len(failed),
        "target_pages_total": sum(r.get("target_pages_n", 0) for r in records),
        "improved_to_high_total": sum(
            (r.get("compare") or {}).get("improved_to_high", 0) for r in ok
        ),
        "confidence_pages_before": {
            "high": _sum_conf("high", "baseline"),
            "medium": _sum_conf("medium", "baseline"),
            "low": _sum_conf("low", "baseline"),
        },
        "confidence_pages_after": {
            "high": _sum_conf("high", "after"),
            "medium": _sum_conf("medium", "after"),
            "low": _sum_conf("low", "after"),
        },
        "issues_by_tag_before": {
            "vertical_table_low_structure": _sum_tag("vertical_table_low_structure", "baseline"),
            "table_structure_medium": _sum_tag("table_structure_medium", "baseline"),
            "missing_table_high_numeric": _sum_tag("missing_table_high_numeric", "baseline"),
            "parse_failed": _sum_tag("parse_failed", "baseline"),
        },
        "issues_by_tag_after": {
            "vertical_table_low_structure": _sum_tag("vertical_table_low_structure", "after"),
            "table_structure_medium": _sum_tag("table_structure_medium", "after"),
            "missing_table_high_numeric": _sum_tag("missing_table_high_numeric", "after"),
            "parse_failed": _sum_tag("parse_failed", "after"),
        },
        "records": records,
    }

    path = output_root / "reparse_low_conf_batch_summary.json"
    path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")

    b = batch["confidence_pages_before"]
    a = batch["confidence_pages_after"]
    ib = batch["issues_by_tag_before"]
    ia = batch["issues_by_tag_after"]
    md_lines = [
        "# 低置信度页重跑 — 批量前后对比",
        "",
        f"- 生成时间: {batch['generated_at']}",
        f"- 文档: {batch['n_docs']}（成功 {batch['ok']} / 跳过 {batch['skipped']} / 失败 {batch['failed']}）",
        f"- 重跑目标页合计: {batch['target_pages_total']}",
        f"- 提升至 high 的页数合计: {batch['improved_to_high_total']}",
        "",
        "## 表结构置信度（含 table 的页）",
        "",
        "| 等级 | 重跑前 | 重跑后 | Δ |",
        "| --- | ---: | ---: | ---: |",
    ]
    for k in ("high", "medium", "low"):
        d = a[k] - b[k]
        md_lines.append(f"| `{k}` | {b[k]} | {a[k]} | {d:+d} |")

    md_lines.extend(
        [
            "",
            "## 关键 QA 标签",
            "",
            "| 标签 | 重跑前 | 重跑后 | Δ |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for tag in (
        "vertical_table_low_structure",
        "table_structure_medium",
        "missing_table_high_numeric",
        "parse_failed",
    ):
        d = ia[tag] - ib[tag]
        md_lines.append(f"| `{tag}` | {ib[tag]} | {ia[tag]} | {d:+d} |")

    md_lines.extend(["", "## 各文档", "", "| 文档 | 目标页 | →high | high前→后 | 问题前→后 |", "| --- | ---: | ---: | --- | --- |"])
    for r in ok:
        c = r.get("compare") or {}
        bb = c.get("baseline", {})
        aa = c.get("after", {})
        hb = bb.get("table_structure_confidence_pages", {}).get("high", 0)
        ha = aa.get("table_structure_confidence_pages", {}).get("high", 0)
        ibc = bb.get("issue_count", 0)
        iac = aa.get("issue_count", 0)
        md_lines.append(
            f"| `{r.get('stem')}` | {r.get('target_pages_n', 0)} | "
            f"{c.get('improved_to_high', 0)} | {hb}→{ha} | {ibc}→{iac} |"
        )
    for r in failed:
        md_lines.append(f"| `{r.get('stem')}` | - | - | **失败**: {r.get('error', '')[:60]} | - |")

    md_path = output_root / "reparse_low_conf_batch_summary.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"\n批量对比摘要: {path}")
    print(f"Markdown: {md_path}")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="批量重跑 table_structure_confidence 非 high 的页面（rotate+回退，合并覆盖）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES)
    p.add_argument("-o", "--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--pdf", type=Path, default=None, help="只处理这一份")
    p.add_argument("--model", default="./models/infly/Infinity-Parser2-Flash")
    p.add_argument("--gpus", default="2,3,4,5,6")
    p.add_argument("--page-workers", type=int, default=2)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--max-new-tokens", type=int, default=16384)
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> None:
    args = build_argparser().parse_args(argv)
    samples_dir = args.samples_dir.resolve()
    output_root = args.output_dir.resolve()
    gpu_ids = [int(x.strip()) for x in args.gpus.split(",") if x.strip()]

    if args.pdf:
        pdf = args.pdf.resolve()
        fp = output_root / pdf.stem / "full_parse.json"
        if not fp.is_file():
            raise SystemExit(f"缺少 {fp}")
        doc = json.loads(fp.read_text(encoding="utf-8"))
        build_report(doc)
        pages = collect_non_high_pages(doc)
        jobs = [(pdf, pages)]
    else:
        jobs = scan_jobs(samples_dir, output_root)

    total_pages = sum(len(p) for _, p in jobs)
    print(f"output: {output_root}")
    print(f"待处理 PDF: {len(jobs)}，非 high 目标页合计: {total_pages}")
    for pdf, pages in jobs:
        print(f"  {pdf.name}: {len(pages)} 页")

    if args.dry_run:
        print("\n[dry-run] 退出。")
        return

    cfg = {
        "workdir": str(_THIS_DIR),
        "output_root": str(output_root),
        "samples_dir": str(samples_dir),
        "model": args.model,
        "batch_size": args.batch_size,
        "dpi": args.dpi,
        "max_new_tokens": args.max_new_tokens,
        "page_workers": args.page_workers,
    }

    # 按目标页数均衡分配到各 GPU（大书优先）
    job_items = sorted(
        [(str(pdf), ",".join(str(x) for x in pages)) for pdf, pages in jobs],
        key=lambda x: -len(x[1].split(",")),
    )
    buckets: Dict[int, List[Tuple[str, str]]] = {g: [] for g in gpu_ids}
    load = {g: 0 for g in gpu_ids}
    for item in job_items:
        g = min(gpu_ids, key=lambda x: load[x])
        buckets[g].append(item)
        load[g] += len(item[1].split(","))

    print("\nGPU 分配:")
    for g in gpu_ids:
        n_pages = sum(len(p.split(",")) for _, p in buckets[g])
        print(f"  GPU {g}: {len(buckets[g])} 本, ~{n_pages} 页")

    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    all_records: List[Dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=len(gpu_ids), mp_context=ctx) as ex:
        futs = [
            ex.submit(_worker_process, g, buckets[g], cfg)
            for g in gpu_ids
            if buckets[g]
        ]
        for fut in futs:
            all_records.extend(fut.result())

    write_batch_compare(output_root, all_records)


if __name__ == "__main__":
    main()
