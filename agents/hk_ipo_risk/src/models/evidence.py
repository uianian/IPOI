from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    page: int | None = Field(default=None, description="招股书页码")
    excerpt: str = Field(default="", description="原文切片 50-200 字优先")
    source_type: Literal["table", "text", "title", "unknown"] = "unknown"
    field_code: str | None = None
    confidence: float = 1.0


class ScoreBreakdownItem(BaseModel):
    code: str
    delta: float
    rule_ref: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    note: str | None = None
    metric_value: Any = None
    evidence_page: int | None = None


class RiskPoint(BaseModel):
    code: str
    level: Literal["high", "medium", "low"] = "medium"
    rule_ref: str
    value: Any = None
    description: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)


class AgentResult(BaseModel):
    agent: Literal["finance", "legal", "market"]
    doc_id: str = ""
    risk_score: float = 0.0
    risk_level: str = "very_low"
    score_breakdown: list[ScoreBreakdownItem] = Field(default_factory=list)
    risk_points: list[RiskPoint] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    gates: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
