from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from src.models.enums import AgentRole, StepType
from src.skills.base import SkillInput, SkillOutput
from src.skills.registry import SkillRegistry
from src.tracing.logger import TraceAuditLogger

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    agent_role: AgentRole = AgentRole.MASTER

    def __init__(
        self,
        vllm_client: Any,
        skill_registry: SkillRegistry,
        trace_logger: TraceAuditLogger,
    ) -> None:
        self._vllm = vllm_client
        self._skill_registry = skill_registry
        self._trace_logger = trace_logger

    async def call_skill(self, skill_name: str, doc_id: str, params: dict[str, Any] | None = None) -> SkillOutput:
        skill = self._skill_registry.discover_skill(skill_name)
        if skill is None:
            return SkillOutput(success=False, error=f"Skill not found: {skill_name}")

        skill_input = SkillInput(doc_id=doc_id, params=params or {})
        if not await skill.validate_input(skill_input):
            return SkillOutput(success=False, error=f"Invalid input for skill: {skill_name}")

        start = time.time()
        try:
            result = await skill.execute(skill_input)
            duration = int((time.time() - start) * 1000)
            await self._trace_logger.log_step(
                agent_role=self.agent_role,
                step_type=StepType.RETRIEVE,
                skill_name=skill_name,
                input_summary=f"doc_id={doc_id}, params_keys={list(params or {}).keys()}",
                output_summary=f"success={result.success}, degraded={result.degraded}",
                duration_ms=duration,
            )
            return result
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            await self._trace_logger.log_step(
                agent_role=self.agent_role,
                step_type=StepType.RETRIEVE,
                skill_name=skill_name,
                duration_ms=duration,
                error_message=str(e),
            )
            return SkillOutput(success=False, error=str(e), degraded=True, degraded_reason="Skill调用异常")

    async def llm_call(self, messages: list[dict[str, str]], step_type: StepType = StepType.ANALYZE, **kwargs: Any) -> str:
        start = time.time()
        try:
            result = await self._vllm.chat(messages, **kwargs)
            duration = int((time.time() - start) * 1000)
            await self._trace_logger.log_step(
                agent_role=self.agent_role,
                step_type=step_type,
                input_summary=messages[-1]["content"][:200] if messages else "",
                output_summary=result[:200] if result else "",
                duration_ms=duration,
            )
            return result
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            await self._trace_logger.log_step(
                agent_role=self.agent_role,
                step_type=step_type,
                duration_ms=duration,
                error_message=str(e),
            )
            logger.warning(f"LLM call degraded: {e}")
            return ""

    @abstractmethod
    async def analyze(self, doc_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    async def challenge(self, conclusion: str, challenger_conclusion: str) -> dict[str, Any]:
        from src.llm.prompts import CONFLICT_DEBATE

        messages = [
            {"role": "user", "content": CONFLICT_DEBATE.format(
                agent_role=self.agent_role.value,
                original_conclusion=conclusion,
                challenge=challenger_conclusion,
                additional_evidence="无",
            )},
        ]
        response = await self.llm_call(messages, step_type=StepType.DEBATE)
        import json
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"stance": "assert", "content": response, "evidence_supplement": None, "conclusion_revised": None}