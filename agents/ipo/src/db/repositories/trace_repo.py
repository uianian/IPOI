from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select

from src.db.database import Database
from src.db.models import TraceRecordORM
from src.models.enums import AgentRole, StepType
from src.models.trace import TraceRecord, TraceSummary


class TraceRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def write(self, record: TraceRecord) -> None:
        async with self._db.session() as session:
            orm = TraceRecordORM(
                trace_id=record.trace_id,
                parent_trace_id=record.parent_trace_id,
                doc_id=record.doc_id,
                agent_role=record.agent_role.value,
                skill_name=record.skill_name,
                step_type=record.step_type.value,
                input_summary=record.input_summary,
                output_summary=record.output_summary,
                evidence_refs=json.dumps(record.evidence_refs),
                timestamp=record.timestamp,
                duration_ms=record.duration_ms,
                error_message=record.error_message,
            )
            session.add(orm)
            await session.commit()

    async def query_by_doc(self, doc_id: str) -> list[TraceRecord]:
        async with self._db.session() as session:
            result = await session.execute(
                select(TraceRecordORM).where(TraceRecordORM.doc_id == doc_id).order_by(TraceRecordORM.timestamp)
            )
            rows = result.scalars().all()
            return [self._orm_to_model(r) for r in rows]

    async def query_by_agent(self, doc_id: str, agent_role: AgentRole) -> list[TraceRecord]:
        async with self._db.session() as session:
            result = await session.execute(
                select(TraceRecordORM)
                .where(TraceRecordORM.doc_id == doc_id, TraceRecordORM.agent_role == agent_role.value)
                .order_by(TraceRecordORM.timestamp)
            )
            rows = result.scalars().all()
            return [self._orm_to_model(r) for r in rows]

    async def get_summary(self, doc_id: str) -> TraceSummary:
        records = await self.query_by_doc(doc_id)
        agent_steps: dict[str, int] = {}
        skill_calls: dict[str, int] = {}
        total_ms = 0
        for r in records:
            key = r.agent_role.value
            agent_steps[key] = agent_steps.get(key, 0) + 1
            if r.skill_name:
                skill_calls[r.skill_name] = skill_calls.get(r.skill_name, 0) + 1
            if r.duration_ms:
                total_ms += r.duration_ms
        return TraceSummary(
            doc_id=doc_id,
            total_steps=len(records),
            agent_steps=agent_steps,
            skill_calls=skill_calls,
            evidence_chain_complete=True,
            broken_chains=[],
            total_duration_ms=total_ms if total_ms > 0 else None,
        )

    @staticmethod
    def _orm_to_model(orm: TraceRecordORM) -> TraceRecord:
        return TraceRecord(
            trace_id=orm.trace_id,
            parent_trace_id=orm.parent_trace_id,
            doc_id=orm.doc_id,
            agent_role=AgentRole(orm.agent_role),
            skill_name=orm.skill_name,
            step_type=StepType(orm.step_type),
            input_summary=orm.input_summary,
            output_summary=orm.output_summary,
            evidence_refs=json.loads(orm.evidence_refs) if orm.evidence_refs else [],
            timestamp=orm.timestamp,
            duration_ms=orm.duration_ms,
            error_message=orm.error_message,
        )