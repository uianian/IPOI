from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.enums import AgentRole, StepType


class TraceRecord(BaseModel):
    trace_id: str = Field(description="追踪记录ID")
    parent_trace_id: str | None = Field(default=None, description="父级追踪ID")
    doc_id: str = Field(description="招股书ID")
    agent_role: AgentRole = Field(description="Agent角色")
    skill_name: str | None = Field(default=None, description="调用的Skill名称")
    step_type: StepType = Field(description="步骤类型")
    input_summary: str | None = Field(default=None, description="输入摘要")
    output_summary: str | None = Field(default=None, description="输出摘要")
    evidence_refs: list[str] = Field(default_factory=list, description="证据引用ID列表")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    duration_ms: int | None = Field(default=None, ge=0, description="执行耗时(毫秒)")
    error_message: str | None = Field(default=None, description="错误信息")


class TraceSummary(BaseModel):
    doc_id: str = Field(description="招股书ID")
    total_steps: int = Field(default=0, ge=0, description="总步骤数")
    agent_steps: dict[str, int] = Field(default_factory=dict, description="各Agent步骤数")
    skill_calls: dict[str, int] = Field(default_factory=dict, description="各Skill调用次数")
    evidence_chain_complete: bool = Field(default=True, description="证据链路是否完整")
    broken_chains: list[str] = Field(default_factory=list, description="断链的追踪ID")
    total_duration_ms: int | None = Field(default=None, ge=0, description="总耗时(毫秒)")