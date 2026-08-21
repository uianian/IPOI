from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.agents.market_agent import MarketAgent
from src.models.evidence import AgentResult, EvidenceRef
from src.models.master import DebateQuestion
from src.skills.debate_reply import expert_respond_to_controller
from src.skills.base import SkillInput
from src.skills.run_debate import RunDebateSkill
from service.thought_mapper import map_debate_expert_event
from src.tools.market_debate import search_market_evidence_standalone


class _Logger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def debate_search(self, **kwargs):
        self.events.append(("debate_search", kwargs))

    def debate_reply(self, **kwargs):
        self.events.append(("debate_reply", kwargs))


class _LLM:
    available = True

    def __init__(self) -> None:
        self.messages = None

    async def chat_json(self, messages, **kwargs):
        self.messages = messages
        return {
            "data": {
                "stance": "maintain",
                "response": "本地證據不足以推翻原結論。",
                "requires_new_evidence": False,
            }
        }


def test_market_controller_uses_local_evidence_and_emits_search_reply() -> None:
    async def run():
        logger = _Logger()
        llm = _LLM()
        agent = MarketAgent(
            llm=llm,
            run_logger=logger,
            market_settings={
                "llm": {"enabled": True},
                "data": {"features_csv": "features.csv", "news_dir": "news"},
            },
        )
        agent._last_result = AgentResult(
            agent="market",
            doc_id="d",
            risk_score=60,
            features={"stock_code": "02097"},
        )
        question = DebateQuestion(
            question_id="q-market",
            target_agent="market",
            question="近期舆情是否足以推翻结论？",
            search_hints={"keywords": ["近期", "舆情"]},
        )
        local = {
            "available": True,
            "cutoff_verified": True,
            "remote_fetch_attempted": False,
            "news_hits": [{"title": "本地新闻", "excerpt": "已采集的上市前信息"}],
        }
        with patch("src.agents.market_agent.search_market_evidence_standalone", return_value=local) as search:
            update = await agent.respond_to_controller(question, round_no=1)
        return update, logger, search, llm

    update, logger, search, llm = asyncio.run(run())
    assert update.target_agent == "market"
    assert update.status == "verified"
    assert update.evidence
    assert update.search_hit_count == 1
    assert all(isinstance(item, EvidenceRef) for item in update.evidence)
    search.assert_called_once()
    assert search.call_args.kwargs["stock_code"] == "02097"
    assert search.call_args.kwargs["limit"] == 10
    assert search.call_args.kwargs["features_csv"] == "features.csv"
    assert search.call_args.kwargs["news_dir"] == "news"
    assert search.call_args.kwargs["query"] == "近期 舆情"
    prompt = llm.messages[-1]["content"]
    assert "本地新闻" in prompt
    assert "title" in prompt and "url" in prompt and "description" in prompt
    names = [name for name, _ in logger.events]
    assert names == ["debate_search", "debate_reply"]
    assert logger.events[0][1]["target_agent"] == "market"
    assert logger.events[0][1]["tool_calls"][0]["arguments"]["remote_fetch"] is False
    assert logger.events[1][1]["target_agent"] == "market"
    search_thoughts = map_debate_expert_event(
        {"event": "debate_search", **logger.events[0][1]},
        with_category=True,
    )
    reply_thoughts = map_debate_expert_event(
        {"event": "debate_reply", **logger.events[1][1]},
        with_category=True,
    )
    assert any(item["agentId"] == "market" for item in search_thoughts)
    assert any(item["agentId"] == "market" for item in reply_thoughts)


def test_market_controller_without_llm_or_local_evidence_degrades_safely() -> None:
    async def run():
        logger = _Logger()
        agent = MarketAgent(
            run_logger=logger,
            market_settings={
                "llm": {"enabled": False},
                "data": {},
            },
        )
        agent._last_result = AgentResult(agent="market", doc_id="d", risk_score=60)
        question = DebateQuestion(target_agent="market", question="为何给出该风险分？")
        return await agent.respond_to_controller(question), logger

    update, logger = asyncio.run(run())
    assert update.status == "unresolved"
    assert update.evidence == []
    assert [name for name, _ in logger.events] == ["debate_search", "debate_reply"]
    assert logger.events[0][1]["evidence"] == []


def test_market_question_flows_to_debate_history_and_sse_reply() -> None:
    class _DebateLLM:
        available = True

        async def chat_json(self, messages, **kwargs):
            return {
                "data": {
                    "questions": [
                        {
                            "question_id": "q-market",
                            "target_agent": "market",
                            "question": "市場是否足以推翻原結論？",
                        }
                    ]
                },
                "content": "{}",
                "reasoning": "internal reasoning must not enter SSE",
                "usage": {},
            }

    async def run():
        logger = _Logger()
        agent = MarketAgent(
            run_logger=logger,
            market_settings={"llm": {"enabled": False}, "data": {}},
        )
        # Dict result is intentional: HTTP/skip paths can hand back serialized results.
        agent._last_result = {"features": {"stock_code": "02097"}, "risk_score": 60}
        output = await RunDebateSkill().execute(
            SkillInput(
                doc_id="d",
                params={
                    "llm": _DebateLLM(),
                    "respond_fn": agent.respond_to_controller,
                    "conflicts": [{"need_discussion": True}],
                    "market_cards": {},
                    "max_rounds": 1,
                },
            )
        )
        return output, logger

    output, logger = asyncio.run(run())
    history = output.data["debate_history"]
    assert history[0]["questions"][0]["target_agent"] == "market"
    assert history[0]["replies"][0]["target_agent"] == "market"
    reply_event = next(kwargs for name, kwargs in logger.events if name == "debate_reply")
    reply_thoughts = map_debate_expert_event(
        {"event": "debate_reply", **reply_event},
        with_category=True,
    )
    assert any(item["agentId"] == "market" for item in reply_thoughts)
    assert all("rawThink" not in item.get("meta", {}) for item in reply_thoughts)
    assert all("reasoning" not in item for item in reply_thoughts)


def test_feature_only_local_evidence_becomes_a_bounded_evidence_ref() -> None:
    async def run():
        agent = MarketAgent(
            market_settings={
                "llm": {"enabled": False},
                "data": {"features_csv": "features.csv", "news_dir": "news"},
            }
        )
        agent._last_result = {"features": {"stock_code": "02097"}}
        question = DebateQuestion(target_agent="market", question="市場指標如何？")
        local = {
            "available": True,
            "cutoff_verified": True,
            "remote_fetch_attempted": False,
            "news_hits": [],
            "feature_hits": {"hsi_ret_20d": 0.1},
        }
        with patch("src.agents.market_agent.search_market_evidence_standalone", return_value=local):
            return await agent.respond_to_controller(question)

    update = asyncio.run(run())
    assert update.evidence
    assert update.evidence[0].field_code == "hsi_ret_20d"


def test_market_fallback_search_missing_paths_returns_safe_degradation() -> None:
    result = asyncio.run(search_market_evidence_standalone(query="舆情"))
    assert result["available"] is False
    assert result["remote_fetch_attempted"] is False
    assert result["error"] == "market_local_paths_not_configured"


def test_market_generic_fallback_does_not_raise_on_missing_local_paths() -> None:
    question = DebateQuestion(target_agent="market", question="市场是否过热？")
    update = asyncio.run(
        expert_respond_to_controller(
            agent="market",
            question=question,
            claim_card=None,
            llm=None,
            doc_id="d",
            parse_json=None,
            demo_market=True,
        )
    )
    assert update.status == "unresolved"
    assert update.search_hit_count == 0
