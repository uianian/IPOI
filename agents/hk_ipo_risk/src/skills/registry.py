from __future__ import annotations

import logging
from typing import Any

from src.skills.base import BaseSkill, HealthCheckResult

logger = logging.getLogger(__name__)


class SkillRegistry:
    """可注册 Skill 表；按 name 取最新版本。"""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.skill_name] = skill
        logger.info("Skill registered: %s v%s", skill.skill_name, skill.version)

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def list_names(self) -> list[str]:
        return sorted(self._skills.keys())

    def as_openai_tools(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        """若 Skill 暴露 tool_schema，一并导出（多数 Skill 通过 ToolRegistry 暴露）。"""
        out: list[dict[str, Any]] = []
        for name, skill in self._skills.items():
            if names and name not in names:
                continue
            schema = getattr(skill, "tool_schema", None)
            if callable(schema):
                out.append(schema())
            elif isinstance(schema, dict):
                out.append(schema)
        return out

    async def check_health(self) -> dict[str, HealthCheckResult]:
        results: dict[str, HealthCheckResult] = {}
        for name, skill in self._skills.items():
            try:
                results[name] = await skill.health_check()
            except Exception as e:
                results[name] = HealthCheckResult(
                    skill_name=name,
                    version=skill.version,
                    is_healthy=False,
                    details=str(e),
                )
        return results
