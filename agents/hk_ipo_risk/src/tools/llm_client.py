from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    """轻量 OpenAI/OpenRouter 兼容客户端；支持 Gemma4 reasoning tokens。"""

    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings
        self._client: httpx.AsyncClient | None = None

    async def init(self) -> None:
        headers = {"Content-Type": "application/json"}
        key = self.settings.get("api_key") or ""
        if key:
            headers["Authorization"] = f"Bearer {key}"
        if self.settings.get("provider") == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/ipo-risk-agent"
            headers["X-Title"] = "hk_ipo_risk"
        # reasoning 可能较长，超时放宽
        timeout = int(self.settings.get("timeout_seconds") or 60)
        self._client = httpx.AsyncClient(
            base_url=self.settings["api_base"],
            timeout=max(timeout, 120),
            headers=headers,
            verify=False,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def available(self) -> bool:
        return bool(self.settings.get("api_key"))

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        enable_reasoning: bool = True,
        reasoning_effort: str | None = None,
        max_tokens: int | None = None,
        reasoning_max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """返回 content + reasoning + tool_calls（Gemma4/OpenRouter）。"""
        if not self._client:
            raise RuntimeError("LLMClient not initialized")
        if not self.available:
            raise RuntimeError("No API key configured")

        # 财务 JSON 需要足够 completion 空间；reasoning 必须单独限预算，否则会吃光 max_tokens
        out_tokens = int(max_tokens if max_tokens is not None else self.settings.get("max_tokens") or 8192)
        payload: dict[str, Any] = {
            "model": self.settings["chat_model"],
            "messages": messages,
            "temperature": temperature if temperature is not None else self.settings.get("temperature", 0.0),
            "max_tokens": out_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice if tool_choice is not None else "auto"
        if enable_reasoning:
            # OpenRouter：effort 与 max_tokens 互斥，优先用 max_tokens 限制 think 预算
            rmax = reasoning_max_tokens
            if rmax is None:
                rmax = self.settings.get("reasoning_max_tokens", 1024)
            reasoning_cfg: dict[str, Any] = {
                "enabled": True,
                "exclude": False,
            }
            if rmax is not None:
                reasoning_cfg["max_tokens"] = int(rmax)
            else:
                effort = reasoning_effort or self.settings.get("reasoning_effort") or "low"
                reasoning_cfg["effort"] = effort
            payload["reasoning"] = reasoning_cfg

        last_err: Exception | None = None
        max_retries = int(self.settings.get("max_retries", 5))
        for attempt in range(max_retries):
            try:
                resp = await self._client.post("/chat/completions", json=payload)
                if resp.status_code == 429:
                    last_err = RuntimeError(f"HTTP 429: {resp.text[:300]}")
                    wait = min(30, 2 ** (attempt + 1))
                    logger.warning("LLM rate-limited 429, sleep %ss attempt=%s", wait, attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                    logger.warning("LLM chat failed attempt=%s: %s", attempt + 1, last_err)
                    await asyncio.sleep(1)
                    continue
                data = resp.json()
                msg = (data.get("choices") or [{}])[0].get("message") or {}
                reasoning = msg.get("reasoning")
                if not reasoning and isinstance(msg.get("reasoning_details"), list):
                    parts = []
                    for d in msg["reasoning_details"]:
                        if isinstance(d, dict):
                            parts.append(str(d.get("text") or d.get("content") or d.get("summary") or ""))
                        else:
                            parts.append(str(d))
                    reasoning = "\n".join(p for p in parts if p) or None
                tool_calls = normalize_tool_calls(msg)
                return {
                    "content": msg.get("content") or "",
                    "reasoning": reasoning,
                    "reasoning_details": msg.get("reasoning_details") or [],
                    "tool_calls": tool_calls,
                    "usage": data.get("usage"),
                    "raw_message": msg,
                }
            except Exception as e:
                last_err = e
                logger.warning("LLM chat failed attempt=%s: %s", attempt + 1, e)
                await asyncio.sleep(1)
        raise RuntimeError(f"LLM chat failed: {last_err}")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        *,
        enable_reasoning: bool = False,
    ) -> str:
        """兼容旧接口：仅返回 content 字符串。"""
        result = await self.chat_completion(
            messages,
            temperature=temperature,
            enable_reasoning=enable_reasoning,
        )
        return result.get("content") or ""

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        *,
        enable_reasoning: bool = True,
        reasoning_effort: str | None = None,
        max_tokens: int | None = None,
        reasoning_max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """解析 JSON content，并附带 reasoning* 字段。"""
        result = await self.chat_completion(
            messages,
            temperature=0.0,
            enable_reasoning=enable_reasoning,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            reasoning_max_tokens=reasoning_max_tokens,
        )
        parsed = parse_json_object(result.get("content") or "")
        return {
            "data": parsed,
            "content": result.get("content") or "",
            "reasoning": result.get("reasoning"),
            "reasoning_details": result.get("reasoning_details") or [],
            "usage": result.get("usage"),
            "raw_message": result.get("raw_message") or {},
        }


def normalize_tool_calls(msg: dict[str, Any]) -> list[dict[str, Any]]:
    """统一为 [{id, name, arguments: dict}]。"""
    raw = msg.get("tool_calls") or []
    out: list[dict[str, Any]] = []
    for i, tc in enumerate(raw):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        name = fn.get("name") or tc.get("name") or ""
        args_raw = fn.get("arguments") if "function" in tc else tc.get("arguments")
        args: dict[str, Any]
        if isinstance(args_raw, dict):
            args = args_raw
        elif isinstance(args_raw, str):
            try:
                args = json.loads(args_raw) if args_raw.strip() else {}
            except json.JSONDecodeError:
                args = {}
        else:
            args = {}
        out.append({
            "id": tc.get("id") or f"call_{i}",
            "name": name,
            "arguments": args,
        })
    return out


def parse_json_action_fallback(content: str) -> list[dict[str, Any]]:
    """当模型不返回 tool_calls 时，尝试解析 JSON action。"""
    obj = parse_json_object(content or "")
    if not obj:
        return []
    # submit 整包
    if "risk_score" in obj and "summary" in obj:
        return [{"id": "fallback_submit", "name": "submit_finance_report", "arguments": obj}]
    name = obj.get("tool") or obj.get("action") or obj.get("name")
    if not name:
        return []
    args = obj.get("arguments") or obj.get("args") or obj.get("parameters") or {}
    if not isinstance(args, dict):
        args = {}
    # 允许扁平字段
    if not args:
        args = {k: v for k, v in obj.items() if k not in {"tool", "action", "name", "arguments", "args", "parameters"}}
    return [{"id": "fallback_0", "name": str(name), "arguments": args}]


def parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    # strip markdown fences if model wraps JSON
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}
