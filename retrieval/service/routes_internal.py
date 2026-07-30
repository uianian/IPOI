"""内部检索 API：R0–R4。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from service.config import (
    FORCE_REBUILD,
    PACKAGE_TOP_K,
    PREPARE_AGENTS,
    SERVICE_VERSION,
)
from service.prep_runner import PrepRunner, doc_status
from service.prep_store import PrepStore

router = APIRouter(prefix="/internal/retrieval", tags=["retrieval-internal"])


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _ok(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": True, "data": data})


class PrepareBody(BaseModel):
    taskId: str = Field(..., min_length=1)
    parseJsonPath: str = Field(..., min_length=1)
    companyName: str = Field(..., min_length=1)
    stockCode: str = Field(..., min_length=1)
    issuerType: str = Field(default="general")
    listingDate: str = Field(..., min_length=1)


@router.get("/health")
async def health(request: Request):
    from service.config import INDEX_ROOT

    return _ok(
        {
            "status": "healthy",
            "version": SERVICE_VERSION,
            "indexRoot": str(INDEX_ROOT.resolve()),
            "forceRebuild": FORCE_REBUILD,
            "prepareAgents": PREPARE_AGENTS,
            "packageTopK": PACKAGE_TOP_K,
        }
    )


@router.post("/prepare")
async def prepare(body: PrepareBody, request: Request):
    parse_path = Path(body.parseJsonPath)
    if not parse_path.is_file():
        return _err(404, "PARSE_NOT_FOUND", f"parseJsonPath not found: {parse_path}")

    store: PrepStore = request.app.state.prep_store
    runner: PrepRunner = request.app.state.prep_runner

    st = doc_status(body.taskId, str(parse_path.resolve()))
    cached = bool(st["readyForAnalysis"] and not FORCE_REBUILD)

    prep_id = store.next_prep_id()
    store.create(
        prep_id,
        task_id=body.taskId,
        parse_json_path=str(parse_path.resolve()),
        company_name=body.companyName,
        stock_code=body.stockCode,
        issuer_type=body.issuerType,
        listing_date=body.listingDate,
        cached=cached,
    )
    if cached:
        store.update(prep_id, progress=100, stage="READY")
    else:
        runner.start(prep_id)

    return _ok(
        {
            "prepId": prep_id,
            "taskId": body.taskId,
            "status": "ready" if cached else "queued",
            "cached": cached,
        },
        status=202,
    )


@router.get("/preps/{prep_id}/progress")
async def prep_progress(prep_id: str, request: Request):
    store: PrepStore = request.app.state.prep_store
    data = store.read(prep_id)
    if data is None:
        return _err(404, "PREP_NOT_FOUND", f"prep not found: {prep_id}")
    return _ok(
        {
            "prepId": data["prepId"],
            "taskId": data["taskId"],
            "progress": int(data.get("progress") or 0),
            "stage": data.get("stage") or "QUEUED",
            "etaSeconds": data.get("etaSeconds"),
            "error": data.get("error"),
            "cached": data.get("cached"),
            "updatedAt": data.get("updatedAt"),
        }
    )


@router.get("/docs/{task_id}/status")
async def docs_status(task_id: str):
    st = doc_status(task_id)
    return _ok(
        {
            "taskId": st["taskId"],
            "indexExists": st["indexExists"],
            "financePackageExists": st["financePackageExists"],
            "legalPackageExists": st["legalPackageExists"],
            "readyForAnalysis": st["readyForAnalysis"],
        }
    )


@router.get("/docs/{task_id}/artifacts")
async def docs_artifacts(task_id: str):
    st = doc_status(task_id)
    if not st["indexExists"]:
        return _err(404, "DOC_NOT_READY", f"index not ready for taskId={task_id}")
    return _ok(
        {
            "taskId": st["taskId"],
            "readyForAnalysis": st["readyForAnalysis"],
            "indexDir": st["indexDir"],
            "metaPath": st["metaPath"],
            "parseJsonPath": st["parseJsonPath"],
            "financePackagePath": st["financePackagePath"],
            "legalPackagePath": st["legalPackagePath"],
            "sectionMapEmbedded": st["sectionMapEmbedded"],
        }
    )
