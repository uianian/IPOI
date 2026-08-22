from pathlib import Path
import sys

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.llm.debate_prompts import MARKET_DEBATE_REPLY
from src.llm.master_prompts import MASTER_CONFLICT_SYSTEM, MASTER_QUESTIONS_SYSTEM
from src.models.debate import DebateClaim
from src.models.evidence import EvidenceRef
from src.models.master import DebateQuestion
from src.skills.master_cards import claim_to_card
from src.skills.run_debate import _ensure_real_market_question, _parse_questions


def test_market_debate_prompt_distinguishes_risk_and_direction_and_forbids_future_data():
    assert "risk_score" in MARKET_DEBATE_REPLY
    assert "overall_net_support" in MARKET_DEBATE_REPLY
    assert "量纲不同" in MARKET_DEBATE_REPLY
    assert "净支持率不参与 risk_score 的机械换算" in MARKET_DEBATE_REPLY
    assert "上市后真实行情" in MARKET_DEBATE_REPLY
    assert '"target_agent": "market"' in MARKET_DEBATE_REPLY


def test_master_prompts_route_market_conflicts_and_questions():
    assert "将 market 列入 source_agents" in MASTER_CONFLICT_SYSTEM
    assert "对 market 的质询" in MASTER_QUESTIONS_SYSTEM
    assert "不得强求或编造页码" in MASTER_QUESTIONS_SYSTEM
    assert "必须至少有一条 target_agent=market" in MASTER_QUESTIONS_SYSTEM


def test_real_market_is_deterministically_added_to_active_debate_plan():
    questions = [DebateQuestion(question_id="q1", target_agent="finance", question="现金跑道？")]
    market = {
        "agent": "market",
        "risk_score": 61,
        "claims": [{"claim_id": "market-1"}],
    }
    routed = _ensure_real_market_question(questions, market, cap=4)
    market_questions = [q for q in routed if q.target_agent == "market"]
    assert len(market_questions) == 1
    assert market_questions[0].claim_id == "market-1"
    assert "overall_net_support" in market_questions[0].question


def test_demo_market_is_not_added_to_debate_plan():
    questions = [DebateQuestion(question_id="q1", target_agent="finance", question="现金跑道？")]
    routed = _ensure_real_market_question(
        questions,
        {"agent": "market", "risk_score": 50, "demo": True},
        cap=4,
    )
    assert routed == questions


def test_market_structured_evidence_counts_without_pdf_pages():
    claim = DebateClaim(
        agent="market",
        code="MARKET_FINAL_SCORE",
        evidence_ids=["HIST-HSI-20D", "HIST-BREAK-RATE-60D"],
        evidence_refs=[EvidenceRef(page=None, excerpt="value=43.7", field_code="HIST-HSI-20D")],
    )
    card = claim_to_card(claim)
    assert card["n_evidence"] == 2
    assert card["evidence_ids"] == ["HIST-HSI-20D", "HIST-BREAK-RATE-60D"]


def test_market_question_is_sanitized_away_from_prospectus_pages():
    questions = _parse_questions([{
        "question_id": "m1",
        "target_agent": "market",
        "question": "请提供招股书页码及招股书或规则层面的证据",
        "required_evidence_types": ["page_excerpt"],
        "search_hints": {"pages": [428]},
    }], cap=4)
    assert len(questions) == 1
    q = questions[0]
    assert "招股书页码" not in q.question
    assert "市场数据来源" in q.question
    assert "market_field" in q.required_evidence_types
    assert q.search_hints["pages"] == []
