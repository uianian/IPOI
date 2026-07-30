from __future__ import annotations

import logging
from typing import Any

from src.skills.base import BaseSkill, SkillInput, SkillOutput

logger = logging.getLogger(__name__)


class CashFlowCalculator:
    def calculate_burn_rate(
        self,
        operating_cash_outflow: float,
        months: int,
        cash_reserve: float,
    ) -> dict[str, Any]:
        monthly_burn_rate = operating_cash_outflow / max(months, 1)
        runway_months = cash_reserve / monthly_burn_rate if monthly_burn_rate > 0 else float("inf")

        return {
            "monthly_burn_rate": round(monthly_burn_rate, 2),
            "cash_reserve": round(cash_reserve, 2),
            "runway_months": round(runway_months, 2),
            "scenario": "neutral",
            "assumptions": {
                "operating_cash_outflow": operating_cash_outflow,
                "months": months,
                "cash_reserve": cash_reserve,
            },
        }

    def sensitivity_analysis(
        self,
        operating_cash_outflow: float,
        months: int,
        cash_reserve: float,
        optimistic_factor: float = 0.7,
        pessimistic_factor: float = 1.5,
    ) -> list[dict[str, Any]]:
        scenarios = [
            ("optimistic", optimistic_factor),
            ("neutral", 1.0),
            ("pessimistic", pessimistic_factor),
        ]

        results = []
        for scenario_name, factor in scenarios:
            adjusted_outflow = operating_cash_outflow * factor
            result = self.calculate_burn_rate(adjusted_outflow, months, cash_reserve)
            result["scenario"] = scenario_name
            result["assumptions"]["adjustment_factor"] = factor
            results.append(result)

        burn_rates = [r["monthly_burn_rate"] for r in results]
        if max(burn_rates) > 0 and (max(burn_rates) - min(burn_rates)) / max(burn_rates) > 0.5:
            for r in results:
                r["sensitivity_note"] = "不同假设下消耗率差异超50%，请关注敏感性分析结论"

        return results


class CashFlowCalculationSkill(BaseSkill):
    skill_name = "cash_flow_calculation"
    version = "0.1.0"
    description = "现金流消耗测算Skill：计算消耗率、资金耗尽时间与敏感性分析"

    def __init__(self) -> None:
        self._calculator = CashFlowCalculator()

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        action = skill_input.params.get("action", "calculate")

        try:
            if action == "calculate":
                return await self._calculate_burn_rate(skill_input)
            elif action == "sensitivity":
                return await self._sensitivity_analysis(skill_input)
            else:
                return SkillOutput(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            logger.error(f"CashFlowCalculationSkill error: {e}")
            return SkillOutput(success=False, error=str(e))

    async def _calculate_burn_rate(self, skill_input: SkillInput) -> SkillOutput:
        operating_cash_outflow = skill_input.params.get("operating_cash_outflow", 0.0)
        months = skill_input.params.get("months", 12)
        cash_reserve = skill_input.params.get("cash_reserve", 0.0)

        if months <= 0:
            return SkillOutput(success=False, error="months must be positive")

        result = self._calculator.calculate_burn_rate(operating_cash_outflow, months, cash_reserve)
        return SkillOutput(success=True, data=result)

    async def _sensitivity_analysis(self, skill_input: SkillInput) -> SkillOutput:
        operating_cash_outflow = skill_input.params.get("operating_cash_outflow", 0.0)
        months = skill_input.params.get("months", 12)
        cash_reserve = skill_input.params.get("cash_reserve", 0.0)
        optimistic_factor = skill_input.params.get("optimistic_factor", 0.7)
        pessimistic_factor = skill_input.params.get("pessimistic_factor", 1.5)

        results = self._calculator.sensitivity_analysis(
            operating_cash_outflow, months, cash_reserve, optimistic_factor, pessimistic_factor
        )
        return SkillOutput(success=True, data={"scenarios": results})