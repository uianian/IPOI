from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from src.agents.base import BaseAgent
from src.models.enums import AgentRole
from src.models.sentiment import (
    FactorContribution,
    MarketEvent,
    SectorLiquidity,
    SentimentResult,
    SentimentScore,
)

logger = logging.getLogger(__name__)


class MarketDataAdapter:
    def __init__(self) -> None:
        self._market_data: dict[str, Any] = {}

    def update_data(self, stock_code: str, data: dict[str, Any]) -> None:
        self._market_data[stock_code] = {**data, "updated_at": datetime.now().isoformat()}

    def get_data(self, stock_code: str) -> dict[str, Any] | None:
        return self._market_data.get(stock_code)

    def is_stale(self, stock_code: str, max_hours: int = 24) -> bool:
        data = self._market_data.get(stock_code)
        if not data or "updated_at" not in data:
            return True
        updated = datetime.fromisoformat(data["updated_at"])
        return (datetime.now() - updated) > timedelta(hours=max_hours)


class SentimentAgent(BaseAgent):
    agent_role = AgentRole.SENTIMENT

    def __init__(self, vllm_client: Any, skill_registry: Any, trace_logger: Any) -> None:
        super().__init__(vllm_client, skill_registry, trace_logger)
        self._market_adapter = MarketDataAdapter()

    async def analyze(self, doc_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        stock_code = params.get("stock_code", "")
        industry = params.get("industry", "")

        market_data = params.get("market_data", {})
        if market_data:
            self._market_adapter.update_data(stock_code, market_data)

        is_data_stale = self._market_adapter.is_stale(stock_code) if stock_code else True

        daily_change = market_data.get("daily_change", 0.0)
        is_extreme = abs(daily_change) > 0.05

        mt_score = params.get("market_temperature_score", 50.0)
        sl_score = params.get("sector_liquidity_score", 50.0)
        po_score = params.get("public_opinion_score", 50.0)
        ipo_score = params.get("ipo_subscription_score", 50.0)

        if market_data:
            mt_score = self._calculate_market_temperature(market_data)
            sl_score = self._calculate_sector_liquidity(market_data)
            ipo_score = self._calculate_ipo_subscription(market_data)

        sentiment_result = await self.call_skill(
            "sentiment_scoring", doc_id,
            {
                "action": "score",
                "market_temperature_score": mt_score,
                "sector_liquidity_score": sl_score,
                "public_opinion_score": po_score,
                "ipo_subscription_score": ipo_score,
                "is_data_stale": is_data_stale,
                "is_extreme_market": is_extreme,
            },
        )

        sentiment_score = None
        if sentiment_result.success:
            score_data = sentiment_result.data
            sentiment_score = SentimentScore(
                overall_score=score_data.get("overall_score", 50.0),
                market_temperature_score=score_data.get("market_temperature_score", 50.0),
                sector_liquidity_score=score_data.get("sector_liquidity_score", 50.0),
                public_opinion_score=score_data.get("public_opinion_score", 50.0),
                ipo_subscription_score=score_data.get("ipo_subscription_score", 50.0),
                market_temperature_level=score_data.get("market_temperature_level", "neutral"),
                is_data_stale=score_data.get("is_data_stale", False),
                is_extreme_market=score_data.get("is_extreme_market", False),
                reliability_degraded=score_data.get("reliability_degraded", False),
            )

        decompose_result = await self.call_skill(
            "sentiment_scoring", doc_id,
            {
                "action": "decompose",
                "market_temperature_score": mt_score,
                "sector_liquidity_score": sl_score,
                "public_opinion_score": po_score,
                "ipo_subscription_score": ipo_score,
            },
        )

        factor_contributions = []
        if decompose_result.success:
            for fc in decompose_result.data.get("factor_contributions", []):
                factor_contributions.append(FactorContribution(
                    factor_name=fc.get("factor_name", ""),
                    score=fc.get("score", 0.0),
                    weight=fc.get("weight", 0.0),
                    contribution=fc.get("contribution", 0.0),
                ))

        market_events: list[MarketEvent] = []
        if market_data.get("news"):
            from src.llm.prompts import SENTIMENT_EVENT_EXTRACTION
            event_messages = [
                {"role": "user", "content": SENTIMENT_EVENT_EXTRACTION.format(market_data=json.dumps(market_data.get("news", []), ensure_ascii=False))},
            ]
            event_response = await self.llm_call(event_messages, step_type=StepType.ANALYZE)
            try:
                parsed = json.loads(event_response)
                for evt in parsed.get("events", []):
                    market_events.append(MarketEvent(
                        event_name=evt.get("event_name", ""),
                        event_type=evt.get("event_type", ""),
                        impact_assessment=evt.get("impact_assessment", ""),
                        sentiment_direction=evt.get("sentiment_direction", "neutral"),
                    ))
            except (json.JSONDecodeError, KeyError):
                pass

        result = SentimentResult(
            doc_id=doc_id,
            sentiment_score=sentiment_score,
            factor_contributions=factor_contributions,
            market_events=market_events,
            summary=f"综合情绪评分: {sentiment_score.overall_score if sentiment_score else 'N/A'}"
            + ("，数据过期预警" if is_data_stale else "")
            + ("，极端行情模式" if is_extreme else ""),
        )

        await self._trace_logger.log_step(
            agent_role=self.agent_role,
            step_type=StepType.REPORT,
            output_summary=result.summary,
        )

        return result.model_dump()

    @staticmethod
    def _calculate_market_temperature(data: dict[str, Any]) -> float:
        index_change = data.get("index_change", 0.0)
        turnover_change = data.get("turnover_change", 0.0)
        score = 50.0 + index_change * 200 + turnover_change * 100
        return max(0.0, min(100.0, score))

    @staticmethod
    def _calculate_sector_liquidity(data: dict[str, Any]) -> float:
        daily_turnover = data.get("sector_daily_turnover", 0.0)
        turnover_rate = data.get("sector_turnover_rate", 0.0)
        score = min(100.0, daily_turnover / 1e8 * 10 + turnover_rate * 100)
        return max(0.0, min(100.0, score))

    @staticmethod
    def _calculate_ipo_subscription(data: dict[str, Any]) -> float:
        subscription_ratio = data.get("ipo_subscription_ratio", 1.0)
        score = min(100.0, (subscription_ratio - 1) * 10)
        return max(0.0, min(100.0, score))