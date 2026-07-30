from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import SeverityLevel
from src.models.evidence import EvidenceRef


class LegalRiskFeature(BaseModel):
    feature_name: str = Field(description="风险特征名称")
    description: str = Field(description="风险特征描述")
    severity: SeverityLevel = Field(description="严重程度")
    legal_basis: str | None = Field(default=None, description="法律条款/监管规定引用")
    evidence: list[EvidenceRef] = Field(default_factory=list, description="证据引用")
    needs_full_scan: bool = Field(default=False, description="是否需要全文档补充扫描")


class ComplianceFlaw(BaseModel):
    flaw_name: str = Field(description="合规瑕疵名称")
    severity: SeverityLevel = Field(description="严重程度分级")
    description: str = Field(description="合规瑕疵描述")
    regulation_reference: str | None = Field(default=None, description="监管规定引用")
    evidence: list[EvidenceRef] = Field(default_factory=list, description="证据引用")


class CrossReference(BaseModel):
    source_feature: str = Field(description="源风险特征")
    target_section: str = Field(description="交叉引用目标章节")
    target_page: int = Field(ge=1, description="目标页码")
    consistency: bool = Field(description="判断是否一致")
    note: str | None = Field(default=None, description="不一致说明")


class LegalAnalysisResult(BaseModel):
    doc_id: str = Field(description="招股书ID")
    risk_features: list[LegalRiskFeature] = Field(default_factory=list, description="法律风险特征")
    compliance_flaws: list[ComplianceFlaw] = Field(default_factory=list, description="合规瑕疵")
    cross_references: list[CrossReference] = Field(default_factory=list, description="交叉引用验证")
    full_scan_triggered: bool = Field(default=False, description="是否触发了全文档补充扫描")
    high_risk_count: int = Field(default=0, ge=0, description="高危风险数量")
    summary: str = Field(default="", description="法务分析摘要")