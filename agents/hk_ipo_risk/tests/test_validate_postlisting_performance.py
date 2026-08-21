from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from service.report_data import build_report_data
from scripts.generate_analysis_report import _master_debate_md, build_master_report
from src.skills.base import SkillInput
from src.skills.generate_warning_report import render_master_markdown
from src.skills.validate_postlisting_performance import ValidatePostlistingPerformanceSkill


def _checkpoint(day: int, *, issue_ret: float, cumulative: float, drawdown: float, below: bool) -> dict:
    observation_date = date(2025, 12, 15) + timedelta(days=day)
    return {
        "score_version": "historical-v1",
        "stock_code": "03378",
        "checkpoint": f"D{day}",
        "trading_day": day,
        "listing_date": "2025-12-15",
        "observation_date": observation_date.isoformat(),
        "first_trading_day_open": 12.0,
        "issue_price": 18.6,
        "below_issue_price": below,
        "cumulative_return_from_open": cumulative,
        "issue_price_return": issue_ret,
        "max_drawdown_from_open": drawdown,
        "realized_volatility": 0.1,
        "turnover_change": -0.2,
        "realized_risk_score": 88.0 if below else 35.0,
        "risk_level": "very_high" if below else "low",
        "metrics": [],
        "evidence_ids": [],
        "limitations": [],
    }


def _forecasts() -> list[dict]:
    return [
        {
            "window": "D1",
            "risk_label": "high",
            "expected_direction": "预计上市首日破发或显著承压",
            "expected_pattern": "首日可能低开后弱势震荡",
            "volatility_view": "回撤和波动风险高",
            "key_drivers": ["行业 IPO 破发率高", "发行人持续亏损"],
            "confidence": "medium",
        },
        {
            "window": "D5",
            "risk_label": "high",
            "expected_direction": "预计上市后5个交易日内显著下跌风险高",
            "expected_pattern": "首日承压后继续弱势",
            "volatility_view": "高波动下探",
            "key_drivers": ["创新药板块承压", "赎回压力"],
            "confidence": "medium",
        },
        {"window": "D20", "risk_label": "medium", "expected_direction": "20日下行风险中等", "expected_pattern": "弱势整理", "volatility_view": "波动中等", "key_drivers": [], "confidence": "medium"},
        {"window": "D60", "risk_label": "medium", "expected_direction": "60日下行风险中等", "expected_pattern": "等待基本面验证", "volatility_view": "波动中等", "key_drivers": [], "confidence": "low"},
    ]


def _run_validation(payload: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "postlisting.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        out = asyncio.run(
            ValidatePostlistingPerformanceSkill().execute(
                SkillInput(
                    doc_id="analysis_20260817_000033",
                    params={
                        "stock_code": "03378",
                        "postlisting_json": path,
                        "predicted_windows": {
                            "ipo_day_break_risk": "high",
                            "d5_significant_downside_risk": "high",
                            "d20_downside_risk": "medium",
                            "d60_downside_risk": "medium",
                        },
                        "price_path_forecast": _forecasts(),
                    },
                )
            )
        )
    return out.data["post_listing"]


def test_validate_postlisting_weights_and_d5_priority_hit():
    post = _run_validation(
        {
            "checkpoints": [
                _checkpoint(1, issue_ret=-0.4625, cumulative=-0.05, drawdown=-0.08, below=True),
                _checkpoint(5, issue_ret=-0.55, cumulative=-0.18, drawdown=-0.20, below=True),
                _checkpoint(20, issue_ret=-0.10, cumulative=0.02, drawdown=-0.05, below=True),
                _checkpoint(60, issue_ret=0.05, cumulative=0.08, drawdown=-0.04, below=False),
            ]
        }
    )
    assert post["status"] == "completed"
    assert post["weights"] == {"D1": 0.30, "D5": 0.35, "D20": 0.20, "D60": 0.15}
    assert post["d5_priority_hit"] is True
    assert post["checkpoints"][0]["alignment"] == "hit"
    assert post["checkpoints"][1]["alignment"] == "hit"
    assert post["weighted_hit_score"] is not None


def test_validate_postlisting_d5_compound_rule_by_cumulative_or_drawdown():
    for cumulative, drawdown in [(-0.11, -0.02), (-0.01, -0.16)]:
        post = _run_validation(
            {
                "checkpoints": [
                    _checkpoint(5, issue_ret=0.02, cumulative=cumulative, drawdown=drawdown, below=False),
                ]
            }
        )
        d5 = next(item for item in post["checkpoints"] if item["window"] == "D5")
        assert post["d5_priority_hit"] is True
        assert d5["actual_severity"] == "severe"


def test_report_and_report_data_include_forecast_validation_without_rewriting_score():
    post = _run_validation(
        {
            "checkpoints": [
                _checkpoint(1, issue_ret=-0.4625, cumulative=-0.05, drawdown=-0.08, below=True),
                _checkpoint(5, issue_ret=-0.55, cumulative=-0.18, drawdown=-0.20, below=True),
            ]
        }
    )
    master = {
        "judgment": {"overall_score": 72, "risk_level_http": "HIGH", "confidence": "medium"},
        "predicted_windows": {
            "ipo_day_break_risk": "high",
            "d5_significant_downside_risk": "high",
            "d20_downside_risk": "medium",
            "d60_downside_risk": "medium",
        },
        "price_path_forecast": _forecasts(),
        "post_listing": post,
        "report_sections": {"composite": "上市前终裁维持高风险"},
    }
    markdown = render_master_markdown(master)
    assert "上市前走勢預判" in markdown
    assert "上市後真實行情驗證" in markdown
    assert "显著下跌风险高" in markdown

    report = build_report_data(
        {"master": master, "finance": {}, "legal": {}, "market": {}},
        overall_score=72,
        risk_level="HIGH",
    )
    assert report["overallScore"] == 72
    assert report["pricePathForecast"][1]["expectedDirection"].endswith("风险高")
    assert report["postListingValidation"]["d5PriorityHit"] is True

    final_md = build_master_report(
        {"doc_id": "analysis_20260817_000033", "master": master},
        doc_name="翰思艾泰",
        pdf_name="03378.pdf",
    )
    assert "IPO风险穿透预警报告" in final_md
    assert "逐时间窗走势预判如下" in final_md
    assert "上市后真实行情验证" in final_md
    assert "显著下跌风险高" in final_md
    assert "上市首日" in final_md
    assert "上市后5个交易日内" in final_md
    assert "高风险" in final_md
    assert "中等置信度" in final_md


def test_master_debate_report_uses_actual_judgment_instead_of_hardcoded_high_risk():
    master = {
        "judgment": {
            "overall_score": 35,
            "risk_level_http": "MEDIUM",
            "confidence": "medium",
            "verdict_reasoning": "财务稳健，但治理与加盟模式仍有不确定性。",
        },
        "debate_history": [
            {
                "round": 1,
                "questions": [],
                "replies": [],
                "continue_debate": True,
                "continue_reason": "证据仍需补充",
            },
            {
                "round": 2,
                "questions": [],
                "replies": [],
                "continue_debate": False,
                "continue_reason": "已达最大轮次（第3轮），关键问题已回应",
            },
        ],
    }

    markdown = _master_debate_md(master)

    assert "本次共完成2轮辩论" in markdown
    assert "35.0分（中等风险，中等置信度）" in markdown
    assert "财务稳健，但治理与加盟模式仍有不确定性" in markdown
    assert "第3轮" not in markdown
    assert "赎回负债、现金跑道和流动性压力" not in markdown


def test_report_layers_backfill_missing_price_path_forecast_from_predicted_windows():
    master = {
        "judgment": {"overall_score": 65, "risk_level_http": "HIGH", "confidence": "medium"},
        "predicted_windows": {
            "ipo_day_break_risk": "high",
            "d5_significant_downside_risk": "high",
            "d20_downside_risk": "medium",
            "d60_downside_risk": "medium",
        },
        "report_sections": {"composite": "旧总控 JSON 只有标签级预测"},
    }

    report = build_report_data(
        {"master": master, "finance": {}, "legal": {}, "market": {}},
        overall_score=65,
        risk_level="HIGH",
    )
    assert [item["window"] for item in report["pricePathForecast"]] == ["D1", "D5", "D20", "D60"]
    assert report["pricePathForecast"][0]["riskLabel"] == "high"
    assert report["pricePathForecast"][1]["riskLabel"] == "high"

    final_md = build_master_report(
        {"doc_id": "analysis_20260817_000033", "master": master},
        doc_name="翰思艾泰",
        pdf_name="03378.pdf",
    )
    assert "逐时间窗走势预判如下" in final_md
    assert "本次结构化结果未提供逐时间窗走势文字" not in final_md
    assert "上市首日破发风险中等" in final_md
