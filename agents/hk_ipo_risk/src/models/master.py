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
    search_hints: dict[str, Any] | None = None


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


class EmbellishmentHighRiskExcerpt(BaseModel):
    candidate_id: str = ""
    dimension: str = ""
    tactic: str = ""
    section: str = ""
    page: int | None = None
    excerpt: str = ""
    context: str = ""
    reason: str = ""
    support_status: Literal[
        "supported", "weakly_supported", "unsupported", "contradictory", "unknown"
    ] = "unknown"
    score_contribution: int = 0
    severity: Literal["high", "medium", "low"] = "low"
    confidence: Literal["high", "medium", "low"] = "low"
    cross_evidence: list[dict[str, Any]] = Field(default_factory=list)


class EmbellishmentCoverage(BaseModel):
    first_pages: list[int] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    pages_analyzed: list[int] = Field(default_factory=list)
    risk_factor_pages: list[int] = Field(default_factory=list)
    candidate_count: int = 0
    evaluated_candidate_count: int = 0
    verified_excerpt_count: int = 0


class EmbellishmentResult(BaseModel):
    score: int = 0  # 0–10
    level: Literal["low", "medium", "high"] = "low"
    status: Literal["complete", "partial", "not_available"] = "not_available"
    reason: str = ""
    hits: list[EmbellishmentHit] = Field(default_factory=list)
    dimensions: dict[str, Any] = Field(default_factory=dict)
    buzzword_hints: list[str] = Field(default_factory=list)
    coverage: EmbellishmentCoverage = Field(default_factory=EmbellishmentCoverage)
    high_risk_excerpts: list[EmbellishmentHighRiskExcerpt] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


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


class PricePathForecastItem(BaseModel):
    window: Literal["D1", "D5", "D20", "D60"]
    risk_label: str = "medium"
    expected_direction: str = ""
    expected_pattern: str = ""
    volatility_view: str = ""
    key_drivers: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


def default_price_path_forecast() -> list[PricePathForecastItem]:
    return [
        PricePathForecastItem(
            window="D1",
            risk_label="medium",
            expected_direction="上市首日破发风险中等",
            expected_pattern="仅有标签级预测，未生成结构化走势文本",
            volatility_view="波动风险中等",
            confidence="medium",
        ),
        PricePathForecastItem(
            window="D5",
            risk_label="medium",
            expected_direction="上市后5个交易日显著下跌风险中等",
            expected_pattern="仅有标签级预测，未生成结构化走势文本",
            volatility_view="波动风险中等",
            confidence="medium",
        ),
        PricePathForecastItem(
            window="D20",
            risk_label="medium",
            expected_direction="上市后20个交易日下行风险中等",
            expected_pattern="仅有标签级预测，未生成结构化走势文本",
            volatility_view="波动风险中等",
            confidence="medium",
        ),
        PricePathForecastItem(
            window="D60",
            risk_label="medium",
            expected_direction="上市后60个交易日下行风险中等",
            expected_pattern="仅有标签级预测，未生成结构化走势文本",
            volatility_view="波动风险中等",
            confidence="medium",
        ),
    ]


class PostListingCheckpointValidation(BaseModel):
    window: Literal["D1", "D5", "D20", "D60"]
    prediction_label: str = "medium"
    prediction_text: str = ""
    actual_severity: Literal["severe", "moderate", "benign", "unknown"] = "unknown"
    hit: bool | None = None
    alignment: Literal["hit", "partial", "miss", "not_available"] = "not_available"
    observation_date: str | None = None
    below_issue_price: bool | None = None
    cumulative_return_from_open: float | None = None
    issue_price_return: float | None = None
    max_drawdown_from_open: float | None = None
    realized_risk_score: float | None = None
    note: str = ""


class PostListingValidation(BaseModel):
    status: Literal["completed", "partial", "not_available"] = "not_available"
    source: str = ""
    summary: str = "上市后真实行情验证未接入"
    business_value_score: float | None = None
    weighted_hit_score: float | None = None
    d5_priority_hit: bool | None = None
    forecast_alignment_summary: str = ""
    weights: dict[str, float] = Field(
        default_factory=lambda: {"D1": 0.30, "D5": 0.35, "D20": 0.20, "D60": 0.15}
    )
    checkpoints: list[PostListingCheckpointValidation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class MasterResult(BaseModel):
    doc_id: str = ""
    degraded: bool = False
    degraded_reason: str | None = None
    conflicts: list[ConflictItem] = Field(default_factory=list)
    debate_history: list[DebateRoundRecord] = Field(default_factory=list)
    embellishment: EmbellishmentResult | None = Field(default_factory=EmbellishmentResult)
    analysis_options: dict[str, bool] = Field(
        default_factory=lambda: {"embellishment_enabled": True}
    )
    judgment: CompositeJudgment = Field(default_factory=CompositeJudgment)
    risk_factors: list[RiskFactorItem] = Field(default_factory=list)
    predicted_windows: PredictedWindows = Field(default_factory=PredictedWindows)
    price_path_forecast: list[PricePathForecastItem] = Field(default_factory=default_price_path_forecast)
    post_listing: PostListingValidation = Field(default_factory=PostListingValidation)
    report_sections: dict[str, Any] = Field(default_factory=dict)
    report_markdown: str = ""
    reference_fundamental_score: float | None = None
    dossier_path: str | None = None
    trace: dict[str, Any] = Field(default_factory=dict)
