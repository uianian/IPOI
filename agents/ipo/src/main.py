from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.app_state import (
    redis_client,
    database,
    skill_registry,
    vllm_client,
    document_index_store,
)
from src.api.routes import analysis, system, websocket, documents
from src.api.middleware import AccessControlMiddleware
from src.api.error_handlers import ErrorHandlerMiddleware

logger = logging.getLogger(__name__)


def _register_skills() -> None:
    if skill_registry.discover_skill("long_doc_retrieval"):
        return
    from src.skills.long_doc_retrieval.skill import LongDocRetrievalSkill
    from src.skills.peer_comparison.skill import PeerComparisonSkill
    from src.skills.cash_flow.skill import CashFlowCalculationSkill
    from src.skills.sentiment_scoring.skill import SentimentScoringSkill

    skill_registry.register_skill(LongDocRetrievalSkill(vllm_client, document_index_store))
    skill_registry.register_skill(PeerComparisonSkill())
    skill_registry.register_skill(CashFlowCalculationSkill())
    skill_registry.register_skill(SentimentScoringSkill())
    logger.info("Skills registered on shared skill_registry")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init()
    await redis_client.init()
    await vllm_client.init()
    _register_skills()
    # Ensure new tables exist
    try:
        from src.db.models import Base

        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.warning("create_all failed: %s", e)
    yield
    await database.close()
    await redis_client.close()
    await vllm_client.close()


app = FastAPI(
    title=settings.system.app_name,
    description="基于多智能体协同的港股IPO招股书解析与上市后风险预警系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessControlMiddleware)
app.add_middleware(ErrorHandlerMiddleware)

app.include_router(analysis.router)
app.include_router(documents.router)
app.include_router(system.router)
app.include_router(websocket.router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.system.app_name}
