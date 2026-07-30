from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from datetime import datetime

from src.db.repositories.trace_repo import TraceRepo
from src.models.enums import AgentRole, StepType
from src.models.trace import TraceRecord, TraceSummary


_current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)
_current_parent_trace_id: ContextVar[str | None] = ContextVar("current_parent_trace_id", default=None)
_current_doc_id: ContextVar[str | None] = ContextVar("current_doc_id", default=None)


class TraceAuditLogger:
    def __init__(self, trace_repo: TraceRepo) -> None:
        self._repo = trace_repo

    def set_context(self, doc_id: str, trace_id: str | None = None, parent_trace_id: str | None = None) -> None:
        _current_doc_id.set(doc_id)
        _current_trace_id.set(trace_id or str(uuid.uuid4()))
        _current_parent_trace_id.set(parent_trace_id)

    def get_trace_id(self) -> str | None:
        return _current_trace_id.get()

    def get_parent_trace_id(self) -> str | None:
        return _current_parent_trace_id.get()

    def get_doc_id(self) -> str | None:
        return _current_doc_id.get()

    async def log_step(
        self,
        agent_role: AgentRole,
        step_type: StepType,
        input_summary: str | None = None,
        output_summary: str | None = None,
        evidence_refs: list[str] | None = None,
        skill_name: str | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> TraceRecord | None:
        trace_id = str(uuid.uuid4())
        parent_trace_id = self.get_trace_id()
        doc_id = self.get_doc_id()

        if doc_id is None:
            return None

        record = TraceRecord(
            trace_id=trace_id,
            parent_trace_id=parent_trace_id,
            doc_id=doc_id,
            agent_role=agent_role,
            skill_name=skill_name,
            step_type=step_type,
            input_summary=input_summary,
            output_summary=output_summary,
            evidence_refs=evidence_refs or [],
            timestamp=datetime.now(),
            duration_ms=duration_ms,
            error_message=error_message,
        )
        await self._repo.write(record)
        return record

    async def query_trace(self, doc_id: str) -> list[TraceRecord]:
        return await self._repo.query_by_doc(doc_id)

    async def get_summary(self, doc_id: str) -> TraceSummary:
        return await self._repo.get_summary(doc_id)

    async def verify_evidence_chain(self, doc_id: str) -> tuple[bool, list[str]]:
        records = await self._repo.query_by_doc(doc_id)
        child_ids = {r.trace_id for r in records}
        broken = []
        for r in records:
            if r.parent_trace_id and r.parent_trace_id not in child_ids and r.parent_trace_id != self.get_trace_id():
                broken.append(r.trace_id)
        return len(broken) == 0, broken


class TraceContext:
    def __init__(self, logger: TraceAuditLogger, doc_id: str, parent_trace_id: str | None = None) -> None:
        self._logger = logger
        self._doc_id = doc_id
        self._parent_trace_id = parent_trace_id

    async def __aenter__(self) -> TraceAuditLogger:
        self._logger.set_context(self._doc_id, parent_trace_id=self._parent_trace_id)
        return self._logger

    async def __aexit__(self, *args) -> None:
        _current_trace_id.set(None)
        _current_parent_trace_id.set(None)
        _current_doc_id.set(None)