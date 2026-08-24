from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import IPOI_ROOT, resolve_market_agent_settings
from src.models.market import PostlistingCheckpointAssessment
from src.models.master import (
    PostListingCheckpointValidation,
    PostListingValidation,
    PredictedWindows,
    PricePathForecastItem,
    default_price_path_forecast,
)
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.score_postlisting import PostlistingRiskScorer
from src.tools.market_data import normalize_stock_code


WINDOW_WEIGHTS = {"D1": 0.30, "D5": 0.35, "D20": 0.20, "D60": 0.15}
WINDOW_DAYS = {"D1": 1, "D5": 5, "D20": 20, "D60": 60}
PREDICTED_FIELDS = {
    "D1": "ipo_day_break_risk",
    "D5": "d5_significant_downside_risk",
    "D20": "d20_downside_risk",
    "D60": "d60_downside_risk",
}


WINDOW_LABELS = {
    "D1": "上市首日",
    "D5": "上市后5个交易日内",
    "D20": "上市后20个交易日内",
    "D60": "上市后60个交易日内",
}


def _join_chinese(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "、".join(items[:-1]) + "和" + items[-1]


def _checkpoint_value(checkpoint: Any, field: str) -> Any:
    if isinstance(checkpoint, dict):
        aliases = {
            "below_issue_price": "belowIssuePrice",
            "issue_price_return": "issuePriceReturn",
        }
        value = checkpoint.get(field)
        return value if value is not None else checkpoint.get(aliases.get(field, ""))
    return getattr(checkpoint, field, None)


def build_postlisting_summary(
    checkpoints: list[Any] | None,
    *,
    weighted_hit_score: Any = None,
    d5_priority_hit: bool | None = None,
    status: str = "completed",
) -> str:
    """Generate a reader-facing Chinese summary without backend window codes."""
    available = [
        checkpoint for checkpoint in (checkpoints or [])
        if str(_checkpoint_value(checkpoint, "alignment") or "") != "not_available"
    ]
    if status == "not_available" or not available:
        return "尚未取得可用于验证的上市后行情数据，当前无法评估事前预测与实际表现的一致程度。"

    labels = [
        WINDOW_LABELS.get(str(_checkpoint_value(item, "window") or "").upper(), "上市后对应交易日")
        for item in available
    ]
    sentences = [f"本次上市后表现验证覆盖{_join_chinese(labels)}，共{len(available)}个检查点。"]
    score = _safe_float(weighted_hit_score)
    if score is not None:
        sentences.append(f"预测加权命中分为{score:g}分。")

    alignment_phrases = []
    for alignment, phrase in (("hit", "一致"), ("partial", "部分一致"), ("miss", "不一致")):
        matched = [
            WINDOW_LABELS.get(str(_checkpoint_value(item, "window") or "").upper(), "上市后对应交易日")
            for item in available
            if str(_checkpoint_value(item, "alignment") or "") == alignment
        ]
        if matched:
            alignment_phrases.append(f"{_join_chinese(matched)}的预测与实际表现{phrase}")
    if alignment_phrases:
        sentences.append("；".join(alignment_phrases) + "。")

    if any(str(_checkpoint_value(item, "window") or "").upper() == "D5" for item in available):
        priority = "命中" if d5_priority_hit is True else "未命中" if d5_priority_hit is False else "暂无法判断"
        sentences.append(f"上市后5个交易日重点预警{priority}。")

    below_count = sum(_checkpoint_value(item, "below_issue_price") is True for item in available)
    returns = [
        (item, _safe_float(_checkpoint_value(item, "issue_price_return")))
        for item in available
    ]
    returns = [(item, value) for item, value in returns if value is not None]
    if below_count:
        price_sentence = f"{below_count}个检查点的实际价格低于发行价"
        if returns:
            worst_item, worst_return = min(returns, key=lambda pair: pair[1])
            worst_label = WINDOW_LABELS.get(str(_checkpoint_value(worst_item, "window") or "").upper(), "上市后对应交易日")
            price_sentence += f"，其中{worst_label}相对发行价跌幅最大，为{abs(worst_return):.2%}"
        sentences.append(price_sentence + "。")
    return "".join(sentences)


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _forecast_text(item: PricePathForecastItem) -> str:
    parts = [item.expected_direction, item.expected_pattern, item.volatility_view]
    if item.key_drivers:
        parts.append("；".join(item.key_drivers))
    return "；".join(part for part in parts if part)


def _forecast_map(
    *,
    price_path_forecast: Any,
    predicted_windows: Any,
) -> dict[str, PricePathForecastItem]:
    try:
        windows = PredictedWindows(**predicted_windows) if isinstance(predicted_windows, dict) else PredictedWindows()
    except Exception:
        windows = PredictedWindows()
    fallback = {item.window: item for item in default_price_path_forecast()}
    for window, field in PREDICTED_FIELDS.items():
        fallback[window].risk_label = str(getattr(windows, field) or "medium")

    for raw in price_path_forecast or []:
        if not isinstance(raw, dict):
            continue
        window = str(raw.get("window") or "").upper()
        if window not in fallback:
            continue
        try:
            fallback[window] = PricePathForecastItem(**{**raw, "window": window})
        except Exception:
            continue
    return fallback


def _read_postlisting_json(path: Path) -> list[PostlistingCheckpointAssessment]:
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    rows = payload.get("checkpoints") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"postlisting JSON missing checkpoints: {path}")
    return [PostlistingCheckpointAssessment.model_validate(row) for row in rows]


def _candidate_json_paths(doc_id: str, stock_code: str, explicit: Any = None) -> list[Path]:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit))
    try:
        settings = resolve_market_agent_settings()
        output = settings.get("output") or {}
        directory = Path(output.get("directory") or IPOI_ROOT / "agents" / "hk_ipo_risk" / ".runtime" / "market")
        variables = {"doc_id": doc_id, "stock_code": stock_code}
        name = str(output.get("postlisting_json_filename") or "{doc_id}_{stock_code}_postlisting.json")
        paths.append(directory / name.format(**variables))
        paths.append(directory / f"{doc_id}_{stock_code}_postlisting.json")
        paths.append(directory / f"{doc_id}_postlisting.json")
    except Exception:
        pass
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def _actual_severity(item: PostlistingCheckpointAssessment) -> str:
    score = _safe_float(item.realized_risk_score)
    cumulative = _safe_float(item.cumulative_return_from_open)
    drawdown = _safe_float(item.max_drawdown_from_open)
    if (
        item.below_issue_price is True
        or (cumulative is not None and cumulative <= -0.10)
        or (drawdown is not None and drawdown <= -0.15)
        or (score is not None and score >= 70)
    ):
        return "severe"
    if (
        (cumulative is not None and cumulative <= -0.05)
        or (drawdown is not None and drawdown <= -0.10)
        or (score is not None and score >= 50)
    ):
        return "moderate"
    return "benign"


def _alignment(prediction_label: str, actual_severity: str) -> str:
    label = str(prediction_label or "medium").lower()
    if label == "high":
        return "hit" if actual_severity == "severe" else "partial" if actual_severity == "moderate" else "miss"
    if label == "medium":
        return "hit" if actual_severity == "moderate" else "partial"
    if label == "low":
        return "hit" if actual_severity == "benign" else "partial" if actual_severity == "moderate" else "miss"
    return "not_available"


def _d5_significant_downside(item: PostlistingCheckpointAssessment) -> bool:
    cumulative = _safe_float(item.cumulative_return_from_open)
    drawdown = _safe_float(item.max_drawdown_from_open)
    return bool(
        item.below_issue_price is True
        or (cumulative is not None and cumulative <= -0.10)
        or (drawdown is not None and drawdown <= -0.15)
    )


class ValidatePostlistingPerformanceSkill(BaseSkill):
    skill_name = "validate_postlisting_performance"
    version = "0.1.0"
    description = "对齐总控上市前走势预测与上市后真实 D1/D5/D20/D60 表现"

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        p = skill_input.params
        doc_id = str(skill_input.doc_id or p.get("doc_id") or "")
        stock_code_raw = p.get("stock_code")
        if not stock_code_raw:
            return SkillOutput(
                success=True,
                data={"post_listing": PostListingValidation(limitations=["missing stock_code"]).model_dump()},
            )
        stock_code = normalize_stock_code(str(stock_code_raw))
        limitations: list[str] = []
        source = ""
        assessments: list[PostlistingCheckpointAssessment] = []

        for path in _candidate_json_paths(doc_id, stock_code, p.get("postlisting_json")):
            if path.is_file():
                try:
                    assessments = _read_postlisting_json(path)
                    source = str(path)
                    break
                except Exception as exc:
                    limitations.append(f"{path}: {exc}")
        if not assessments:
            try:
                settings = resolve_market_agent_settings(settings_path=p.get("market_settings_path"))
                csv_path = Path(settings["data"]["postlisting_checkpoints_csv"])
                assessments = PostlistingRiskScorer().load_and_score(
                    stock_code,
                    checkpoints_csv=csv_path,
                    through_day=60,
                )
                source = str(csv_path)
            except Exception as exc:
                result = PostListingValidation(
                    status="not_available",
                    source=source,
                    summary="上市后真实行情验证未接入",
                    limitations=limitations + [str(exc)],
                )
                return SkillOutput(success=True, data={"post_listing": result.model_dump()})

        forecasts = _forecast_map(
            price_path_forecast=p.get("price_path_forecast"),
            predicted_windows=p.get("predicted_windows"),
        )
        by_window = {f"D{item.trading_day}": item for item in assessments}
        checkpoints: list[PostListingCheckpointValidation] = []
        weighted = 0.0
        present_weight = 0.0
        d5_priority_hit: bool | None = None

        for window, weight in WINDOW_WEIGHTS.items():
            forecast = forecasts[window]
            actual = by_window.get(window)
            if actual is None:
                checkpoints.append(
                    PostListingCheckpointValidation(
                        window=window,  # type: ignore[arg-type]
                        prediction_label=forecast.risk_label,
                        prediction_text=_forecast_text(forecast),
                        note="真实行情检查点缺失，仅保留上市前预测",
                    )
                )
                continue
            severity = _actual_severity(actual)
            alignment = _alignment(forecast.risk_label, severity)
            score = 1.0 if alignment == "hit" else 0.5 if alignment == "partial" else 0.0
            weighted += score * weight
            present_weight += weight
            if window == "D5":
                d5_priority_hit = str(forecast.risk_label).lower() == "high" and _d5_significant_downside(actual)
            checkpoints.append(
                PostListingCheckpointValidation(
                    window=window,  # type: ignore[arg-type]
                    prediction_label=forecast.risk_label,
                    prediction_text=_forecast_text(forecast),
                    actual_severity=severity,  # type: ignore[arg-type]
                    hit=alignment == "hit",
                    alignment=alignment,  # type: ignore[arg-type]
                    observation_date=actual.observation_date.isoformat(),
                    below_issue_price=actual.below_issue_price,
                    cumulative_return_from_open=actual.cumulative_return_from_open,
                    issue_price_return=actual.issue_price_return,
                    max_drawdown_from_open=actual.max_drawdown_from_open,
                    realized_risk_score=actual.realized_risk_score,
                    note=(
                        f"真实{window}: 累计收益={actual.cumulative_return_from_open:.2%}, "
                        f"发行价收益={'不可用' if actual.issue_price_return is None else format(actual.issue_price_return, '.2%')}, "
                        f"最大回撤={'不可用' if actual.max_drawdown_from_open is None else format(actual.max_drawdown_from_open, '.2%')}"
                    ),
                )
            )
            limitations.extend(actual.limitations)

        status = "completed" if present_weight >= 0.999 else "partial" if present_weight > 0 else "not_available"
        weighted_hit_score = round(weighted / present_weight * 100.0, 2) if present_weight else None
        summary = "上市后真实行情验证未接入"
        if status != "not_available":
            summary = build_postlisting_summary(
                checkpoints,
                weighted_hit_score=weighted_hit_score,
                d5_priority_hit=d5_priority_hit,
                status=status,
            )
        result = PostListingValidation(
            status=status,  # type: ignore[arg-type]
            source=source,
            summary=summary,
            business_value_score=weighted_hit_score,
            weighted_hit_score=weighted_hit_score,
            d5_priority_hit=d5_priority_hit,
            forecast_alignment_summary=summary,
            weights=WINDOW_WEIGHTS,
            checkpoints=checkpoints,
            limitations=sorted({item for item in limitations if item}),
        )
        return SkillOutput(success=True, data={"post_listing": result.model_dump()})
