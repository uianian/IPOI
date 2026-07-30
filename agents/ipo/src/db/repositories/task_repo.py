from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update

from src.db.database import Database
from src.db.models import AnalysisTaskORM
from src.models.api import AnalysisTask
from src.models.enums import ExecutionStatus


class TaskRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, task: AnalysisTask) -> None:
        async with self._db.session() as session:
            orm = AnalysisTaskORM(
                task_id=task.task_id,
                doc_id=task.doc_id,
                status=task.status.value,
                created_at=task.created_at,
                progress=task.progress,
            )
            session.add(orm)
            await session.commit()

    async def get(self, task_id: str) -> AnalysisTask | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(AnalysisTaskORM).where(AnalysisTaskORM.task_id == task_id)
            )
            orm = result.scalar_one_or_none()
            if orm is None:
                return None
            return AnalysisTask(
                task_id=orm.task_id,
                doc_id=orm.doc_id,
                status=ExecutionStatus(orm.status),
                created_at=orm.created_at,
                updated_at=orm.updated_at,
                progress=orm.progress,
                error_message=orm.error_message,
            )

    async def update_status(self, task_id: str, status: ExecutionStatus, progress: float = 0.0, error_message: str | None = None) -> None:
        async with self._db.session() as session:
            values: dict = {"status": status.value, "progress": progress, "updated_at": datetime.now()}
            if error_message:
                values["error_message"] = error_message
            await session.execute(
                update(AnalysisTaskORM).where(AnalysisTaskORM.task_id == task_id).values(**values)
            )
            await session.commit()