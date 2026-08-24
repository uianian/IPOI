"""契约组：expert start / progress / result。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from service.config import BACKEND_PARSE_ENABLED, MAX_UPLOAD_BYTES, PARSE_DEFAULTS, QUEUE_FULL_LIMIT
from service.preview_clean import slice_markdown_by_pages
from service.sample_catalog import SampleCatalog
from service.stub_runner import StubRunner
from service.real_runner import RealRunner
from service.task_store import TaskStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/parse/expert", tags=["parse-expert"])


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _ok(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": True, "data": data})


def get_store(request: Request) -> TaskStore:
    return request.app.state.store


def get_catalog(request: Request) -> SampleCatalog:
    return request.app.state.catalog


def get_runner(request: Request) -> StubRunner:
    return request.app.state.runner

def get_real_runner(request: Request) -> RealRunner:
    return request.app.state.real_runner


@router.post("/start")
async def start_parse(
    request: Request,
    file: UploadFile = File(...),
    ticker: str = Form(...),
    clientProjectId: str = Form(...),
    fileName: str = Form(...),
    isBiotech: str = Form(...),
    enableEmbellishment: str = Form(...),
    companyName: Optional[str] = Form(""),
    listDate: Optional[str] = Form(""),
    maxPages: Optional[int] = Form(None),
    forceReparse: Optional[str] = Form(None),
):
    store = get_store(request)
    catalog = get_catalog(request)
    catalog.reload()  # 纳入服务运行期间刚完成的 realtime 解析产物

    # 粗略队列限制
    running = sum(
        1
        for p in store.tasks_dir.glob("task_expert_*/meta.json")
        if '"status": "running"' in p.read_text(encoding="utf-8")
        or '"status": "queued"' in p.read_text(encoding="utf-8")
    )
    if running >= QUEUE_FULL_LIMIT:
        return _err(429, "QUEUE_FULL", f"队列已满（>{QUEUE_FULL_LIMIT}），请稍后重试")

    if not ticker or not clientProjectId or not fileName:
        return _err(400, "MISSING_FIELD", "ticker / clientProjectId / fileName 必填")

    biotech_raw = (isBiotech or "").strip().lower()
    if biotech_raw not in ("true", "false", "1", "0"):
        return _err(400, "MISSING_FIELD", 'isBiotech 须为 "true" 或 "false"')
    is_biotech = biotech_raw in ("true", "1")

    embellishment_raw = (enableEmbellishment or "").strip().lower()
    if embellishment_raw not in ("true", "false"):
        return _err(400, "MISSING_FIELD", "enableEmbellishment 须为 true 或 false")
    enable_embellishment = embellishment_raw == "true"

    from service.index_trigger import (
        issuer_type_from_biotech,
        normalize_listing_date,
        normalize_stock_code,
    )

    stock_code = normalize_stock_code(ticker)
    listing_date = normalize_listing_date(listDate or "")
    issuer_type = issuer_type_from_biotech(is_biotech)
    company_name = (companyName or "").strip()

    raw = await file.read()
    if not raw:
        return _err(400, "INVALID_FILE", "空文件")
    if len(raw) > MAX_UPLOAD_BYTES:
        return _err(413, "FILE_TOO_LARGE", f"PDF 超过 {MAX_UPLOAD_BYTES} 字节上限")
    if not raw.startswith(b"%PDF-"):
        return _err(400, "INVALID_FILE", "文件不是有效 PDF（magic number 校验失败）")

    import hashlib

    sha = hashlib.sha256(raw).hexdigest()
    matched_by = "default"
    sample = catalog.match(sha256=sha)
    if sample is not None:
        matched_by = "sha256"
    else:
        sample = catalog.match(ticker=ticker, file_name=fileName)
        if sample is not None:
            matched_by = "ticker/fileName"
        else:
            sample = None
            matched_by = "miss"

    force_reparse = (forceReparse or "").lower() in ("true", "1")
    use_cached = sample is not None and not force_reparse
    if not use_cached and not BACKEND_PARSE_ENABLED:
        return _err(503, "REAL_PARSE_DISABLED", "pdf_parsing/output 未找到该 PDF 的完整解析结果，且后端实时解析开关未开启")

    task_id = store.next_task_id()
    store.create_task(
        task_id=task_id,
        client_project_id=clientProjectId,
        ticker=ticker,
        file_name=fileName,
        is_biotech=is_biotech,
        enable_embellishment=enable_embellishment,
        pdf_sha256=sha,
        sample_key=sample.key if use_cached else None,
        page_count=sample.page_count if use_cached else 0,
        stub=use_cached,
        company_name=company_name,
        list_date=(listDate or "").strip(),
        stock_code=stock_code,
        issuer_type=issuer_type,
        listing_date=listing_date,
        params={
            **PARSE_DEFAULTS,
            "maxPages": maxPages,
            "forceReparse": force_reparse,
            "matchedBy": matched_by,
        },
    )
    store.save_upload(task_id, raw)
    store.link_cache(sha, task_id)

    # ETA：桩模式几秒；真解析时按页数估算
    if use_cached:
        estimated = 3
        get_runner(request).start(task_id, sample, client_project_id=clientProjectId)
    else:
        estimated = 0
        get_real_runner(request).start(task_id, client_project_id=clientProjectId)

    logger.info(
        "start %s ticker=%s sample=%s matchedBy=%s project=%s embellishment=%s",
        task_id,
        ticker,
        sample.key if use_cached else None,
        matched_by,
        clientProjectId,
        enable_embellishment,
    )
    return _ok(
        {
            "taskId": task_id,
            "status": "parsing",
            "cached": use_cached,
            "queuePosition": 0,
            "estimatedSeconds": estimated,
            "sampleKey": sample.key if use_cached else None,
            "stub": use_cached,
        },
        status=202,
    )


@router.get("/tasks/{task_id}/progress")
async def get_progress(request: Request, task_id: str):
    store = get_store(request)
    if not store.exists(task_id):
        return _err(404, "TASK_NOT_FOUND", f"任务不存在: {task_id}")
    data = store.read_progress(task_id)
    # 对外契约字段
    out = {
        "progress": int(data.get("progress") or 0),
        "stage": data.get("stage") or "PARSING",
        "stageDetail": data.get("stageDetail"),
        "pagesDone": data.get("pagesDone"),
        "pagesTotal": data.get("pagesTotal"),
        "etaSeconds": data.get("etaSeconds"),
        "updatedAt": data.get("updatedAt"),
    }
    if data.get("error"):
        out["error"] = data["error"]
    return _ok(out)


@router.get("/tasks/{task_id}/result")
async def get_result(request: Request, task_id: str):
    store = get_store(request)
    if not store.exists(task_id):
        return _err(404, "TASK_NOT_FOUND", f"任务不存在: {task_id}")

    progress = store.read_progress(task_id)
    stage = progress.get("stage")
    if stage == "FAILED":
        meta = store.read_meta(task_id)
        return _ok(
            {
                "taskId": task_id,
                "projectId": meta.get("clientProjectId"),
                "mode": "expert",
                "status": "failed",
                "stats": {
                    "totalPages": 0,
                    "parsedPages": 0,
                    "chartCount": 0,
                    "tableCount": 0,
                    "textChunkCount": 0,
                },
                "markdown": "",
                "parseSummary": {},
                "error": progress.get("error")
                or meta.get("error")
                or {"code": "PARSE_FAILED", "message": "解析失败"},
            }
        )

    result = store.read_result(task_id)
    if result is None or stage != "READY":
        return _err(404, "PARSE_NOT_COMPLETED", "解析尚未完成")
    return _ok(result)


@router.get("/tasks/{task_id}/result/content.md")
async def get_result_markdown(
    request: Request,
    task_id: str,
    pageFrom: Optional[int] = None,
    pageTo: Optional[int] = None,
):
    store = get_store(request)
    if not store.exists(task_id):
        return _err(404, "TASK_NOT_FOUND", f"任务不存在: {task_id}")
    result = store.read_result(task_id)
    progress = store.read_progress(task_id)
    if result is None or progress.get("stage") != "READY":
        return _err(404, "PARSE_NOT_COMPLETED", "解析尚未完成")
    md = slice_markdown_by_pages(result.get("markdown") or "", pageFrom, pageTo)
    return PlainTextResponse(content=md, media_type="text/markdown; charset=utf-8")
