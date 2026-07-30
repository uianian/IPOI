"""解析完成后触发检索 prepare（9101），并映射 index-status。"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Optional
from urllib import error, request
import json

from service.config import RETRIEVAL_BASE_URL

logger = logging.getLogger(__name__)


def normalize_stock_code(ticker: str) -> str:
    t = (ticker or "").strip().upper().replace(" ", "")
    t = t.replace(".HK", "").replace(".hk", "")
    if t.isdigit():
        return t.zfill(5)
    m = re.match(r"^(\d{1,5})", t)
    return m.group(1).zfill(5) if m else t


def normalize_listing_date(list_date: str) -> str:
    """前端 listDate → YYYYMMDD；空则 00000000。"""
    s = (list_date or "").strip()
    if not s:
        return "00000000"
    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:
        # 20200630 or from 2020-06-30
        if digits[:4].startswith("20") or digits[:4].startswith("19"):
            return digits
        # 30062020 → unlikely; try DDMMYYYY
        return digits[4:8] + digits[2:4] + digits[0:2]
    # 30-06-2020
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}{int(mo):02d}{int(d):02d}"
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}{int(mo):02d}{int(d):02d}"
    return digits[:8].ljust(8, "0") if digits else "00000000"


def issuer_type_from_biotech(is_biotech: bool) -> str:
    return "biotech" if is_biotech else "general"


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 30.0) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def trigger_prepare(
    *,
    task_id: str,
    parse_json_path: str,
    company_name: str,
    stock_code: str,
    issuer_type: str,
    listing_date: str,
) -> dict[str, Any]:
    url = f"{RETRIEVAL_BASE_URL.rstrip('/')}/internal/retrieval/prepare"
    payload = {
        "taskId": task_id,
        "parseJsonPath": parse_json_path,
        "companyName": company_name or stock_code,
        "stockCode": stock_code,
        "issuerType": issuer_type,
        "listingDate": listing_date,
    }
    return _http_json("POST", url, payload, timeout=60.0)


def fetch_prep_progress(prep_id: str) -> Optional[dict[str, Any]]:
    url = f"{RETRIEVAL_BASE_URL.rstrip('/')}/internal/retrieval/preps/{prep_id}/progress"
    try:
        out = _http_json("GET", url, timeout=10.0)
        return out.get("data") if out.get("success") else None
    except Exception as e:
        logger.warning("fetch prep progress failed: %s", e)
        return None


def fetch_doc_status(task_id: str) -> Optional[dict[str, Any]]:
    url = f"{RETRIEVAL_BASE_URL.rstrip('/')}/internal/retrieval/docs/{task_id}/status"
    try:
        out = _http_json("GET", url, timeout=10.0)
        return out.get("data") if out.get("success") else None
    except Exception as e:
        logger.warning("fetch doc status failed: %s", e)
        return None


def map_index_status(
    *,
    meta: dict[str, Any],
    prep: Optional[dict[str, Any]] = None,
    doc: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """映射为契约 status: indexing | ready | failed。"""
    local = (meta.get("indexStatus") or "").lower()
    if local == "failed" or (prep and (prep.get("stage") or "").upper() == "FAILED"):
        err = (prep or {}).get("error") or meta.get("indexError") or {}
        msg = err.get("message") if isinstance(err, dict) else (meta.get("indexMessage") or "索引构建失败")
        return {
            "status": "failed",
            "message": msg or "索引构建失败",
            "progress": int((prep or {}).get("progress") or meta.get("indexProgress") or 0),
        }
    if doc and doc.get("readyForAnalysis"):
        return {"status": "ready", "message": "向量索引已就绪", "progress": 100}
    if prep:
        stage = (prep.get("stage") or "").upper()
        progress = int(prep.get("progress") or 0)
        if stage == "READY" or progress >= 100:
            return {"status": "ready", "message": "向量索引已就绪", "progress": 100}
        msg = prep.get("message")
        if not msg:
            if stage == "BUILDING_INDEX":
                msg = "正在计算向量嵌入并写入 FAISS（大文档可能需数分钟）"
            elif stage == "BUILDING_PACKAGES":
                msg = "正在生成财务/法务检索包"
            elif stage in ("BUILDING_SECTION", "QUEUED"):
                msg = "准备建索引"
            else:
                msg = "向量索引构建中"
        return {
            "status": "indexing",
            "message": msg,
            "progress": progress,
        }
    if local == "ready":
        return {"status": "ready", "message": "向量索引已就绪", "progress": 100}
    if local in ("indexing", "queued", "pending"):
        return {
            "status": "indexing",
            "message": meta.get("indexMessage") or "向量索引构建中",
            "progress": int(meta.get("indexProgress") or 0),
        }
    # 解析已完成但尚未触发
    if (meta.get("status") or "") == "completed":
        return {
            "status": "indexing",
            "message": meta.get("indexMessage") or "等待启动向量索引",
            "progress": int(meta.get("indexProgress") or 0),
        }
    return {
        "status": "indexing",
        "message": "等待解析完成后再建索引",
        "progress": 0,
    }


def start_index_after_parse(store: Any, task_id: str) -> None:
    """后台线程：写 parseJsonPath 并调用 9101 prepare。"""

    def _run() -> None:
        try:
            meta = store.read_meta(task_id)
            parse_path = meta.get("parseJsonPath")
            if not parse_path:
                store.update_meta(
                    task_id,
                    indexStatus="failed",
                    indexMessage="缺少 parseJsonPath，无法建索引",
                    indexError={"code": "PARSE_NOT_FOUND", "message": "缺少 parseJsonPath"},
                )
                return
            from pathlib import Path

            if not Path(parse_path).is_file():
                store.update_meta(
                    task_id,
                    indexStatus="failed",
                    indexMessage=f"full_parse 不存在: {parse_path}",
                    indexError={"code": "PARSE_NOT_FOUND", "message": parse_path},
                )
                return

            store.update_meta(
                task_id,
                indexStatus="indexing",
                indexProgress=1,
                indexMessage="向量索引构建中",
            )
            stock = meta.get("stockCode") or normalize_stock_code(meta.get("ticker") or "")
            listing = meta.get("listingDate") or normalize_listing_date(meta.get("listDate") or "")
            issuer = meta.get("issuerType") or issuer_type_from_biotech(bool(meta.get("isBiotech")))
            company = meta.get("companyName") or stock

            out = trigger_prepare(
                task_id=task_id,
                parse_json_path=parse_path,
                company_name=company,
                stock_code=stock,
                issuer_type=issuer,
                listing_date=listing,
            )
            data = out.get("data") or {}
            prep_id = data.get("prepId")
            cached = bool(data.get("cached"))
            store.update_meta(
                task_id,
                prepId=prep_id,
                indexStatus="ready" if cached else "indexing",
                indexProgress=100 if cached else 5,
                indexMessage="向量索引已就绪" if cached else "向量索引构建中",
            )
            logger.info(
                "index prepare started task=%s prepId=%s cached=%s",
                task_id,
                prep_id,
                cached,
            )
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            logger.exception("prepare HTTP error task=%s: %s", task_id, body)
            store.update_meta(
                task_id,
                indexStatus="failed",
                indexMessage=f"检索服务错误: {e.code}",
                indexError={"code": "INDEX_BUILD_FAILED", "message": body},
            )
        except Exception as e:
            logger.exception("prepare failed task=%s", task_id)
            store.update_meta(
                task_id,
                indexStatus="failed",
                indexMessage=str(e),
                indexError={"code": "INDEX_BUILD_FAILED", "message": str(e)},
            )

    threading.Thread(target=_run, name=f"index-{task_id}", daemon=True).start()
