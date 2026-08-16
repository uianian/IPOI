"""--skip-experts：从已有 merged JSON 直接进总控，不跑专家探查。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.graph.parallel import run_master_from_saved
from src.models.evidence import AgentResult


class SeqLLM:
    available = True
    settings = {"chat_model": "mock", "provider": "openai"}

    def __init__(self) -> None:
        self.n = 0

    async def chat_json(self, messages, **kwargs):
        self.n += 1
        if self.n == 1:
            data = {"conflicts": [], "need_debate": False, "observation": "無須辯論"}
        elif self.n == 2:
            data = {"score": 2, "level": "low", "reason": "平實", "hits": [], "dimensions": {}}
        else:
            data = {
                "overall_score": 55,
                "level": "medium",
                "confidence": "medium",
                "triggered_gates": [],
                "verdict_reasoning": "復用專家結論",
                "score_explanation": "ok",
                "risk_factors": [],
                "predicted_windows": {},
                "report_sections": {"composite": "中等"},
            }
        return {"data": data, "content": json.dumps(data), "reasoning": "t", "usage": {}}


def test_run_master_from_saved_skips_explore(tmp_path: Path):
    payload = {
        "doc_id": "hansiaitai",
        "finance": AgentResult(
            agent="finance", doc_id="hansiaitai", risk_score=75, risk_level="high", summary="財務高"
        ).model_dump(),
        "legal": AgentResult(
            agent="legal", doc_id="hansiaitai", risk_score=60, risk_level="medium", summary="法務中"
        ).model_dump(),
        "reference_fundamental_score": 68.25,
    }
    src = tmp_path / "saved.json"
    src.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    llm = SeqLLM()
    out = asyncio.run(
        run_master_from_saved(
            src,
            master_llm=llm,
            debate_dir=tmp_path / "debate",
            doc_name="翰思艾泰",
        )
    )
    assert out["doc_id"] == "hansiaitai"
    assert out["finance"]["risk_score"] == 75
    assert out["legal"]["risk_score"] == 60
    assert out["master"]["judgment"]["overall_score"] == 55
    assert "skip-experts" in (out.get("note") or "")
    assert llm.n >= 3
