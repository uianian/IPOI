"""财务空 submit 恢复、主题去重与 section_hint 路由。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.skills.finance_toolbox import (  # noqa: E402
    _canonical_score_code,
    _compose_finance_dimensions_from_skills,
    _compose_finance_submit_payload,
    _draft_finance_dimensions,
    _merge_rules_floor,
    _sanitize_negative_findings,
    _tool_submit_finance_report,
)
from src.skills.gates import compute_cash_burn  # noqa: E402
from src.skills.score_finance import cv_pref_material  # noqa: E402
from src.tools.retrieval_tool import (  # noqa: E402
    _split_section_hints,
    diversify_section_hits,
    resolve_sections,
)


def test_empty_submit_recovers_dimensions_and_score() -> None:
    state = {
        "doc_id": "hansiaitai",
        "issuer_type": "18a",
        "metrics": {
            "NET_LOSS": {"2023": -85160.0, "2024": -116922.0},
            "CFO": {"2023": -51994.0, "2024": -104894.0},
            "CASH_EQ": {"2025_i1": 150000.0},
            "END_CASH": {"2025_i1": 150000.0},
            "NET_ASSETS": {"2023": 319581.0, "2024": 216604.0},
            "TOTAL_LIAB": {"2023": 266659.0, "2024": 284867.0},
        },
        "gates": {
            "issuer_type": "18a",
            "is_biotech_18a": True,
            "is_unprofitable": True,
            "continuous_net_loss": True,
            "latest_full_year_loss": True,
            "profitability_known": True,
            "profitability_status": "unprofitable",
            "skip_3_4": False,
        },
        "cash_burn": {
            "skipped": False,
            "CASH_RUNWAY_MONTHS": 20.21,
            "BURN_RATE_MONTHLY": 7423.75,
            "END_CASH": 150000.0,
        },
        "extracted": {"evidence": {}, "table_meta": {}},
        "finished": False,
    }
    out = asyncio.run(_tool_submit_finance_report({}, state))
    assert out["ok"] is True
    assert out.get("submit_recovered") is True
    report = state["final_report"]
    assert report.get("submit_recovered") is True
    assert report.get("dimensions")
    assert len(report["dimensions"]) == 4
    assert float(report.get("risk_score") or 0) > 0
    assert "submit_recovered" in " ".join(report.get("submit_warnings") or [])


def test_biotech_business_context_draft() -> None:
    dims = _draft_finance_dimensions(
        {
            "issuer_type": "18a",
            "metrics": {"NET_LOSS": {"2024": -1.0}, "CFO": {"2024": -1.0}},
            "gates": {
                "issuer_type": "18a",
                "is_biotech_18a": True,
                "is_unprofitable": True,
                "continuous_net_loss": True,
            },
            "cash_burn": {"CASH_RUNWAY_MONTHS": 20.0},
        }
    )
    biz = next(d for d in dims if d["dimension"] == "business_context")
    assert biz["status"] == "analyzed"
    assert "18A" in biz["analysis"] or "生物科技" in biz["analysis"]


def test_compose_dimensions_from_skills_enriches_analysis() -> None:
    state = {
        "issuer_type": "18a",
        "metrics": {
            "NET_LOSS": {"2024": -100.0},
            "CFO": {"2024": -50.0},
            "NET_ASSETS": {"2024": 200.0},
            "TOTAL_LIAB": {"2024": 80.0},
        },
        "gates": {
            "issuer_type": "18a",
            "is_biotech_18a": True,
            "is_unprofitable": True,
            "continuous_net_loss": True,
        },
        "cash_burn": {"CASH_RUNWAY_MONTHS": 18.0},
        "skill_results": {
            "finance_profitability": {
                "reasoning": "連續虧損擴大",
                "risk_points": [
                    {"code": "CONTINUOUS_LOSS", "description": "業績記錄期連續虧損"}
                ],
            },
            "finance_cash_flow": {
                "reasoning": "CFO 持續為負",
                "risk_points": [{"code": "CFO_NEGATIVE", "description": "經營現金流為負"}],
            },
            "finance_solvency": {"reasoning": "淨資產下降", "risk_points": []},
            "finance_business_context": {
                "reasoning": "18A 未商業化",
                "risk_points": [{"code": "PIPE_EARLY", "description": "管線早期"}],
            },
        },
        "rule_pack": {"risk_score": 75, "risk_level": "high", "score_breakdown": []},
    }
    dims = _compose_finance_dimensions_from_skills(state)
    assert len(dims) == 4
    profit = next(d for d in dims if d["dimension"] == "profitability_growth")
    assert "連續虧損擴大" in profit["analysis"]
    assert "CONTINUOUS_LOSS" in profit["analysis"]
    assert profit.get("source") == "skill+metrics"
    payload = _compose_finance_submit_payload(state, state["rule_pack"])
    assert payload["submit_composed_from_skills"] is True
    assert len(payload["dimensions"]) == 4
    assert "skill" in (payload["reasoning"] or "")


def test_submit_with_skills_marks_composed_not_empty_draft() -> None:
    state = {
        "doc_id": "hansiaitai",
        "issuer_type": "18a",
        "metrics": {
            "NET_LOSS": {"2023": -85160.0, "2024": -116922.0},
            "CFO": {"2023": -51994.0, "2024": -104894.0},
            "CASH_EQ": {"2025_i1": 150000.0},
            "END_CASH": {"2025_i1": 150000.0},
            "NET_ASSETS": {"2023": 319581.0, "2024": 216604.0},
            "TOTAL_LIAB": {"2023": 266659.0, "2024": 284867.0},
        },
        "gates": {
            "issuer_type": "18a",
            "is_biotech_18a": True,
            "is_unprofitable": True,
            "continuous_net_loss": True,
            "latest_full_year_loss": True,
            "profitability_known": True,
            "profitability_status": "unprofitable",
            "skip_3_4": False,
        },
        "cash_burn": {
            "skipped": False,
            "CASH_RUNWAY_MONTHS": 20.21,
            "BURN_RATE_MONTHLY": 7423.75,
            "END_CASH": 150000.0,
        },
        "extracted": {"evidence": {}, "table_meta": {}},
        "skill_results": {
            "finance_profitability": {
                "reasoning": "連續虧損",
                "risk_points": [
                    {"code": "CONTINUOUS_LOSS", "level": "high", "description": "連續虧損"}
                ],
                "negative_findings": [],
            },
            "finance_cash_flow": {
                "reasoning": "CFO 負",
                "risk_points": [
                    {"code": "CFO_NEGATIVE", "level": "high", "description": "CFO 負"}
                ],
            },
            "finance_solvency": {"reasoning": "負債上升", "risk_points": []},
            "finance_business_context": {
                "reasoning": "18A",
                "risk_points": [{"code": "CTX", "description": "未商業化"}],
            },
        },
        "rule_pack": {
            "risk_score": 75.0,
            "risk_level": "high",
            "score_breakdown": [{"code": "CONTINUOUS_LOSS", "delta": 25}],
            "risk_points": [],
            "negative_findings": [],
        },
        "finished": False,
    }
    payload = _compose_finance_submit_payload(state, state["rule_pack"])
    out = asyncio.run(_tool_submit_finance_report(payload, state))
    assert out["ok"] is True
    report = state["final_report"]
    assert report.get("submit_composed_from_skills") is True
    assert len(report.get("dimensions") or []) == 4
    assert "連續虧損" in (report.get("dimensions") or [])[0].get("analysis", "")


def test_resolve_think_from_content() -> None:
    from src.agents.react_loop import _resolve_think_status

    st, proxy = _resolve_think_status(None, "先检索主表", [{"arguments": {"reason": "x"}}])
    assert st == "think_from_content"
    assert proxy == "先检索主表"
    st2, _ = _resolve_think_status(None, "", [{"arguments": {"reason": "定位损益表"}}])
    assert st2 == "think_from_content"
    st3, _ = _resolve_think_status(None, "", [{"arguments": {}}])
    assert st3 == "reasoning_missing"
    st4, _ = _resolve_think_status("有思考", "", [])
    assert st4 == "ok"


def test_theme_merge_dedupes_llm_and_rules() -> None:
    """PROFIT_001/CASHFLOW_001/CASH_RUNWAY 与规则同主题不去双计；跑道用规则档 +10。"""
    state: dict[str, Any] = {
        "metrics": {
            "NET_LOSS": {"2023": -1.0, "2024": -2.0},
            "CFO": {"2023": -1.0, "2024": -2.0},
        },
        "gates": {
            "is_unprofitable": True,
            "continuous_net_loss": True,
            "latest_full_year_loss": True,
            "skip_3_4": False,
            "issuer_type": "18a",
        },
        "cash_burn": {
            "skipped": False,
            "CASH_RUNWAY_MONTHS": 20.21,
            "END_CASH": 150000.0,
        },
        "extracted": {
            "evidence": {
                "TBL_IS": [
                    {
                        "page": 562,
                        "excerpt": "虧損",
                        "source_type": "text",
                        "field_code": "TBL_IS",
                        "confidence": 1.0,
                    }
                ],
                "TBL_CF": [
                    {
                        "page": 569,
                        "excerpt": "現金流",
                        "source_type": "table",
                        "field_code": "TBL_CF",
                        "confidence": 1.0,
                    }
                ],
                "TBL_BS": [
                    {
                        "page": 563,
                        "excerpt": "現金",
                        "source_type": "text",
                        "field_code": "TBL_BS",
                        "confidence": 1.0,
                    }
                ],
            },
            "table_meta": {},
        },
    }
    report = {
        "risk_score": 85.0,
        "risk_level": "high",
        "score_breakdown": [
            {"code": "PROFIT_001", "delta": 30, "rule_ref": "連續虧損且擴大"},
            {"code": "CASHFLOW_001", "delta": 25, "rule_ref": "經營現金流持續為負"},
            {"code": "CASH_RUNWAY", "delta": 20, "rule_ref": "現金跑道不足"},
            {"code": "REV_NONCORE", "delta": 10, "rule_ref": "收入非產品收入"},
        ],
    }
    warnings: list[str] = []
    _merge_rules_floor(report, state, warnings)
    codes = {str(b.get("code") or "") for b in report["score_breakdown"]}
    assert "CONTINUOUS_LOSS" in codes
    assert "CFO_NEGATIVE" in codes
    assert "CASH_RUNWAY_12_24" in codes
    assert "PROFIT_001" not in codes
    assert "CASHFLOW_001" not in codes
    # 无双计：不应同时存在同主题两行
    assert sum(1 for c in codes if c == "CONTINUOUS_LOSS") == 1
    runway = next(b for b in report["score_breakdown"] if b["code"] == "CASH_RUNWAY_12_24")
    assert float(runway["delta"]) == 10.0  # 规则档，非 LLM+20
    final = float(report["risk_score"])
    assert final < 100.0
    assert 50.0 <= final <= 80.0  # 25/30 + 15/25 + 10 + 10(other)
    assert report["rules_floor"].get("theme_merge") is True


def test_canonical_runway_and_profit_codes() -> None:
    state = {"cash_burn": {"skipped": False, "CASH_RUNWAY_MONTHS": 20.0}}
    assert _canonical_score_code("PROFIT_001", state) == "CONTINUOUS_LOSS"
    assert _canonical_score_code("CASHFLOW_001", state) == "CFO_NEGATIVE"
    assert _canonical_score_code("CASH_RUNWAY", state) == "CASH_RUNWAY_12_24"
    state_lt = {"cash_burn": {"skipped": False, "CASH_RUNWAY_MONTHS": 8.0}}
    assert _canonical_score_code("SHORT_CASH_RUNWAY", state_lt) == "CASH_RUNWAY_LT_12"


def test_split_section_hints() -> None:
    assert _split_section_hints("business/industry/financing") == [
        "business",
        "industry",
        "financing",
    ]
    assert _split_section_hints("financial_information,risk_factors") == [
        "financial_information",
        "risk_factors",
    ]


class _FakeSpan:
    def __init__(self, sid: str) -> None:
        self.canonical_section = sid
        self.display_title = sid
        self.start_page = 1
        self.end_page = 2
        self.confidence = 0.9


class _FakeSectionMap:
    def __init__(self, known: set[str]) -> None:
        self._known = known

    def span_for(self, section_id: str) -> _FakeSpan | None:
        if section_id in self._known:
            return _FakeSpan(section_id)
        return None


def test_resolve_sections_splits_slash_hint() -> None:
    sm = _FakeSectionMap({"business", "risk_factors", "summary"})
    out = resolve_sections(
        intent="business_context",
        section_map=sm,
        section_hint="business/industry/financing",
    )
    assert any(x["section_id"] == "business" for x in out)


def test_resolve_sections_fallback_when_hint_all_invalid() -> None:
    sm = _FakeSectionMap({"business", "risk_factors", "summary"})
    out = resolve_sections(
        intent="business_context",
        section_map=sm,
        section_hint="industry/financing",
    )
    ids = {x["section_id"] for x in out}
    assert "business" in ids or "risk_factors" in ids or "summary" in ids


def test_burn_yoy_full_or_interim() -> None:
    """全年翻倍、中期略降 → 仍触发；纯中期加速亦触发。"""
    gates = {"skip_3_4": False, "is_unprofitable": True}
    hans = {
        "CFO": {
            "2023": -51994.0,
            "2024": -104894.0,
            "2024_i1": -67918.0,
            "2025_i1": -59390.0,
        },
        "CASH_EQ": {"2025_i1": 150000.0},
        "END_CASH": {"2025_i1": 150000.0},
    }
    cb = compute_cash_burn(hans, gates)
    assert cb["burn_yoy_up_gt_30"] is True
    assert cb["burn_yoy_basis"] == "full"
    assert float(cb["burn_yoy_growth_full"] or 0) > 0.30

    interim_only = {
        "CFO": {"2024_i1": -100.0, "2025_i1": -160.0},
        "CASH_EQ": {"2025_i1": 1000.0},
        "END_CASH": {"2025_i1": 1000.0},
    }
    cb2 = compute_cash_burn(interim_only, gates)
    assert cb2["burn_yoy_up_gt_30"] is True
    assert cb2["burn_yoy_basis"] in {"interim", "both"}


def test_cv_pref_liability_flag() -> None:
    assert cv_pref_material(
        {
            "CV_PREF": {"2024": 131564.0, "2025_i1": 138481.0},
            "TOTAL_ASSETS": {"2025_i1": 444298.0},
            "CASH_EQ": {"2025_i1": 150000.0},
        }
    )
    assert not cv_pref_material({"CV_PREF": {"2024": 0.0}, "TOTAL_ASSETS": {"2024": 100.0}})
    assert _canonical_score_code("OTHER_SOLVENCY_RISK", {}) == "CV_PREF_LIABILITY"
    assert _canonical_score_code("PREFERRED_LIABILITY", {}) == "CV_PREF_LIABILITY"


def test_theme_merge_keeps_metric_value() -> None:
    state: dict[str, Any] = {
        "metrics": {
            "NET_LOSS": {"2023": -1.0, "2024": -2.0},
            "CFO": {"2023": -1.0, "2024": -2.0},
        },
        "gates": {
            "is_unprofitable": True,
            "continuous_net_loss": True,
            "latest_full_year_loss": True,
            "skip_3_4": False,
        },
        "cash_burn": {"skipped": False, "CASH_RUNWAY_MONTHS": 20.0, "END_CASH": 100.0},
        "extracted": {
            "evidence": {
                "TBL_IS": [
                    {
                        "page": 1,
                        "excerpt": "loss",
                        "source_type": "text",
                        "field_code": "TBL_IS",
                        "confidence": 1.0,
                    }
                ],
                "TBL_CF": [
                    {
                        "page": 2,
                        "excerpt": "cfo",
                        "source_type": "table",
                        "field_code": "TBL_CF",
                        "confidence": 1.0,
                    }
                ],
                "TBL_BS": [
                    {
                        "page": 3,
                        "excerpt": "cash",
                        "source_type": "text",
                        "field_code": "TBL_BS",
                        "confidence": 1.0,
                    }
                ],
            },
            "table_meta": {},
        },
    }
    report = {
        "risk_score": 50.0,
        "score_breakdown": [
            {
                "code": "CONTINUOUS_LOSS",
                "delta": 25,
                "metric_value": "NET_LOSS 2024=-2",
                "evidence_page": 562,
                "note": "连续亏损",
            },
            {
                "code": "CFO_NEGATIVE",
                "delta": 15,
                "metric_value": "CFO 2024=-2",
                "evidence_page": 569,
            },
        ],
    }
    warnings: list[str] = []
    _merge_rules_floor(report, state, warnings)
    loss = next(b for b in report["score_breakdown"] if b["code"] == "CONTINUOUS_LOSS")
    assert loss.get("metric_value") == "NET_LOSS 2024=-2"
    assert loss.get("evidence_page") == 562


def test_sanitize_negative_findings() -> None:
    report = {
        "risk_score": 55.0,
        "score_breakdown": [
            {"code": "CONTINUOUS_LOSS", "delta": 25},
            {"code": "CFO_NEGATIVE", "delta": 15},
        ],
        "negative_findings": [
            {"code": "CONTINUOUS_LOSS", "description": "连续亏损", "rule_ref": "x"},
            {"code": "CFO_POSITIVE", "description": "经营现金流为正", "rule_ref": "doc§2.3"},
        ],
        "rules_floor": {"flags": {}},
    }
    warnings: list[str] = []
    _sanitize_negative_findings(report, {}, warnings)
    codes = {x.get("code") for x in report["negative_findings"]}
    assert "CONTINUOUS_LOSS" not in codes
    assert "CFO_POSITIVE" in codes
    assert any("negative_findings_dropped" in w for w in warnings)


def test_diversify_section_hits_page_and_section() -> None:
    hits = [
        {
            "page": 80,
            "source_type": "text",
            "score": 4.3,
            "section_id": "risk_factors",
            "excerpt": "经营现金流" + ("a" * 100),
        },
        {
            "page": 80,
            "source_type": "text",
            "score": 4.2,
            "section_id": "risk_factors",
            "excerpt": "流动负债净额" + ("b" * 100),
        },
        {
            "page": 498,
            "source_type": "text",
            "score": 4.1,
            "section_id": "financial_information",
            "excerpt": "融资需求" + ("c" * 100),
        },
        {
            "page": 498,
            "source_type": "text",
            "score": 3.1,
            "section_id": "financial_information",
            "excerpt": "管理现金" + ("d" * 100),
        },
    ]
    out = diversify_section_hits(hits, top_k=5)
    pages = [h["page"] for h in out]
    assert pages.count(80) == 1
    assert pages.count(498) == 1
    assert {h["section_id"] for h in out} >= {"risk_factors", "financial_information"}
