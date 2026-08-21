"""文本粉饰度应覆盖全书重点章节，并只输出可回查候选。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.agents.master_agent import MasterAgent
from src.skills.base import SkillInput
from src.skills.score_embellishment import ScoreEmbellishmentSkill, _score_assessments


class CandidateLLM:
    available = True
    settings = {"chat_model": "mock", "provider": "openai"}

    def __init__(self, *, supported_rules: set[str] | None = None) -> None:
        self.user = ""
        self.supported_rules = supported_rules or set()

    async def chat_json(self, messages, **kwargs):
        self.user = messages[-1]["content"]
        raw = self.user.split("【候选原文】\n", 1)[1].split("\n\n【财务/法务", 1)[0]
        candidates = json.loads(raw)
        assessments = []
        for item in candidates:
            supported = item["rule"] in self.supported_rules
            assessments.append(
                {
                    "candidate_id": item["candidate_id"],
                    "dimension": item["dimension_hint"],
                    "tactic": item["tactic_hint"],
                    "severity": "low" if supported else "high",
                    "confidence": "high",
                    "support_status": "supported" if supported else "unsupported",
                    "score_contribution": 2,
                    "reason": "有明确支撑" if supported else "缺少量化支撑并弱化读者理解",
                    "cross_evidence": [],
                }
            )
        data = {"assessments": assessments}
        return {"data": data, "content": json.dumps(data), "reasoning": "think", "usage": {}}


def _page(page: int, header: str | None, *texts: str) -> dict:
    elements = []
    if header:
        elements.append({"category": "header", "text": header})
    elements.extend({"category": "text", "text": text} for text in texts)
    return {"page": page, "elements": elements}


def _full_prospectus() -> list[dict]:
    pages = [_page(i, None, "全球發售重要提示及預期時間表") for i in range(1, 6)]
    pages.extend(
        [
            _page(6, "概要", "本公司主要業務為現製飲品及供應鏈服務。"),
            _page(7, "風險因素", "我們可能無法達成預期，且不能保證未來表現。"),
            _page(8, "風險因素", "雖然持續錄得虧損，本公司認為相關流動性風險可控，可能造成重大不利影響。"),
            _page(9, "行業概覽", "按門店數目計，本公司在特定低價現製飲品市場排名第一。"),
            _page(10, "業務", "本公司是行業領先且首屈一指的全球品牌。"),
            _page(11, "財務資料", "報告期內本公司持續虧損人民幣10億元。"),
        ]
    )
    return pages


def test_embellishment_scans_beyond_first_pages_and_all_risk_pages(tmp_path: Path):
    parse_path = tmp_path / "full_parse.json"
    parse_path.write_text(json.dumps(_full_prospectus(), ensure_ascii=False), encoding="utf-8")
    llm = CandidateLLM()
    out = asyncio.run(
        ScoreEmbellishmentSkill().execute(
            SkillInput(
                doc_id="t",
                params={
                    "llm": llm,
                    "parse_json": parse_path,
                    "finance_cards": {"summary": "持续亏损10亿元"},
                    "legal_cards": {"summary": "流动性风险需重点关注"},
                },
            )
        )
    )
    result = out.data["embellishment"]
    assert result["status"] == "complete"
    assert result["coverage"]["risk_factor_pages"] == [7, 8]
    assert result["coverage"]["pages_analyzed"] == list(range(1, 12))
    assert set(result["coverage"]["sections"]) == {
        "summary", "risk_factors", "industry_overview", "business", "financial_information"
    }
    assert any(item["page"] == 8 and "風險可控" in item["excerpt"] for item in result["high_risk_excerpts"])
    assert any(item["page"] > 5 for item in result["high_risk_excerpts"])
    assert "candidate_id" in llm.user
    # 普通法定措辞不能仅凭“可能/不能保证”成为候选或高风险原文。
    assert not any(item["page"] == 7 for item in result["hits"])


def test_supported_ranking_does_not_score_or_enter_high_excerpts(tmp_path: Path):
    pages = _full_prospectus()
    pages[7]["elements"][-1]["text"] = "普通行业背景资料。"
    pages[9]["elements"][-1]["text"] = "本公司提供标准饮品服务。"
    parse_path = tmp_path / "full_parse.json"
    parse_path.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    out = asyncio.run(
        ScoreEmbellishmentSkill().execute(
            SkillInput(doc_id="t", params={"llm": CandidateLLM(supported_rules={"ranking"}), "parse_json": parse_path})
        )
    )
    result = out.data["embellishment"]
    assert result["score"] == 0
    assert result["high_risk_excerpts"] == []


def test_missing_parse_is_not_reported_as_low_complete():
    out = asyncio.run(
        ScoreEmbellishmentSkill().execute(
            SkillInput(doc_id="t", params={"llm": CandidateLLM(), "parse_json": "/not/found.json"})
        )
    )
    result = out.data["embellishment"]
    assert result["status"] == "not_available"
    assert out.degraded is True
    assert "无法评估" in result["reason"]


def test_unrecognized_llm_candidate_cannot_fabricate_page_or_excerpt():
    candidates = [
        {
            "candidate_id": "emb-0001",
            "page": 8,
            "section": "risk_factors",
            "dimension_hint": "obscurity",
            "tactic_hint": "risk_minimization",
            "rule": "obscurity",
            "concept_family": "",
            "excerpt": "可在第8页回查的原文",
            "context": "可在第8页回查的原文上下文",
        }
    ]
    score, _, hits, high = _score_assessments(
        candidates,
        [
            {
                "candidate_id": "fabricated-id",
                "page": 999,
                "excerpt": "模型虚构原文",
                "dimension": "obscurity",
                "severity": "high",
                "confidence": "high",
                "support_status": "unsupported",
                "score_contribution": 3,
            }
        ],
    )
    assert score == 0
    assert hits == []
    assert high == []


def test_negative_reason_overrides_inconsistent_high_structured_fields():
    candidates = [
        {
            "candidate_id": "emb-0001",
            "page": 78,
            "section": "risk_factors",
            "dimension_hint": "obscurity",
            "tactic_hint": "risk_minimization",
            "rule": "obscurity",
            "concept_family": "",
            "excerpt": "已完整披露并终止相关安排",
            "context": "已完整披露并终止相关安排",
        }
    ]
    score, dimensions, hits, high = _score_assessments(
        candidates,
        [
            {
                "candidate_id": "emb-0001",
                "dimension": "concept_packaging",
                "tactic": "risk_minimization",
                "severity": "high",
                "confidence": "high",
                "support_status": "contradictory",
                "score_contribution": 2,
                "reason": "已充分披露并妥善整改，故不構成粉飾。",
            }
        ],
    )
    assert score == 0
    assert dimensions["obscurity"]["score"] == 0
    assert dimensions["concept_packaging"]["score"] == 0
    assert hits == []
    assert high == []


class MustNotRunEmbellishment:
    async def execute(self, skill_input):
        raise AssertionError("disabled embellishment skill must not run")


def test_disabled_embellishment_short_circuits_skill_call():
    agent = MasterAgent(enable_embellishment=False, use_langgraph=False)
    agent._embellish = MustNotRunEmbellishment()
    state = asyncio.run(
        agent.step_embellish(
            {"doc_id": "disabled", "embellishment_enabled": False, "embellishment": {}}
        )
    )
    assert state["embellishment"] is None
    assert state["embellish_prompt_user"] is None
