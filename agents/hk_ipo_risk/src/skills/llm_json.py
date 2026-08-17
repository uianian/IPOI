from __future__ import annotations

import json
import logging
import time
from typing import Any, Sequence

from src.tools.llm_client import parse_json_object

logger = logging.getLogger(__name__)

_JSON_RETRY_NUDGE = (
    "上一轮未产出可解析 JSON（思考可能占满了输出预算）。"
    "请立即只输出一个完整 JSON 对象，不要 Markdown，不要长文推理。"
)


def reasoning_tokens_from_usage(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    details = usage.get("completion_tokens_details") or {}
    if isinstance(details, dict) and details.get("reasoning_tokens") is not None:
        try:
            return int(details.get("reasoning_tokens") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def json_payload_usable(
    data: Any,
    *,
    required_keys: Sequence[str] | None = None,
) -> bool:
    if not isinstance(data, dict) or not data:
        return False
    if not required_keys:
        return True
    return all(key in data for key in required_keys)


def json_output_truncated(
    *,
    data: Any,
    content: str,
    finish_reason: Any,
    usage: Any,
    required_keys: Sequence[str] | None = None,
) -> bool:
    """思考占满 max_tokens / 截断 / 空正文时，不能把空 dict 当成有效 JSON。"""
    if json_payload_usable(data, required_keys=required_keys):
        return False
    if str(finish_reason or "") == "length":
        return True
    rtok = reasoning_tokens_from_usage(usage)
    try:
        ctok = int((usage or {}).get("completion_tokens") or 0) if isinstance(usage, dict) else 0
    except (TypeError, ValueError):
        ctok = 0
    if rtok > 0 and ctok > 0 and rtok >= ctok:
        return True
    if not str(content or "").strip():
        return True
    return True


async def llm_json(
    llm: Any,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 800,
    reasoning_effort: str | None = "low",
    enable_reasoning: bool = True,
    reasoning_max_tokens: int | None = None,
    required_keys: Sequence[str] | None = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Call chat_json-like API; always return data/reasoning/duration_ms/usage.

    DeepSeek 思考计入 max_tokens。空 JSON 或截断不算成功：放大预算再试，
    最后一轮关闭 thinking，避免 conflicts=[] / 终裁缺字段被当成有效判定。
    """
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
            "retries": 0,
            "finish_reason": None,
        }

    keys = tuple(required_keys) if required_keys else None
    last: dict[str, Any] = {}
    attempts = 0
    total = max(1, int(max_attempts))
    try:
        for attempt in range(total):
            attempts = attempt + 1
            if attempt == 0:
                call_tokens = int(max_tokens)
                call_rmax = reasoning_max_tokens
                use_reasoning = bool(enable_reasoning)
                call_messages = messages
            elif attempt == 1 and total >= 3:
                call_tokens = min(int(max_tokens) * 2, 8192)
                call_rmax = reasoning_max_tokens
                use_reasoning = bool(enable_reasoning)
                call_messages = messages
            else:
                # 关掉 thinking 后仍需足够正文预算；不得缩回原 max_tokens。
                call_tokens = min(max(int(max_tokens) * 2, 2048), 8192)
                call_rmax = 0
                use_reasoning = False
                call_messages = list(messages) + [
                    {"role": "user", "content": _JSON_RETRY_NUDGE}
                ]

            last = await _call_llm_json(
                llm,
                call_messages,
                max_tokens=call_tokens,
                reasoning_effort=reasoning_effort,
                enable_reasoning=use_reasoning,
                reasoning_max_tokens=call_rmax,
            )
            data = last.get("data") if isinstance(last.get("data"), dict) else {}
            if json_payload_usable(data, required_keys=keys):
                last["ok"] = True
                last["error"] = None
                last["retries"] = attempts - 1
                last["duration_ms"] = int((time.time() - t0) * 1000)
                return last

            truncated = json_output_truncated(
                data=data,
                content=str(last.get("content") or ""),
                finish_reason=last.get("finish_reason"),
                usage=last.get("usage"),
                required_keys=keys,
            )
            logger.warning(
                "llm_json incomplete attempt=%s/%s truncated=%s finish=%s error=%s",
                attempts,
                total,
                truncated,
                last.get("finish_reason"),
                last.get("error"),
            )
            hard_error = last.get("error")
            if hard_error and hard_error != "empty_json":
                break
        return {
            "data": last.get("data") if isinstance(last.get("data"), dict) else {},
            "content": last.get("content") or "",
            "reasoning": last.get("reasoning"),
            "usage": last.get("usage"),
            "duration_ms": int((time.time() - t0) * 1000),
            "ok": False,
            "error": last.get("error") or "empty_json",
            "model": last.get("model"),
            "retries": max(0, attempts - 1),
            "finish_reason": last.get("finish_reason"),
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
            "retries": max(0, attempts - 1),
            "finish_reason": None,
        }


async def _call_llm_json(
    llm: Any,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    reasoning_effort: str | None,
    enable_reasoning: bool,
    reasoning_max_tokens: int | None,
) -> dict[str, Any]:
    if hasattr(llm, "chat_json"):
        raw = await llm.chat_json(
            messages,
            enable_reasoning=enable_reasoning,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            reasoning_max_tokens=reasoning_max_tokens,
        )
        data = raw.get("data") if isinstance(raw.get("data"), dict) else parse_json_object(raw.get("content") or "")
        data = data if isinstance(data, dict) else {}
        return {
            "data": data,
            "content": raw.get("content") or "",
            "reasoning": raw.get("reasoning"),
            "usage": raw.get("usage"),
            "ok": True,
            "error": None if data else "empty_json",
            "model": _chat_model_name(llm),
            "finish_reason": raw.get("finish_reason"),
        }
    content = await llm.chat(messages, enable_reasoning=enable_reasoning)
    data = parse_json_object(content or "")
    return {
        "data": data or {},
        "content": content or "",
        "reasoning": None,
        "usage": None,
        "ok": True,
        "error": None if data else "empty_json",
        "model": None,
        "finish_reason": None,
    }


def _chat_model_name(llm: Any) -> str | None:
    settings = getattr(llm, "settings", None)
    if isinstance(settings, dict):
        return settings.get("chat_model")
    getter = getattr(settings, "get", None)
    if callable(getter):
        return getter("chat_model")
    return None


def dumps_cards(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
