"""辩论检索：关键词/页码规划，禁止整段质询进 BM25。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.models.master import DebateQuestion
from src.skills.base import SkillInput
from src.skills.debate_query import (
    extract_pages,
    hit_is_useful,
    looks_like_instruction,
    plan_debate_searches,
)
from src.skills.debate_reply import (
    _context_evidence_refs,
    _market_structured_fallback,
    expert_respond_to_controller,
)
from src.tools.retrieval_tool import hits_from_prefer_pages

HANSIAITAI_Q1 = (
    "請財務總監提供截至2025年8月31日普通股贖回負債人民幣138.5百萬元的完整明細，"
    "包括其入賬分類（流動/非流動）、計息方式、到期日及贖回觸發條款，"
    "並列出該負債佔流動負債淨額的具體比例（以頁497之數字為基礎）"
    "及其對營運資金、現金流量和持續經營能力的量化影響。"
    "請提供招股章程第563頁及第497頁之相應摘錄及相關會計師報告附註頁碼。"
)


class ReplyLLM:
    available = True
    settings = {"chat_model": "mock", "provider": "openai"}

    def __init__(self) -> None:
        self.user = ""

    async def chat_json(self, messages, **kwargs):
        self.user = messages[-1]["content"]
        data = {
            "reply": "卡片已載明贖回負債人民幣138.5百萬元，本輪命中頁497，維持原主張。",
            "updated_clue": {
                "status": "partially_accepted",
                "confidence": 0.7,
                "clue_id": "6bb8d191",
            },
        }
        return {"data": data, "content": json.dumps(data, ensure_ascii=False), "reasoning": "t", "usage": {}}


def test_extract_pages_from_hansiaitai_question():
    pages = extract_pages(HANSIAITAI_Q1)
    assert 497 in pages
    assert 563 in pages


def test_plan_does_not_use_full_question():
    plan = plan_debate_searches(
        agent="finance",
        question_text=HANSIAITAI_Q1,
        theme="redemption",
        claim_card={
            "code": "CV_PREF_LIABILITY",
            "statement": "表內可轉換可贖回優先股/贖回負債構成財務壓力",
            "excerpts": [{"page": 497, "excerpt": "普通股贖回負債人民幣138.5百萬元"}],
            "n_evidence": 2,
        },
        max_searches=2,
    )
    assert 497 in plan.pages
    assert 563 in plan.pages
    assert any("138.5" in k or "贖回" in k for k in plan.keywords)
    assert any(k in plan.keywords for k in ("贖回負債", "可轉換可贖回優先股", "可贖回優先股"))
    assert plan.steps
    for step in plan.steps:
        assert "請財務總監" not in (step.query or "")
        assert HANSIAITAI_Q1[:80] != step.query
        if step.kind != "page":
            assert not looks_like_instruction(step.query)
    assert any(step.kind == "page" for step in plan.steps)
    assert "138.5" in plan.claimed_evidence


def test_dirty_hit_is_not_useful():
    dirty = {"page": 104, "excerpt": "與依賴第三方有關的風險", "matched_terms": []}
    assert (
        hit_is_useful(dirty, pages=[497, 563], keywords=["贖回負債", "138.5"])
        is False
    )
    good = {"page": 497, "excerpt": "普通股贖回負債人民幣138.5百萬元", "matched_terms": ["138.5"]}
    assert hit_is_useful(good, pages=[497, 563], keywords=["贖回負債", "138.5"]) is True


def test_market_truncated_reply_has_structured_fallback():
    refs = _context_evidence_refs(
        "market",
        {
            "evidence_catalog": [
                {
                    "evidence_id": "MACRO-HSI-5D",
                    "derived_field": "hsi_return_5d",
                    "value": -0.0229,
                    "formatted_value": "-2.29%",
                    "observation_date": "2025-03-02",
                }
            ]
        },
        "请提供市场字段、证据ID及as_of_date",
    )
    reply = _market_structured_fallback(
        {"risk_score": 46.0, "deterministic_score": 43.7, "llm_score": 46.0}, refs
    )
    assert "最终风险分=46.0" in reply
    assert "MACRO-HSI-5D" in reply
    assert "-2.29%" in reply
    assert "2025-03-02" in reply
    assert "不要求招股书页码" in reply


def test_hits_from_prefer_pages(tmp_path: Path):
    parse = tmp_path / "full_parse.json"
    parse.write_text(
        json.dumps(
            [
                {
                    "page": 104,
                    "elements": [{"category": "text", "text": "與依賴第三方有關的風險"}],
                },
                {
                    "page": 497,
                    "elements": [
                        {
                            "category": "text",
                            "text": "截至2025年8月31日普通股贖回負債人民幣138.5百萬元",
                        }
                    ],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    hits = hits_from_prefer_pages(parse, [497, 563], keywords=["贖回負債", "138.5"], top_k=4)
    assert hits
    assert any(h.get("page") == 497 for h in hits)
    assert all(h.get("page") != 104 for h in hits)


def test_debate_reply_searches_page_not_question(tmp_path: Path):
    parse = tmp_path / "full_parse.json"
    parse.write_text(
        json.dumps(
            [
                {
                    "page": 104,
                    "elements": [{"category": "text", "text": "與依賴第三方有關的風險"}],
                },
                {
                    "page": 497,
                    "elements": [
                        {
                            "category": "text",
                            "text": "截至2025年8月31日普通股贖回負債人民幣138.5百萬元",
                        }
                    ],
                },
                {
                    "page": 563,
                    "elements": [{"category": "text", "text": "現金及現金等價物與資金消耗率"}],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    llm = ReplyLLM()
    q = DebateQuestion(
        question_id="q1",
        target_agent="finance",
        claim_id="6bb8d191",
        theme="redemption",
        question=HANSIAITAI_Q1,
    )
    card = {
        "claim_id": "6bb8d191",
        "code": "CV_PREF_LIABILITY",
        "statement": "表內可轉換可贖回優先股/贖回負債構成財務壓力",
        "excerpts": [{"page": 497, "excerpt": "普通股贖回負債人民幣138.5百萬元"}],
        "n_evidence": 2,
    }
    upd = asyncio.run(
        expert_respond_to_controller(
            agent="finance",
            question=q,
            claim_card=card,
            llm=llm,
            doc_id="hansiaitai",
            parse_json=parse,
        )
    )
    queries = [str(item.get("query") or "") for item in upd.new_queries]
    assert queries
    assert all("請財務總監" not in qtext for qtext in queries)
    assert all(HANSIAITAI_Q1[:80] != qtext for qtext in queries)
    assert upd.search_hit_count >= 1
    assert any(e.page == 497 for e in upd.evidence)
    assert "138.5" in llm.user
    assert "己方 claim 已有证据" in llm.user


def test_existing_evidence_still_searches_requested_pages(tmp_path: Path):
    parse = tmp_path / "full_parse.json"
    parse.write_text(
        json.dumps(
            [
                {
                    "page": 497,
                    "elements": [{"category": "text", "text": "贖回負債人民幣138.5百萬元"}],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    q = DebateQuestion(
        question_id="q1",
        target_agent="finance",
        theme="redemption",
        question="請核對頁497贖回負債金額",
    )
    upd = asyncio.run(
        expert_respond_to_controller(
            agent="finance",
            question=q,
            claim_card={"code": "CV_PREF_LIABILITY", "n_evidence": 3, "excerpts": [{"page": 80, "excerpt": "舊摘錄"}]},
            llm=ReplyLLM(),
            doc_id="hansiaitai",
            parse_json=parse,
        )
    )
    assert upd.search_hit_count >= 1
    assert any(item.get("kind") == "page" for item in upd.new_queries)


def test_dirty_hits_continue_to_second_search():
    from unittest.mock import patch

    calls: list[str] = []

    async def fake_step(**kwargs):
        step = kwargs["step"]
        calls.append(step.kind)
        if step.kind == "page":
            return {
                "ok": True,
                "hits": [
                    {
                        "page": 104,
                        "excerpt": "與依賴第三方有關的風險",
                        "matched_terms": [],
                    }
                ],
                "n": 1,
                "query": step.query,
                "duration_ms": 1,
            }
        return {
            "ok": True,
            "hits": [
                {
                    "page": 80,
                    "excerpt": "普通股贖回負債人民幣138.5百萬元",
                    "matched_terms": ["贖回負債"],
                }
            ],
            "n": 1,
            "query": step.query,
            "duration_ms": 1,
        }

    q = DebateQuestion(
        question_id="q1",
        target_agent="finance",
        claim_id="6bb8d191",
        theme="redemption",
        question=HANSIAITAI_Q1,
    )
    with patch("src.skills.debate_reply._run_search_step", new=fake_step):
        upd = asyncio.run(
            expert_respond_to_controller(
                agent="finance",
                question=q,
                claim_card={"code": "CV_PREF_LIABILITY", "n_evidence": 2},
                llm=ReplyLLM(),
                doc_id="hansiaitai",
                parse_json=None,
            )
        )
    assert "page" in calls
    assert "keyword" in calls
    assert upd.search_hit_count >= 1
    assert any(e.page == 80 for e in upd.evidence)


def test_finance_context_restores_audited_statement_pages():
    refs = _context_evidence_refs(
        "finance",
        {"evidence_summary": {"table_meta": {
            "TBL_IS": {"page": 428, "excerpt": "净利润表"},
            "TBL_CF": {"page": 437, "excerpt": "经营活动现金流量表"},
        }}},
        "请列出CFO、经营现金流及净利润并标明页码",
    )
    assert {(x.field_code, x.page) for x in refs} == {("TBL_IS", 428), ("TBL_CF", 437)}
