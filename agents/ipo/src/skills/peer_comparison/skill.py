from __future__ import annotations

import logging
from typing import Any

from src.skills.base import BaseSkill, SkillInput, SkillOutput

logger = logging.getLogger(__name__)


class PeerDataAdapter:
    def __init__(self) -> None:
        self._peer_data: dict[str, list[dict[str, Any]]] = {}

    def load_peer_data(self, industry: str, data: list[dict[str, Any]]) -> None:
        self._peer_data[industry] = data

    def get_peer_data(self, industry: str) -> list[dict[str, Any]]:
        return self._peer_data.get(industry, [])

    def has_data(self, industry: str) -> bool:
        return industry in self._peer_data


class PeerComparator:
    def compare_valuation(
        self,
        issuer_metrics: dict[str, float],
        peer_data: list[dict[str, Any]],
        metrics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if metrics is None:
            metrics = ["PE", "PB", "PS", "EV_EBITDA"]

        results = []
        for metric in metrics:
            issuer_value = issuer_metrics.get(metric)
            peer_values = [p.get(metric) for p in peer_data if p.get(metric) is not None]

            if issuer_value is None or not peer_values:
                results.append({
                    "metric_name": metric,
                    "issuer_value": issuer_value,
                    "industry_mean": None,
                    "industry_median": None,
                    "z_score": None,
                    "is_significant": False,
                    "peer_count": len(peer_values),
                    "peer_sample_limited": len(peer_values) < 3,
                })
                continue

            import statistics

            mean_val = statistics.mean(peer_values)
            median_val = statistics.median(peer_values)
            std_val = statistics.stdev(peer_values) if len(peer_values) >= 2 else 0.0

            z_score = (issuer_value - mean_val) / std_val if std_val > 0 else 0.0
            is_significant = abs(z_score) > 2.0

            results.append({
                "metric_name": metric,
                "issuer_value": issuer_value,
                "industry_mean": round(mean_val, 4),
                "industry_median": round(median_val, 4),
                "z_score": round(z_score, 4),
                "is_significant": is_significant,
                "peer_count": len(peer_values),
                "peer_sample_limited": len(peer_values) < 3,
            })

        return results


class PeerComparisonSkill(BaseSkill):
    skill_name = "peer_comparison"
    version = "0.1.0"
    description = "同行估值比对Skill：计算行业均值/中位数/Z-Score偏离度"

    def __init__(self) -> None:
        self._adapter = PeerDataAdapter()
        self._comparator = PeerComparator()

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        action = skill_input.params.get("action", "compare")

        try:
            if action == "compare":
                return await self._compare_valuation(skill_input)
            elif action == "load_data":
                return await self._load_data(skill_input)
            else:
                return SkillOutput(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            logger.error(f"PeerComparisonSkill error: {e}")
            return SkillOutput(success=False, error=str(e))

    async def _compare_valuation(self, skill_input: SkillInput) -> SkillOutput:
        industry = skill_input.params.get("industry", "")
        issuer_metrics = skill_input.params.get("issuer_metrics", {})
        metrics = skill_input.params.get("metrics")

        peer_data = self._adapter.get_peer_data(industry)
        if not peer_data:
            return SkillOutput(
                success=True, data={"comparison_results": [], "peer_count": 0},
                degraded=True, degraded_reason="无同行数据，请先加载数据"
            )

        results = self._comparator.compare_valuation(issuer_metrics, peer_data, metrics)

        peer_sample_limited = any(r.get("peer_sample_limited", False) for r in results)
        return SkillOutput(
            success=True,
            data={"comparison_results": results, "peer_count": len(peer_data)},
            degraded=peer_sample_limited,
            degraded_reason="对标样本有限，结论可靠度降级" if peer_sample_limited else None,
        )

    async def _load_data(self, skill_input: SkillInput) -> SkillOutput:
        industry = skill_input.params.get("industry", "")
        data = skill_input.params.get("peer_data", [])

        self._adapter.load_peer_data(industry, data)
        return SkillOutput(success=True, data={"industry": industry, "loaded_count": len(data)})