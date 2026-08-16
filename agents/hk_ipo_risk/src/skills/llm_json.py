from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.tools.llm_client import parse_json_object

logger = logging.getLogger(__name__)


async def llm_json(
    llm: Any,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 800,
    reasoning_effort: str | None = "low",
    enable_reasoning: bool = True,
) -> dict[str, Any]:
    """Call chat_json-like API; always return data/reasoning/duration_ms/usage."""
    t0 = time.time()
    if llm is None or not getattr(llm, "available", False):
        return {
            "data": {},
            "content": "",
            "reasoning": None,
            "usage": None,
            "duration_ms": 0,
            "ok": False,
            "error": "llm_unavailable",
        }
    try:
        if hasattr(llm, "chat_json"):
            raw = await llm.chat_json(
                messages,
                enable_reasoning=enable_reasoning,
                reasoning_effort=reasoning_effort,
                max_tokens=max_tokens,
            )
            data = raw.get("data") if isinstance(raw.get("data"), dict) else parse_json_object(raw.get("content") or "")
            return {
                "data": data or {},
                "content": raw.get("content") or "",
                "reasoning": raw.get("reasoning"),
                "usage": raw.get("usage"),
                "duration_ms": int((time.time() - t0) * 1000),
                "ok": True,
                "error": None,
                "model": getattr(getattr(llm, "settings", {}), "get", lambda *_: None)("chat_model")
                if not isinstance(getattr(llm, "settings", None), dict)
                else llm.settings.get("chat_model"),
            }
        content = await llm.chat(messages, enable_reasoning=enable_reasoning)
        return {
            "data": parse_json_object(content or ""),
            "content": content or "",
            "reasoning": None,
            "usage": None,
            "duration_ms": int((time.time() - t0) * 1000),
            "ok": True,
            "error": None,
            "model": None,
        }
    except Exception as exc:
        logger.warning("llm_json failed: %s", exc)
        return {
            "data": {},
            "content": "",
            "reasoning": None,
            "usage": None,
            "duration_ms": int((time.time() - t0) * 1000),
            "ok": False,
            "error": str(exc),
        }


def dumps_cards(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
