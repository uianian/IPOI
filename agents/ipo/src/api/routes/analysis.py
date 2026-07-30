from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from src.db.repositories.task_repo import TaskRepo
from src.app_state import database, vllm_client, skill_registry, document_index_store
from src.models.api import AnalysisRequest, AnalysisStatus, AnalysisTask, APIResponse
from src.models.enums import ExecutionStatus
from src.agents.master.agent import MasterOrchestrator
from src.tracing.logger import TraceAuditLogger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

_task_repo: TaskRepo | None = None


def _get_task_repo() -> TaskRepo:
    global _task_repo
    if _task_repo is None:
        _task_repo = TaskRepo(database)
    return _task_repo


def _ensure_skills() -> None:
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


@router.post("/submit", response_model=APIResponse[AnalysisTask])
async def submit_analysis(request: AnalysisRequest):
    task_id = str(uuid.uuid4())
    doc_id = request.doc_id or str(uuid.uuid4())

    task = AnalysisTask(
        task_id=task_id,
        doc_id=doc_id,
        status=ExecutionStatus.PENDING,
    )

    task_repo = _get_task_repo()
    await task_repo.create(task)

    from src.db.repositories.trace_repo import TraceRepo

    trace_repo = TraceRepo(database)
    trace_logger = TraceAuditLogger(trace_repo)
    _ensure_skills()

    orchestrator = MasterOrchestrator(vllm_client, skill_registry, trace_logger)

    import asyncio

    async def _run():
        try:
            await task_repo.update_status(task_id, ExecutionStatus.RUNNING, 0.1)

            # Prefer pre-built FAISS index; only fall back to PyMuPDF when no index
            if document_index_store.exists(doc_id):
                logger.info("Using existing FAISS index for doc_id=%s", doc_id)
            elif request.options.get("parse_json_path"):
                from src.skills.base import SkillInput

                doc_skill = skill_registry.discover_skill("long_doc_retrieval")
                if doc_skill:
                    await doc_skill.execute(
                        SkillInput(
                            doc_id=doc_id,
                            params={
                                "action": "index_parsed",
                                "parse_json_path": request.options["parse_json_path"],
                                "company_name": request.company_name or "",
                                "stock_code": request.stock_code or "",
                            },
                        )
                    )
            elif request.file_path:
                from src.skills.base import SkillInput

                doc_skill = skill_registry.discover_skill("long_doc_retrieval")
                if doc_skill:
                    await doc_skill.execute(
                        SkillInput(
                            doc_id=doc_id,
                            params={"action": "index", "file_path": request.file_path},
                        )
                    )

            await task_repo.update_status(task_id, ExecutionStatus.RUNNING, 0.3)

            await orchestrator.run_full_analysis(
                doc_id=doc_id,
                file_path=request.file_path,
                company_name=request.company_name,
                stock_code=request.stock_code,
                industry=request.options.get("industry"),
            )

            await task_repo.update_status(task_id, ExecutionStatus.COMPLETED, 1.0)
        except Exception as e:
            await task_repo.update_status(
                task_id, ExecutionStatus.FAILED, 0.0, error_message=str(e)
            )

    asyncio.create_task(_run())

    return APIResponse(success=True, data=task)


@router.get("/{task_id}/status", response_model=APIResponse[AnalysisStatus])
async def get_analysis_status(task_id: str):
    task_repo = _get_task_repo()
    task = await task_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status = AnalysisStatus(
        task_id=task.task_id,
        status=task.status,
        progress=task.progress,
        current_step=task.status.value,
    )
    return APIResponse(success=True, data=status)


@router.get("/{task_id}/report", response_model=APIResponse[dict])
async def get_analysis_report(task_id: str):
    task_repo = _get_task_repo()
    task = await task_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != ExecutionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Analysis not completed yet")

    from src.db.models import RiskReportORM
    from sqlalchemy import select

    async with database.session() as session:
        result = await session.execute(
            select(RiskReportORM).where(RiskReportORM.doc_id == task.doc_id)
        )
        report_orm = result.scalar_one_or_none()
        if report_orm:
            import json

            return APIResponse(
                success=True,
                data=json.loads(report_orm.report_data) if report_orm.report_data else {},
            )
    return APIResponse(success=True, data={"message": "Report available but not persisted"})


@router.get("/{task_id}/trace", response_model=APIResponse[list])
async def get_analysis_trace(task_id: str):
    task_repo = _get_task_repo()
    task = await task_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from src.db.repositories.trace_repo import TraceRepo

    trace_repo = TraceRepo(database)
    records = await trace_repo.query_by_doc(task.doc_id)
    return APIResponse(success=True, data=[r.model_dump() for r in records])


@router.get("/{task_id}/conflicts", response_model=APIResponse[list])
async def get_analysis_conflicts(task_id: str):
    return APIResponse(success=True, data=[], trace_id=task_id)
