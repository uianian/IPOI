"""终裁：压缩辩论摘要、截断后重试，不得把空 JSON 当成对照分终局。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.skills.base import SkillInput
from src.skills.master_decide import MasterDecideSkill, compact_debate_digest


class SeqLLM:
    available = True
    settings = {"chat_model": "mock", "provider": "deepseek"}

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self.payloads:
            return self.payloads.pop(0)
        return {"data": {}, "content": "", "reasoning": "", "usage": {}, "finish_reason": "length"}


def _truncated() -> dict:
    return {
        "data": {},
        "content": "",
        "reasoning": "准备写终裁 JSON",
        "usage": {
            "completion_tokens": 1200,
            "completion_tokens_details": {"reasoning_tokens": 1200},
        },
        "finish_reason": "length",
    }


def _good_judgment(**overrides) -> dict:
    data = {
        "overall_score": 72,
        "level": "high",
        "confidence": "medium",
        "triggered_gates": ["REDEMPTION_HIGH"],
        "verdict_reasoning": "贖回負債與購回權共振，維持高風險。",
        "score_explanation": "吸收辯論頁497證據，不照抄對照分。",
        "risk_factors": [
            {
                "title": "贖回負債",
                "source_agent": "finance",
                "reason": "138.5百萬入賬流動負債",
                "page": 497,
                "excerpt": "普通股贖回負債人民幣138.5百萬元",
            }
        ],
        "predicted_windows": {
            "ipo_day_break_risk": "high",
            "d5_significant_downside_risk": "high",
            "d20_downside_risk": "medium",
            "d60_downside_risk": "medium",
        },
    }
    data.update(overrides)
    return data


def _params(llm) -> dict:
    return {
        "llm": llm,
        "finance": {"risk_score": 75, "risk_level": "high", "score_breakdown": [{"code": "CV_PREF_LIABILITY"}]},
        "legal": {"risk_score": 60.9, "risk_level": "high", "score_breakdown": [{"code": "REDEMPTION_HIGH"}]},
        "market": {"risk_score": 62, "risk_level": "high", "features": {"scoring_mode": "market_react"}},
        "reference_score": 65.41,
        "finance_cards": {"claims": [{"code": "CV_PREF_LIABILITY"}]},
        "legal_cards": {"claims": [{"code": "REDEMPTION_HIGH"}]},
        "market_cards": {"claims": []},
        "embellishment": {"score": 1, "reason": "低粉飾"},
        "debate_history": [
            {
                "round": 1,
                "continue_debate": True,
                "questions": [
                    {
                        "question_id": "q1",
                        "target_agent": "finance",
                        "theme": "redemption",
                        "question": "請核對頁497贖回負債",
                    }
                ],
                "replies": [
                    {
                        "question_id": "q1",
                        "target_agent": "finance",
                        "status": "partially_accepted",
                        "confidence": 0.6,
                        "search_hit_count": 2,
                        "reply": "頁497確認138.5百萬贖回負債。",
                        "evidence": [
                            {
                                "page": 497,
                                "excerpt": "<table><tr><td>普通股贖回負債人民幣138.5百萬元</td></tr></table>",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_compact_debate_digest_drops_html_and_keeps_pages():
    hist = _params(SeqLLM([])).get("debate_history")
    blob = compact_debate_digest(hist)
    assert "<table" not in blob
    assert "497" in blob
    assert "138.5" in blob
    assert len(blob) < 2000


def test_decide_retries_after_length_then_uses_llm_score():
    good = _good_judgment()
    llm = SeqLLM(
        [
            _truncated(),
            {
                "data": good,
                "content": json.dumps(good, ensure_ascii=False),
                "reasoning": "ok",
                "usage": {"completion_tokens": 80},
                "finish_reason": "stop",
            },
        ]
    )
    out = asyncio.run(MasterDecideSkill().execute(SkillInput(doc_id="hansiaitai", params=_params(llm))))
    assert out.degraded is False
    j = out.data["judgment"]
    assert j["overall_score"] == 72
    assert j["level"] == "high"
    assert j["score_explanation"] != "degraded_rules_fallback"
    user = llm.calls[0]["messages"][-1]["content"]
    assert "<table" not in user
    assert "請核對頁497" in user or "497" in user
    assert llm.calls[1]["max_tokens"] >= llm.calls[0]["max_tokens"]


def test_decide_empty_json_is_degraded_not_silent_copy():
    llm = SeqLLM([_truncated(), _truncated(), _truncated()])
    out = asyncio.run(MasterDecideSkill().execute(SkillInput(doc_id="hansiaitai", params=_params(llm))))
    assert out.degraded is True
    assert out.degraded_reason == "empty_json"
    assert out.data["judgment"]["overall_score"] == 65.41
    assert out.data["judgment"]["level"] == "high"
    assert len(llm.calls) == 3
    assert llm.calls[-1]["enable_reasoning"] is False
    assert llm.calls[-1]["max_tokens"] >= 2048


def test_decide_scales_zero_one_score_to_hundred():
    good = _good_judgment(overall_score=0.72)
    llm = SeqLLM(
        [
            {
                "data": good,
                "content": json.dumps(good, ensure_ascii=False),
                "finish_reason": "stop",
                "usage": {},
            }
        ]
    )
    out = asyncio.run(MasterDecideSkill().execute(SkillInput(doc_id="hansiaitai", params=_params(llm))))
    assert out.degraded is False
    assert out.data["judgment"]["overall_score"] == 72
