"""财务 Skill / dossier / standalone 补证单测。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.models.debate import load_dossier  # noqa: E402
from src.skills.base import SkillInput  # noqa: E402
from src.skills.evidence_utils import compact_hits, dedupe_hits, normalize_query_record  # noqa: E402
from src.skills.finance_presets import (  # noqa: E402
    FINANCE_SKILL_NAMES,
    FinanceSkill,
    build_finance_skills,
)
from src.skills.finance_toolbox import (  # noqa: E402
    build_finance_debate_dossier,
    search_finance_evidence_standalone,
    _tool_run_finance_skill,
    _tool_submit_finance_report,
)


def _metrics_unprofitable() -> dict[str, Any]:
    return {
        "NET_LOSS": {"2022": -10.0, "2023": -20.0, "2024": -15.0},
        "GP_MARGIN": {"2022": 40.0, "2023": 38.0, "2024": 30.0},
        "CFO": {"2022": -5.0, "2023": -8.0, "2024": -6.0},
        "CASH_EQ": {"2024": 100.0},
        "END_CASH": {"2024": 100.0},
        "TOTAL_ASSETS": {"2024": 500.0},
        "CV_PREF": {"2024": 80.0},
    }


def _ev(page: int, excerpt: str) -> list[dict[str, Any]]:
    return [{"page": page, "excerpt": excerpt, "source_type": "table"}]


def _base_state(**over: Any) -> dict[str, Any]:
    metrics = _metrics_unprofitable()
    extracted = {
        "evidence": {
            "TBL_IS": _ev(200, "合併損益表…"),
            "TBL_BS": _ev(210, "合併財務狀況表…"),
            "TBL_CF": _ev(220, "合併現金流量表…"),
        },
        "table_meta": {
            "TBL_IS": {"page": 200, "excerpt": "合併損益表…", "source_type": "table"},
            "TBL_BS": {"page": 210, "excerpt": "合併財務狀況表…", "source_type": "table"},
            "TBL_CF": {"page": 220, "excerpt": "合併現金流量表…", "source_type": "table"},
        },
    }
    state: dict[str, Any] = {
        "doc_id": "test_fin",
        "doc_name": "测试财务公司",
        "issuer_type": "18a",
        "client_project_id": "proj_x",
        "task_id": "task_y",
        "analysis_id": "ana_z",
        "metrics": metrics,
        "gates": {
            "issuer_type": "18a",
            "is_biotech_18a": True,
            "is_unprofitable": True,
            "continuous_net_loss": True,
            "latest_full_year_loss": True,
            "skip_3_4": False,
        },
        "cash_burn": {
            "skipped": False,
            "CASH_RUNWAY_MONTHS": 8,
            "burn_yoy_up_gt_30": True,
            "END_CASH": 100.0,
        },
        "extracted": extracted,
        "skill_results": {},
        "queries_used": [],
        "finished": False,
    }
    state.update(over)
    return state


def test_finance_skill_meta_and_names() -> None:
    assert len(FINANCE_SKILL_NAMES) == 4
    skills = build_finance_skills()
    for name in FINANCE_SKILL_NAMES:
        meta = skills[name].meta()
        assert meta["skill"] == name
        assert meta["risk_codes"] or name == "finance_business_context"


def test_profitability_skill_rule_points() -> None:
    state = _base_state()
    skill = FinanceSkill("finance_profitability")
    out = asyncio.run(
        skill.execute(SkillInput(doc_id="test_fin", params={"state": state}))
    )
    assert out.success
    codes = {str(p.get("code")) for p in out.data["risk_points"]}
    assert "CONTINUOUS_LOSS" in codes or "GP_MARGIN_DROP" in codes
    assert out.data["skill"] == "finance_profitability"


def test_solvency_skill_cv_pref() -> None:
    state = _base_state()
    skill = FinanceSkill("finance_solvency")
    out = asyncio.run(
        skill.execute(SkillInput(doc_id="test_fin", params={"state": state}))
    )
    assert out.success
    codes = {str(p.get("code")) for p in out.data["risk_points"]}
    assert "CV_PREF_LIABILITY" in codes


def test_run_finance_skill_tool() -> None:
    state = _base_state()
    out = asyncio.run(
        _tool_run_finance_skill({"skill_name": "finance_cash_flow"}, state)
    )
    assert out["ok"] is True
    assert "finance_cash_flow" in state["skill_results"]
    assert out["risk_point_count"] >= 1


def test_finance_dossier_persist(tmp_path: Path) -> None:
    state = _base_state(debate_dir=tmp_path)
    # 先跑 skill 填充
    asyncio.run(_tool_run_finance_skill({"skill_name": "finance_profitability"}, state))
    asyncio.run(_tool_run_finance_skill({"skill_name": "finance_cash_flow"}, state))
    asyncio.run(_tool_run_finance_skill({"skill_name": "finance_solvency"}, state))
    asyncio.run(
        _tool_run_finance_skill({"skill_name": "finance_business_context"}, state)
    )
    out = asyncio.run(
        _tool_submit_finance_report(
            {
                "risk_score": 50,
                "risk_level": "medium",
                "score_breakdown": [],
                "risk_points": [],
                "negative_findings": [],
                "dimensions": [
                    {
                        "dimension": "profitability_growth",
                        "analysis": "連續虧損需關注",
                    }
                ],
                "reasoning": "測試",
                "summary": "測試摘要",
            },
            state,
        )
    )
    assert out["ok"] is True
    assert out.get("debate_dossier_path")
    path = Path(out["debate_dossier_path"])
    assert path.is_file()
    dossier = load_dossier(path)
    assert dossier.agent == "finance"
    assert dossier.doc_id == "test_fin"
    assert dossier.client_project_id == "proj_x"
    assert dossier.task_id == "task_y"
    assert dossier.analysis_id == "ana_z"
    assert dossier.claims
    assert any(c.skill for c in dossier.claims)


def test_build_finance_debate_dossier_ids() -> None:
    state = _base_state()
    report = {
        "risk_score": 40,
        "risk_level": "medium",
        "summary": "s",
        "reasoning": "r",
        "risk_points": [
            {
                "code": "CONTINUOUS_LOSS",
                "level": "high",
                "description": "連續虧損",
                "evidence_page": 200,
                "skill": "finance_profitability",
            }
        ],
        "score_breakdown": [
            {"code": "CFO_NEGATIVE", "delta": 15, "note": "CFO負", "evidence_page": 220}
        ],
        "negative_findings": [],
        "dimensions": [],
    }
    dossier = build_finance_debate_dossier(state, report)
    assert dossier.client_project_id == "proj_x"
    codes = {c.code for c in dossier.claims}
    assert "CONTINUOUS_LOSS" in codes
    assert "CFO_NEGATIVE" in codes


def test_search_finance_standalone() -> None:
    async def _fake_retrieve(**kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "hits": [
                {"page": 11, "excerpt": "融資需求……", "source_type": "text", "score": 0.9}
            ],
        }

    with patch(
        "src.skills.finance_toolbox.retrieve_section_evidence",
        new=AsyncMock(side_effect=_fake_retrieve),
    ):
        out = asyncio.run(
            search_finance_evidence_standalone(
                doc_id="test_fin",
                query="融資 資金需求",
                intent="financing_dependency",
                parse_json="/tmp/fake.json",
            )
        )
    assert out["ok"] is True
    assert out["n"] == 1
    assert out["query_record"]["tool"] == "search_finance_evidence_standalone"


def test_evidence_utils_compact_and_dedupe() -> None:
    hits = [
        {"page": 1, "excerpt": "aaaa" * 50, "source_type": "text"},
        {"page": 1, "excerpt": "aaaa" * 50, "source_type": "text"},
        {"page": 2, "excerpt": "bbbb", "source_type": "table"},
    ]
    d = dedupe_hits(hits)
    assert len(d) == 2
    c = compact_hits(d, excerpt_chars=10)
    assert len(c[0]["excerpt"]) <= 10
    rec = normalize_query_record(
        tool="search_finance_evidence",
        intent="business_context",
        query="加盟",
        hits=2,
        pages={3, 1},
        skill="finance_business_context",
    )
    assert rec["pages"] == [1, 3]
    assert rec["skill"] == "finance_business_context"
