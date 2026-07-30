from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import SeverityLevel
from src.models.evidence import EvidenceRef


class FinancialIndicator(BaseModel):
    name: str = Field(description="指标名称")
    value: float | str = Field(description="指标值")
    unit: str | None = Field(default=None, description="单位")
    period: str | None = Field(default=None, description="报告期")
    source_page: int | None = Field(default=None, ge=1, description="来源页码")
    is_standard: bool = Field(default=True, description="是否为标准化指标")


class ValidationResult(BaseModel):
    indicator_name: str = Field(description="校验指标名称")
    check_type: str = Field(description="校验类型: internal_consistency/cross_period/peer_comparison")
    passed: bool = Field(description="校验是否通过")
    deviation: float | None = Field(default=None, description="偏离度")
    note: str | None = Field(default=None, description="异常说明")


class ManipulationSignal(BaseModel):
    signal_name: str = Field(description="操纵信号名称")
    description: str = Field(description="信号描述")
    severity: SeverityLevel = Field(description="严重程度")
    cross_evidence_count: int = Field(default=0, ge=0, description="交叉证据数量")
    evidence: list[EvidenceRef] = Field(default_factory=list, description="证据引用")


class BurnRateResult(BaseModel):
    monthly_burn_rate: float = Field(description="月度现金流消耗率")
    cash_reserve: float = Field(description="现金储备")
    runway_months: float = Field(description="资金耗尽时间（月）")
    scenario: str = Field(default="neutral", description="假设场景: optimistic/neutral/pessimistic")
    assumptions: dict = Field(default_factory=dict, description="假设参数")


class ComparisonResult(BaseModel):
    metric_name: str = Field(description="估值指标名称")
    issuer_value: float | None = Field(default=None, description="发行人值")
    industry_mean: float | None = Field(default=None, description="行业均值")
    industry_median: float | None = Field(default=None, description="行业中位数")
    z_score: float | None = Field(default=None, description="Z-Score偏离度")
    is_significant: bool = Field(default=False, description="是否显著偏离")
    peer_count: int = Field(default=0, ge=0, description="可比公司数量")
    peer_sample_limited: bool = Field(default=False, description="对标样本是否有限")


class FinanceAnalysisResult(BaseModel):
    doc_id: str = Field(description="招股书ID")
    indicators: list[FinancialIndicator] = Field(default_factory=list, description="财务指标")
    validation_results: list[ValidationResult] = Field(default_factory=list, description="校验结果")
    manipulation_signals: list[ManipulationSignal] = Field(default_factory=list, description="操纵信号")
    burn_rate_results: list[BurnRateResult] = Field(default_factory=list, description="现金流消耗测算")
    comparison_results: list[ComparisonResult] = Field(default_factory=list, description="同行估值比对")
    summary: str = Field(default="", description="财务分析摘要")