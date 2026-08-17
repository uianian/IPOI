"""冲突研判：思考占满 max_tokens 时不得把空 JSON 当成 need_debate=false。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.skills.base import SkillInput
from src.skills.detect_conflicts import DetectConflictsSkill
from src.skills.llm_json import json_output_truncated, json_payload_usable, llm_json
from src.tools.llm_client import LLMClient


class SeqChatJSON:
    available = True
    settings = {"chat_model": "mock", "provider": "deepseek"}

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self.payloads:
            return self.payloads.pop(0)
        return {"data": {}, "content": "", "reasoning": "", "usage": {}, "finish_reason": "stop"}


def _truncated_payload() -> dict:
    return {
        "data": {},
        "content": "",
        "reasoning": "打算列出赎回共振与现金跑道证据缺口",
        "usage": {
            "completion_tokens": 800,
            "completion_tokens_details": {"reasoning_tokens": 800},
        },
        "finish_reason": "length",
    }


def test_truncated_reasoning_is_not_usable_json():
    assert json_payload_usable({}, required_keys=("conflicts", "need_debate")) is False
    assert (
        json_output_truncated(
            data={},
            content="",
            finish_reason="length",
            usage={"completion_tokens": 800, "completion_tokens_details": {"reasoning_tokens": 800}},
            required_keys=("conflicts", "need_debate"),
        )
        is True
    )


def test_llm_json_retries_after_reasoning_eats_budget():
    good = {
        "conflicts": [
            {
                "theme": "redemption",
                "kind": "resonance",
                "need_discussion": True,
                "source_agents": ["finance", "legal"],
            }
        ],
        "need_debate": True,
        "observation": "贖回共振需交叉核證",
    }
    llm = SeqChatJSON(
        [
            _truncated_payload(),
            {
                "data": good,
                "content": json.dumps(good, ensure_ascii=False),
                "reasoning": "retry",
                "usage": {"completion_tokens": 40},
                "finish_reason": "stop",
            },
        ]
    )
    out = asyncio.run(
        llm_json(
            llm,
            [{"role": "user", "content": "detect"}],
            max_tokens=800,
            required_keys=("conflicts", "need_debate"),
        )
    )
    assert out["ok"] is True
    assert out["retries"] == 1
    assert out["data"]["need_debate"] is True
    assert len(llm.calls) == 2
    assert llm.calls[1]["max_tokens"] >= llm.calls[0]["max_tokens"]


def test_detect_conflicts_retries_then_opens_debate():
    good = {
        "conflicts": [
            {
                "theme": "cash_runway",
                "kind": "evidence_gap",
                "need_discussion": True,
                "source_agents": ["finance"],
                "claim_ids": [],
                "priority": "medium",
                "description": "現金跑道需補證",
            }
        ],
        "need_debate": True,
        "observation": "要辯論",
    }
    llm = SeqChatJSON(
        [
            _truncated_payload(),
            {
                "data": good,
                "content": json.dumps(good, ensure_ascii=False),
                "reasoning": "ok",
                "usage": {},
                "finish_reason": "stop",
            },
        ]
    )
    out = asyncio.run(
        DetectConflictsSkill().execute(
            SkillInput(
                doc_id="hansiaitai",
                params={
                    "llm": llm,
                    "reference_score": 65.41,
                    "finance_cards": {"claims": []},
                    "legal_cards": {"claims": []},
                    "market_cards": {"claims": []},
                },
            )
        )
    )
    assert out.degraded is False
    assert out.data["need_debate"] is True
    assert out.data["llm_ok"] is True
    assert out.data["retries"] == 1
    assert out.data["conflicts"][0]["theme"] == "cash_runway"


def test_detect_conflicts_empty_json_is_degraded_not_no_debate():
    llm = SeqChatJSON([_truncated_payload(), _truncated_payload(), _truncated_payload()])
    out = asyncio.run(
        DetectConflictsSkill().execute(
            SkillInput(
                doc_id="hansiaitai",
                params={
                    "llm": llm,
                    "reference_score": 65.41,
                    "finance_cards": {"claims": []},
                    "legal_cards": {"claims": []},
                    "market_cards": {"claims": []},
                },
            )
        )
    )
    assert out.degraded is True
    assert out.data["need_debate"] is False
    assert out.data["llm_ok"] is False
    assert out.data["conflicts"] == []
    assert len(llm.calls) == 3
    assert llm.calls[-1]["enable_reasoning"] is False
    assert llm.calls[-1]["max_tokens"] >= 2048
    assert "JSON" in llm.calls[-1]["messages"][-1]["content"]


def test_deepseek_payload_reserves_reasoning_tokens():
    client = LLMClient(
        {
            "provider": "deepseek",
            "api_key": "x",
            "api_base": "https://api.deepseek.com",
            "chat_model": "deepseek-v4-flash",
        }
    )
    thinking = client._build_payload(
        [{"role": "user", "content": "hi"}],
        temperature=0.0,
        enable_reasoning=True,
        reasoning_effort="low",
        max_tokens=800,
        reasoning_max_tokens=512,
        tools=None,
        tool_choice=None,
    )
    assert thinking["max_tokens"] == 1312
    assert thinking["thinking"] == {"type": "enabled"}
    disabled = client._build_payload(
        [{"role": "user", "content": "hi"}],
        temperature=0.0,
        enable_reasoning=False,
        reasoning_effort="low",
        max_tokens=800,
        reasoning_max_tokens=512,
        tools=None,
        tool_choice=None,
    )
    assert disabled["max_tokens"] == 800
    assert disabled["thinking"] == {"type": "disabled"}
