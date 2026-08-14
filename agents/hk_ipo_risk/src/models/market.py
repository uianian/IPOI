from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class MarketEvidence(BaseModel):
    """Traceable evidence for a structured market field or news item."""

    source: str
    field: str | None = None
    value: Any = None
    observation_date: date | None = None
    url: str | None = None
    note: str = ""


class IndicatorEvidence(BaseModel):
    """Machine-readable provenance and interpretation for one local indicator."""

    evidence_id: str
    module: Literal["macro", "industry", "ipo_market", "public_opinion"]
    indicator: str
    label: str
    claim: str = ""
    direction: Literal["support", "pressure", "neutral", "mixed", "unavailable"]
    derived_file: str
    derived_field: str
    raw_value: Any = None
    display_value: str = "—"
    unit: str = "unknown"
    window: str = ""
    formula: str = ""
    upstream_files: list[str] = Field(default_factory=list)
    upstream_fields: list[str] = Field(default_factory=list)
    provider: str = ""
    as_of_date: date
    observation_date: date | None = None
    interpretation: str = ""
    quality_flags: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    url: str | None = None
    excerpt: str = ""


class MarketDataBoundary(BaseModel):
    listing_date: date
    as_of_date: date
    market_observation_date: date | None = None
    cutoff_verified: bool = False
    features_file: str
    indicator_catalog_file: str
    news_file: str | None = None
    news_file_exists: bool = False
    news_total_rows: int = 0
    news_pre_cutoff_rows: int = 0
    news_earliest_date: date | None = None
    news_latest_date: date | None = None
    quality_flags: list[str] = Field(default_factory=list)


class ModuleSignalBalance(BaseModel):
    module: Literal["macro", "industry", "ipo_market", "public_opinion"]
    method: str
    support_weight: float = Field(ge=0)
    pressure_weight: float = Field(ge=0)
    neutral_or_context_weight: float = Field(default=0, ge=0)
    directional_weight: float = Field(ge=0)
    net_support: float = Field(ge=-1, le=1)
    qualitative_margin: float = Field(ge=0, le=1)
    state: Literal["supportive", "neutral", "mixed", "pressured", "unavailable"]


class MarketSentimentAnalysis(BaseModel):
    """Evidence-first market sentiment output; numeric score is not primary."""

    overall_state: Literal[
        "supportive",
        "neutral",
        "mixed",
        "pressured",
        "insufficient_data",
    ]
    overall_summary: str
    overall_net_support: float = Field(ge=-1, le=1)
    aggregation_policy: dict[str, Any] = Field(default_factory=dict)
    module_states: dict[str, str] = Field(default_factory=dict)
    module_signal_balances: dict[str, ModuleSignalBalance] = Field(default_factory=dict)
    module_coverage: dict[str, float] = Field(default_factory=dict)
    module_summaries: dict[str, str] = Field(default_factory=dict)
    support_evidence_ids: list[str] = Field(default_factory=list)
    pressure_evidence_ids: list[str] = Field(default_factory=list)
    neutral_evidence_ids: list[str] = Field(default_factory=list)
    unavailable_evidence_ids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    data_boundary: MarketDataBoundary
    evidence_ledger: list[IndicatorEvidence] = Field(default_factory=list)
    report_markdown: str = ""


class MarketSnapshot(BaseModel):
    stock_code: str = Field(pattern=r"^\d{5}$")
    company: str = ""
    listing_date: date
    as_of_date: date
    market_observation_date: date | None = None
    industry: str | None = None
    hsics_l1_name: str | None = None
    industry_source: str | None = None
    industry_return_source: str | None = None
    hsics_index_code: str | None = None
    hsics_index_name: str | None = None
    subscription_source: str | None = None
    features: dict[str, float | str | bool | None] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    cutoff_verified: bool = False
    evidence: list[MarketEvidence] = Field(default_factory=list)


class FactorScore(BaseModel):
    code: str
    label: str
    raw_value: float | None = None
    risk_score: float | None = Field(default=None, ge=0, le=100)
    configured_weight: float = Field(ge=0, le=1)
    effective_weight: float = Field(ge=0, le=1)
    note: str = ""


class MarketModuleScore(BaseModel):
    module: Literal["macro", "industry", "ipo_market", "public_opinion"]
    risk_score: float | None = Field(default=None, ge=0, le=100)
    coverage_ratio: float = Field(ge=0, le=1)
    factors: list[FactorScore] = Field(default_factory=list)
    missing_factors: list[str] = Field(default_factory=list)
    summary: str = ""


class PublicOpinionAssessment(BaseModel):
    available: bool = False
    risk_score: float | None = Field(default=None, ge=0, le=100)
    relevant_articles: int = Field(default=0, ge=0)
    direction_score: float | None = Field(default=None, ge=0, le=100)
    attention_score: float | None = Field(default=None, ge=0, le=100)
    events: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[MarketEvidence] = Field(default_factory=list)
    unavailable_reason: str | None = None


class MarketScorePack(BaseModel):
    risk_score: float = Field(ge=0, le=100)
    risk_level: str
    market_heat_score: float | None = Field(default=None, ge=0, le=100)
    module_scores: dict[str, MarketModuleScore]
    effective_weights: dict[str, float]
    public_opinion_used: bool
    coverage_ratio: float = Field(ge=0, le=1)


class MarketDebateResponse(BaseModel):
    stance: Literal["maintain", "revise", "concede"] = "maintain"
    response: str
    revised_summary: str | None = None
    proposed_risk_score: float | None = Field(default=None, ge=0, le=100)
    evidence_requests: list[str] = Field(default_factory=list)
    requires_new_evidence: bool = True


class HistoricalIndicatorRisk(BaseModel):
    indicator: str
    module: Literal["macro", "industry", "ipo_market", "public_opinion"]
    label: str
    raw_value: float
    risk_direction: Literal["higher", "lower"]
    history_start: date | None = None
    history_end: date
    history_sample_size: int = Field(ge=0)
    history_percentile: float | None = Field(default=None, ge=0, le=1)
    previous_year_same_period: float | None = None
    previous_two_year_same_period: float | None = None
    yoy_change: float | None = None
    two_year_change: float | None = None
    level_risk_score: float | None = Field(default=None, ge=0, le=100)
    trend_risk_score: float | None = Field(default=None, ge=0, le=100)
    risk_score: float | None = Field(default=None, ge=0, le=100)
    configured_weight: float = Field(ge=0)
    effective_weight: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    evidence_id: str
    interpretation: str = ""


class HistoricalModuleRisk(BaseModel):
    module: Literal["macro", "industry", "ipo_market", "public_opinion"]
    risk_score: float | None = Field(default=None, ge=0, le=100)
    configured_weight: float = Field(ge=0, le=1)
    effective_weight: float = Field(ge=0, le=1)
    coverage_ratio: float = Field(ge=0, le=1)
    indicators: list[HistoricalIndicatorRisk] = Field(default_factory=list)


class PrelistingDay1RiskAssessment(BaseModel):
    score_name: str = "prelisting_day1_break_risk_score"
    score_version: str
    score: float = Field(ge=0, le=100)
    risk_level: str
    risk_anchor: Literal["issue_price"] = "issue_price"
    secondary_market_return_base: Literal["first_trading_day_open"] = "first_trading_day_open"
    primary_validation_target: str = "first_day_close_below_issue_price"
    secondary_validation_target: str = "first_day_close_below_first_day_open"
    as_of_date: date
    history_cutoff: date
    issue_price_available: bool
    break_anchor_status: Literal["available", "unavailable"]
    effective_module_weights: dict[str, float] = Field(default_factory=dict)
    module_scores: dict[str, HistoricalModuleRisk] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    calibration_note: str = ""


class PostlistingMetricRisk(BaseModel):
    metric: str
    raw_value: float | bool | None = None
    risk_score: float | None = Field(default=None, ge=0, le=100)
    configured_weight: float = Field(ge=0, le=1)
    effective_weight: float = Field(ge=0, le=1)
    history_sample_size: int = Field(default=0, ge=0)
    history_percentile: float | None = Field(default=None, ge=0, le=1)
    evidence_id: str


class PostlistingCheckpointAssessment(BaseModel):
    score_name: str = "realized_market_risk_score"
    score_version: str
    stock_code: str = Field(pattern=r"^\d{5}$")
    checkpoint: str
    trading_day: int = Field(ge=1, le=60)
    listing_date: date
    observation_date: date
    first_trading_day_open: float = Field(gt=0)
    issue_price: float | None = Field(default=None, gt=0)
    below_issue_price: bool | None = None
    cumulative_return_from_open: float
    issue_price_return: float | None = None
    excess_hsi_return: float | None = None
    excess_industry_return: float | None = None
    max_drawdown_from_open: float | None = None
    realized_volatility: float | None = None
    turnover_change: float | None = None
    realized_risk_score: float = Field(ge=0, le=100)
    risk_level: str
    risk_anchor: str = "issue_price"
    secondary_market_return_base: str = "first_trading_day_open"
    metrics: list[PostlistingMetricRisk] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

