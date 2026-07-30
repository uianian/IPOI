from __future__ import annotations

import logging
from typing import Any

from src.config import settings
from src.models.enums import MarketTemperature
from src.skills.base import BaseSkill, SkillInput, SkillOutput

logger = logging.getLogger(__name__)


class SentimentScorer:
    def __init__(self) -> None:
        self._weights = {
            "market_temperature": settings.sentiment.market_temperature_weight,
            "sector_liquidity": settings.sentiment.sector_liquidity_weight,
            "public_opinion": settings.sentiment.public_opinion_weight,
            "ipo_subscription": settings.sentiment.ipo_subscription_weight,
        }

    def calculate_score(
        self,
        market_temperature_score: float,
        sector_liquidity_score: float,
        public_opinion_score: float,
        ipo_subscription_score: float,
        is_data_stale: bool = False,
        is_extreme_market: bool = False,
    ) -> dict[str, Any]:
        overall = (
            market_temperature_score * self._weights["market_temperature"]
            + sector_liquidity_score * self._weights["sector_liquidity"]
            + public_opinion_score * self._weights["public_opinion"]
            + ipo_subscription_score * self._weights["ipo_subscription"]
        )

        market_temp_level = self._map_temperature(market_temperature_score)
        reliability_degraded = is_data_stale or is_extreme_market

        return {
            "overall_score": round(overall, 2),
            "market_temperature_score": round(market_temperature_score, 2),
            "sector_liquidity_score": round(sector_liquidity_score, 2),
            "public_opinion_score": round(public_opinion_score, 2),
            "ipo_subscription_score": round(ipo_subscription_score, 2),
            "market_temperature_level": market_temp_level,
            "is_data_stale": is_data_stale,
            "is_extreme_market": is_extreme_market,
            "reliability_degraded": reliability_degraded,
        }

    def decompose_factors(
        self,
        market_temperature_score: float,
        sector_liquidity_score: float,
        public_opinion_score: float,
        ipo_subscription_score: float,
    ) -> list[dict[str, Any]]:
        factors = [
            ("大盘冷暖", market_temperature_score, self._weights["market_temperature"]),
            ("板块流动性", sector_liquidity_score, self._weights["sector_liquidity"]),
            ("舆情热度", public_opinion_score, self._weights["public_opinion"]),
            ("IPO认购倍数", ipo_subscription_score, self._weights["ipo_subscription"]),
        ]

        results = []
        for name, score, weight in factors:
            contribution = score * weight
            results.append({
                "factor_name": name,
                "score": round(score, 2),
                "weight": weight,
                "contribution": round(contribution, 2),
            })

        return results

    @staticmethod
    def _map_temperature(score: float) -> str:
        if score < 20:
            return MarketTemperature.VERY_COLD.value
        elif score < 40:
            return MarketTemperature.COLD.value
        elif score < 60:
            return MarketTemperature.NEUTRAL.value
        elif score < 80:
            return MarketTemperature.HOT.value
        else:
            return MarketTemperature.VERY_HOT.value


class SentimentScoringSkill(BaseSkill):
    skill_name = "sentiment_scoring"
    version = "0.1.0"
    description = "情绪热度打分Skill：多因子加权评分与贡献度分解"

    def __init__(self) -> None:
        self._scorer = SentimentScorer()

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        action = skill_input.params.get("action", "score")

        try:
            if action == "score":
                return await self._calculate_score(skill_input)
            elif action == "decompose":
                return await self._decompose_factors(skill_input)
            else:
                return SkillOutput(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            logger.error(f"SentimentScoringSkill error: {e}")
            return SkillOutput(success=False, error=str(e))

    async def _calculate_score(self, skill_input: SkillInput) -> SkillOutput:
        mt_score = skill_input.params.get("market_temperature_score", 50.0)
        sl_score = skill_input.params.get("sector_liquidity_score", 50.0)
        po_score = skill_input.params.get("public_opinion_score", 50.0)
        ipo_score = skill_input.params.get("ipo_subscription_score", 50.0)
        is_data_stale = skill_input.params.get("is_data_stale", False)
        is_extreme = skill_input.params.get("is_extreme_market", False)

        result = self._scorer.calculate_score(mt_score, sl_score, po_score, ipo_score, is_data_stale, is_extreme)

        degraded_reason = None
        if is_data_stale:
            degraded_reason = "数据过期预警：核心市场数据时间戳超24小时"
        elif is_extreme:
            degraded_reason = "极端行情模式：评分可靠度降级"

        return SkillOutput(
            success=True,
            data=result,
            degraded=is_data_stale or is_extreme,
            degraded_reason=degraded_reason,
        )

    async def _decompose_factors(self, skill_input: SkillInput) -> SkillOutput:
        mt_score = skill_input.params.get("market_temperature_score", 50.0)
        sl_score = skill_input.params.get("sector_liquidity_score", 50.0)
        po_score = skill_input.params.get("public_opinion_score", 50.0)
        ipo_score = skill_input.params.get("ipo_subscription_score", 50.0)

        factors = self._scorer.decompose_factors(mt_score, sl_score, po_score, ipo_score)
        return SkillOutput(success=True, data={"factor_contributions": factors})