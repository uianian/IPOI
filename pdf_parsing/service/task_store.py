"""任务目录读写：meta / progress / result 原子落盘。"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from service.config import CACHE_DIR, TASKS_DIR


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class TaskStore:
    def __init__(self, tasks_dir: Path = TASKS_DIR, cache_dir: Path = CACHE_DIR) -> None:
        self.tasks_dir = tasks_dir
        self.cache_dir = cache_dir
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = self._load_seq()

    def _load_seq(self) -> int:
        seq = 0
        for p in self.tasks_dir.glob("task_expert_*"):
            try:
                n = int(p.name.rsplit("_", 1)[-1])
                seq = max(seq, n)
            except ValueError:
                continue
        return seq

    def next_task_id(self) -> str:
        with self._lock:
            self._seq += 1
            day = datetime.now().strftime("%Y%m%d")
            return f"task_expert_{day}_{self._seq:06d}"

    def task_dir(self, task_id: str) -> Path:
        return self.tasks_dir / task_id

    def create_task(
        self,
        *,
        task_id: str,
        client_project_id: str,
        ticker: str,
        file_name: str,
        is_biotech: bool,
        pdf_sha256: str,
        sample_key: Optional[str],
        page_count: int,
        stub: bool,
        params: Dict[str, Any],
        company_name: str = "",
        list_date: str = "",
        stock_code: str = "",
        issuer_type: str = "general",
        listing_date: str = "00000000",
    ) -> Path:
        td = self.task_dir(task_id)
        td.mkdir(parents=True, exist_ok=True)
        (td / "parse").mkdir(exist_ok=True)
        (td / "export").mkdir(exist_ok=True)
        meta = {
            "taskId": task_id,
            "clientProjectId": client_project_id,
            "ticker": ticker,
            "stockCode": stock_code or ticker,
            "fileName": file_name,
            "isBiotech": is_biotech,
            "issuerType": issuer_type,
            "companyName": company_name or "",
            "listDate": list_date or "",
            "listingDate": listing_date or "00000000",
            "pdfSha256": pdf_sha256,
            "sampleKey": sample_key,
            "pageCount": page_count,
            "stub": stub,
            "params": params,
            "parseJsonPath": None,
            "indexStatus": "pending",
            "indexProgress": 0,
            "prepId": None,
            "createdAt": _utcnow(),
            "startedAt": None,
            "finishedAt": None,
            "status": "queued",
        }
        atomic_write_json(td / "meta.json", meta)
        atomic_write_json(
            td / "progress.json",
            {
                "progress": 1,
                "stage": "PARSING",
                "stageDetail": "QUEUED",
                "pagesDone": 0,
                "pagesTotal": page_count,
                "etaSeconds": None,
                "updatedAt": _utcnow(),
            },
        )
        return td

    def find_by_client_project_id(self, client_project_id: str) -> Optional[str]:
        """同一 clientProjectId 取最新创建的任务。"""
        best_id: Optional[str] = None
        best_ts = ""
        for meta_path in self.tasks_dir.glob("task_expert_*/meta.json"):
            try:
                meta = read_json(meta_path)
            except Exception:
                continue
            if meta.get("clientProjectId") != client_project_id:
                continue
            ts = str(meta.get("createdAt") or "")
            if ts >= best_ts:
                best_ts = ts
                best_id = meta.get("taskId") or meta_path.parent.name
        return best_id

    def update_meta(self, task_id: str, **fields: Any) -> None:
        path = self.task_dir(task_id) / "meta.json"
        meta = read_json(path)
        meta.update(fields)
        atomic_write_json(path, meta)

    def write_progress(self, task_id: str, progress: Dict[str, Any]) -> None:
        progress = {**progress, "updatedAt": _utcnow()}
        atomic_write_json(self.task_dir(task_id) / "progress.json", progress)

    def read_progress(self, task_id: str) -> Dict[str, Any]:
        return read_json(self.task_dir(task_id) / "progress.json")

    def read_meta(self, task_id: str) -> Dict[str, Any]:
        return read_json(self.task_dir(task_id) / "meta.json")

    def write_result(self, task_id: str, result: Dict[str, Any]) -> None:
        td = self.task_dir(task_id)
        atomic_write_json(td / "export" / "result.json", result)
        md_path = td / "export" / "content.md"
        md_path.write_text(result.get("markdown") or "", encoding="utf-8")

    def read_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        path = self.task_dir(task_id) / "export" / "result.json"
        if not path.is_file():
            return None
        return read_json(path)

    def exists(self, task_id: str) -> bool:
        return (self.task_dir(task_id) / "meta.json").is_file()

    def save_upload(self, task_id: str, data: bytes) -> Path:
        path = self.task_dir(task_id) / "source.pdf"
        path.write_bytes(data)
        return path

    def link_cache(self, sha256: str, task_id: str) -> None:
        link = self.cache_dir / sha256
        target = self.task_dir(task_id)
        if link.exists() or link.is_symlink():
            return
        try:
            link.symlink_to(target)
        except OSError:
            # 跨设备或不支持软链时写指针文件
            link.write_text(str(target), encoding="utf-8")
