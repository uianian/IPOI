from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.tools.llm_client import parse_json_action_fallback
from src.tools.schemas import ToolRegistry

logger = logging.getLogger(__name__)


async def run_react_loop(
    *,
    llm: Any,
    tools: ToolRegistry,
    system_prompt: str,
    user_prompt: str,
    state: dict[str, Any],
    run_logger: Any | None = None,
    max_turns: int = 8,
    enable_reasoning: bool = True,
) -> dict[str, Any]:
    """LLM 多轮选工具 → 执行 → 观察，直到 submit 或耗尽轮次。"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    openai_tools = tools.openai_tools()
    turns: list[dict[str, Any]] = []

    for turn in range(1, max_turns + 1):
        t0 = time.time()
        resp = await llm.chat_completion(
            messages,
            temperature=0.0,
            enable_reasoning=enable_reasoning,
            # Tool calls and final finance JSON are compact; keeping this
            # small reduces upstream rate-limit pressure and runaway thinking.
            max_tokens=2048,
            reasoning_max_tokens=256,
            tools=openai_tools,
            tool_choice="auto",
        )
        duration_ms = int((time.time() - t0) * 1000)
        reasoning = resp.get("reasoning")
        content = resp.get("content") or ""
        state["last_reasoning"] = reasoning
        state["last_reasoning_details"] = resp.get("reasoning_details")

        tool_calls = list(resp.get("tool_calls") or [])
        if not tool_calls:
            tool_calls = parse_json_action_fallback(content)

        # 将英文 rawThink 译为繁体+英文混合，供前端 Thought.content 展示
        reasoning_display = None
        if reasoning and str(reasoning).strip():
            try:
                from src.skills.think_translate import translate_think_to_hant_mixed

                reasoning_display = await translate_think_to_hant_mixed(llm, str(reasoning))
            except Exception as exc:
                logger.warning("think translate failed turn=%s: %s", turn, exc)
                reasoning_display = None

        if run_logger is not None:
            run_logger.react_turn(
                turn=turn,
                reasoning=reasoning,
                reasoning_display=reasoning_display,
                content=content,
                tool_calls=[{"name": t.get("name"), "arguments": t.get("arguments")} for t in tool_calls],
                duration_ms=duration_ms,
                usage=resp.get("usage"),
                model=(getattr(llm, "settings", {}) or {}).get("chat_model"),
            )

        if not tool_calls:
            # 提示模型必须调工具
            messages.append({"role": "assistant", "content": content or "(无输出)"})
            messages.append({
                "role": "user",
                "content": (
                    "请通过 function/tool 调用继续：先 retrieve_finance → extract_metrics → "
                    "derive_gates，信息足够后调用 submit_finance_report。不要只输出自然语言。"
                ),
            })
            turns.append({"turn": turn, "status": "no_tool_call", "content": content[:500]})
            continue

        # assistant message with tool_calls (OpenAI format)
        raw_msg = resp.get("raw_message") or {}
        if raw_msg.get("tool_calls"):
            messages.append(raw_msg)
        else:
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            })

        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("arguments") or {}
            obs = await tools.execute(name, args, state)
            turns.append({
                "turn": turn,
                "tool": name,
                "arguments": args,
                "observation": obs,
                "duration_ms": duration_ms,
            })
            if run_logger is not None:
                run_logger.step(
                    name,
                    kind="tool",
                    input_summary=args,
                    output=obs,
                    duration_ms=duration_ms,
                    status="ok" if obs.get("ok", True) else "error",
                    error=obs.get("error"),
                )
            # tool role message
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": name,
                "content": json.dumps(obs, ensure_ascii=False, default=str)[:6000],
            })

            if state.get("finished") and state.get("final_report"):
                return {
                    "ok": True,
                    "report": state["final_report"],
                    "turns": turns,
                    "n_turns": turn,
                }

    # 超时未 submit：若有 metrics，尝试用规则兜底标记
    return {
        "ok": False,
        "error": "max_turns_exceeded_without_submit",
        "turns": turns,
        "n_turns": max_turns,
        "state_keys": list(state.keys()),
    }
