"""rules fallback：无证据仍计分；runway=null → RUNWAY_UNCERTAIN。"""

from __future__ import annotations

import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.skills.score_finance import (  # noqa: E402
    build_rules_summary,
    runway_uncertain,
    score_finance,
)
from src.skills.finance_toolbox import _canonical_score_code  # noqa: E402


def test_score_finance_keeps_points_without_evidence_pages() -> None:
    metrics = {
        "NET_LOSS": {"2023": -100.0, "2024": -200.0},
        "CFO": {"2023": -50.0, "2024": -80.0},
        "CASH_EQ": {"2024": 500.0},
    }
    gates = {
        "issuer_type": "18a",
        "is_biotech_18a": True,
        "is_unprofitable": True,
        "continuous_net_loss": True,
        "latest_full_year_loss": True,
        "skip_3_4": False,
        "profitability_known": True,
        "profitability_status": "unprofitable",
    }
    cash_burn = {
        "skipped": False,
        "END_CASH": 500.0,
        "BURN_RATE_MONTHLY": 80.0 / 12,
        "CASH_RUNWAY_MONTHS": 500.0 / (80.0 / 12),
        "burn_yoy_up_gt_30": False,
    }
    # 无 evidence / table_meta —— 旧逻辑会 continue 跳过全部扣分
    out = score_finance(metrics, gates, cash_burn, {"evidence": {}, "table_meta": {}})
    codes = {b["code"] for b in out["score_breakdown"]}
    assert "CONTINUOUS_LOSS" in codes
    assert "CFO_NEGATIVE" in codes
    assert float(out["risk_score"]) >= 40
    assert "[rules]" not in (out.get("summary") or "")
    assert "财务指标" not in (out.get("summary") or "")


def test_runway_null_adds_uncertain_not_only_loss() -> None:
    metrics = {
        "NET_LOSS": {"2023": -733376.0, "2024": -174690.0},
        "CASH_EQ": {"2025_i1": 556664.0},
        # 无 CFO → 算不出 runway
    }
    gates = {
        "issuer_type": "18a",
        "is_biotech_18a": True,
        "is_unprofitable": True,
        "continuous_net_loss": True,
        "latest_full_year_loss": True,
        "skip_3_4": False,
        "profitability_known": True,
        "profitability_status": "unprofitable",
    }
    cash_burn = {
        "skipped": False,
        "END_CASH": 556664.0,
        "BURN_RATE_MONTHLY": None,
        "CASH_RUNWAY_MONTHS": None,
        "burn_yoy_up_gt_30": False,
    }
    assert runway_uncertain(metrics, gates, cash_burn) is True
    out = score_finance(metrics, gates, cash_burn, {"evidence": {}, "table_meta": {}})
    codes = {b["code"] for b in out["score_breakdown"]}
    assert "CONTINUOUS_LOSS" in codes
    assert "RUNWAY_UNCERTAIN" in codes
    assert "CASH_RUNWAY_12_24" not in codes
    assert float(out["risk_score"]) >= 40  # 25+15
    assert "RUNWAY_UNCERTAIN" in (out.get("summary") or "")


def test_canonical_preserves_runway_uncertain() -> None:
    state = {"cash_burn": {"skipped": False, "CASH_RUNWAY_MONTHS": None}}
    assert _canonical_score_code("RUNWAY_UNCERTAIN", state) == "RUNWAY_UNCERTAIN"
    # LLM 瞎写 RUNWAY 且 months=null → uncertain，不发明 12_24
    assert _canonical_score_code("CASH_RUNWAY_LT_12", state) == "RUNWAY_UNCERTAIN"


def test_build_rules_summary_not_template() -> None:
    s = build_rules_summary(
        risk_score=40.0,
        risk_level="medium",
        flags={"runway_uncertain": True, "continuous_net_loss": True},
        breakdown=[
            {"code": "CONTINUOUS_LOSS", "delta": 25, "note": "連續虧損"},
            {"code": "RUNWAY_UNCERTAIN", "delta": 15, "note": "跑道未知"},
        ],
        metrics={"NET_LOSS": {"2024": -1.0}},
        cash_burn={"CASH_RUNWAY_MONTHS": None},
        gates={"issuer_type": "18a", "is_biotech_18a": True},
    )
    assert "40.0" in s
    assert "CONTINUOUS_LOSS" in s
    assert not s.startswith("财务指标")
