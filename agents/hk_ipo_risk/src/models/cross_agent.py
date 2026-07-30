from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CrossSignal(BaseModel):
    agent: Literal["finance", "legal"]
    code: str = ""
    description: str = ""
    evidence_page: int | None = None
    metric_value: Any = None


class CrossAgentFeature(BaseModel):
    """跨 Agent 交叉风险主题（总控后续消费）。"""

    theme: Literal[
        "franchise",
        "supply_chain",
        "overseas",
        "data_privacy",
        "concentration",
        "other",
    ]
    finance_signals: list[CrossSignal] = Field(default_factory=list)
    legal_signals: list[CrossSignal] = Field(default_factory=list)
    master_label: str | None = None
    note: str = ""


# GPT 建议映射（文档/README 用）
CROSS_AGENT_THEME_TABLE: list[dict[str, str]] = [
    {"theme": "franchise", "finance": "加盟收入依赖", "legal": "加盟合同责任", "master": "商业模式风险"},
    {"theme": "supply_chain", "finance": "成本/供应商集中", "legal": "供应协议终止", "master": "供应链风险"},
    {"theme": "overseas", "finance": "汇率/海外收入", "legal": "境外监管", "master": "出海合规风险"},
    {"theme": "data_privacy", "finance": "数据相关收入", "legal": "隐私/数据合规", "master": "数据业务风险"},
]
