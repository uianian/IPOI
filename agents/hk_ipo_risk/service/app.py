"""财务/法务分析服务入口 — 默认端口 9102（机房放行 9100–9200）。"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from service import __version__
from service.analysis_runner import AnalysisRunner
from service.analysis_store import AnalysisStore
from service.config import ANALYSES_DIR, SERVICE_VERSION
from service.routes_analysis import router as analysis_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("analysis-service")

_STARTED_AT = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ANALYSES_DIR.mkdir(parents=True, exist_ok=True)
    store = AnalysisStore()
    runner = AnalysisRunner(store)
    app.state.analysis_store = store
    app.state.analysis_runner = runner
    logger.info("analysis-service v%s analysesDir=%s", SERVICE_VERSION, ANALYSES_DIR)
    yield


app = FastAPI(
    title="IPO Finance/Legal Analysis Service",
    version=SERVICE_VERSION,
    description="财务‖法务分析：start / stream / result（繁体 Thought + result 打包）",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router)


@app.get("/api/v1/agents/status")
async def agents_status():
    agents = [
        {"id": "legal", "name": "法务合规Agent", "status": "ready"},
        {"id": "financial", "name": "财务穿透Agent", "status": "ready"},
        {"id": "market", "name": "市场情绪Agent", "status": "ready"},
        {"id": "orchestrator", "name": "风险融合总控Agent", "status": "ready"},
    ]
    return {
        "success": True,
        "data": {
            "agents": agents,
            "readyCount": 4,
            "totalCount": 4,
        },
    }


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    return {
        "success": True,
        "data": {
            "status": "healthy",
            "version": SERVICE_VERSION,
            "packageVersion": __version__,
            "uptime": int(time.time() - _STARTED_AT),
            "service": "analysis",
        },
    }
