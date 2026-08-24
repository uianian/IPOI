#!/usr/bin/env python3
"""
批量解析 dataset/samples 招股书：全文解析 → QA。

默认流水线：
  Pass1  pdf_parser_pro  batch_size=8，带 figure，rotate-mode=auto + rotate-fallback
  Pass2  qa_parse_quality → qa_report.json / qa_report.md

说明：同参定向重跑 + merge 实测 replaced≈0，已从默认流水线移除。
若需人工修补个别页，可单独用 pdf_parser_pro --pages + merge_parse_pages。

吞吐策略（Flash 仅 ~4GB，24GB 卡显存远未吃满）：
  1) 多本 PDF：一卡一本数据并行
  2) 同卡：--page-workers 2 把一本书页范围切两半，两进程各载一份模型并行推
  3) 一份 PDF 跨多卡：总进程数 = GPU数 × page_workers，按页轮询分片
  4) 默认 batch_size=8、max_new_tokens=16384

用法（在 pdf_parsing/ 下，infinity_parser 环境）：
  # 一份 PDF：多卡 + 每卡 2 分片（例 4 卡 → 8 进程）
  python batch_parse_samples.py --pdf pdf/xiaomi.pdf --gpus 0,1,2,3 --page-workers 2 --batch-size 2
  # 单卡 2 分片
  python batch_parse_samples.py --pdf pdf/xiaomi.pdf --gpus 0 --page-workers 2 --batch-size 2
  # 多本：多卡一卡一本
  python batch_parse_samples.py --limit 5 --gpus auto --page-workers 2 --batch-size 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

DEFAULT_SAMPLES = _REPO_ROOT / "dataset" / "samples"
DEFAULT_OUTPUT = _THIS_DIR / "output" / "samples_batch"


def list_sample_pdfs(
    samples_dir: Path, limit: int, offset: int = 0
) -> List[Path]:
    """按文件名排序后取 [offset, offset+limit)。offset/limit 均为 0-based 切片语义。"""
    pdfs = sorted(samples_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"未找到 PDF: {samples_dir}")
    if offset < 0:
        raise ValueError(f"offset 不能为负: {offset}")
    if offset >= len(pdfs):
        raise ValueError(f"offset={offset} 超出 samples 数量 {len(pdfs)}")
    return pdfs[offset : offset + limit]


def free_gpu_ids(min_free_mib: int = 20000) -> List[int]:
    """用 nvidia-smi 找空闲显存足够的物理 GPU id。"""
    import subprocess

    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise RuntimeError(f"无法查询 GPU: {e}") from e

    free: List[int] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        idx, mem_free = int(parts[0]), int(float(parts[1]))
        if mem_free >= min_free_mib:
            free.append(idx)
    return free


def resolve_gpu_ids(gpus_spec: Optional[str], *, min_free_mib: int = 20000) -> List[int]:
    """解析物理 GPU 列表。auto → 全部空闲卡；'1,2,3' → 指定。"""
    if gpus_spec is None:
        env = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
        if env:
            return [int(x) for x in env.split(",") if x.strip() != ""]
        gpus_spec = "auto"

    if gpus_spec.strip().lower() == "auto":
        ids = free_gpu_ids(min_free_mib=min_free_mib)
        if not ids:
            raise RuntimeError(
                f"没有空闲显存 ≥{min_free_mib}MiB 的 GPU；"
                "请用 --gpus 1,2,3 手动指定，或释放占用卡"
            )
        return ids

    return [int(x.strip()) for x in gpus_spec.split(",") if x.strip() != ""]


def assign_pdfs_to_gpus(
    pdfs: List[Path], gpu_ids: List[int]
) -> List[Tuple[int, List[Path]]]:
    """轮询分配：返回 [(gpu_id, [pdf, ...]), ...]。"""
    buckets: Dict[int, List[Path]] = {g: [] for g in gpu_ids}
    for i, pdf in enumerate(pdfs):
        buckets[gpu_ids[i % len(gpu_ids)]].append(pdf)
    return [(g, buckets[g]) for g in gpu_ids if buckets[g]]


def pdf_page_count(pdf_path: Path) -> int:
    import fitz

    doc = fitz.open(str(pdf_path))
    n = len(doc)
    doc.close()
    return n


def split_page_ranges(
    page_numbers: Sequence[int], n_shards: int
) -> List[List[int]]:
    """尽量均匀切页码列表。"""
    pages = list(page_numbers)
    if n_shards <= 1 or len(pages) <= 1:
        return [pages]
    n_shards = min(n_shards, len(pages))
    # 轮询分片，避免前半/后半页复杂度不均时某一 shard 过慢
    shards: List[List[int]] = [[] for _ in range(n_shards)]
    for i, p in enumerate(pages):
        shards[i % n_shards].append(p)
    return [s for s in shards if s]


def run_qa(
    full_parse: Path,
    *,
    write_confidence: bool = True,
    markdown: bool = True,
    suffix: str = "",
) -> Dict[str, Any]:
    from qa_parse_quality import build_report

    doc = json.loads(full_parse.read_text(encoding="utf-8"))
    if not isinstance(doc, list):
        raise ValueError(f"期望页数组: {full_parse}")

    report = build_report(doc)
    if write_confidence:
        full_parse.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    out_json = full_parse.parent / f"qa_report{suffix}.json"
    out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if markdown:
        out_md = full_parse.parent / f"qa_report{suffix}.md"
        lines = [
            f"# 解析质量 QA 报告{suffix}",
            "",
            f"- 输入: `{full_parse}`",
            f"- 总页数: {report['total_pages']}",
            f"- 问题条数: {report['issue_count']}",
            f"- 建议重跑: `{report['reparse_pages_csv'] or '无'}`",
            "",
            "## 按标签统计",
            "",
            "| 标签 | 次数 |",
            "| --- | ---: |",
        ]
        for tag, cnt in sorted(
            report["issues_by_tag"].items(), key=lambda x: -x[1]
        ):
            lines.append(f"| `{tag}` | {cnt} |")
        lines.extend(["", "## 问题明细", ""])
        for iss in report["issues"]:
            lines.append(
                f"- **p{iss['page']}** `{iss['tag']}` [{iss['severity']}] "
                f"{iss.get('detail', '')}"
            )
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return report


def _write_progress(path: Path, data: Dict[str, Any]) -> None:
    """跨进程进度采用每 shard 独立文件，再由服务端汇总。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _page_shard_worker(payload: Dict[str, Any]) -> str:
    """同卡页分片子进程：绑 GPU → 载模型 → 解析指定页 → 返回 shard full_parse 路径。"""
    gpu_id = int(payload["gpu_id"])
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    workdir = payload["workdir"]
    os.chdir(workdir)
    if workdir not in sys.path:
        sys.path.insert(0, workdir)

    from pdf_parser_pro import load_model, parse_pdf, save_outputs

    pages = list(payload["pages"])
    shard_out = Path(payload["shard_out"])
    figures_dir = Path(payload["figures_dir"])
    print(
        f"[GPU {gpu_id}|shard{payload['shard_id']}] "
        f"pages {pages[0]}..{pages[-1]} ({len(pages)} 页)",
        flush=True,
    )
    progress_path = Path(payload["progress_path"])
    _write_progress(progress_path, {"done": 0, "total": len(pages), "stage": "MODEL_LOADING"})
    model, processor = load_model(payload["model"], device_map="cuda:0")
    def report_done(done: int) -> None:
        _write_progress(progress_path, {"done": done, "total": len(pages), "stage": "PAGE_PARSING"})
    doc, preview = parse_pdf(
        Path(payload["pdf"]),
        model,
        processor,
        dpi=payload["dpi"],
        batch_size=payload["batch_size"],
        max_new_tokens=payload["max_new_tokens"],
        save_figures=payload["save_figures"],
        out_dir=shard_out,
        figures_dir=figures_dir,
        page_numbers=pages,
        rotate_mode=payload["rotate_mode"],
        rotate_pages=None,
        rotate_degrees=90,
        rotate_fallback=payload["rotate_fallback"],
        progress_callback=report_done,
    )
    _write_progress(progress_path, {"done": len(pages), "total": len(pages), "stage": "SHARD_COMPLETE"})
    save_outputs(shard_out, doc, preview, save_risk_chunks=False)
    return str(shard_out / "full_parse.json")


def parse_pdf_sharded(
    pdf_path: Path,
    *,
    out_dir: Path,
    page_workers: int,
    workdir: str,
    model_name: str,
    batch_size: int,
    dpi: int,
    max_new_tokens: int,
    rotate_mode: str,
    rotate_fallback: bool,
    save_figures: bool,
    page_numbers: Optional[List[int]] = None,
    gpu_id: Optional[int] = None,
    gpu_ids: Optional[List[int]] = None,
) -> List[dict]:
    """
    按页分片并行解析并合并。
    - 单卡：gpu_id + page_workers → 同卡 page_workers 个进程
    - 多卡：gpu_ids + page_workers → 总进程 = len(gpu_ids)*page_workers，页轮询到各卡
    """
    if page_numbers is None:
        page_numbers = list(range(1, pdf_page_count(pdf_path) + 1))
    gpus = list(gpu_ids) if gpu_ids else ([gpu_id] if gpu_id is not None else [])
    if not gpus:
        raise ValueError("parse_pdf_sharded 需要 gpu_id 或 gpu_ids")
    page_workers = max(int(page_workers), 1)
    n_shards = len(gpus) * page_workers
    shards = split_page_ranges(page_numbers, n_shards)
    out_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    progress_dir = out_dir / "_progress"
    _write_progress(progress_dir / "status.json", {"stage": "PAGE_PARSING", "pagesTotal": len(page_numbers)})

    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    payloads = []
    for sid, pages in enumerate(shards):
        gid = gpus[sid % len(gpus)]
        shard_out = out_dir / f"_shard{sid}_gpu{gid}"
        payloads.append(
            {
                "gpu_id": gid,
                "shard_id": sid,
                "pdf": str(pdf_path),
                "pages": pages,
                "shard_out": str(shard_out),
                "figures_dir": str(figures_dir),
                "workdir": workdir,
                "model": model_name,
                "batch_size": batch_size,
                "dpi": dpi,
                "max_new_tokens": max_new_tokens,
                "rotate_mode": rotate_mode,
                "rotate_fallback": rotate_fallback,
                "save_figures": save_figures,
                "progress_path": str(progress_dir / f"shard{sid}.json"),
            }
        )

    print(
        f"[{pdf_path.stem}] 分片并行: GPUs={gpus}, "
        f"page_workers/卡={page_workers}, 总进程={len(payloads)}, "
        f"pages={len(page_numbers)}",
        flush=True,
    )
    for p in payloads:
        print(
            f"  shard{p['shard_id']} → GPU {p['gpu_id']}: "
            f"{len(p['pages'])} 页 ({p['pages'][0]}..{p['pages'][-1]})",
            flush=True,
        )

    merged_map: Dict[int, dict] = {}
    with ProcessPoolExecutor(max_workers=len(payloads), mp_context=ctx) as ex:
        futs = [ex.submit(_page_shard_worker, p) for p in payloads]
        for fut in as_completed(futs):
            shard_json = Path(fut.result())
            for page in json.loads(shard_json.read_text(encoding="utf-8")):
                merged_map[int(page["page"])] = page

    _write_progress(progress_dir / "status.json", {"stage": "MERGING", "pagesDone": len(merged_map), "pagesTotal": len(page_numbers)})
    return [merged_map[k] for k in sorted(merged_map)]


def process_one(
    pdf_path: Path,
    *,
    output_root: Path,
    model,
    processor,
    batch_size: int,
    dpi: int,
    max_new_tokens: int,
    rotate_mode: str,
    rotate_fallback: bool,
    save_figures: bool,
    save_risk_chunks: bool,
    skip_pass1: bool,
    page_workers: int = 1,
    gpu_id: Optional[int] = None,
    gpu_ids: Optional[List[int]] = None,
    model_name: str = "./models/infly/Infinity-Parser2-Flash",
    workdir: Optional[str] = None,
) -> Dict[str, Any]:
    from pdf_parser_pro import page_to_preview_markdown, parse_pdf, save_outputs

    stem = pdf_path.stem
    out_dir = output_root / stem
    full_parse = out_dir / "full_parse.json"
    workdir = workdir or str(_THIS_DIR)
    gpus_for_pdf = list(gpu_ids) if gpu_ids else ([gpu_id] if gpu_id is not None else [])
    record: Dict[str, Any] = {
        "pdf": str(pdf_path),
        "stem": stem,
        "out_dir": str(out_dir),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "page_workers": page_workers,
        "gpu_ids": gpus_for_pdf,
    }
    t0 = time.time()

    # ── Pass1: 全文解析 ─────────────────────────────────────
    if skip_pass1:
        if not full_parse.is_file():
            raise FileNotFoundError(
                f"--skip-pass1 需要已有 {full_parse}"
            )
        print(f"[{stem}] Pass1 跳过，使用已有 full_parse.json", flush=True)
        record["pass1"] = "skipped"
        n_pages = len(json.loads(full_parse.read_text(encoding="utf-8")))
    else:
        use_shard = page_workers > 1 or len(gpus_for_pdf) > 1
        print(
            f"[{stem}] Pass1 全文解析 → {out_dir} "
            f"(gpus={gpus_for_pdf}, page_workers={page_workers}, "
            f"batch_size={batch_size}, shard={use_shard})",
            flush=True,
        )
        if use_shard:
            if not gpus_for_pdf:
                raise ValueError("分片解析需要 gpu_id / gpu_ids")
            doc_result = parse_pdf_sharded(
                pdf_path,
                gpu_id=gpus_for_pdf[0],
                gpu_ids=gpus_for_pdf,
                out_dir=out_dir,
                page_workers=page_workers,
                workdir=workdir,
                model_name=model_name,
                batch_size=batch_size,
                dpi=dpi,
                max_new_tokens=max_new_tokens,
                rotate_mode=rotate_mode,
                rotate_fallback=rotate_fallback,
                save_figures=save_figures,
            )
            preview_md = "\n\n---\n\n".join(
                page_to_preview_markdown(
                    int(p["page"]), p.get("elements") or []
                )
                for p in doc_result
            )
        else:
            if model is None or processor is None:
                raise ValueError("page_workers=1 需要已加载的 model/processor")
            doc_result, preview_md = parse_pdf(
                pdf_path,
                model,
                processor,
                dpi=dpi,
                batch_size=batch_size,
                max_new_tokens=max_new_tokens,
                save_figures=save_figures,
                out_dir=out_dir,
                page_numbers=None,
                rotate_mode=rotate_mode,
                rotate_pages=None,
                rotate_degrees=90,
                rotate_fallback=rotate_fallback,
            )
        save_outputs(
            out_dir,
            doc_result,
            preview_md,
            save_risk_chunks=save_risk_chunks,
        )
        n_pages = len(doc_result)
        elapsed = round(time.time() - t0, 1)
        record["pass1"] = {
            "pages": n_pages,
            "elapsed_sec": elapsed,
            "sec_per_page": round(elapsed / max(n_pages, 1), 2),
            "page_workers": page_workers,
            "batch_size": batch_size,
        }

    # ── Pass2: QA ───────────────────────────────────────────
    progress_dir = out_dir / "_progress"
    _write_progress(progress_dir / "status.json", {"stage": "QA", "pagesDone": n_pages, "pagesTotal": n_pages})
    print(f"[{stem}] Pass2 QA", flush=True)
    qa1 = run_qa(full_parse, suffix="")
    record["qa_pass1"] = {
        "issue_count": qa1["issue_count"],
        "issues_by_tag": qa1["issues_by_tag"],
        "reparse_pages_csv": qa1.get("reparse_pages_csv") or "",
        "reparse_pages": list(qa1.get("reparse_pages") or []),
    }

    record["elapsed_sec"] = round(time.time() - t0, 1)
    record["finished_at"] = datetime.now().isoformat(timespec="seconds")
    record["status"] = "ok"
    _write_progress(progress_dir / "status.json", {"stage": "COMPLETE", "pagesDone": n_pages, "pagesTotal": n_pages})
    return record


def _worker_process(
    gpu_id: int,
    pdf_paths: List[str],
    cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    GPU 队列进程。
    page_workers=1：本进程载一份模型串行跑 PDF。
    page_workers>1：本进程不占显存，每本 PDF 再 spawn 分片 worker（同卡并行）。
    """
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    os.chdir(cfg["workdir"])
    if cfg["workdir"] not in sys.path:
        sys.path.insert(0, cfg["workdir"])

    page_workers = int(cfg.get("page_workers") or 1)
    model = processor = None
    if page_workers <= 1:
        print(f"[GPU {gpu_id}] 加载模型，待处理 {len(pdf_paths)} 份", flush=True)
        from pdf_parser_pro import load_model

        model, processor = load_model(cfg["model"], device_map="cuda:0")
    else:
        print(
            f"[GPU {gpu_id}] page_workers={page_workers}，"
            f"待处理 {len(pdf_paths)} 份（分片子进程各自加载模型）",
            flush=True,
        )

    records: List[Dict[str, Any]] = []
    for pdf_s in pdf_paths:
        pdf = Path(pdf_s)
        print(f"\n[GPU {gpu_id}] ===== {pdf.name} =====", flush=True)
        try:
            rec = process_one(
                pdf,
                output_root=Path(cfg["output_root"]),
                model=model,
                processor=processor,
                batch_size=cfg["batch_size"],
                dpi=cfg["dpi"],
                max_new_tokens=cfg["max_new_tokens"],
                rotate_mode=cfg["rotate_mode"],
                rotate_fallback=cfg["rotate_fallback"],
                save_figures=cfg["save_figures"],
                save_risk_chunks=cfg["save_risk_chunks"],
                skip_pass1=cfg["skip_pass1"],
                page_workers=page_workers,
                gpu_id=gpu_id,
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
    print(f"[GPU {gpu_id}] 本卡队列完成", flush=True)
    return records


def write_batch_summary(output_root: Path, records: List[Dict[str, Any]]) -> None:
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_docs": len(records),
        "ok": sum(1 for r in records if r.get("status") == "ok"),
        "failed": sum(1 for r in records if r.get("status") == "failed"),
        "records": records,
    }
    path = output_root / "batch_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# samples 批量解析摘要",
        "",
        f"- 生成时间: {summary['generated_at']}",
        f"- 文档数: {summary['n_docs']}（成功 {summary['ok']} / 失败 {summary['failed']}）",
        "",
        "| 文档 | GPU | 状态 | 总耗时 | Pass1 | sec/页 | QA问题 | 建议关注页 |",
        "| --- | ---: | --- | ---: | --- | ---: | ---: | --- |",
    ]
    for r in records:
        qa1 = r.get("qa_pass1") or {}
        p1 = r.get("pass1") if isinstance(r.get("pass1"), dict) else {}
        issues = qa1.get("issue_count", "-")
        focus = qa1.get("reparse_pages_csv") or "-"
        if isinstance(focus, str) and len(focus) > 40:
            focus = focus[:37] + "..."
        total_h = (
            f"{r['elapsed_sec'] / 3600:.2f}h"
            if isinstance(r.get("elapsed_sec"), (int, float))
            else "-"
        )
        p1_h = (
            f"{p1['elapsed_sec'] / 3600:.2f}h"
            if isinstance(p1.get("elapsed_sec"), (int, float))
            else "-"
        )
        md_lines.append(
            f"| `{r.get('stem')}` | {r.get('gpu_id', '-')} | {r.get('status')} | "
            f"{total_h} | {p1_h} | {p1.get('sec_per_page', '-')} | "
            f"{issues} | `{focus}` |"
        )
    md_path = output_root / "batch_summary.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"\n批量摘要: {path}")
    print(f"Markdown: {md_path}")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="批量解析 samples：全文解析 + 旋转回退 + QA（支持多卡）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--samples-dir",
        type=Path,
        default=DEFAULT_SAMPLES,
        help="招股书 PDF 目录",
    )
    p.add_argument(
        "--pdf",
        type=Path,
        default=None,
        help="只解析这一份 PDF（优先于 --samples-dir/--offset/--limit）",
    )
    p.add_argument(
        "--offset",
        type=int,
        default=0,
        help="跳过前 N 份（按文件名排序）。例：前 4 份已跑完则 --offset 4",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=5,
        help="从 offset 起再取 N 份",
    )
    p.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="输出根目录（每份一份子目录）",
    )
    p.add_argument(
        "--model",
        default="./models/infly/Infinity-Parser2-Flash",
    )
    p.add_argument(
        "--gpus",
        default="auto",
        help='物理 GPU：如 "1" / "1,2,3,4"；"auto"=全部空闲卡；'
        '空字符串 ""=沿用环境变量',
    )
    p.add_argument(
        "--min-free-mib",
        type=int,
        default=20000,
        help="--gpus auto 时要求的最小空闲显存 (MiB)",
    )
    p.add_argument(
        "--no-parallel",
        action="store_true",
        help="强制单进程（即使指定多卡也只在第一张上跑）",
    )
    p.add_argument(
        "--page-workers",
        type=int,
        default=2,
        help="同卡页分片并行进程数（Flash~4GB，2 份通常可同驻 24GB；OOM 则改 1）",
    )
    p.add_argument(
        "--device-map",
        default="cuda:0",
        help="单卡/每进程内的 device_map（并行时固定 cuda:0）",
    )
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="推理 batch（显存有余量时 8 优于 4；OOM 降到 4）",
    )
    p.add_argument(
        "--max-new-tokens",
        type=int,
        default=16384,
        help="生成上限（过大易被个别长页拖慢整个 batch）",
    )
    p.add_argument(
        "--rotate-mode",
        default="auto",
        choices=("none", "auto", "cw90", "ccw90", "180", "manual"),
    )
    p.add_argument(
        "--no-rotate-fallback",
        action="store_true",
        help="关闭旋转质量回退（默认开启）",
    )
    p.add_argument(
        "--no-figures",
        action="store_true",
        help="不裁剪保存 figure 图片（默认保存）",
    )
    p.add_argument("--no-risk-chunks", action="store_true")
    p.add_argument(
        "--skip-pass1",
        action="store_true",
        help="跳过全文解析，直接对已有 full_parse 做 QA",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出 PDF 与 GPU 分配，不加载模型",
    )
    return p


def _check_runtime_env() -> None:
    """尽早发现跑错 conda / 缺依赖（spawn 子进程会继承 sys.executable）。"""
    print(f"python: {sys.executable}", flush=True)
    missing = []
    for mod in ("torch", "transformers", "qwen_vl_utils", "fitz", "PIL"):
        try:
            __import__(mod if mod != "PIL" else "PIL.Image")
        except ImportError:
            missing.append(mod)
    if missing:
        raise SystemExit(
            "缺少依赖: "
            + ", ".join(missing)
            + "\n请用 infinity_parser 环境启动，例如:\n"
            "  /nfs/users/wuqianqian/anaconda3/envs/infinity_parser/bin/python "
            "batch_parse_samples.py ..."
        )


def main(argv: Optional[List[str]] = None) -> None:
    args = build_argparser().parse_args(argv)
    samples_dir = args.samples_dir.resolve()
    output_root = args.output_dir.resolve()
    if args.pdf is not None:
        pdf_path = args.pdf.resolve()
        if not pdf_path.is_file():
            raise SystemExit(f"--pdf 不存在: {pdf_path}")
        pdfs = [pdf_path]
        print(f"单文件: {pdf_path}")
    else:
        pdfs = list_sample_pdfs(samples_dir, args.limit, offset=args.offset)
        print(f"samples: {samples_dir}")
    print(f"output:  {output_root}")
    if args.pdf is None:
        print(
            f"将处理第 {args.offset + 1}-{args.offset + len(pdfs)} 份"
            f"（offset={args.offset}, limit={args.limit}）:"
        )
        for i, p in enumerate(pdfs):
            print(f"  {args.offset + i + 1}. {p.name}")
    else:
        print(f"将处理: {pdfs[0].name}")

    if not args.dry_run:
        _check_runtime_env()

    gpus_spec = args.gpus if args.gpus != "" else None
    try:
        gpu_ids = resolve_gpu_ids(gpus_spec, min_free_mib=args.min_free_mib)
    except Exception as e:
        print(f"GPU 解析失败: {e}")
        sys.exit(1)

    if args.no_parallel and len(gpu_ids) > 1:
        print(f"--no-parallel：仅使用 GPU {gpu_ids[0]}（忽略 {gpu_ids[1:]}）")
        gpu_ids = gpu_ids[:1]

    single_pdf_multi_gpu = len(pdfs) == 1 and len(gpu_ids) > 1
    if single_pdf_multi_gpu:
        n_proc = len(gpu_ids) * max(args.page_workers, 1)
        print(
            f"\n模式: 一份 PDF 跨多卡分片 | GPUs={gpu_ids} | "
            f"每卡 page_workers={args.page_workers} | 总进程≈{n_proc}"
        )
        print(f"  PDF: {pdfs[0].name}")
    else:
        assignments = assign_pdfs_to_gpus(pdfs, gpu_ids)
        print(f"\nGPU 分配（一卡一本并行，共 {len(gpu_ids)} 卡）:")
        for gid, plist in assignments:
            names = ", ".join(p.name for p in plist)
            print(f"  GPU {gid}: {names}")
    print(
        f"page_workers={args.page_workers}, batch_size={args.batch_size}, "
        f"max_new_tokens={args.max_new_tokens}"
    )

    if args.dry_run:
        print("\n[dry-run] 退出，未加载模型。")
        return

    output_root.mkdir(parents=True, exist_ok=True)
    rotate_fallback = not args.no_rotate_fallback
    cfg: Dict[str, Any] = {
        "workdir": str(_THIS_DIR),
        "output_root": str(output_root),
        "model": args.model,
        "batch_size": args.batch_size,
        "dpi": args.dpi,
        "max_new_tokens": args.max_new_tokens,
        "rotate_mode": args.rotate_mode,
        "rotate_fallback": rotate_fallback,
        "save_figures": not args.no_figures,
        "save_risk_chunks": not args.no_risk_chunks,
        "skip_pass1": args.skip_pass1,
        "page_workers": args.page_workers,
    }

    print(
        f"\n参数: batch_size={args.batch_size} page_workers={args.page_workers} "
        f"rotate={args.rotate_mode} fallback={'on' if rotate_fallback else 'off'} "
        f"figures={'on' if not args.no_figures else 'off'}"
    )

    records: List[Dict[str, Any]] = []

    if single_pdf_multi_gpu:
        # 主进程直接调度跨卡分片（不再一卡一本）
        pdf = pdfs[0]
        try:
            rec = process_one(
                pdf,
                output_root=output_root,
                model=None,
                processor=None,
                batch_size=args.batch_size,
                dpi=args.dpi,
                max_new_tokens=args.max_new_tokens,
                rotate_mode=args.rotate_mode,
                rotate_fallback=rotate_fallback,
                save_figures=not args.no_figures,
                save_risk_chunks=not args.no_risk_chunks,
                skip_pass1=args.skip_pass1,
                page_workers=args.page_workers,
                gpu_ids=gpu_ids,
                model_name=args.model,
                workdir=str(_THIS_DIR),
            )
            rec["gpu_id"] = gpu_ids
        except Exception as e:
            print(f"[失败] {pdf.name}: {e}")
            traceback.print_exc()
            rec = {
                "pdf": str(pdf),
                "stem": pdf.stem,
                "gpu_ids": gpu_ids,
                "status": "failed",
                "error": str(e),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
        records = [rec]
        write_batch_summary(output_root, records)
    elif len(gpu_ids) == 1:
        # 单卡：复用 GPU worker 逻辑（支持 page_workers）
        gid = gpu_ids[0]
        records = _worker_process(gid, [str(p) for p in pdfs], cfg)
        write_batch_summary(output_root, records)
    else:
        # 多本 × 多卡：一卡一本
        print(f"启动 {len(assignments)} 个 GPU worker …")
        # Linux 默认 fork；spawn 更安全（CUDA 子进程）
        try:
            import multiprocessing as mp

            ctx = mp.get_context("spawn")
        except Exception:
            ctx = None

        executor_kwargs: Dict[str, Any] = {"max_workers": len(assignments)}
        if ctx is not None:
            executor_kwargs["mp_context"] = ctx

        with ProcessPoolExecutor(**executor_kwargs) as ex:
            futures = {
                ex.submit(
                    _worker_process,
                    gid,
                    [str(p) for p in plist],
                    cfg,
                ): gid
                for gid, plist in assignments
            }
            for fut in as_completed(futures):
                gid = futures[fut]
                try:
                    part = fut.result()
                    records.extend(part)
                    print(f"[主进程] GPU {gid} 返回 {len(part)} 条记录")
                except Exception as e:
                    print(f"[主进程] GPU {gid} worker 崩溃: {e}")
                    traceback.print_exc()
                    records.append(
                        {
                            "gpu_id": gid,
                            "status": "failed",
                            "error": f"worker crashed: {e}",
                            "finished_at": datetime.now().isoformat(
                                timespec="seconds"
                            ),
                        }
                    )
                write_batch_summary(output_root, records)

    # 按原始 PDF 顺序重排摘要
    order = {p.stem: i for i, p in enumerate(pdfs)}
    records.sort(key=lambda r: order.get(r.get("stem", ""), 10**9))
    write_batch_summary(output_root, records)

    failed = [r for r in records if r.get("status") == "failed"]
    if failed:
        print(f"\n完成，但有 {len(failed)} 份失败。")
        sys.exit(1)
    print("\n全部完成。")


if __name__ == "__main__":
    main()
