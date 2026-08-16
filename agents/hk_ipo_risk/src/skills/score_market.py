from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from src.models.market import (
    FactorScore,
    MarketModuleScore,
    MarketScorePack,
    MarketSnapshot,
    PublicOpinionAssessment,
)


def _clip(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _higher_is_risk(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError("high must be greater than low")
    return _clip((value - low) / (high - low) * 100.0)


def _lower_is_risk(value: float, bad: float, good: float) -> float:
    return 100.0 - _higher_is_risk(value, bad, good)


def _signed_flow_risk(value: float, scale: float) -> float:
    return _clip(50.0 - 50.0 * math.tanh(value / scale))


def _subscription_risk(value: float) -> float:
    # IPO subscription multiples are extremely heavy-tailed (1x to 5000x+).
    return _clip(100.0 - 25.0 * math.log10(max(float(value), 1.0)))


@dataclass(frozen=True)
class _FactorDef:
    code: str
    label: str
    weight: float
    transform: Callable[[float], float]
    note: str = ""


class MarketRiskScorer:
    """Deterministic, auditable baseline score for the market agent.

    Thresholds are deliberately centralized here so that calibration can move
    to YAML without changing the agent contract. Missing values are omitted and
    the remaining factor weights are renormalized; they are never treated as 0.
    """

    def score(
        self,
        snapshot: MarketSnapshot,
        public_opinion: PublicOpinionAssessment | None = None,
    ) -> MarketScorePack:
        modules = {
            "macro": self._score_macro(snapshot),
            "industry": self._score_industry(snapshot),
            "ipo_market": self._score_ipo_market(snapshot),
            "public_opinion": self._score_public_opinion(public_opinion),
        }
        public_used = bool(
            public_opinion
            and public_opinion.available
            and public_opinion.risk_score is not None
            and modules["public_opinion"].risk_score is not None
        )
        configured = (
            {name: 0.25 for name in modules}
            if public_used
            else {"macro": 1 / 3, "industry": 1 / 3, "ipo_market": 1 / 3, "public_opinion": 0.0}
        )
        available = {
            name: weight
            for name, weight in configured.items()
            if weight > 0 and modules[name].risk_score is not None
        }
        total_weight = sum(available.values())
        if total_weight <= 0:
            raise ValueError("no scoreable market modules")
        effective_weights = {
            name: (available.get(name, 0.0) / total_weight) for name in modules
        }
        risk_score = sum(
            float(modules[name].risk_score or 0.0) * effective_weights[name]
            for name in modules
        )
        coverage = sum(
            modules[name].coverage_ratio * effective_weights[name]
            for name in modules
        )
        # User-facing heat is the inverse of the final composite risk, not only
        # the macro module. This keeps both scales aligned across 3/4 modules.
        market_heat = _clip(100.0 - risk_score)
        return MarketScorePack(
            risk_score=round(risk_score, 2),
            risk_level=self.risk_level(risk_score),
            market_heat_score=round(market_heat, 2),
            module_scores=modules,
            effective_weights={k: round(v, 6) for k, v in effective_weights.items()},
            public_opinion_used=public_used,
            coverage_ratio=round(coverage, 4),
        )

    @staticmethod
    def risk_level(score: float) -> str:
        if score < 20:
            return "very_low"
        if score < 40:
            return "low"
        if score < 60:
            return "medium"
        if score < 80:
            return "high"
        return "very_high"

    def _module(
        self,
        module: str,
        snapshot: MarketSnapshot,
        defs: list[_FactorDef],
        *,
        summary: str,
    ) -> MarketModuleScore:
        present: list[tuple[_FactorDef, float, float]] = []
        missing: list[str] = []
        for definition in defs:
            raw = snapshot.features.get(definition.code)
            if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not math.isfinite(float(raw)):
                missing.append(definition.code)
                continue
            raw_float = float(raw)
            present.append((definition, raw_float, definition.transform(raw_float)))

        configured_total = sum(d.weight for d in defs)
        present_total = sum(d.weight for d, _, _ in present)
        coverage = present_total / configured_total if configured_total else 0.0
        factors: list[FactorScore] = []
        for definition, raw, risk in present:
            effective = definition.weight / present_total if present_total else 0.0
            factors.append(
                FactorScore(
                    code=definition.code,
                    label=definition.label,
                    raw_value=raw,
                    risk_score=round(risk, 2),
                    configured_weight=definition.weight,
                    effective_weight=effective,
                    note=definition.note,
                )
            )
        score = (
            sum(float(f.risk_score or 0.0) * f.effective_weight for f in factors)
            if factors
            else None
        )
        return MarketModuleScore(
            module=module,
            risk_score=None if score is None else round(score, 2),
            coverage_ratio=round(coverage, 4),
            factors=factors,
            missing_factors=missing,
            summary=summary,
        )

    def _score_macro(self, snapshot: MarketSnapshot) -> MarketModuleScore:
        # Macro internal allocation follows market/README: trend 30%,
        # liquidity 40%, volatility 20%, external environment 10%.
        defs = [
            _FactorDef("hsi_ret_5d", "恒指5日走势", 0.075, lambda v: _lower_is_risk(v, -0.10, 0.10)),
            _FactorDef("hsi_ret_20d", "恒指20日走势", 0.105, lambda v: _lower_is_risk(v, -0.15, 0.15)),
            _FactorDef("hsi_ret_60d", "恒指60日走势", 0.045, lambda v: _lower_is_risk(v, -0.25, 0.25)),
            _FactorDef("hstech_ret_20d", "恒生科技20日走势", 0.075, lambda v: _lower_is_risk(v, -0.20, 0.20)),
            _FactorDef("mkt_turnover_chg_20d", "全市场成交额变化", 0.20, lambda v: _lower_is_risk(v, -0.50, 0.50)),
            _FactorDef("southbound_net_20d", "南向资金20日净额", 0.20, lambda v: _signed_flow_risk(v, 500.0)),
            _FactorDef("vhsi_avg_5d", "VHSI五日均值", 0.20, lambda v: _higher_is_risk(v, 15.0, 45.0), "缺失时由恒指波动率替代"),
            _FactorDef("dxy_ret_20d", "美元指数20日走势", 0.04, lambda v: _higher_is_risk(v, -0.05, 0.05)),
            _FactorDef("us10y_chg_20d", "美债10Y变化", 0.03, lambda v: _higher_is_risk(v, -0.50, 0.50)),
            _FactorDef("dff_chg_30cd", "联储利率30日变化", 0.03, lambda v: _higher_is_risk(v, -0.50, 0.50)),
        ]
        # Preserve the 20% volatility allocation when VHSI did not yet exist.
        if not isinstance(snapshot.features.get("vhsi_avg_5d"), (int, float)):
            defs = [d for d in defs if d.code != "vhsi_avg_5d"]
            defs.append(
                _FactorDef("hsi_vol_20d", "恒指20日实现波动率", 0.20, lambda v: _higher_is_risk(v, 0.01, 0.04), "VHSI fallback")
            )
        return self._module("macro", snapshot, defs, summary="宏观发行环境风险")

    def _score_industry(self, snapshot: MarketSnapshot) -> MarketModuleScore:
        defs = [
            _FactorDef("ind_ret_20d", "行业20日收益", 0.25, lambda v: _lower_is_risk(v, -0.20, 0.20)),
            _FactorDef("ind_excess_20d", "行业相对恒指超额", 0.25, lambda v: _lower_is_risk(v, -0.15, 0.15)),
            _FactorDef("ind_amount_chg_20d", "行业成交额变化", 0.15, lambda v: _lower_is_risk(v, -0.50, 0.50)),
            _FactorDef("ind_newhigh_ratio", "行业创新高比例", 0.10, lambda v: _lower_is_risk(v, 0.0, 0.30)),
            _FactorDef("ind_net_inflow_20d", "行业20日资金净流入", 0.10, lambda v: _signed_flow_risk(v, 1_000_000_000.0)),
            _FactorDef("ind_avg_day1_return_365d", "行业IPO首日表现", 0.10, lambda v: _lower_is_risk(v, -0.15, 0.20)),
            _FactorDef("ind_break_rate_365d", "行业IPO破发率", 0.05, lambda v: _higher_is_risk(v, 0.20, 0.80)),
        ]
        return self._module("industry", snapshot, defs, summary="发行人所属行业热度风险")

    def _score_ipo_market(self, snapshot: MarketSnapshot) -> MarketModuleScore:
        defs = [
            _FactorDef("ipo_count_30d", "近30日IPO数量", 0.08, lambda v: _lower_is_risk(v, 0.0, 10.0)),
            _FactorDef("ipo_count_90d", "近90日IPO数量", 0.07, lambda v: _lower_is_risk(v, 0.0, 25.0)),
            _FactorDef("avg_day1_return_60d", "近期IPO首日收益", 0.18, lambda v: _lower_is_risk(v, -0.15, 0.20)),
            _FactorDef("avg_day5_return_60d", "近期IPO五日收益", 0.10, lambda v: _lower_is_risk(v, -0.20, 0.25)),
            _FactorDef("avg_day20_return_60d", "近期IPO二十日收益", 0.10, lambda v: _lower_is_risk(v, -0.30, 0.30)),
            _FactorDef("break_rate_60d", "近期IPO破发率", 0.20, lambda v: _higher_is_risk(v, 0.20, 0.80)),
            _FactorDef("avg_mdd20_60d", "近期IPO平均最大回撤", 0.12, lambda v: _lower_is_risk(v, -0.40, -0.05)),
            _FactorDef("subscription_multiple", "整体超额认购倍数", 0.06, _subscription_risk),
            _FactorDef("public_offer_multiple", "公开发售认购倍数", 0.05, _subscription_risk),
            _FactorDef("international_placing_multiple", "网下认购倍数", 0.04, _subscription_risk),
        ]
        return self._module("ipo_market", snapshot, defs, summary="IPO供需与近期上市表现风险")

    @staticmethod
    def _score_public_opinion(
        assessment: PublicOpinionAssessment | None,
    ) -> MarketModuleScore:
        if not assessment or not assessment.available or assessment.risk_score is None:
            reason = assessment.unavailable_reason if assessment else "no_reliable_prelisting_public_opinion"
            return MarketModuleScore(
                module="public_opinion",
                risk_score=None,
                coverage_ratio=0.0,
                missing_factors=["public_opinion"],
                summary=reason or "no_reliable_prelisting_public_opinion",
            )
        direction = assessment.direction_score
        attention = assessment.attention_score
        factors: list[FactorScore] = []
        if direction is not None:
            factors.append(
                FactorScore(
                    code="opinion_direction",
                    label="舆情方向",
                    raw_value=direction,
                    risk_score=direction,
                    configured_weight=0.8,
                    effective_weight=0.8,
                )
            )
        if attention is not None:
            factors.append(
                FactorScore(
                    code="opinion_attention",
                    label="舆情关注度",
                    raw_value=attention,
                    risk_score=attention,
                    configured_weight=0.2,
                    effective_weight=0.2,
                )
            )
        return MarketModuleScore(
            module="public_opinion",
            risk_score=assessment.risk_score,
            coverage_ratio=1.0,
            factors=factors,
            summary=f"可靠上市前舆情 {assessment.relevant_articles} 篇",
        )

