"""项目级契约：index-status（解析后建索引门控）。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from service.config import ROOT, SAMPLES_DIR
from service.index_trigger import (
    fetch_doc_status,
    fetch_prep_progress,
    map_index_status,
    start_index_after_parse,
)
from service.task_store import TaskStore, read_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

# 检索包目录（与 9101 同机）
_RETRIEVAL_RUNTIME = Path(
    os.getenv(
        "RETRIEVAL_RUNTIME",
        str(ROOT.parent / "retrieval" / ".runtime"),
    )
)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _ok(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": True, "data": data})


def _recover_parse_json_path(meta: dict) -> Optional[str]:
    """旧任务可能缺 parseJsonPath：用 sampleKey / 同源 ready 任务补全。"""
    existing = meta.get("parseJsonPath")
    if existing and Path(existing).is_file():
        return existing

    sample_key = meta.get("sampleKey")
    if sample_key:
        cand = SAMPLES_DIR / sample_key / "full_parse.json"
        if cand.is_file():
            return str(cand.resolve())

    sha = meta.get("pdfSha256")
    if sha:
        # 找已有 ready 且同 sha 的任务
        for meta_path in (ROOT / ".runtime" / "tasks").glob("task_expert_*/meta.json"):
            try:
                other = read_json(meta_path)
            except Exception:
                continue
            if other.get("pdfSha256") != sha:
                continue
            p = other.get("parseJsonPath")
            if p and Path(p).is_file():
                return p
    return None


def _needs_prepare(meta: dict) -> bool:
    """解析已完成但从未成功挂上 prep / ready。"""
    if (meta.get("status") or "") != "completed":
        return False
    st = (meta.get("indexStatus") or "").lower()
    if st in {"ready", "failed"}:
        return False
    if meta.get("prepId"):
        return False
    # 有路径，或可从 sampleKey 恢复
    return bool(meta.get("parseJsonPath") or meta.get("sampleKey") or meta.get("pdfSha256"))


def _try_reuse_sibling_index(store: TaskStore, task_id: str, meta: dict) -> bool:
    """同 parseJsonPath / pdfSha256 已有 ready 任务时，复用检索包并直接标记 ready。"""
    parse_path = meta.get("parseJsonPath")
    sha = meta.get("pdfSha256")
    sibling: Optional[dict] = None
    for meta_path in store.tasks_dir.glob("task_expert_*/meta.json"):
        try:
            other = read_json(meta_path)
        except Exception:
            continue
        oid = other.get("taskId") or meta_path.parent.name
        if oid == task_id:
            continue
        if (other.get("indexStatus") or "").lower() != "ready":
            continue
        same_path = parse_path and other.get("parseJsonPath") == parse_path
        same_sha = sha and other.get("pdfSha256") == sha
        if not (same_path or same_sha):
            continue
        sibling = other
        break
    if not sibling:
        return False

    sid = sibling.get("taskId")
    if not sid:
        return False

    linked = 0
    for agent in ("finance", "legal"):
        src = _RETRIEVAL_RUNTIME / f"agent_retrieval_{sid}_{agent}.json"
        dst = _RETRIEVAL_RUNTIME / f"agent_retrieval_{task_id}_{agent}.json"
        if not src.is_file():
            continue
        try:
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            dst.symlink_to(src)
            linked += 1
        except OSError:
            try:
                dst.write_bytes(src.read_bytes())
                linked += 1
            except OSError:
                logger.warning("reuse package copy failed %s -> %s", src, dst)

    idx_src = _RETRIEVAL_RUNTIME / "indexes" / sid
    idx_dst = _RETRIEVAL_RUNTIME / "indexes" / task_id
    if idx_src.is_dir() and not idx_dst.exists():
        try:
            idx_dst.symlink_to(idx_src)
        except OSError:
            pass

    if linked < 1:
        return False

    patch = {
        "indexStatus": "ready",
        "indexProgress": 100,
        "indexMessage": f"复用已有索引（同源: {sid}）",
        "prepId": sibling.get("prepId"),
        "indexReusedFrom": sid,
    }
    if not meta.get("parseJsonPath") and sibling.get("parseJsonPath"):
        patch["parseJsonPath"] = sibling["parseJsonPath"]
    store.update_meta(task_id, **patch)
    logger.info("index reused task=%s from=%s packages=%s", task_id, sid, linked)
    return True


def _ensure_prepare(store: TaskStore, task_id: str, meta: dict) -> dict:
    """卡住时：补 parseJsonPath → 复用同源索引 → 否则补触发 prepare。"""
    recovered = _recover_parse_json_path(meta)
    if recovered and meta.get("parseJsonPath") != recovered:
        store.update_meta(task_id, parseJsonPath=recovered)
        meta = store.read_meta(task_id)
        logger.info("recovered parseJsonPath task=%s path=%s", task_id, recovered)

    if _try_reuse_sibling_index(store, task_id, meta):
        return store.read_meta(task_id)
    if meta.get("indexPrepareRequested"):
        return meta
    if not meta.get("parseJsonPath"):
        store.update_meta(
            task_id,
            indexStatus="failed",
            indexMessage="无法定位 full_parse.json，请重新上传解析",
            indexError={"code": "PARSE_NOT_FOUND", "message": "missing parseJsonPath"},
        )
        return store.read_meta(task_id)
    store.update_meta(
        task_id,
        indexPrepareRequested=True,
        indexStatus="indexing",
        indexProgress=1,
        indexMessage="向量索引构建中（补触发）",
    )
    start_index_after_parse(store, task_id)
    logger.info("index prepare re-triggered for task=%s", task_id)
    return store.read_meta(task_id)


@router.get("/{client_project_id}/index-status")
async def index_status(
    request: Request,
    client_project_id: str,
    taskId: Optional[str] = Query(None),
):
    """契约 §6.5：前端轮询；ready 后才可 analysis/start。"""
    store: TaskStore = request.app.state.store
    task_id = taskId
    if not task_id:
        task_id = store.find_by_client_project_id(client_project_id)
    if not task_id or not store.exists(task_id):
        return _err(
            404,
            "INDEX_STATUS_NOT_FOUND",
            f"未找到项目/任务: clientProjectId={client_project_id} taskId={taskId}",
        )

    meta = store.read_meta(task_id)
    if meta.get("clientProjectId") and meta["clientProjectId"] != client_project_id:
        return _err(
            404,
            "INDEX_STATUS_NOT_FOUND",
            "taskId 与 clientProjectId 不匹配",
        )

    # 解析完成但从未 prepare → 自动补触发 / 复用同源索引（修复前端永久卡在「建立索引」）
    if _needs_prepare(meta):
        meta = _ensure_prepare(store, task_id, meta)

    prep = None
    if meta.get("prepId"):
        prep = fetch_prep_progress(meta["prepId"])
        if prep:
            stage = (prep.get("stage") or "").upper()
            if stage == "READY":
                store.update_meta(
                    task_id,
                    indexStatus="ready",
                    indexProgress=100,
                    indexMessage="向量索引已就绪",
                )
                meta = store.read_meta(task_id)
            elif stage == "FAILED":
                err = prep.get("error") or {}
                store.update_meta(
                    task_id,
                    indexStatus="failed",
                    indexProgress=int(prep.get("progress") or 0),
                    indexMessage=(err.get("message") if isinstance(err, dict) else None)
                    or "索引构建失败",
                    indexError=err if isinstance(err, dict) else {"message": str(err)},
                )
                meta = store.read_meta(task_id)
            else:
                msg = prep.get("message") or "向量索引构建中"
                if not prep.get("message"):
                    if stage == "BUILDING_INDEX":
                        msg = "正在计算向量嵌入并写入 FAISS（大文档可能需数分钟）"
                    elif stage == "BUILDING_PACKAGES":
                        msg = "正在生成财务/法务检索包"
                store.update_meta(
                    task_id,
                    indexStatus="indexing",
                    indexProgress=int(prep.get("progress") or 0),
                    indexMessage=msg,
                )
                meta = store.read_meta(task_id)

    doc = fetch_doc_status(task_id)
    mapped = map_index_status(meta=meta, prep=prep, doc=doc)
    return _ok(mapped)
