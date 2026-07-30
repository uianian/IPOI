from __future__ import annotations

import logging
from typing import Any

from src.config import settings
from src.models.enums import RiskLevel
from src.models.legal import LegalAnalysisResult
from src.models.finance import FinanceAnalysisResult
from src.models.sentiment import SentimentResult
from src.models.report import FusedRiskAssessment, RiskFactorDetail

logger = logging.getLogger(__name__)


class CrossModalFusion:
    def __init__(
        self,
        fundamental_weight: float | None = None,
        sentiment_weight: float | None = None,
    ) -> None:
        self._fundamental_weight = fundamental_weight or settings.fusion.fundamental_weight
        self._sentiment_weight = sentiment_weight or settings.fusion.sentiment_weight

    def align_features(
        self,
        sentiment_result: dict[str, Any],
    ) -> dict[str, Any]:
        score_data = sentiment_result.get("sentiment_score", {})
        aligned = {
            "overall_score": score_data.get("overall_score", 50.0),
            "market_temperature_score": score_data.get("market_temperature_score", 50.0),
            "sector_liquidity_score": score_data.get("sector_liquidity_score", 50.0),
            "is_data_stale": score_data.get("is_data_stale", False),
            "is_extreme_market": score_data.get("is_extreme_market", False),
        }
        return aligned

    def fuse_and_rate(
        self,
        legal_result: dict[str, Any],
        finance_result: dict[str, Any],
        sentiment_result: dict[str, Any],
    ) -> FusedRiskAssessment:
        fundamental_score = self._calculate_fundamental_score(legal_result, finance_result)
        aligned_sentiment = self.align_features(sentiment_result)
        sentiment_score = aligned_sentiment["overall_score"]

        inverted_sentiment = 100.0 - sentiment_score

        overall = (
            fundamental_score * self._fundamental_weight
            + inverted_sentiment * self._sentiment_weight
        )
        overall = max(0.0, min(100.0, overall))

        overall_level = self._score_to_level(overall)

        factor_details = self._build_factor_details(legal_result, finance_result, aligned_sentiment)

        return FusedRiskAssessment(
            overall_score=round(overall, 2),
            overall_level=overall_level,
            fundamental_score=round(fundamental_score, 2),
            fundamental_weight=self._fundamental_weight,
            sentiment_score=round(inverted_sentiment, 2),
            sentiment_weight=self._sentiment_weight,
            factor_details=factor_details,
        )

    def _calculate_fundamental_score(
        self, legal_result: dict[str, Any], finance_result: dict[str, Any],
    ) -> float:
        legal_risks = legal_result.get("risk_features", [])
        high_risk_count = legal_result.get("high_risk_count", 0)
        compliance_flaws = legal_result.get("compliance_flaws", [])

        legal_score = min(100.0, high_risk_count * 25 + len(compliance_flaws) * 10)

        manipulation_signals = finance_result.get("manipulation_signals", [])
        high_severity_signals = [s for s in manipulation_signals if s.get("severity") == "high"]
        failed_validations = [v for v in finance_result.get("validation_results", []) if not v.get("passed", True)]

        finance_score = min(100.0, len(high_severity_signals) * 30 + len(failed_validations) * 15)

        burn_results = finance_result.get("burn_rate_results", [])
        low_runway = [b for b in burn_results if b.get("runway_months", 999) < 12 and b.get("scenario") == "neutral"]
        if low_runway:
            finance_score = min(100.0, finance_score + 20)

        fundamental = legal_score * 0.45 + finance_score * 0.55
        return min(100.0, fundamental)

    def _build_factor_details(
        self,
        legal_result: dict[str, Any],
        finance_result: dict[str, Any],
        aligned_sentiment: dict[str, Any],
    ) -> list[RiskFactorDetail]:
        factors: list[RiskFactorDetail] = []

        high_risk_count = legal_result.get("high_risk_count", 0)
        if high_risk_count > 0:
            factors.append(RiskFactorDetail(
                factor_name="法律风险",
                risk_level=RiskLevel.HIGH,
                score=min(100.0, high_risk_count * 25),
                source_agent="legal",
                description=f"发现{high_risk_count}个高危法律风险",
                weight=0.3,
                contribution=min(100.0, high_risk_count * 25) * 0.3,
            ))

        manipulation_signals = finance_result.get("manipulation_signals", [])
        high_severity = [s for s in manipulation_signals if s.get("severity") == "high"]
        if high_severity:
            factors.append(RiskFactorDetail(
                factor_name="财务操纵风险",
                risk_level=RiskLevel.HIGH,
                score=min(100.0, len(high_severity) * 30),
                source_agent="finance",
                description=f"发现{len(high_severity)}个高危财务操纵信号",
                weight=0.25,
                contribution=min(100.0, len(high_severity) * 30) * 0.25,
            ))

        burn_results = finance_result.get("burn_rate_results", [])
        low_runway = [b for b in burn_results if b.get("runway_months", 999) < 12 and b.get("scenario") == "neutral"]
        if low_runway:
            factors.append(RiskFactorDetail(
                factor_name="现金流消耗风险",
                risk_level=RiskLevel.HIGH,
                score=80.0,
                source_agent="finance",
                description=f"中性假设下资金耗尽时间仅{low_runway[0].get('runway_months', 0):.1f}个月",
                weight=0.2,
                contribution=80.0 * 0.2,
            ))

        if aligned_sentiment.get("is_extreme_market"):
            factors.append(RiskFactorDetail(
                factor_name="极端市场行情",
                risk_level=RiskLevel.HIGH,
                score=90.0,
                source_agent="sentiment",
                description="市场出现极端行情，评分可靠度降级",
                weight=0.15,
                contribution=90.0 * 0.15,
            ))

        mt_score = aligned_sentiment.get("market_temperature_score", 50.0)
        if mt_score < 30:
            factors.append(RiskFactorDetail(
                factor_name="大盘低迷",
                risk_level=RiskLevel.MEDIUM,
                score=100.0 - mt_score,
                source_agent="sentiment",
                description=f"大盘冷暖评分仅{mt_score}，市场环境偏冷",
                weight=0.1,
                contribution=(100.0 - mt_score) * 0.1,
            ))

        return factors

    @staticmethod
    def _score_to_level(score: float) -> RiskLevel:
        if score < 20:
            return RiskLevel.VERY_LOW
        elif score < 40:
            return RiskLevel.LOW
        elif score < 60:
            return RiskLevel.MEDIUM
        elif score < 80:
            return RiskLevel.HIGH
        else:
            return RiskLevel.VERY_HIGH