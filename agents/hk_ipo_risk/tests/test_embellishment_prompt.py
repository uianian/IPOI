"""粉饰 Prompt 含前五页截断 + 词表提示。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.skills.base import SkillInput
from src.skills.score_embellishment import ScoreEmbellishmentSkill


class CaptureLLM:
    available = True
    settings = {"chat_model": "mock", "provider": "openai"}

    def __init__(self) -> None:
        self.user = ""

    async def chat_json(self, messages, **kwargs):
        self.user = messages[-1]["content"]
        data = {
            "score": 8,
            "level": "high",
            "reason": "營銷語過密",
            "dimensions": {"marketing_language": "領先/第一"},
            "hits": [{"page": 1, "excerpt": "行業第一", "dimension": "marketing_language", "note": ""}],
        }
        return {"data": data, "content": json.dumps(data), "reasoning": "think", "usage": {}}


def test_embellishment_prompt_has_first_pages_and_buzzwords(tmp_path: Path):
    pages = []
    for i in range(1, 6):
        pages.append(
            {
                "page": i,
                "elements": [
                    {"category": "text", "text": f"第{i}页正文 本公司為行業領先與第一。"}
                ],
            }
        )
    parse_path = tmp_path / "full_parse.json"
    parse_path.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    llm = CaptureLLM()
    out = asyncio.run(
        ScoreEmbellishmentSkill().execute(
            SkillInput(
                doc_id="t",
                params={"llm": llm, "parse_json": parse_path},
            )
        )
    )
    prompt = out.data["prompt_user"]
    assert "第1页" in prompt or "第1頁" in prompt or "[第1页]" in prompt
    assert "领先" in prompt or "領先" in prompt
    assert "第一" in prompt
    assert "词表提示" in prompt or "詞表" in prompt
    assert out.data["embellishment"]["score"] == 8
    assert "领先" in str(out.data["embellishment"].get("buzzword_hints")) or "第一" in str(
        out.data["embellishment"].get("buzzword_hints")
    )
