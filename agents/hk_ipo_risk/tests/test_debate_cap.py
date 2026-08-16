"""已知独立质询同轮打包；新矛盾进入 round 2；第 3 轮后强制停；空 hits 仍发言。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.models.master import ClaimUpdate, DebateQuestion
from src.skills.base import SkillInput
from src.skills.debate_reply import expert_respond_to_controller
from src.skills.run_debate import RunDebateSkill


class SeqLLM:
    available = True
    settings = {"chat_model": "mock", "provider": "openai"}

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.n_calls = 0

    async def chat_json(self, messages, **kwargs):
        self.n_calls += 1
        data = self.payloads.pop(0) if self.payloads else {"continue_debate": False, "questions": []}
        return {"data": data, "content": json.dumps(data), "reasoning": "t", "usage": {}}


def test_pack_same_round_then_followup_then_hard_stop():
    llm = SeqLLM(
        [
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "target_agent": "finance",
                        "question": "跑道是否不足12個月？",
                        "theme": "cash_runway",
                    },
                    {
                        "question_id": "q2",
                        "target_agent": "legal",
                        "question": "贖回條款是否已清理？",
                        "theme": "redemption",
                    },
                ]
            },
            {
                "continue_debate": True,
                "reason": "財務補證後與法務清理聲明衝突",
                "questions": [
                    {
                        "question_id": "q3",
                        "target_agent": "legal",
                        "question": "請對照表內 CV_PREF 解釋清理聲明",
                        "theme": "redemption",
                    }
                ],
            },
            {
                "continue_debate": True,
                "reason": "仍未决",
                "questions": [
                    {
                        "question_id": "q4",
                        "target_agent": "finance",
                        "question": "再確認跑道計算口徑",
                        "theme": "cash_runway",
                    }
                ],
            },
            {
                "continue_debate": True,
                "reason": "不應再跑第4輪",
                "questions": [
                    {
                        "question_id": "q5",
                        "target_agent": "finance",
                        "question": "這題不該出現",
                    }
                ],
            },
        ]
    )
    seen_rounds: list[int] = []
    packed: dict[int, list[str]] = {}

    async def respond(question: DebateQuestion, claim_card, *, round_no: int = 1) -> ClaimUpdate:
        seen_rounds.append(round_no)
        packed.setdefault(round_no, []).append(question.question_id)
        return ClaimUpdate(
            question_id=question.question_id,
            target_agent=question.target_agent,
            status="unresolved",
            reply=f"r{round_no} 答 {question.question_id}",
            confidence=0.3,
        )

    out = asyncio.run(
        RunDebateSkill().execute(
            SkillInput(
                doc_id="d",
                params={
                    "llm": llm,
                    "respond_fn": respond,
                    "conflicts": [{}, {}],
                    "finance_cards": {},
                    "legal_cards": {},
                    "market_cards": {},
                    "max_rounds": 3,
                },
            )
        )
    )
    hist = out.data["debate_history"]
    assert out.data["n_rounds"] == 3
    assert hist[0]["round"] == 1
    qids_r1 = [q["question_id"] for q in hist[0]["questions"]]
    assert qids_r1 == ["q1", "q2"]  # 已知独立问题同轮打包
    assert packed[1] == ["q1", "q2"]
    assert hist[1]["round"] == 2
    assert [q["question_id"] for q in hist[1]["questions"]] == ["q3"]
    assert hist[2]["round"] == 3
    assert max(seen_rounds) == 3
    assert "q5" not in {q["question_id"] for rnd in hist for q in rnd["questions"]}


def test_empty_hits_still_speak():
    class ReplyLLM(SeqLLM):
        async def chat_json(self, messages, **kwargs):
            data = {
                "reply": "檢索未命中，僅能基於已有卡片做有限推理。",
                "updated_clue": {
                    "status": "verified",
                    "confidence": 0.9,
                    "clue_id": "c1",
                },
            }
            return {"data": data, "content": json.dumps(data), "reasoning": "r", "usage": {}}

    q = DebateQuestion(
        question_id="q1",
        target_agent="finance",
        claim_id="c1",
        theme="embellishment",
        question="「第一」有無量化營收或市占支撐？",
    )
    upd = asyncio.run(
        expert_respond_to_controller(
            agent="finance",
            question=q,
            claim_card={"claim_id": "c1", "n_evidence": 0, "code": "X"},
            llm=ReplyLLM([]),
            doc_id="d",
            parse_json=None,
        )
    )
    assert upd.reply
    assert "未命中" in upd.reply or upd.reply
    assert upd.confidence <= 0.4
    assert upd.status != "verified"
    assert upd.status == "unresolved"
