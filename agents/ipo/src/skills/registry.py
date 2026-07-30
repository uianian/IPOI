from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from src.skills.base import BaseSkill, HealthCheckResult

logger = logging.getLogger(__name__)


class SkillRegistration(BaseModel):
    skill_name: str
    version: str
    description: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    registered_at: datetime = datetime.now()
    is_active: bool = True


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, dict[str, BaseSkill]] = {}
        self._registrations: dict[str, dict[str, SkillRegistration]] = {}

    def register_skill(self, skill: BaseSkill) -> None:
        name = skill.skill_name
        version = skill.version

        if name not in self._skills:
            self._skills[name] = {}
            self._registrations[name] = {}

        self._skills[name][version] = skill
        self._registrations[name][version] = SkillRegistration(
            skill_name=name,
            version=version,
            description=skill.description,
        )
        logger.info(f"Skill registered: {name} v{version}")

    def discover_skill(self, skill_name: str, version: str | None = None) -> BaseSkill | None:
        versions = self._skills.get(skill_name)
        if not versions:
            return None
        if version:
            return versions.get(version)
        latest = sorted(versions.keys())[-1]
        return versions[latest]

    def list_skills(self) -> list[SkillRegistration]:
        result = []
        for name, versions in self._registrations.items():
            for ver, reg in versions.items():
                result.append(reg)
        return result

    def get_versions(self, skill_name: str) -> list[str]:
        return list(self._skills.get(skill_name, {}).keys())

    async def check_health(self) -> dict[str, HealthCheckResult]:
        results = {}
        for name, versions in self._skills.items():
            latest = sorted(versions.keys())[-1]
            skill = versions[latest]
            try:
                results[name] = await skill.health_check()
            except Exception as e:
                results[name] = HealthCheckResult(
                    skill_name=name,
                    version=latest,
                    is_healthy=False,
                    details=str(e),
                )
        return results