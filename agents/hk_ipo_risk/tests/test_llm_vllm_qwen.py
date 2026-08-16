"""vLLM 无 key 仍 available；payload 不含 DeepSeek thinking；不存在 qwen 跳过总控 LLM 的分支。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.tools.llm_client import LLMClient


def test_vllm_empty_key_available_and_no_thinking_payload():
    client = LLMClient(
        {
            "provider": "vllm",
            "api_key": "",
            "api_base": "http://127.0.0.1:8000/v1",
            "chat_model": "Qwen3.6-35B",
            "max_tokens": 256,
            "temperature": 0.0,
        }
    )
    assert client.available is True
    payload = client._build_payload(
        [{"role": "user", "content": "hi"}],
        temperature=0.0,
        enable_reasoning=True,
        reasoning_effort="low",
        max_tokens=128,
        reasoning_max_tokens=64,
        tools=None,
        tool_choice=None,
    )
    assert "thinking" not in payload
    assert "reasoning" not in payload
    assert "reasoning_effort" not in payload
    assert payload["model"] == "Qwen3.6-35B"


def test_no_qwen_skip_master_llm_branch():
    src = PKG_ROOT / "src"
    skip_re = re.compile(
        r"(skip_master_llm|if\s+.*qwen.*skip|if\s+model\s*==\s*['\"]qwen)",
        re.I,
    )
    hits: list[str] = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if skip_re.search(text):
            hits.append(str(path.relative_to(PKG_ROOT)))
    assert hits == [], f"forbidden qwen-skip branches: {hits}"
