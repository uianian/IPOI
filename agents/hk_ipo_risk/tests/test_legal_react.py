"""法务 ReAct 单测：submit 校验、规则托底合并、辩论素材包、skill prompt/阈值。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.llm.prompts import LEGAL_SKILL_EXTRACTION_PROMPTS  # noqa: E402
from src.models.debate import DebateDossier, load_dossier  # noqa: E402
from src.skills.legal_presets import LEGAL_SKILL_NAMES, LegalSkill, build_legal_skills  # noqa: E402
from src.skills.legal_toolbox import (  # noqa: E402
    _merge_legal_rules_floor,
    _tool_submit_legal_report,
    build_legal_debate_dossier,
)


def _base_state(**over: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "doc_id": "test_doc",
        "doc_name": "测试公司",
        "issuer_type": "18a",
        "gates": {"issuer_type": "18a", "is_biotech_18a": True, "skip_3_5": False},
        "bundle": {"evidence_by_field": {}},
        "extra_hits": [],
        "skill_results": {
            "legal_shareholder_rights": {
                "exists": True,
                "confidence": "medium",
                "features": {"exists_redemption": True},
                "reasoning": "优先股赎回条款于 p120 有明确披露。",
                "risk_points": [
                    {
                        "code": "REDEMPTION_MEDIUM",
                        "level": "medium",
                        "confidence": "medium",
                        "description": "存在優先股贖回條款",
                        "evidence_page": 120,
                        "evidence_excerpt": "若未能如期上市，优先股股东有权要求公司赎回股份",
                        "skill": "legal_shareholder_rights",
                    }
                ],
                "negative_findings": [],
                "evidence": [
                    {"page": 120, "excerpt": "赎回条款……", "source_type": "text",
                     "field_code": "legal_shareholder_rights", "confidence": 0.8},
                    {"page": 121, "excerpt": "特別權利……", "source_type": "text",
                     "field_code": "legal_shareholder_rights", "confidence": 0.6},
                ],
                "queries_used": [{"tool": "retrieve_section_evidence", "query": "贖回權", "hits": 2}],
            },
        },
        "queries_used": [
            {"tool": "retrieve_section_evidence", "query": "贖回權", "hits": 2,
             "skill": "legal_shareholder_rights"},
        ],
        "rule_pack": {
            "risk_score": 18.0,
            "risk_level": "very_low",
            "score_breakdown": [
                {"code": "REDEMPTION_DISCLOSURE", "delta": 18, "rule_ref": "doc§3.1",
                 "note": "存在赎回/优先股相关披露", "evidence": [{"page": 120, "excerpt": "x"}]},
            ],
            "risk_points": [],
            "flags": {"redemption_medium": True},
        },
        "finished": False,
    }
    state.update(over)
    return state


def test_submit_rejects_missing_evidence(tmp_path: Path) -> None:
    """无 skill 背书且页码不可核实的风险点：第一次拒绝，第二次降级接受。"""
    state = _base_state(debate_dir=tmp_path)
    args = {
        "risk_points": [
            {"code": "MADE_UP_RISK", "level": "high", "description": "臆造", "evidence_page": 999},
        ],
        "reasoning": "r",
        "summary": "s",
    }
    out1 = asyncio.run(_tool_submit_legal_report(dict(args), state))
    assert out1["ok"] is False
    assert "MADE_UP_RISK" in out1["error"]
    assert not state.get("finished")

    out2 = asyncio.run(_tool_submit_legal_report(dict(args), state))
    assert out2["ok"] is True
    report = state["final_report"]
    made_up = [p for p in report["risk_points"] if p["code"] == "MADE_UP_RISK"]
    assert made_up and made_up[0]["level"] != "high"  # high 已降级
    assert any("unverified_points_accepted" in w for w in report["submit_warnings"])


def test_submit_merges_rules_floor_and_dossier(tmp_path: Path) -> None:
    state = _base_state(debate_dir=tmp_path)
    # 规则包改为实质赎回项，避免披露被同主题 LLM 实质点隔离后分数塌陷
    state["rule_pack"] = {
        "risk_score": 25.0,
        "risk_level": "low",
        "score_breakdown": [
            {
                "code": "REDEMPTION_HIGH",
                "delta": 25,
                "rule_ref": "doc§3.1",
                "note": "赎回条款高风险",
                "evidence": [{"page": 120, "excerpt": "x"}],
            },
        ],
        "risk_points": [],
        "flags": {"redemption_high": True},
    }
    args = {
        "risk_points": [
            {
                "code": "REDEMPTION_MEDIUM",
                "level": "medium",
                "point_kind": "issuer_specific",
                "description": "優先股贖回條款於2024年終止購回（LLM 覆核）",
                "evidence_page": 120,
                "skill": "legal_shareholder_rights",
            },
        ],
        "negative_findings": [{"code": "GOV_OK", "description": "治理結構未見異常"}],
        "reasoning": "推理链",
        "summary": "存在贖回條款，整體法務風險可控",
    }
    out = asyncio.run(_tool_submit_legal_report(args, state))
    assert out["ok"] and out["finished"]
    report = state["final_report"]
    # 主题归并：redemption 规则实质 25 vs LLM medium 8 → 取 max=25
    redemption_items = [
        b for b in report["score_breakdown"] if b["theme"] == "redemption"
    ]
    assert len(redemption_items) == 1
    assert float(redemption_items[0]["delta"]) == 25.0
    assert report["risk_score"] >= 25.0
    assert report["scoring_mode"] == "react+rules_floor"
    # dossier 落盘且可回读
    path = report.get("debate_dossier_path")
    assert path and Path(path).is_file()
    dossier = load_dossier(path)
    assert isinstance(dossier, DebateDossier)
    assert dossier.agent == "legal"
    assert dossier.claims, "claims 不应为空"
    claim = dossier.claims[0]
    assert claim.evidence_refs and claim.evidence_refs[0].page == 120
    assert claim.retrieval_queries, "claim 应携带补证据检索方式"
    assert dossier.retrieval_queries


def test_rules_floor_never_below_substantive_rules_score() -> None:
    rules_pack = {
        "risk_score": 43.0,  # 含披露；托底只看实质 25
        "score_breakdown": [
            {"code": "REDEMPTION_HIGH", "delta": 25, "rule_ref": "doc§3.1"},
            {"code": "RELATED_PARTY_DISCLOSURE", "delta": 18, "rule_ref": "doc§3.2"},
        ],
        "flags": {},
    }
    warnings: list[str] = []
    points = [{"code": "LITIGATION_PENDING", "level": "low", "confidence": "low"}]
    floor = _merge_legal_rules_floor(points, rules_pack, warnings)
    assert floor["risk_score"] >= 25.0
    assert floor["rules_floor"]["rules_substantive_score"] == 25.0
    codes = {b["code"] for b in floor["score_breakdown"]}
    assert "REDEMPTION_HIGH" in codes
    # 关联披露：无同主题实质项时可保留；诉讼 low/structural 会占 litigation 主题
    assert "RELATED_PARTY_DISCLOSURE" in codes


def test_hansiai_like_score_lands_medium() -> None:
    """翰思型：结构关注 + 无重大事件；样板/披露不计满，饱和聚合落 medium。"""
    rules_pack = {
        "risk_score": 51.0,
        "score_breakdown": [
            {"code": "REDEMPTION_DISCLOSURE", "delta": 18, "rule_ref": "doc§3.1"},
            {"code": "RELATED_PARTY_DISCLOSURE", "delta": 15, "rule_ref": "doc§3.2"},
            {"code": "REGULATORY_DISCLOSURE", "delta": 18, "rule_ref": "doc§3.x"},
        ],
        "flags": {},
    }
    points = [
        {
            "code": "RIGHTS_CLEANUP_INCOMPLETE",
            "level": "high",
            "point_kind": "issuer_specific",
            "description": "特別權利於上市前終止購回尚未完整清理",
            "confidence": "medium",
        },
        {
            "code": "REDEMPTION_HIGH",
            "level": "high",
            "point_kind": "issuer_specific",
            "description": "優先股贖回條款金額人民幣1億元",
            "confidence": "medium",
        },
        {
            "code": "GOVERNANCE_CONTROL_GT_50",
            "level": "medium",
            "point_kind": "structural",
            "description": "控股股東合計持股約62%",
            "confidence": "medium",
        },
        {
            "code": "IP_LICENSE_DEPENDENCY",
            "level": "medium",
            "point_kind": "issuer_specific",
            "description": "核心專利授權依賴第三方框架協議",
            "confidence": "medium",
        },
        {
            # 轻量实质项：挡住同主题披露基线，本身只贡献 low delta
            "code": "RELATED_PARTY_REVIEWED",
            "level": "low",
            "point_kind": "issuer_specific",
            "description": "關連交易框架協議已按上市規則披露，金額人民幣200萬",
            "confidence": "medium",
        },
        {
            "code": "HEALTHCARE_LICENSE_STRUCTURAL",
            "level": "medium",
            "point_kind": "structural",
            "description": "醫療器械經營許可為行業常規准入",
            "confidence": "medium",
        },
        {
            "code": "REGULATORY_INVESTIGATION",
            "level": "high",
            "point_kind": "boilerplate",
            "description": "任何調查均可能產生負面影響，公司受虛假索賠法約束",
            "confidence": "medium",
        },
        {
            "code": "LITIGATION_ABSENT",
            "level": "low",
            "point_kind": "benign_negative",
            "description": "概未牽涉任何重大訴訟或仲裁",
            "confidence": "high",
        },
    ]
    warnings: list[str] = []
    floor = _merge_legal_rules_floor(points, rules_pack, warnings)
    codes = {b["code"] for b in floor["score_breakdown"]}
    assert "REGULATORY_INVESTIGATION" not in codes
    assert "LITIGATION_ABSENT" not in codes
    # 同主题已有实质项 → 三披露均不计
    assert "REDEMPTION_DISCLOSURE" not in codes
    assert "RELATED_PARTY_DISCLOSURE" not in codes
    assert "REGULATORY_DISCLOSURE" not in codes
    assert 35.0 <= float(floor["risk_score"]) <= 65.0
    assert floor["risk_level"] == "medium"


def test_substantive_rules_floor_without_llm() -> None:
    rules_pack = {
        "risk_score": 25.0,
        "score_breakdown": [{"code": "REDEMPTION_HIGH", "delta": 25, "rule_ref": "doc§3.1"}],
        "flags": {},
    }
    floor = _merge_legal_rules_floor([], rules_pack, [])
    assert float(floor["risk_score"]) == 25.0
    assert floor["risk_level"] in {"low", "medium"}


def test_benign_litigation_absent_adds_zero() -> None:
    rules_pack = {"risk_score": 0.0, "score_breakdown": [], "flags": {}}
    points = [
        {
            "code": "LITIGATION_ABSENT",
            "level": "low",
            "description": "公司未涉及任何重大訴訟",
        }
    ]
    floor = _merge_legal_rules_floor(points, rules_pack, [])
    assert float(floor["risk_score"]) == 0.0
    assert floor["score_breakdown"] == []


def test_skill_prompts_format() -> None:
    assert set(LEGAL_SKILL_EXTRACTION_PROMPTS) == set(LEGAL_SKILL_NAMES)
    for name, tpl in LEGAL_SKILL_EXTRACTION_PROMPTS.items():
        text = tpl.format(evidence_text="[p12] 示例原文")
        assert "[p12] 示例原文" in text
        assert '"skill"' in text and name in text
        assert "evidence_page" in text


def test_skill_threshold_and_validation() -> None:
    skills = build_legal_skills()
    assert set(skills) == set(LEGAL_SKILL_NAMES)
    skill = skills["legal_related_party"]
    assert isinstance(skill, LegalSkill)
    hits = [
        {"page": 88, "excerpt": "關連交易佔比 45%", "score": 1.0},
        {"page": 89, "excerpt": "持續關連交易協議", "score": 0.9},
    ]
    # 页码臆造 → 降级；LLM 漏报阈值风险 → 自动补 RELATED_PARTY_HIGH
    points = skill._validate_points(
        [{"code": "RELATED_PARTY_UNFAIR", "level": "high", "evidence_page": 777}],
        hits,
    )
    assert points[0]["evidence_page"] is None
    assert points[0]["level"] != "high"
    points = skill._threshold_checks({"max_ratio_pct": 45}, points, hits)
    codes = {p["code"] for p in points}
    assert "RELATED_PARTY_HIGH" in codes
    auto = next(p for p in points if p["code"] == "RELATED_PARTY_HIGH")
    assert auto["evidence_page"] == 88
    # meta 可序列化（可移植 skill 元数据）
    meta = skill.meta()
    assert meta["skill"] == "legal_related_party"
    assert meta["risk_codes"] and meta["queries"]


def test_governance_threshold() -> None:
    skill = LegalSkill("legal_governance")
    hits = [{"page": 55, "excerpt": "控股股東合計持股 62%", "score": 1.0}]
    points = skill._threshold_checks({"control_pct": 62}, [], hits)
    assert any(p["code"] == "GOVERNANCE_CONTROL_GT_50" for p in points)


def test_auto_submit_from_skill_state(tmp_path: Path) -> None:
    """模拟 max_turns 耗尽后，用 skill_results 强制 submit 并落盘 dossier。"""
    from src.agents.legal_agent import LegalAgent
    from src.skills.legal_toolbox import build_legal_tool_registry

    agent = LegalAgent(react=True)
    tools = build_legal_tool_registry()
    state = _base_state(debate_dir=tmp_path)
    # 再放一个 skill，满足 auto_submit 的 ≥2 skill 门槛
    state["skill_results"]["legal_governance"] = {
        "exists": True,
        "confidence": "medium",
        "features": {"control_pct": 55},
        "reasoning": "控股比例偏高。",
        "risk_points": [
            {
                "code": "GOVERNANCE_CONTROL_GT_50",
                "level": "medium",
                "confidence": "medium",
                "description": "控股比例 >50%",
                "evidence_page": 80,
                "evidence_excerpt": "控股股東持股約55%",
                "skill": "legal_governance",
            }
        ],
        "negative_findings": [],
        "evidence": [{"page": 80, "excerpt": "控股股東持股約55%", "source_type": "text"}],
        "queries_used": [],
    }
    ok = asyncio.run(agent._auto_submit_if_ready(state, tools, reason="max_turns_exceeded"))
    assert ok is True
    report = state["final_report"]
    assert report["scoring_mode"] == "react+rules_floor"
    assert any("auto_submit" in w for w in report["submit_warnings"])
    assert Path(report["debate_dossier_path"]).is_file()


def test_search_quota_blocks_when_exhausted() -> None:
    from src.skills.legal_toolbox import _tool_search_legal_evidence

    state = {
        "doc_id": "x",
        "search_quota": 2,
        "search_used": 2,
        "bundle": {"evidence_by_field": {}},
        "extra_hits": [],
        "skill_results": {},
        "gates": {},
    }
    out = asyncio.run(_tool_search_legal_evidence({"query": "贖回", "intent": "redemption"}, state))
    assert out["ok"] is False
    assert "配额" in str(out.get("error") or "")


def test_governance_control_forced_structural() -> None:
    """GOVERNANCE_CONTROL_GT_50 强制 structural，忽略模型 issuer_specific。"""
    from src.skills.legal_point_kind import classify_legal_point_kind

    kind = classify_legal_point_kind(
        {
            "code": "GOVERNANCE_CONTROL_GT_50",
            "point_kind": "issuer_specific",
            "description": "控股股東集團持股約55.89%，超過50%",
            "evidence_excerpt": "持股約55.89%",
        }
    )
    assert kind == "structural"


def test_rule_checks_ready_to_submit_when_no_gaps() -> None:
    """无 coverage_hints 且 5 skill 齐全 → ready_to_submit。"""
    from src.skills.legal_toolbox import _tool_run_rule_checks

    skills = {
        name: {
            "exists": True,
            "risk_points": [{"code": f"X_{i}", "level": "low", "description": "x", "evidence_page": 1}],
            "negative_findings": [],
            "evidence": [{"page": 1}],
        }
        for i, name in enumerate(
            [
                "legal_governance",
                "legal_shareholder_rights",
                "legal_related_party",
                "legal_contracts_and_ip",
                "legal_regulatory_litigation",
            ]
        )
    }
    state = {
        "doc_id": "hansiaitai",
        "issuer_type": "18a",
        "gates": {"issuer_type": "18a", "is_biotech_18a": True, "skip_3_5": False},
        "bundle": {"evidence_by_field": {}},
        "extra_hits": [],
        "skill_results": skills,
        "search_used": 0,
        "search_quota": 2,
    }
    out = asyncio.run(_tool_run_rule_checks({"reason": "test"}, state))
    assert out["ok"] is True
    assert out.get("coverage_hints") == []
    assert out.get("ready_to_submit") is True
    assert state.get("ready_to_submit") is True
    assert out.get("prefer_llm_submit") is True
    assert state.get("prefer_llm_submit") is True


def test_submit_fills_empty_risk_points_from_skills(tmp_path: Path) -> None:
    """模型 submit 空 risk_points 时用 skill_results 填充。"""
    state = _base_state(debate_dir=tmp_path)
    out = asyncio.run(
        _tool_submit_legal_report(
            {"summary": "測試交卷", "reasoning": "測試", "risk_points": []},
            state,
        )
    )
    assert out["ok"] is True
    assert state["finished"] is True
    assert any(
        "skill_results_filled_empty_submit" in w
        for w in (state["final_report"].get("submit_warnings") or [])
    )
    assert any(
        p.get("code") == "REDEMPTION_MEDIUM"
        for p in state["final_report"].get("risk_points") or []
    )


def test_report_reads_legal_sections_from_rule_features() -> None:
    sys.path.insert(0, str(PKG_ROOT / "scripts"))
    from generate_analysis_report import _legal_section_feat, build_legal_report  # noqa: E402

    legal = {
        "risk_score": 50,
        "risk_level": "medium",
        "score_breakdown": [],
        "features": {
            "rule_features": {
                "3.1": {
                    "exists": True,
                    "evidence_strength": "high",
                    "redemption_high": True,
                    "evidence": [{"page": 120, "excerpt": "赎回", "source_type": "text"}],
                },
                "3.2": {"exists": True, "ratio_pct": 12.5, "evidence_strength": "medium"},
                "3.3": {"exists": False, "evidence_strength": "low"},
                "3.4": {"owner": "finance", "skipped_by_legal": True},
                "3.5": {"exists": True, "skipped": False, "pipeline_high": True},
                "3.6": {"valuation_inversion": False, "evidence": []},
            },
            "skill_results": {"legal_governance": {"risk_points": [{}]}},
        },
        "evidence_summary": {},
    }
    assert _legal_section_feat(legal, "3.1").get("exists") is True
    assert _legal_section_feat(legal, "3.2").get("ratio_pct") == 12.5
    md = build_legal_report(
        {"doc_id": "t", "finance": {}, "legal": legal},
        doc_name="测试",
        pdf_name="t.pdf",
        legal_retrieval=None,
    )
    assert "exists=True" in md
    assert "ratio_pct=12.5" in md
    assert "| 3.1 |" in md
