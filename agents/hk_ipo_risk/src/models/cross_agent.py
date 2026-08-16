from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CrossSignal(BaseModel):
    agent: Literal["finance", "legal", "market"]
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
        "redemption",
        "cash_runway",
        "valuation",
        "embellishment",
        "related_party",
        "other",
    ]
    finance_signals: list[CrossSignal] = Field(default_factory=list)
    legal_signals: list[CrossSignal] = Field(default_factory=list)
    master_label: str | None = None
    note: str = ""


# GPT 建议映射（文档/README 用）
CROSS_AGENT_THEME_TABLE: list[dict[str, str]] = [
    {"theme": "redemption", "finance": "CV_PREF 表内负债", "legal": "赎回/清理条款", "master": "兑付与上市前清理"},
    {"theme": "cash_runway", "finance": "现金跑道/烧钱", "legal": "不计分", "master": "持续经营资金压力"},
    {"theme": "concentration", "finance": "收入/供应依赖（解释钱）", "legal": "客户供应商集中度", "master": "集中度风险"},
    {"theme": "related_party", "finance": "不做占比打分", "legal": "关联交易占比/公允", "master": "关联交易风险"},
    {"theme": "valuation", "finance": "融资依赖", "legal": "估值倒挂", "master": "发行估值压力"},
    {"theme": "embellishment", "finance": "量化佐证", "legal": "宣传与风险因素矛盾", "master": "文本粉饰"},
    {"theme": "franchise", "finance": "加盟收入依赖", "legal": "加盟合同责任", "master": "商业模式风险"},
    {"theme": "supply_chain", "finance": "成本/供应商集中", "legal": "供应协议终止", "master": "供应链风险"},
    {"theme": "overseas", "finance": "汇率/海外收入", "legal": "境外监管", "master": "出海合规风险"},
    {"theme": "data_privacy", "finance": "数据相关收入", "legal": "隐私/数据合规", "master": "数据业务风险"},
]
