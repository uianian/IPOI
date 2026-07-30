from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.enums import MarketTemperature


class SentimentScore(BaseModel):
    overall_score: float = Field(ge=0.0, le=100.0, description="综合情绪评分")
    market_temperature_score: float = Field(ge=0.0, le=100.0, description="大盘冷暖因子评分")
    sector_liquidity_score: float = Field(ge=0.0, le=100.0, description="板块流动性因子评分")
    public_opinion_score: float = Field(ge=0.0, le=100.0, description="舆情热度因子评分")
    ipo_subscription_score: float = Field(ge=0.0, le=100.0, description="IPO认购倍数因子评分")
    market_temperature_level: MarketTemperature = Field(description="大盘冷暖五级评估")
    is_data_stale: bool = Field(default=False, description="数据是否过期")
    is_extreme_market: bool = Field(default=False, description="是否处于极端行情")
    reliability_degraded: bool = Field(default=False, description="评分可靠度是否降级")


class FactorContribution(BaseModel):
    factor_name: str = Field(description="因子名称")
    score: float = Field(ge=0.0, le=100.0, description="因子评分")
    weight: float = Field(ge=0.0, le=1.0, description="因子权重")
    contribution: float = Field(ge=0.0, description="贡献度(评分×权重)")
    data_timestamp: datetime | None = Field(default=None, description="数据时间戳")


class MarketEvent(BaseModel):
    event_name: str = Field(description="事件名称")
    event_type: str = Field(description="事件类型")
    impact_assessment: str = Field(description="影响评估")
    sentiment_direction: str = Field(default="neutral", description="情绪方向: positive/negative/neutral")
    source: str | None = Field(default=None, description="信息来源")


class SectorLiquidity(BaseModel):
    sector_name: str = Field(description="板块名称")
    daily_avg_turnover: float | None = Field(default=None, description="日均成交额")
    turnover_rate: float | None = Field(default=None, description="换手率")
    net_capital_flow: float | None = Field(default=None, description="资金净流入")
    liquidity_score: float = Field(ge=0.0, le=100.0, description="流动性评分")


class SentimentResult(BaseModel):
    doc_id: str = Field(description="招股书ID")
    sentiment_score: SentimentScore | None = Field(default=None, description="情绪评分")
    factor_contributions: list[FactorContribution] = Field(default_factory=list, description="因子贡献度")
    market_events: list[MarketEvent] = Field(default_factory=list, description="市场事件")
    sector_liquidity: list[SectorLiquidity] = Field(default_factory=list, description="板块流动性")
    summary: str = Field(default="", description="情绪分析摘要")