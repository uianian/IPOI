"""分析任务落盘：meta / events / thoughts / result。"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from service.config import ANALYSES_DIR, PARSE_TASKS_DIR


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_parse_task(
    *,
    client_project_id: str,
    task_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """同机读 pdf_parsing/.runtime/tasks meta。"""
    if task_id:
        meta_path = PARSE_TASKS_DIR / task_id / "meta.json"
        if meta_path.is_file():
            meta = read_json(meta_path)
            if meta.get("clientProjectId") and meta["clientProjectId"] != client_project_id:
                return None
            return meta
        return None

    best: Optional[Dict[str, Any]] = None
    best_ts = ""
    if not PARSE_TASKS_DIR.is_dir():
        return None
    for meta_path in PARSE_TASKS_DIR.glob("task_expert_*/meta.json"):
        try:
            meta = read_json(meta_path)
        except Exception:
            continue
        if meta.get("clientProjectId") != client_project_id:
            continue
        ts = str(meta.get("createdAt") or "")
        if ts >= best_ts:
            best_ts = ts
            best = meta
    return best


class AnalysisStore:
    def __init__(self, analyses_dir: Path = ANALYSES_DIR) -> None:
        self.analyses_dir = analyses_dir
        self.analyses_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = self._load_seq()
        # analysisId → Condition，供 SSE 唤醒
        self._conds: dict[str, threading.Condition] = {}

    def _load_seq(self) -> int:
        seq = 0
        for p in self.analyses_dir.glob("analysis_*"):
            try:
                n = int(p.name.rsplit("_", 1)[-1])
                seq = max(seq, n)
            except ValueError:
                continue
        return seq

    def next_analysis_id(self) -> str:
        with self._lock:
            self._seq += 1
            day = datetime.now().strftime("%Y%m%d")
            return f"analysis_{day}_{self._seq:06d}"

    def analysis_dir(self, analysis_id: str) -> Path:
        return self.analyses_dir / analysis_id

    def _cond(self, analysis_id: str) -> threading.Condition:
        with self._lock:
            if analysis_id not in self._conds:
                self._conds[analysis_id] = threading.Condition()
            return self._conds[analysis_id]

    def create(
        self,
        *,
        analysis_id: str,
        client_project_id: str,
        task_id: str,
        parse_meta: Dict[str, Any],
    ) -> Path:
        ad = self.analysis_dir(analysis_id)
        ad.mkdir(parents=True, exist_ok=True)
        (ad / "logs").mkdir(exist_ok=True)
        meta = {
            "analysisId": analysis_id,
            "clientProjectId": client_project_id,
            "taskId": task_id,
            "status": "started",
            "phase": "analysis",
            "createdAt": _utcnow(),
            "completedAt": None,
            "overallScore": None,
            "riskLevel": None,
            "parseMeta": {
                "companyName": parse_meta.get("companyName"),
                "issuerType": parse_meta.get("issuerType"),
                "isBiotech": parse_meta.get("isBiotech"),
                "ticker": parse_meta.get("ticker"),
                "fileName": parse_meta.get("fileName"),
                "parseJsonPath": parse_meta.get("parseJsonPath"),
            },
            "error": None,
        }
        atomic_write_json(ad / "meta.json", meta)
        (ad / "events.jsonl").write_text("", encoding="utf-8")
        atomic_write_json(ad / "thoughts.json", [])
        return ad

    def exists(self, analysis_id: str) -> bool:
        return (self.analysis_dir(analysis_id) / "meta.json").is_file()

    def read_meta(self, analysis_id: str) -> Dict[str, Any]:
        return read_json(self.analysis_dir(analysis_id) / "meta.json")

    def update_meta(
        self,
        analysis_id: str,
        *,
        notify: bool = True,
        **fields: Any,
    ) -> None:
        path = self.analysis_dir(analysis_id) / "meta.json"
        meta = read_json(path)
        meta.update(fields)
        atomic_write_json(path, meta)
        if notify:
            self._notify(analysis_id)

    def append_sse_event(self, analysis_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """写入 SSE 事件；thought 同步追加 thoughts.json。"""
        ad = self.analysis_dir(analysis_id)
        rec = {"event": event_type, "data": data, "ts": _utcnow()}
        with self._lock:
            with (ad / "events.jsonl").open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            if event_type == "thought" and isinstance(data.get("thought"), dict):
                thoughts_path = ad / "thoughts.json"
                thoughts: List[Dict[str, Any]] = []
                if thoughts_path.is_file():
                    try:
                        thoughts = json.loads(thoughts_path.read_text(encoding="utf-8"))
                    except Exception:
                        thoughts = []
                thoughts.append(data["thought"])
                atomic_write_json(thoughts_path, thoughts)
        self._notify(analysis_id)

    def _notify(self, analysis_id: str) -> None:
        cond = self._cond(analysis_id)
        with cond:
            cond.notify_all()

    def read_events_from(self, analysis_id: str, offset: int) -> tuple[list[dict[str, Any]], int]:
        path = self.analysis_dir(analysis_id) / "events.jsonl"
        if not path.is_file():
            return [], offset
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[offset:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out, len(lines)

    def wait_events(self, analysis_id: str, timeout: float = 1.0) -> None:
        cond = self._cond(analysis_id)
        with cond:
            cond.wait(timeout=timeout)

    def read_thoughts(self, analysis_id: str) -> list[dict[str, Any]]:
        path = self.analysis_dir(analysis_id) / "thoughts.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def write_result(self, analysis_id: str, result: Dict[str, Any]) -> None:
        atomic_write_json(self.analysis_dir(analysis_id) / "result.json", result)
        self._notify(analysis_id)

    def read_result(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        path = self.analysis_dir(analysis_id) / "result.json"
        if not path.is_file():
            return None
        return read_json(path)

    def find_latest_by_project(self, client_project_id: str) -> Optional[str]:
        best_id: Optional[str] = None
        best_ts = ""
        for meta_path in self.analyses_dir.glob("analysis_*/meta.json"):
            try:
                meta = read_json(meta_path)
            except Exception:
                continue
            if meta.get("clientProjectId") != client_project_id:
                continue
            ts = str(meta.get("createdAt") or "")
            if ts >= best_ts:
                best_ts = ts
                best_id = meta.get("analysisId") or meta_path.parent.name
        return best_id
