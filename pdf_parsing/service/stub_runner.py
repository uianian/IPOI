"""桩模式：用现有 samples_batch 产物模拟解析进度并导出契约结果。"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from service.config import PARSE_DEFAULTS, STUB_PROGRESS_SECONDS
from service.preview_clean import build_result_payload
from service.sample_catalog import SampleEntry
from service.task_store import TaskStore

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StubRunner:
    def __init__(self, store: TaskStore) -> None:
        self.store = store
        self._threads: dict[str, threading.Thread] = {}

    def start(
        self,
        task_id: str,
        sample: SampleEntry,
        *,
        client_project_id: str,
        duration_sec: float = STUB_PROGRESS_SECONDS,
    ) -> None:
        t = threading.Thread(
            target=self._run,
            args=(task_id, sample, client_project_id, duration_sec),
            name=f"stub-{task_id}",
            daemon=True,
        )
        self._threads[task_id] = t
        t.start()

    def _run(
        self,
        task_id: str,
        sample: SampleEntry,
        client_project_id: str,
        duration_sec: float,
    ) -> None:
        pages = max(sample.page_count, 1)
        try:
            self.store.update_meta(
                task_id, status="running", startedAt=_utcnow(), sampleKey=sample.key
            )
            # PREPARING
            self.store.write_progress(
                task_id,
                {
                    "progress": 3,
                    "stage": "PARSING",
                    "stageDetail": "PREPARING",
                    "pagesDone": 0,
                    "pagesTotal": pages,
                    "etaSeconds": int(duration_sec),
                },
            )
            time.sleep(max(duration_sec * 0.05, 0.05))

            # PARSING 模拟
            steps = max(int(duration_sec / 0.2), 5)
            for i in range(1, steps + 1):
                frac = i / steps
                # progress: 8 → 90
                progress = int(8 + 82 * frac)
                done = int(pages * frac)
                eta = max(int(duration_sec * (1 - frac)), 0)
                self.store.write_progress(
                    task_id,
                    {
                        "progress": min(progress, 90),
                        "stage": "PARSING",
                        "stageDetail": "PARSING",
                        "pagesDone": done,
                        "pagesTotal": pages,
                        "etaSeconds": eta,
                    },
                )
                time.sleep(duration_sec / steps)

            # MERGING / EXPORTING
            self.store.write_progress(
                task_id,
                {
                    "progress": 94,
                    "stage": "PARSING",
                    "stageDetail": "MERGING",
                    "pagesDone": pages,
                    "pagesTotal": pages,
                    "etaSeconds": 1,
                },
            )
            self._export(task_id, sample, client_project_id)

            # 桩模式：指向样本 full_parse，供检索建索引
            full_parse = sample.parse_dir / "full_parse.json"
            if full_parse.is_file():
                self.store.update_meta(
                    task_id, parseJsonPath=str(full_parse.resolve())
                )
            else:
                self.store.update_meta(
                    task_id,
                    parseJsonPath=None,
                    indexStatus="failed",
                    indexMessage=f"样本无 full_parse.json: {sample.parse_dir}",
                )

            self.store.write_progress(
                task_id,
                {
                    "progress": 100,
                    "stage": "READY",
                    "stageDetail": "READY",
                    "pagesDone": pages,
                    "pagesTotal": pages,
                    "etaSeconds": 0,
                },
            )
            self.store.update_meta(task_id, status="completed", finishedAt=_utcnow())
            logger.info("桩任务完成 %s ← %s", task_id, sample.key)

            # 解析完成后自动建索引（前端轮询 index-status）
            if full_parse.is_file():
                from service.index_trigger import start_index_after_parse

                start_index_after_parse(self.store, task_id)
        except Exception as e:
            logger.exception("桩任务失败 %s: %s", task_id, e)
            self.store.write_progress(
                task_id,
                {
                    "progress": 0,
                    "stage": "FAILED",
                    "stageDetail": "FAILED",
                    "pagesDone": 0,
                    "pagesTotal": pages,
                    "etaSeconds": None,
                    "error": {"code": "PARSE_FAILED", "message": str(e)},
                },
            )
            self.store.update_meta(
                task_id,
                status="failed",
                finishedAt=_utcnow(),
                error={"code": "PARSE_FAILED", "message": str(e)},
            )

    def _export(
        self, task_id: str, sample: SampleEntry, client_project_id: str
    ) -> None:
        td = self.store.task_dir(task_id)
        parse_dst = td / "parse"
        parse_dst.mkdir(parents=True, exist_ok=True)

        # 复制契约需要的两份文件；full_parse 不复制（体积大，桩模式不需要）
        for name in ("preview.md", "parse_summary.json"):
            src = sample.parse_dir / name
            if src.is_file():
                shutil.copy2(src, parse_dst / name)

        summary = json.loads(
            (parse_dst / "parse_summary.json").read_text(encoding="utf-8")
        )
        preview = (parse_dst / "preview.md").read_text(encoding="utf-8")
        result = build_result_payload(
            task_id=task_id,
            project_id=client_project_id,
            summary=summary,
            preview_md=preview,
            completed_at=_utcnow(),
            timing={
                "mode": "stub",
                "sampleKey": sample.key,
                "elapsedSec": STUB_PROGRESS_SECONDS,
                "pageCount": sample.page_count,
                "parseDefaults": PARSE_DEFAULTS,
            },
        )
        self.store.write_result(task_id, result)
