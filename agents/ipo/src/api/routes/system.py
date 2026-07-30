from __future__ import annotations

from fastapi import APIRouter

from src.app_state import skill_registry, vllm_client, database
from src.models.api import APIResponse, HealthStatus

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health", response_model=APIResponse[HealthStatus])
async def health_check():
    llm_ok = await vllm_client.health_check()
    db_ok = database._engine is not None

    skill_health = await skill_registry.check_health()
    agents_status = {
        "legal": True,
        "finance": True,
        "sentiment": True,
        "master": True,
    }
    skills_status = {name: h.is_healthy for name, h in skill_health.items()}

    health = HealthStatus(
        status="ok" if llm_ok and db_ok else "degraded",
        agents=agents_status,
        skills=skills_status,
        llm_available=llm_ok,
        database_available=db_ok,
    )
    return APIResponse(success=True, data=health)


@router.get("/skills", response_model=APIResponse[list])
async def list_skills():
    skills = skill_registry.list_skills()
    return APIResponse(success=True, data=[s.model_dump() for s in skills])


@router.get("/skills/{skill_name}/versions", response_model=APIResponse[list])
async def get_skill_versions(skill_name: str):
    versions = skill_registry.get_versions(skill_name)
    if not versions:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
    return APIResponse(success=True, data=versions)