from __future__ import annotations

import csv
import math
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from src.config import IPOI_ROOT
from src.models.market import (
    HistoricalIndicatorRisk,
    HistoricalModuleRisk,
    MarketSnapshot,
    MarketScorePack,
    PrelistingDay1RiskAssessment,
    PublicOpinionAssessment,
)

DEFAULT_CONFIG = IPOI_ROOT / "market" / "configs" / "historical_scoring.yaml"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], value: float) -> float | None:
    if not values:
        return None
    lower = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    return (lower + 0.5 * equal) / len(values)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _risk_level(score: float) -> str:
    if score < 20:
        return "very_low"
    if score < 40:
        return "low"
    if score < 60:
        return "medium"
    if score < 80:
        return "high"
    return "very_high"


class HistoricalMarketRiskScorer:
    """Point-in-time historical calibration for the pre-listing D1 break risk.

    Only rows whose ``as_of_date`` is earlier than the target snapshot are used.
    Outcome columns are never read by this scorer. Raw fixed thresholds are
    replaced with oriented empirical percentiles plus same-period trend context.
    """

    def __init__(self, config_path: Path | str = DEFAULT_CONFIG) -> None:
        self.config_path = Path(config_path)
        with self.config_path.open("r", encoding="utf-8") as source:
            self.config = yaml.safe_load(source) or {}

    def score(
        self,
        snapshot: MarketSnapshot,
        *,
        features_csv: Path | str,
        public_opinion: PublicOpinionAssessment | None = None,
        fallback_score_pack: MarketScorePack | None = None,
    ) -> PrelistingDay1RiskAssessment:
        rows = self._history_rows(Path(features_csv), snapshot.as_of_date)
        history_cfg = self.config.get("history") or {}
        min_history = int(history_cfg.get("minimum_history_samples") or 12)
        level_weight = float(history_cfg.get("level_weight") or 0.7)
        trend_weight = float(history_cfg.get("trend_weight") or 0.3)
        lookback_years = int(history_cfg.get("lookback_years") or 2)
        lower_bound = snapshot.as_of_date - timedelta(days=366 * lookback_years)
        rows = [row for row in rows if row["as_of_date"] >= lower_bound]

        indicator_scores: dict[str, list[HistoricalIndicatorRisk]] = {
            "macro": [],
            "industry": [],
            "ipo_market": [],
            "public_opinion": [],
        }
        limitations: list[str] = []
        definitions = self.config.get("indicators") or {}
        vhsi_present = _number(snapshot.features.get("vhsi_avg_5d")) is not None
        for indicator, definition in definitions.items():
            if definition.get("fallback_for") == "vhsi_avg_5d" and vhsi_present:
                continue
            if indicator == "vhsi_avg_5d" and not vhsi_present:
                continue
            raw = _number(snapshot.features.get(indicator))
            if raw is None:
                continue
            values = [
                value
                for row in rows
                if (value := _number(row["values"].get(indicator))) is not None
            ]
            if len(values) < min_history:
                limitations.append(
                    f"{indicator}: historical sample {len(values)} < {min_history}; omitted"
                )
                continue
            percentile = _percentile(values, raw)
            direction = str(definition.get("risk_direction") or "higher")
            level_risk = (
                percentile * 100.0
                if direction == "higher"
                else (1.0 - percentile) * 100.0
            )
            y1 = self._same_period_median(rows, indicator, snapshot.as_of_date, 1)
            y2 = self._same_period_median(rows, indicator, snapshot.as_of_date, 2)
            yoy = raw - y1 if y1 is not None else None
            two_year = raw - y2 if y2 is not None else None
            trend_risk = None
            reference = y1 if y1 is not None else y2
            if reference is not None:
                median = statistics.median(values)
                deviations = [abs(value - median) for value in values]
                scale = statistics.median(deviations) * 1.4826
                if scale <= 1e-12:
                    scale = statistics.pstdev(values) if len(values) > 1 else 1.0
                scale = max(scale, 1e-9)
                oriented_delta = (raw - reference) * (1.0 if direction == "higher" else -1.0)
                trend_risk = 50.0 + 50.0 * math.tanh(oriented_delta / scale)
            risk = level_risk
            if trend_risk is not None:
                risk = level_risk * level_weight + trend_risk * trend_weight
            confidence = min(1.0, len(values) / max(min_history * 2, 1))
            module = str(definition["module"])
            item = HistoricalIndicatorRisk(
                indicator=indicator,
                module=module,
                label=str(definition.get("label") or indicator),
                raw_value=raw,
                risk_direction=direction,
                history_start=min(row["as_of_date"] for row in rows) if rows else None,
                history_end=max(row["as_of_date"] for row in rows),
                history_sample_size=len(values),
                history_percentile=round(float(percentile), 6),
                previous_year_same_period=y1,
                previous_two_year_same_period=y2,
                yoy_change=yoy,
                two_year_change=two_year,
                level_risk_score=round(level_risk, 2),
                trend_risk_score=None if trend_risk is None else round(trend_risk, 2),
                risk_score=round(risk, 2),
                configured_weight=float(definition.get("weight") or 0.0),
                effective_weight=0.0,
                confidence=round(confidence, 4),
                evidence_id=f"HIST-{indicator.upper().replace('_', '-')}",
                interpretation=self._interpret(indicator, raw, percentile, direction, y1),
            )
            indicator_scores[module].append(item)

        modules: dict[str, HistoricalModuleRisk] = {}
        for module in ("macro", "industry", "ipo_market"):
            items = indicator_scores[module]
            configured_total = sum(
                float(definition.get("weight") or 0.0)
                for indicator_name, definition in definitions.items()
                if definition.get("module") == module
                and not (
                    definition.get("fallback_for") == "vhsi_avg_5d" and vhsi_present
                )
                and not (
                    indicator_name == "vhsi_avg_5d" and not vhsi_present
                )
            )
            present_total = sum(item.configured_weight for item in items)
            for item in items:
                item.effective_weight = (
                    item.configured_weight / present_total if present_total else 0.0
                )
            module_score = (
                sum(float(item.risk_score or 0.0) * item.effective_weight for item in items)
                if items
                else None
            )
            modules[module] = HistoricalModuleRisk(
                module=module,
                risk_score=None if module_score is None else round(module_score, 2),
                configured_weight=0.0,
                effective_weight=0.0,
                coverage_ratio=min(1.0, present_total / configured_total) if configured_total else 0.0,
                indicators=items,
            )

        opinion_available = bool(
            public_opinion and public_opinion.available and public_opinion.risk_score is not None
        )
        modules["public_opinion"] = HistoricalModuleRisk(
            module="public_opinion",
            risk_score=float(public_opinion.risk_score) if opinion_available else None,
            configured_weight=0.0,
            effective_weight=0.0,
            coverage_ratio=1.0 if opinion_available else 0.0,
            indicators=[],
        )
        weight_key = (
            "overall_module_weights_with_opinion"
            if opinion_available
            else "overall_module_weights_without_opinion"
        )
        configured_weights = self.config.get(weight_key) or {}
        available_weight = sum(
            float(configured_weights.get(name) or 0.0)
            for name, module in modules.items()
            if module.risk_score is not None
        )
        if available_weight <= 0 and fallback_score_pack is not None:
            limitations.append(
                "historical cohort unavailable; fixed-threshold compatibility modules used as an explicit fallback"
            )
            for name, fallback in fallback_score_pack.module_scores.items():
                modules[name] = HistoricalModuleRisk(
                    module=name,
                    risk_score=fallback.risk_score,
                    configured_weight=float(fallback_score_pack.effective_weights.get(name) or 0.0),
                    effective_weight=float(fallback_score_pack.effective_weights.get(name) or 0.0),
                    coverage_ratio=fallback.coverage_ratio,
                    indicators=[],
                )
            configured_weights = fallback_score_pack.effective_weights
            available_weight = sum(
                float(configured_weights.get(name) or 0.0)
                for name, module in modules.items()
                if module.risk_score is not None
            )
        if available_weight <= 0:
            raise ValueError("no historically scoreable market modules")
        total_score = 0.0
        effective_weights: dict[str, float] = {}
        for name, module in modules.items():
            configured = float(configured_weights.get(name) or 0.0)
            effective = configured / available_weight if module.risk_score is not None else 0.0
            module.configured_weight = configured
            module.effective_weight = effective
            effective_weights[name] = round(effective, 6)
            total_score += float(module.risk_score or 0.0) * effective

        issue_price = _number(snapshot.features.get("issue_price"))
        if issue_price is None:
            limitations.append(
                "issue_price unavailable: break-risk prediction is produced, but the primary break anchor cannot be validated for this issuer"
            )
        evidence_ids = [
            item.evidence_id
            for module in modules.values()
            for item in module.indicators
        ]
        return PrelistingDay1RiskAssessment(
            score_version=str(self.config.get("version") or "historical-v1"),
            score=round(total_score, 2),
            risk_level=_risk_level(total_score),
            as_of_date=snapshot.as_of_date,
            history_cutoff=snapshot.as_of_date,
            issue_price_available=issue_price is not None,
            break_anchor_status="available" if issue_price is not None else "unavailable",
            effective_module_weights=effective_weights,
            module_scores=modules,
            evidence_ids=evidence_ids,
            limitations=limitations,
            calibration_note=(
                "Empirical risk index from point-in-time two-year percentiles and same-period trends. "
                "Primary validation anchor is first-day close below issue price; secondary return base is first-day open."
            ),
        )

    @staticmethod
    def _history_rows(path: Path, cutoff: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                observed = _date(row.get("as_of_date"))
                if observed is None or observed >= cutoff:
                    continue
                rows.append({"as_of_date": observed, "values": row})
        return rows

    def _same_period_median(
        self,
        rows: list[dict[str, Any]],
        indicator: str,
        target: date,
        years_back: int,
    ) -> float | None:
        history_cfg = self.config.get("history") or {}
        width = int(history_cfg.get("same_period_days") or 45)
        minimum = int(history_cfg.get("minimum_same_period_samples") or 3)
        try:
            center = target.replace(year=target.year - years_back)
        except ValueError:
            center = target.replace(year=target.year - years_back, day=28)
        values = [
            value
            for row in rows
            if abs((row["as_of_date"] - center).days) <= width
            and (value := _number(row["values"].get(indicator))) is not None
        ]
        return _median(values) if len(values) >= minimum else None

    @staticmethod
    def _interpret(
        indicator: str,
        raw: float,
        percentile: float,
        direction: str,
        previous_year: float | None,
    ) -> str:
        risk_percentile = percentile if direction == "higher" else 1.0 - percentile
        text = (
            f"{indicator}={raw:.6g}; oriented historical risk percentile="
            f"{risk_percentile:.1%}"
        )
        if previous_year is not None:
            text += f"; previous-year same-period median={previous_year:.6g}"
        return text

