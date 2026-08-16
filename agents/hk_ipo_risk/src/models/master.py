from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.evidence import EvidenceRef


class ConflictItem(BaseModel):
    conflict_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    theme: str = "other"
    source_agents: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    kind: Literal["resonance", "conflict", "evidence_gap"] = "conflict"
    need_discussion: bool = False
    priority: Literal["high", "medium", "low"] = "medium"
    description: str = ""


class DebateQuestion(BaseModel):
    question_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    target_agent: Literal["finance", "legal", "market"] = "finance"
    claim_id: str | None = None
    theme: str = ""
    question: str = ""
    required_evidence_types: list[str] = Field(default_factory=list)
    priority: Literal["high", "medium", "low"] = "medium"


class ClaimUpdate(BaseModel):
    question_id: str = ""
    target_agent: str = ""
    clue_id: str | None = None
    status: Literal[
        "proposed",
        "challenged",
        "verified",
        "partially_accepted",
        "rejected",
        "unresolved",
    ] = "unresolved"
    severity: str = "medium"
    confidence: float = 0.4
    reply: str = ""
    revision_reason: str = ""
    remaining_uncertainty: str = ""
    new_queries: list[dict[str, Any]] = Field(default_factory=list)
    search_hit_count: int = 0
    evidence: list[EvidenceRef] = Field(default_factory=list)


class DebateRoundRecord(BaseModel):
    round: int = 1
    questions: list[DebateQuestion] = Field(default_factory=list)
    replies: list[ClaimUpdate] = Field(default_factory=list)
    continue_debate: bool = False
    continue_reason: str = ""
    duration_ms: int | None = None


class EmbellishmentHit(BaseModel):
    page: int | None = None
    excerpt: str = ""
    dimension: str = ""
    note: str = ""


class EmbellishmentResult(BaseModel):
    score: int = 0  # 0–10
    level: Literal["low", "medium", "high"] = "low"
    reason: str = ""
    hits: list[EmbellishmentHit] = Field(default_factory=list)
    dimensions: dict[str, Any] = Field(default_factory=dict)
    buzzword_hints: list[str] = Field(default_factory=list)


class RiskFactorItem(BaseModel):
    title: str = ""
    source_agent: str = ""
    reason: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    weight: float | None = None


class CompositeJudgment(BaseModel):
    overall_score: float = 0.0
    level: Literal["high", "medium", "low"] = "low"
    risk_level_http: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    confidence: Literal["high", "medium", "low"] = "medium"
    triggered_gates: list[str] = Field(default_factory=list)
    verdict_reasoning: str = ""
    score_explanation: str = ""
    gate_warning: str | None = None
    revised: bool = False


class PredictedWindows(BaseModel):
    ipo_day_break_risk: str = "medium"
    d5_significant_downside_risk: str = "medium"
    d20_downside_risk: str = "medium"
    d60_downside_risk: str = "medium"


class PostListingPlaceholder(BaseModel):
    day1: float | None = None
    day5: float | None = None
    day20: float | None = None
    day60: float | None = None
    broke_issue_price: bool | None = None
    hit: bool | None = None
    note: str = "上市后真实行情验证本轮未接入"


class MasterResult(BaseModel):
    doc_id: str = ""
    degraded: bool = False
    degraded_reason: str | None = None
    conflicts: list[ConflictItem] = Field(default_factory=list)
    debate_history: list[DebateRoundRecord] = Field(default_factory=list)
    embellishment: EmbellishmentResult = Field(default_factory=EmbellishmentResult)
    judgment: CompositeJudgment = Field(default_factory=CompositeJudgment)
    risk_factors: list[RiskFactorItem] = Field(default_factory=list)
    predicted_windows: PredictedWindows = Field(default_factory=PredictedWindows)
    post_listing: PostListingPlaceholder = Field(default_factory=PostListingPlaceholder)
    report_sections: dict[str, Any] = Field(default_factory=dict)
    report_markdown: str = ""
    reference_fundamental_score: float | None = None
    dossier_path: str | None = None
    trace: dict[str, Any] = Field(default_factory=dict)
