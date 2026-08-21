"""分析契约路由：start / stream / result。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from service.analysis_store import AnalysisStore, find_parse_task
from service.stock_code import resolve_stock_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["analysis"])


class AnalysisStartBody(BaseModel):
    clientProjectId: str
    taskId: Optional[str] = None
    llmConfig: Optional[dict[str, Any]] = None
    isBiotech: Optional[bool] = None
    ticker: Optional[str] = None
    stockCode: Optional[str] = None
    enableEmbellishment: bool = True


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _ok(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": True, "data": data})


def _check_index_ready(meta: dict[str, Any]) -> bool:
    if (meta.get("indexStatus") or "").lower() == "ready":
        return True
    return False


@router.post("/{client_project_id}/analysis/start")
async def analysis_start(
    request: Request,
    client_project_id: str,
    body: AnalysisStartBody,
):
    store: AnalysisStore = request.app.state.analysis_store
    runner = request.app.state.analysis_runner

    if body.clientProjectId and body.clientProjectId != client_project_id:
        return _err(400, "CLIENT_PROJECT_MISMATCH", "路径与 body 的 clientProjectId 不一致")

    parse_meta = find_parse_task(
        client_project_id=client_project_id,
        task_id=body.taskId,
    )
    if not parse_meta:
        return _err(
            404,
            "TASK_NOT_FOUND",
            f"未找到解析任务: clientProjectId={client_project_id} taskId={body.taskId}",
        )

    if not _check_index_ready(parse_meta):
        return _err(
            409,
            "INDEX_NOT_READY",
            f"索引未就绪（indexStatus={parse_meta.get('indexStatus')}），请等待 index-status=ready",
        )

    task_id = parse_meta.get("taskId")
    if not task_id:
        return _err(404, "TASK_NOT_FOUND", "meta 缺少 taskId")

    analysis_id = store.next_analysis_id()

    # body.isBiotech 可覆盖（解析任务未存时由前端补传）
    # true → issuerType=biotech；与 CLI 的 18a/18c 门控等价（2.4/3.5）
    if body.isBiotech is not None:
        parse_meta = {
            **parse_meta,
            "isBiotech": bool(body.isBiotech),
            "issuerType": "biotech" if body.isBiotech else "general",
        }

    stock_code = resolve_stock_code(
        ticker=body.ticker,
        stock_code=body.stockCode,
        parse_meta=parse_meta,
    )
    if stock_code:
        parse_meta = {
            **parse_meta,
            "stockCode": stock_code,
            "ticker": body.ticker or parse_meta.get("ticker") or stock_code,
        }

    # 记录是否使用前端覆盖的 LLM（不落盘明文 key）
    llm_cfg = body.llmConfig or {}
    store.create(
        analysis_id=analysis_id,
        client_project_id=client_project_id,
        task_id=task_id,
        parse_meta=parse_meta,
    )
    store.update_meta(
        analysis_id,
        analysisOptions={"embellishmentEnabled": body.enableEmbellishment},
        llmOverride={
            "hasApiKey": bool(str(llm_cfg.get("apiKey") or "").strip()),
            "apiBaseUrl": (str(llm_cfg.get("apiBaseUrl") or "").strip() or None),
            "model": (str(llm_cfg.get("model") or "").strip() or None),
        },
    )
    runner.start_background(
        analysis_id=analysis_id,
        parse_meta=parse_meta,
        llm_config=body.llmConfig,
        enable_embellishment=body.enableEmbellishment,
    )
    return _ok({"analysisId": analysis_id, "status": "started"}, status=202)


@router.get("/{client_project_id}/analysis/stream")
async def analysis_stream(
    request: Request,
    client_project_id: str,
    analysisId: Optional[str] = None,
):
    store: AnalysisStore = request.app.state.analysis_store
    analysis_id = analysisId or store.find_latest_by_project(client_project_id)
    if not analysis_id or not store.exists(analysis_id):
        return _err(404, "ANALYSIS_NOT_FOUND", "未找到分析任务")

    meta = store.read_meta(analysis_id)
    if meta.get("clientProjectId") != client_project_id:
        return _err(404, "ANALYSIS_NOT_FOUND", "analysisId 与 clientProjectId 不匹配")

    async def event_gen() -> AsyncIterator[str]:
        offset = 0
        last_hb = time.time()
        terminal = False
        while not terminal:
            if await request.is_disconnected():
                break
            events, offset = store.read_events_from(analysis_id, offset)
            for ev in events:
                et = ev.get("event") or "message"
                data = ev.get("data") or {}
                yield f"event: {et}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if et == "analysis_complete":
                    terminal = True
            meta_now = store.read_meta(analysis_id)
            if meta_now.get("status") in {"completed", "failed"} and not events:
                # 确保发过 complete
                if meta_now.get("status") == "completed":
                    yield (
                        "event: analysis_complete\ndata: "
                        + json.dumps(
                            {
                                "overallScore": meta_now.get("overallScore"),
                                "riskLevel": meta_now.get("riskLevel"),
                            },
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )
                terminal = True
                break
            now = time.time()
            if now - last_hb >= 15:
                yield (
                    "event: heartbeat\ndata: "
                    + json.dumps({"timestamp": int(now * 1000)}, ensure_ascii=False)
                    + "\n\n"
                )
                last_hb = now
            if not terminal:
                await asyncio.to_thread(store.wait_events, analysis_id, 1.0)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{client_project_id}/analysis/result")
async def analysis_result(
    request: Request,
    client_project_id: str,
    analysisId: Optional[str] = None,
):
    store: AnalysisStore = request.app.state.analysis_store
    analysis_id = analysisId or store.find_latest_by_project(client_project_id)
    if not analysis_id or not store.exists(analysis_id):
        return _err(404, "ANALYSIS_NOT_FOUND", "未找到分析任务")

    meta = store.read_meta(analysis_id)
    if meta.get("clientProjectId") != client_project_id:
        return _err(404, "ANALYSIS_NOT_FOUND", "analysisId 与 clientProjectId 不匹配")

    result = store.read_result(analysis_id)
    if result:
        return _ok(result)

    # 进行中
    thoughts = store.read_thoughts(analysis_id)
    return _ok(
        {
            "analysisId": analysis_id,
            "status": meta.get("status") or "running",
            "phase": meta.get("phase") or "analysis",
            "overallScore": meta.get("overallScore"),
            "riskLevel": meta.get("riskLevel"),
            "thoughts": thoughts,
            "agents": {},
            "debate": {"rounds": 0, "messages": [], "completedAt": None},
            "completedAt": meta.get("completedAt"),
            "error": meta.get("error"),
        }
    )


def _completed_result_or_404(
    request: Request, client_project_id: str, analysis_id: Optional[str]
):
    store: AnalysisStore = request.app.state.analysis_store
    aid = analysis_id or store.find_latest_by_project(client_project_id)
    if not aid or not store.exists(aid):
        return None, _err(404, "ANALYSIS_NOT_FOUND", "未找到分析任务")
    meta = store.read_meta(aid)
    if meta.get("clientProjectId") != client_project_id:
        return None, _err(404, "ANALYSIS_NOT_FOUND", "analysisId 与 clientProjectId 不匹配")
    result = store.read_result(aid)
    if not result or meta.get("status") != "completed":
        return None, _err(404, "REPORT_NOT_READY", "分析尚未完成，报告不可用")
    return result, None


@router.get("/{client_project_id}/report")
async def analysis_report(
    request: Request,
    client_project_id: str,
    analysisId: Optional[str] = None,
):
    result, err = _completed_result_or_404(request, client_project_id, analysisId)
    if err is not None:
        return err
    report = (result or {}).get("report")
    if not isinstance(report, dict):
        return _err(404, "REPORT_NOT_READY", "报告尚未生成")
    return _ok(report)


@router.get("/{client_project_id}/report/export")
async def analysis_report_export(
    request: Request,
    client_project_id: str,
    analysisId: Optional[str] = None,
):
    from datetime import datetime
    from urllib.parse import quote

    from service.report_pdf import render_report_pdf

    result, err = _completed_result_or_404(request, client_project_id, analysisId)
    if err is not None:
        return err
    report = (result or {}).get("report")
    if not isinstance(report, dict):
        return _err(404, "REPORT_NOT_READY", "报告尚未生成")
    store: AnalysisStore = request.app.state.analysis_store
    aid = analysisId or store.find_latest_by_project(client_project_id)
    meta = store.read_meta(aid) if aid else {}
    parse_meta = meta.get("parseMeta") or {}
    ticker = str(parse_meta.get("ticker") or parse_meta.get("stockCode") or "")
    date_s = datetime.now().strftime("%Y-%m-%d")
    filename = f"IPO风险报告_{ticker or 'unknown'}_{date_s}.pdf"
    pdf_bytes = render_report_pdf(report, ticker=ticker)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )

