from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.enums import RiskLevel
from src.models.evidence import EvidenceRef


class RiskFactorDetail(BaseModel):
    factor_name: str = Field(description="风险因子名称")
    risk_level: RiskLevel = Field(description="风险等级")
    score: float = Field(ge=0.0, le=100.0, description="风险评分")
    source_agent: str = Field(description="来源Agent")
    description: str = Field(description="风险描述")
    evidence: list[EvidenceRef] = Field(default_factory=list, description="证据引用")
    weight: float = Field(ge=0.0, le=1.0, description="权重")
    contribution: float = Field(ge=0.0, description="贡献度")


class FusedRiskAssessment(BaseModel):
    overall_score: float = Field(ge=0.0, le=100.0, description="综合风险评分")
    overall_level: RiskLevel = Field(description="综合风险等级")
    fundamental_score: float = Field(ge=0.0, le=100.0, description="基本面风险评分")
    fundamental_weight: float = Field(ge=0.0, le=1.0, description="基本面权重")
    sentiment_score: float = Field(ge=0.0, le=100.0, description="市场情绪评分")
    sentiment_weight: float = Field(ge=0.0, le=1.0, description="市场情绪权重")
    factor_details: list[RiskFactorDetail] = Field(default_factory=list, description="因子明细")
    risk_level_mapping: dict[str, list[float]] = Field(
        default_factory=lambda: {
            "very_low": [0, 20],
            "low": [20, 40],
            "medium": [40, 60],
            "high": [60, 80],
            "very_high": [80, 100],
        },
        description="风险等级映射",
    )


class RiskReport(BaseModel):
    report_id: str = Field(description="报告唯一标识")
    doc_id: str = Field(description="招股书ID")
    company_name: str = Field(description="公司名称")
    generated_at: datetime = Field(default_factory=datetime.now, description="生成时间")
    risk_assessment: FusedRiskAssessment | None = Field(default=None, description="风险综合评估")
    high_risk_factors: list[RiskFactorDetail] = Field(default_factory=list, description="高风险因子")
    conflicts: list[dict] = Field(default_factory=list, description="冲突记录")
    debate_results: list[dict] = Field(default_factory=list, description="辩论结果")
    summary: str = Field(default="", description="报告摘要")
    trace_root_id: str | None = Field(default=None, description="追踪根ID")