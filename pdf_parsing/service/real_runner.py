"""缓存未命中时调用现有批量解析器，并汇总逐页进度。"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from service.config import PARSE_DEFAULTS, ROOT
from service.preview_clean import build_result_payload

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_batch_progress(progress_dir: Path) -> dict:
    """汇总 status.json 和每个 shard 的原子进度文件。"""
    status: dict = {}
    try:
        status = json.loads((progress_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    done = 0
    shard_total = 0
    shard_stages: list[str] = []
    for path in progress_dir.glob("shard*.json") if progress_dir.is_dir() else ():
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        done += int(item.get("done") or 0)
        shard_total += int(item.get("total") or 0)
        shard_stages.append(str(item.get("stage") or ""))
    total = int(status.get("pagesTotal") or shard_total or 0)
    stage = str(status.get("stage") or "MODEL_LOADING")
    if stage == "PAGE_PARSING" and shard_stages and all(x == "MODEL_LOADING" for x in shard_stages):
        stage = "MODEL_LOADING"
    return {"stage": stage, "pagesDone": min(done, total) if total else done, "pagesTotal": total}


def progress_percent(stage: str, done: int, total: int) -> int:
    if stage == "MODEL_LOADING":
        return 5
    if stage == "PAGE_PARSING":
        return min(88, 5 + int(83 * done / total)) if total else 5
    return {"MERGING": 92, "QA": 96, "COMPLETE": 98}.get(stage, 3)


class RealRunner:
    def __init__(self, store):
        self.store = store
        self._threads: dict[str, threading.Thread] = {}

    def start(self, task_id: str, *, client_project_id: str) -> None:
        thread = threading.Thread(
            target=self._run, args=(task_id, client_project_id),
            daemon=True, name=f"real-{task_id}",
        )
        self._threads[task_id] = thread
        thread.start()

    def _run(self, task_id: str, project_id: str) -> None:
        task_dir = self.store.task_dir(task_id)
        source = task_dir / "source.pdf"
        output_root = ROOT / "output" / "realtime" / task_id
        parse_dir = output_root / source.stem
        progress_dir = parse_dir / "_progress"
        params = self.store.read_meta(task_id).get("params") or {}
        cmd = [
            sys.executable, str(ROOT / "batch_parse_samples.py"),
            "--pdf", str(source), "--output-dir", str(output_root),
            "--gpus", str(params.get("gpus") or "auto"),
            "--page-workers", str(params.get("page_workers") or 2),
            "--min-free-mib", str(params.get("min_free_mib") or 20000),
            "--dpi", str(params.get("dpi") or 300),
            "--batch-size", str(params.get("batch_size") or 2),
            "--max-new-tokens", str(params.get("max_new_tokens") or 16384),
            "--rotate-mode", str(params.get("rotate_mode") or "none"),
        ]
        if not params.get("rotate_fallback"):
            cmd.append("--no-rotate-fallback")
        if params.get("no_figures"):
            cmd.append("--no-figures")
        try:
            self.store.update_meta(task_id, status="running", startedAt=_now())
            self.store.write_progress(task_id, {
                "progress": 3, "stage": "PARSING", "stageDetail": "PREPARING",
                "pagesDone": 0, "pagesTotal": 0, "etaSeconds": None,
            })
            log_path = task_dir / "parse.log"
            started = time.monotonic()
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, text=True,
                )
                while process.poll() is None:
                    current = read_batch_progress(progress_dir)
                    done, total = current["pagesDone"], current["pagesTotal"]
                    elapsed = time.monotonic() - started
                    eta = int(elapsed / done * (total - done)) if done and total > done else None
                    self.store.write_progress(task_id, {
                        "progress": progress_percent(current["stage"], done, total),
                        "stage": "PARSING", "stageDetail": current["stage"],
                        "pagesDone": done, "pagesTotal": total, "etaSeconds": eta,
                    })
                    time.sleep(0.5)
                return_code = process.wait()
            if return_code:
                raise RuntimeError(f"批量解析退出码 {return_code}；详见 {log_path}")

            full_parse = parse_dir / "full_parse.json"
            summary_path = parse_dir / "parse_summary.json"
            preview_path = parse_dir / "preview.md"
            if not all(path.is_file() for path in (full_parse, summary_path, preview_path)):
                raise RuntimeError(f"未生成完整解析产物: {parse_dir}")
            pages = json.loads(full_parse.read_text(encoding="utf-8"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(pages, list) or len(pages) != int(summary.get("total_pages") or 0):
                raise RuntimeError("解析结果页数不完整")
            payload = build_result_payload(
                task_id=task_id, project_id=project_id, summary=summary,
                preview_md=preview_path.read_text(encoding="utf-8"), completed_at=_now(),
                timing={"mode": "real", "parseDefaults": PARSE_DEFAULTS},
            )
            self.store.write_result(task_id, payload)
            self.store.update_meta(
                task_id, status="completed", finishedAt=_now(),
                parseJsonPath=str(full_parse.resolve()), stub=False,
            )
            self.store.write_progress(task_id, {
                "progress": 100, "stage": "READY", "stageDetail": "READY",
                "pagesDone": len(pages), "pagesTotal": len(pages), "etaSeconds": 0,
            })
            from service.index_trigger import start_index_after_parse
            start_index_after_parse(self.store, task_id)
        except Exception as exc:
            logger.exception("实时解析失败 %s", task_id)
            error = {"code": "PARSE_FAILED", "message": str(exc)}
            self.store.write_progress(task_id, {
                "progress": 0, "stage": "FAILED", "stageDetail": "FAILED",
                "pagesDone": 0, "pagesTotal": 0, "etaSeconds": None, "error": error,
            })
            self.store.update_meta(task_id, status="failed", finishedAt=_now(), error=error)
