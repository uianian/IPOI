from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import ConflictType, DebateStance


class ConflictItem(BaseModel):
    conflict_id: str = Field(description="冲突唯一标识")
    conflict_type: ConflictType = Field(description="冲突类型")
    description: str = Field(description="冲突描述")
    source_agents: list[str] = Field(description="涉及Agent")
    source_conclusions: list[str] = Field(default_factory=list, description="各方原始结论")
    severity: str = Field(default="medium", description="冲突严重程度")


class DebateMessage(BaseModel):
    round_number: int = Field(ge=1, description="辩论轮次")
    agent_role: str = Field(description="发言Agent角色")
    stance: DebateStance = Field(description="发言立场")
    content: str = Field(description="辩论内容")
    evidence_supplement: str | None = Field(default=None, description="补充证据")
    conclusion_revised: str | None = Field(default=None, description="修正后结论")


class DebateRound(BaseModel):
    round_number: int = Field(ge=1, description="轮次编号")
    messages: list[DebateMessage] = Field(default_factory=list, description="本轮辩论消息")
    is_resolved: bool = Field(default=False, description="本轮是否解决冲突")
    consensus_conclusion: str | None = Field(default=None, description="共识结论")


class DebateResult(BaseModel):
    conflict_id: str = Field(description="关联冲突ID")
    rounds: list[DebateRound] = Field(default_factory=list, description="辩论轮次")
    final_resolved: bool = Field(default=False, description="最终是否解决")
    is_irreconcilable: bool = Field(default=False, description="是否为不可调和冲突")
    final_conclusion: str | None = Field(default=None, description="最终结论")
    total_rounds: int = Field(default=0, ge=0, description="总辩论轮次")