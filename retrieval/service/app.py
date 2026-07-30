"""检索前置内部服务入口 — 默认端口 9101（机房放行 9100–9200）。"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from service import __version__
from service.config import (
    FORCE_REBUILD,
    INDEX_ROOT,
    PACKAGE_TOP_K,
    PREPARE_AGENTS,
    SERVICE_VERSION,
)
from service.prep_runner import PrepRunner
from service.prep_store import PrepStore
from service.routes_internal import router as internal_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("retrieval-service")

_STARTED_AT = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    store = PrepStore()
    runner = PrepRunner(store)
    app.state.prep_store = store
    app.state.prep_runner = runner
    logger.info(
        "retrieval-service v%s indexRoot=%s force=%s agents=%s topK=%s",
        SERVICE_VERSION,
        INDEX_ROOT,
        FORCE_REBUILD,
        PREPARE_AGENTS,
        PACKAGE_TOP_K,
    )
    yield


app = FastAPI(
    title="IPO Retrieval Prep Service",
    version=SERVICE_VERSION,
    description="内部检索前置：建索引 + 财务/法务检索包。不对前端开放。",
    lifespan=lifespan,
)

app.include_router(internal_router)


@app.get("/health")
async def health_alias():
    """兼容简短探活。"""
    return {
        "success": True,
        "data": {
            "status": "healthy",
            "version": SERVICE_VERSION,
            "packageVersion": __version__,
            "uptime": int(time.time() - _STARTED_AT),
        },
    }
