"""theme 标签进入冲突 Prompt 卡片；是否辩论由 mock 总控输出决定。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.skills.base import SkillInput
from src.skills.detect_conflicts import DetectConflictsSkill
from src.skills.master_cards import claim_to_card


class CaptureLLM:
    available = True
    settings = {"chat_model": "mock", "provider": "openai"}

    def __init__(self, data: dict) -> None:
        self.data = data
        self.user = ""

    async def chat_json(self, messages, **kwargs):
        self.user = messages[-1]["content"]
        return {
            "data": self.data,
            "content": json.dumps(self.data, ensure_ascii=False),
            "reasoning": "think",
            "usage": {},
        }


def test_theme_hint_in_conflict_prompt_and_mock_decides_debate():
    card = claim_to_card(
        {
            "claim_id": "c1",
            "agent": "finance",
            "code": "CV_PREF_LIABILITY",
            "level": "high",
            "statement": "表内优先股负债重大",
            "evidence_refs": [{"page": 10, "excerpt": "可轉換可贖回優先股", "source_type": "table"}],
        }
    )
    assert card["theme_hint"] == "redemption"
    llm = CaptureLLM(
        {
            "conflicts": [
                {
                    "theme": "redemption",
                    "kind": "resonance",
                    "need_discussion": False,
                    "description": "共振而非衝突",
                    "claim_ids": ["c1"],
                    "source_agents": ["finance", "legal"],
                    "priority": "medium",
                }
            ],
            "need_debate": False,
            "observation": "無須辯論",
        }
    )
    out = asyncio.run(
        DetectConflictsSkill().execute(
            SkillInput(
                doc_id="t",
                params={
                    "llm": llm,
                    "reference_score": 40,
                    "finance_cards": {"agent": "finance", "claims": [card]},
                    "legal_cards": {"agent": "legal", "claims": []},
                    "market_cards": {"agent": "market", "claims": []},
                },
            )
        )
    )
    assert "theme_hint" in llm.user
    assert "redemption" in llm.user
    assert out.data["need_debate"] is False
    assert out.data["conflicts"][0]["kind"] == "resonance"


def test_mock_controller_can_open_debate():
    llm = CaptureLLM(
        {
            "conflicts": [
                {
                    "theme": "cash_runway",
                    "kind": "evidence_gap",
                    "need_discussion": True,
                    "description": "需補證",
                    "claim_ids": [],
                    "source_agents": ["finance"],
                    "priority": "high",
                }
            ],
            "need_debate": True,
            "observation": "要問",
        }
    )
    out = asyncio.run(
        DetectConflictsSkill().execute(
            SkillInput(
                doc_id="t",
                params={
                    "llm": llm,
                    "reference_score": 70,
                    "finance_cards": {"claims": []},
                    "legal_cards": {"claims": []},
                    "market_cards": {"claims": []},
                },
            )
        )
    )
    assert out.data["need_debate"] is True
