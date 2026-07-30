from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class SkillInput(BaseModel):
    doc_id: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class SkillOutput(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    degraded: bool = False
    degraded_reason: str | None = None


class HealthCheckResult(BaseModel):
    skill_name: str
    version: str
    is_healthy: bool
    details: str | None = None


class BaseSkill(ABC):
    skill_name: str = ""
    version: str = "0.1.0"
    description: str = ""

    @abstractmethod
    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        ...

    async def validate_input(self, skill_input: SkillInput) -> bool:
        return True

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            skill_name=self.skill_name,
            version=self.version,
            is_healthy=True,
        )
