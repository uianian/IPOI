"""专家模式解析服务入口 — 默认端口 9100（机房放行 9100–9200）。

对外唯一网关：parse / index-status 本机处理；analysis/* 反代到 9102。
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from service import __version__
from service.config import ANALYSIS_BASE_URL, PARSE_DEFAULTS, SERVICE_VERSION, STUB_MODE
from service.routes_contract import router as contract_router
from service.routes_gateway import probe_analysis_health, router as gateway_router
from service.routes_projects import router as projects_router
from service.sample_catalog import SampleCatalog
from service.stub_runner import StubRunner
from service.task_store import TaskStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("expert-parse")

_STARTED_AT = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = TaskStore()
    catalog = SampleCatalog()
    runner = StubRunner(store)
    app.state.store = store
    app.state.catalog = catalog
    app.state.runner = runner
    logger.info(
        "expert-parse-service v%s stub=%s samples=%d analysisUpstream=%s",
        SERVICE_VERSION,
        STUB_MODE,
        len(catalog.entries),
        ANALYSIS_BASE_URL,
    )
    for e in catalog.entries:
        logger.info(
            "  sample %-40s ticker=%s pages=%s sha=%s",
            e.key[:40],
            e.ticker,
            e.page_count,
            (e.sha256 or "-")[:12],
        )
    yield


app = FastAPI(
    title="IPO Expert PDF Parse Service (Gateway :9100)",
    version=SERVICE_VERSION,
    description=(
        "前端唯一 Base :9100。"
        "本机：parse / index-status；"
        "反代：analysis/start|stream|result → ANALYSIS_BASE_URL(9102)。"
    ),
    lifespan=lifespan,
)

# credentials + "*" 在浏览器里不合法；用 regex 回显 Origin，避免联调被拦
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
# SSE 不宜 gzip；仅压缩较大 JSON
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(gateway_router)
app.include_router(contract_router)
app.include_router(projects_router)


@app.get("/api/v1/health")
@app.get("/health")
async def health():
    """契约探活：含分析上游状态。"""
    catalog: SampleCatalog = app.state.catalog
    analysis = await probe_analysis_health()
    analysis_ok = isinstance(analysis, dict) and analysis.get("status") == "healthy"
    return {
        "success": True,
        "data": {
            "status": "healthy" if catalog.entries else "degraded",
            "version": SERVICE_VERSION,
            "packageVersion": __version__,
            "uptime": int(time.time() - _STARTED_AT),
            "stubMode": STUB_MODE,
            "sampleCount": len(catalog.entries),
            "model": "Infinity-Parser2-Flash",
            "parseDefaults": PARSE_DEFAULTS,
            "gateway": True,
            "upstreams": {
                "analysis": {
                    "baseUrl": ANALYSIS_BASE_URL,
                    "ok": analysis_ok,
                    "detail": analysis,
                }
            },
        },
    }


@app.get("/capacity")
async def capacity():
    """运维探测；桩模式下 acceptingJobs=true（不占 GPU）。"""
    return {
        "success": True,
        "data": {
            "acceptingJobs": STUB_MODE,
            "stubMode": STUB_MODE,
            "running": 0,
            "queued": 0,
            "maxConcurrent": 1,
            "minFreeMiB": PARSE_DEFAULTS["min_free_mib"],
            "usableGpuCount": 0,
            "plannedShardCount": 0,
            "reason": "stub mode — serving existing parse outputs; no GPU required"
            if STUB_MODE
            else "real parse not enabled",
        },
    }
