"""漏用高风险清单 → gate_warning + 总控再修订；禁止 Python 直接改 riskLevel。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.skills.base import SkillInput
from src.skills.master_decide import MasterDecideSkill


class SeqLLM:
    available = True
    settings = {"chat_model": "mock", "provider": "openai"}

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[list] = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        data = self.payloads.pop(0) if self.payloads else {}
        return {
            "data": data,
            "content": json.dumps(data, ensure_ascii=False),
            "reasoning": "mock-think",
            "usage": {"total_tokens": 12},
        }


def test_gate_warning_triggers_revise_not_python_override():
    llm = SeqLLM(
        [
            {
                "overall_score": 20,
                "level": "low",
                "confidence": "high",
                "triggered_gates": [],
                "verdict_reasoning": "忽略跑道",
                "score_explanation": "first",
                "risk_factors": [],
                "predicted_windows": {},
                "report_sections": {},
            },
            {
                "overall_score": 75,
                "level": "high",
                "confidence": "medium",
                "triggered_gates": ["CASH_RUNWAY_LT_12"],
                "verdict_reasoning": "修訂：現金跑道不足12個月",
                "score_explanation": "revised",
                "risk_factors": [],
                "predicted_windows": {},
                "report_sections": {},
            },
        ]
    )
    finance = {
        "risk_score": 80,
        "risk_level": "high",
        "score_breakdown": [{"code": "CASH_RUNWAY_LT_12", "delta": 20}],
    }
    out = asyncio.run(
        MasterDecideSkill().execute(
            SkillInput(
                doc_id="t",
                params={
                    "llm": llm,
                    "finance": finance,
                    "legal": {"risk_score": 10, "score_breakdown": []},
                    "market": {"risk_score": 50, "features": {"demo": True}},
                    "reference_score": 48.5,
                    "finance_cards": {},
                    "legal_cards": {},
                    "market_cards": {},
                    "embellishment": {"score": 2, "reason": ""},
                    "debate_history": [],
                },
            )
        )
    )
    j = out.data["judgment"]
    assert len(llm.calls) == 2
    assert out.data["llm_calls"] == 2
    assert j["level"] == "high"
    assert j["risk_level_http"] == "HIGH"
    assert j["revised"] is True
    assert j["gate_warning"] and "CASH_RUNWAY_LT_12" in j["gate_warning"]
    # 第二次调用才是修订；分数来自 LLM 而非 Python max()
    assert j["overall_score"] == 75
    assert "跑道" in j["verdict_reasoning"]
