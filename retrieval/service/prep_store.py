"""Prep 任务状态存储（内存 + 落盘 progress.json）。"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from service.config import PREPS_DIR


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class PrepStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PREPS_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0
        self._mem: dict[str, dict[str, Any]] = {}

    def next_prep_id(self) -> str:
        with self._lock:
            self._seq += 1
            day = datetime.now(timezone.utc).strftime("%Y%m%d")
            return f"prep_{day}_{self._seq:06d}"

    def create(
        self,
        prep_id: str,
        *,
        task_id: str,
        parse_json_path: str,
        company_name: str,
        stock_code: str,
        issuer_type: str,
        listing_date: str,
        cached: bool = False,
    ) -> dict[str, Any]:
        data = {
            "prepId": prep_id,
            "taskId": task_id,
            "parseJsonPath": parse_json_path,
            "companyName": company_name,
            "stockCode": stock_code,
            "issuerType": issuer_type,
            "listingDate": listing_date,
            "progress": 0,
            "stage": "QUEUED",
            "etaSeconds": None,
            "error": None,
            "cached": cached,
            "createdAt": _utcnow(),
            "updatedAt": _utcnow(),
        }
        self._write(prep_id, data)
        return data

    def update(self, prep_id: str, **fields: Any) -> dict[str, Any]:
        data = self.read(prep_id)
        if data is None:
            raise KeyError(prep_id)
        data.update(fields)
        data["updatedAt"] = _utcnow()
        self._write(prep_id, data)
        return data

    def read(self, prep_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            if prep_id in self._mem:
                return dict(self._mem[prep_id])
        path = self.root / prep_id / "progress.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        with self._lock:
            self._mem[prep_id] = data
        return dict(data)

    def _write(self, prep_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._mem[prep_id] = dict(data)
        atomic_write_json(self.root / prep_id / "progress.json", data)
