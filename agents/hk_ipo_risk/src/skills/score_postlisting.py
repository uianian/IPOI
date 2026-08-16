from __future__ import annotations

import csv
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from src.config import IPOI_ROOT
from src.models.market import PostlistingCheckpointAssessment, PostlistingMetricRisk
from src.tools.market_data import normalize_stock_code

DEFAULT_CONFIG = IPOI_ROOT / "market" / "configs" / "historical_scoring.yaml"
DEFAULT_CHECKPOINTS = IPOI_ROOT / "market" / "data" / "derived" / "ipo_postlisting_checkpoints.csv"


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


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _percentile(values: list[float], value: float) -> float | None:
    if not values:
        return None
    return (sum(item < value for item in values) + 0.5 * sum(item == value for item in values)) / len(values)


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


class PostlistingRiskScorer:
    """Score realized D5..D60 performance against prior IPOs at the same age."""

    def __init__(self, config_path: Path | str = DEFAULT_CONFIG) -> None:
        self.config_path = Path(config_path)
        with self.config_path.open("r", encoding="utf-8") as source:
            self.config = yaml.safe_load(source) or {}

    def load_and_score(
        self,
        stock_code: str,
        *,
        checkpoints_csv: Path | str = DEFAULT_CHECKPOINTS,
        through_day: int = 60,
    ) -> list[PostlistingCheckpointAssessment]:
        code = normalize_stock_code(stock_code)
        rows = self._load_rows(Path(checkpoints_csv))
        targets = [
            row for row in rows
            if row["stock_code"] == code and int(row["trading_day"]) <= through_day
        ]
        if not targets:
            raise KeyError(f"no post-listing checkpoints for stock_code {code}")
        results = []
        for target in sorted(targets, key=lambda row: int(row["trading_day"])):
            history = [
                row for row in rows
                if int(row["trading_day"]) == int(target["trading_day"])
                and row["listing_date"] < target["listing_date"]
            ]
            results.append(self.score_row(target, history))
        return results

    def score_row(
        self,
        row: dict[str, Any],
        history_rows: list[dict[str, Any]],
    ) -> PostlistingCheckpointAssessment:
        cfg = self.config.get("postlisting") or {}
        definitions = cfg.get("metrics") or {}
        minimum = int(cfg.get("minimum_history_samples") or 10)
        metric_scores: list[PostlistingMetricRisk] = []
        limitations: list[str] = []
        present_weight = 0.0

        for metric, definition in definitions.items():
            configured_weight = float(definition.get("weight") or 0.0)
            if metric == "below_issue_price":
                raw_bool = _boolean(row.get(metric))
                if raw_bool is None:
                    limitations.append(
                        "issue price unavailable; primary break anchor omitted from realized score"
                    )
                    continue
                risk = 100.0 if raw_bool else 0.0
                percentile = None
                history_size = sum(
                    _boolean(item.get(metric)) is not None for item in history_rows
                )
                raw_value: float | bool | None = raw_bool
            else:
                raw = _number(row.get(metric))
                if raw is None:
                    continue
                values = [
                    value
                    for item in history_rows
                    if (value := _number(item.get(metric))) is not None
                ]
                history_size = len(values)
                percentile = _percentile(values, raw)
                if percentile is None:
                    limitations.append(f"{metric}: no same-checkpoint historical cohort")
                    continue
                direction = str(definition.get("risk_direction") or "higher")
                risk = percentile * 100.0 if direction == "higher" else (1.0 - percentile) * 100.0
                if history_size < minimum:
                    limitations.append(
                        f"{metric}: same-checkpoint history {history_size} < {minimum}; low confidence"
                    )
                raw_value = raw
            present_weight += configured_weight
            metric_scores.append(
                PostlistingMetricRisk(
                    metric=metric,
                    raw_value=raw_value,
                    risk_score=round(risk, 2),
                    configured_weight=configured_weight,
                    effective_weight=0.0,
                    history_sample_size=history_size,
                    history_percentile=None if percentile is None else round(percentile, 6),
                    evidence_id=f"POST-{row['checkpoint']}-{metric.upper().replace('_', '-')}",
                )
            )
        if present_weight <= 0:
            raise ValueError(f"checkpoint {row.get('checkpoint')} has no scoreable realized metrics")
        score = 0.0
        for metric in metric_scores:
            metric.effective_weight = metric.configured_weight / present_weight
            score += float(metric.risk_score or 0.0) * metric.effective_weight

        issue_price = _number(row.get("issue_price"))
        return PostlistingCheckpointAssessment(
            score_version=str(self.config.get("version") or "historical-v1"),
            stock_code=normalize_stock_code(str(row["stock_code"])),
            checkpoint=str(row["checkpoint"]),
            trading_day=int(row["trading_day"]),
            listing_date=row["listing_date"] if isinstance(row["listing_date"], date) else _date(row["listing_date"]),
            observation_date=row["observation_date"] if isinstance(row["observation_date"], date) else _date(row["observation_date"]),
            first_trading_day_open=float(row["first_trading_day_open"]),
            issue_price=issue_price,
            below_issue_price=_boolean(row.get("below_issue_price")),
            cumulative_return_from_open=float(row["cumulative_return_from_open"]),
            issue_price_return=_number(row.get("issue_price_return")),
            excess_hsi_return=_number(row.get("excess_hsi_return")),
            excess_industry_return=_number(row.get("excess_industry_return")),
            max_drawdown_from_open=_number(row.get("max_drawdown_from_open")),
            realized_volatility=_number(row.get("realized_volatility")),
            turnover_change=_number(row.get("turnover_change")),
            realized_risk_score=round(score, 2),
            risk_level=_risk_level(score),
            metrics=metric_scores,
            evidence_ids=[metric.evidence_id for metric in metric_scores],
            limitations=limitations,
        )

    @staticmethod
    def _load_rows(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            raise FileNotFoundError(f"post-listing checkpoint table not found: {path}")
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                listing = _date(row.get("listing_date"))
                observation = _date(row.get("observation_date"))
                if listing is None or observation is None:
                    continue
                row["listing_date"] = listing
                row["observation_date"] = observation
                row["stock_code"] = normalize_stock_code(str(row.get("stock_code") or ""))
                rows.append(row)
        return rows

