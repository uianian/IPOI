"""辩论 jsonl 含 utterance、duration_ms、tool_calls、reasoning、evidence.excerpt。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.models.evidence import EvidenceRef
from src.models.master import ClaimUpdate, DebateQuestion
from src.skills.base import SkillInput
from src.skills.run_debate import RunDebateSkill
from src.tracing.run_logger import AgentRunLogger


class SeqLLM:
    available = True
    settings = {"chat_model": "mock", "provider": "openai"}

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)

    async def chat_json(self, messages, **kwargs):
        data = self.payloads.pop(0) if self.payloads else {"continue_debate": False, "questions": []}
        return {
            "data": data,
            "content": json.dumps(data),
            "reasoning": "controller-think-full",
            "usage": {"total_tokens": 9},
        }


def test_debate_jsonl_has_full_trace_fields(tmp_path: Path):
    llm = SeqLLM(
        [
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "target_agent": "finance",
                        "claim_id": "c1",
                        "theme": "cash_runway",
                        "question": "請用頁碼證明現金跑道少於12個月",
                        "priority": "high",
                    }
                ]
            },
            {"continue_debate": False, "reason": "證據已足", "questions": []},
        ]
    )
    logger = AgentRunLogger(agent="master", doc_id="doc", log_dir=tmp_path, doc_name="trace_doc")

    async def respond(question: DebateQuestion, claim_card, *, round_no: int = 1) -> ClaimUpdate:
        return ClaimUpdate(
            question_id=question.question_id,
            target_agent="finance",
            status="verified",
            confidence=0.7,
            reply="根據第88頁現金流表，跑道約9個月。",
            new_queries=[{"query": "現金及現金等價物", "intent": "business_context"}],
            search_hit_count=1,
            evidence=[EvidenceRef(page=88, excerpt="現金及現金等價物人民幣1億元", source_type="table")],
        )

    asyncio.run(
        RunDebateSkill().execute(
            SkillInput(
                doc_id="doc",
                params={
                    "llm": llm,
                    "run_logger": logger,
                    "respond_fn": respond,
                    "conflicts": [{"theme": "cash_runway", "need_discussion": True}],
                    "finance_cards": {"claims": [{"claim_id": "c1", "code": "CASH_RUNWAY_LT_12"}]},
                    "legal_cards": {},
                    "market_cards": {},
                },
            )
        )
    )
    logger.close()
    events = [
        json.loads(line)
        for line in logger.jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kinds = {e.get("event") for e in events}
    assert "debate_question" in kinds
    assert "debate_reply" in kinds
    q = next(e for e in events if e.get("event") == "debate_question")
    assert q["utterance"] == "請用頁碼證明現金跑道少於12個月"
    assert q.get("reasoning") == "controller-think-full"
    r = next(e for e in events if e.get("event") == "debate_reply")
    assert "第88頁" in r["utterance"]
    assert r.get("tool_calls")
    assert r["evidence"][0]["excerpt"] == "現金及現金等價物人民幣1億元"
    assert r.get("duration_ms") is not None or r.get("search_hit_count") is not None
