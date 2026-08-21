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
        "price_path_forecast": [
            {
                "window": "D1",
                "risk_label": "high",
                "expected_direction": "預計上市首日破發或承壓",
                "expected_pattern": "首日可能低開後弱勢震盪",
                "volatility_view": "波動和回撤風險高",
                "key_drivers": ["市場破發率高", "持續虧損"],
                "confidence": "medium",
            },
            {
                "window": "D5",
                "risk_label": "high",
                "expected_direction": "預計5個交易日內顯著下跌風險高",
                "expected_pattern": "首日承壓後繼續弱勢",
                "volatility_view": "高波動下探",
                "key_drivers": ["創新藥板塊承壓", "贖回壓力"],
                "confidence": "medium",
            },
            {
                "window": "D20",
                "risk_label": "medium",
                "expected_direction": "20日下行風險中等",
                "expected_pattern": "弱勢整理",
                "volatility_view": "波動中等",
                "key_drivers": ["估值壓力"],
                "confidence": "medium",
            },
            {
                "window": "D60",
                "risk_label": "medium",
                "expected_direction": "60日下行風險中等",
                "expected_pattern": "等待基本面驗證",
                "volatility_view": "波動中等",
                "key_drivers": ["融資依賴"],
                "confidence": "low",
            },
        ],
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


def test_decide_preserves_price_path_forecast_and_predicted_windows():
    good = _good_judgment()
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
    assert out.data["predicted_windows"]["ipo_day_break_risk"] == "high"
    forecasts = out.data["price_path_forecast"]
    assert [item["window"] for item in forecasts] == ["D1", "D5", "D20", "D60"]
    assert forecasts[1]["risk_label"] == "high"
    assert "顯著下跌" in forecasts[1]["expected_direction"]


def test_decide_missing_price_path_forecast_falls_back_to_labels():
    good = _good_judgment()
    good.pop("price_path_forecast")
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
    forecasts = out.data["price_path_forecast"]
    assert [item["risk_label"] for item in forecasts[:2]] == ["high", "high"]
    assert "标签级预测" in forecasts[0]["expected_pattern"]


def test_partial_embellishment_without_minimum_coverage_cannot_trigger_gate():
    params = _params(SeqLLM([_truncated(), _truncated(), _truncated()]))
    params["reference_score"] = 20
    params["finance"] = {"risk_score": 20, "risk_level": "low", "score_breakdown": []}
    params["legal"] = {"risk_score": 20, "risk_level": "low", "score_breakdown": []}
    params["finance_cards"] = {"claims": []}
    params["legal_cards"] = {"claims": []}
    params["embellishment"] = {
        "status": "partial",
        "score": 8,
        "reason": "仅复核少量候选",
        "coverage": {
            "candidate_count": 10,
            "evaluated_candidate_count": 2,
            "sections": ["risk_factors"],
            "risk_factor_pages": [55],
        },
    }
    out = asyncio.run(MasterDecideSkill().execute(SkillInput(doc_id="partial", params=params)))
    assert out.degraded is True
    assert out.data["judgment"]["level"] == "low"
    assert "EMBELLISHMENT_HIGH" not in out.data["judgment"]["triggered_gates"]
    prompt = params["llm"].calls[0]["messages"][-1]["content"]
    assert "usable=false" in prompt
    assert "score=不可用于门控" in prompt



def test_disabled_embellishment_is_absent_from_decision_prompt_and_gate():
    good = _good_judgment(overall_score=25, level="low", triggered_gates=[])
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
    params = _params(llm)
    params["embellishment_enabled"] = False
    params["embellishment"] = {"status": "complete", "score": 10, "reason": "应被忽略"}
    out = asyncio.run(MasterDecideSkill().execute(SkillInput(doc_id="disabled", params=params)))
    assert out.degraded is False
    assert out.data["judgment"]["overall_score"] == 25
    assert "EMBELLISHMENT_HIGH" not in out.data["judgment"]["triggered_gates"]
    prompt = " ".join(message["content"] for message in llm.calls[0]["messages"])
    assert "粉饰" not in prompt
    assert "EMBELLISHMENT_HIGH" not in prompt
