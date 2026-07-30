"""9100 网关：把分析相关请求反代到 9102（前端只认 9100）。"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from service.config import ANALYSIS_BASE_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["gateway-analysis"])

# 透传头（去掉 hop-by-hop）
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def _upstream(path: str, query: str = "") -> str:
    base = ANALYSIS_BASE_URL.rstrip("/")
    url = f"{base}{path}"
    if query:
        url = f"{url}?{query}"
    return url


def _filter_request_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in request.headers.items():
        if k.lower() in _HOP_BY_HOP:
            continue
        out[k] = v
    return out


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in _HOP_BY_HOP:
            continue
        # 由网关 CORS 处理
        if k.lower().startswith("access-control-"):
            continue
        out[k] = v
    return out


async def _proxy_json(request: Request, upstream_path: str) -> Response:
    url = _upstream(upstream_path, request.url.query)
    body = await request.body()
    timeout = httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.request(
                request.method,
                url,
                content=body if body else None,
                headers=_filter_request_headers(request),
            )
    except httpx.ConnectError as e:
        logger.error("analysis upstream unreachable %s: %s", ANALYSIS_BASE_URL, e)
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": {
                    "code": "ANALYSIS_UPSTREAM_DOWN",
                    "message": f"分析服务不可达（{ANALYSIS_BASE_URL}），请确认 9102 已启动",
                },
            },
        )
    except httpx.HTTPError as e:
        logger.exception("analysis proxy error")
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": {"code": "ANALYSIS_PROXY_ERROR", "message": str(e)},
            },
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_filter_response_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


async def _proxy_sse(request: Request, upstream_path: str) -> Response:
    url = _upstream(upstream_path, request.url.query)
    timeout = httpx.Timeout(connect=10.0, read=None, write=60.0, pool=10.0)

    try:
        client = httpx.AsyncClient(timeout=timeout)
        req = client.build_request(
            "GET",
            url,
            headers=_filter_request_headers(request),
        )
        upstream = await client.send(req, stream=True)
    except httpx.ConnectError as e:
        logger.error("analysis SSE upstream unreachable: %s", e)
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": {
                    "code": "ANALYSIS_UPSTREAM_DOWN",
                    "message": f"分析服务不可达（{ANALYSIS_BASE_URL}），请确认 9102 已启动",
                },
            },
        )
    except httpx.HTTPError as e:
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": {"code": "ANALYSIS_PROXY_ERROR", "message": str(e)},
            },
        )

    if upstream.status_code >= 400:
        raw = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        return Response(
            content=raw,
            status_code=upstream.status_code,
            headers=_filter_response_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
        )

    async def event_iter() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    headers = _filter_response_headers(upstream.headers)
    headers["Cache-Control"] = "no-cache"
    headers["Connection"] = "keep-alive"
    headers["X-Accel-Buffering"] = "no"

    return StreamingResponse(
        event_iter(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type") or "text/event-stream",
        headers=headers,
    )


@router.post("/{client_project_id}/analysis/start")
async def gateway_analysis_start(client_project_id: str, request: Request):
    return await _proxy_json(
        request, f"/api/v1/projects/{client_project_id}/analysis/start"
    )


@router.get("/{client_project_id}/analysis/stream")
async def gateway_analysis_stream(client_project_id: str, request: Request):
    return await _proxy_sse(
        request, f"/api/v1/projects/{client_project_id}/analysis/stream"
    )


@router.get("/{client_project_id}/analysis/result")
async def gateway_analysis_result(client_project_id: str, request: Request):
    return await _proxy_json(
        request, f"/api/v1/projects/{client_project_id}/analysis/result"
    )


async def probe_analysis_health() -> Optional[dict]:
    """供网关 /health 聚合。"""
    url = f"{ANALYSIS_BASE_URL.rstrip('/')}/api/v1/health"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                body = r.json()
                return body.get("data") if isinstance(body, dict) else {"raw": body}
            return {"status": "down", "httpStatus": r.status_code}
    except Exception as e:
        return {"status": "down", "message": str(e)}
