from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.tools.llm_client import parse_json_action_fallback
from src.tools.schemas import ToolRegistry

logger = logging.getLogger(__name__)

# 收束轮抬高输出预算，给 tool JSON 留空间（DeepSeek reasoning 计入 max_tokens）
_SUBMIT_MAX_TOKENS = 4096
_DEFAULT_MAX_TOKENS = 2048
_EMPTY_TOOL_RETRY_NUDGE = (
    "上一轮未发出有效 tool call（可能因思考占满输出预算）。"
    "请立即通过 function/tool 调用下一步工具，禁止只输出自然语言或长文推理。"
    "若证据已齐，直接调用结束工具 submit。"
)
_MISSING_THINK_NUDGE = (
    "上一轮有工具调用但缺少 think/reasoning。"
    "请先用简短中文思考（2-4句说明本步目的与观察），再通过 function/tool 调用工具。"
)
_FINANCE_LLM_SUBMIT_NUDGE = (
    "规则交叉核对已完成且无覆盖缺口。"
    "请立即调用 submit_finance_report，填写完整 dimensions（四维分析）、"
    "reasoning、summary、risk_score 与 score_breakdown；"
    "禁止再 search / run_finance_skill / run_finance_rule_checks。"
)
_LEGAL_LLM_SUBMIT_NUDGE = (
    "规则交叉核对已完成且无覆盖缺口。"
    "请立即调用 submit_legal_report："
    "arguments 必须含非空 summary（一句繁體中文终裁摘要）与非空 reasoning（2-5句风险归因）；"
    "risk_points 可精炼或留空（系统会从 skill 结果填充）；"
    "禁止再 search / run_legal_skill / run_rule_checks；禁止空 arguments {}。"
    "最终参考分仍由规则托底合并。"
)


def _llm_submit_nudge(submit_tool_name: str) -> str:
    if submit_tool_name == "submit_legal_report":
        return _LEGAL_LLM_SUBMIT_NUDGE
    return _FINANCE_LLM_SUBMIT_NUDGE


def _tool_call_reason(tool_calls: list[dict[str, Any]] | None) -> str | None:
    """从 tool arguments.reason / thinking 提取可展示意图（DeepSeek 常无 reasoning）。"""
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        args = tc.get("arguments") or {}
        if not isinstance(args, dict):
            continue
        for key in ("reason", "thinking", "rationale"):
            val = args.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    return None


def _resolve_think_status(
    reasoning: Any,
    content: Any,
    tool_calls: list[dict[str, Any]] | None,
) -> tuple[str, str | None]:
    """返回 (think_status, proxy_text)。

    - ok：有 message.reasoning
    - think_from_content：无 reasoning，但有 content 或 tool.reason（勿误判为检索失败）
    - reasoning_missing：真正空思考
    """
    if reasoning is not None and str(reasoning).strip():
        return "ok", None
    content_s = str(content or "").strip()
    reason = _tool_call_reason(tool_calls)
    proxy = content_s or reason
    if proxy:
        return "think_from_content", proxy
    return "reasoning_missing", None


def _is_submit_ready_turn(state: dict[str, Any], submit_tool_name: str) -> bool:
    """收束轮：财务已有主链路结果；或法务已标记 ready_to_submit。

    prefer_llm_submit 强制 submit 轮也抬高 max_tokens（勿因清 ready 标志掉预算）。
    """
    if state.get("ready_to_submit") or state.get("_force_submit_turn"):
        return True
    if submit_tool_name == "submit_finance_report":
        if not state.get("metrics") or not state.get("gates"):
            return False
        gates = state.get("gates") or {}
        if gates.get("is_unprofitable") and not state.get("cash_burn"):
            return False
        return True
    return False


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
    submit_tool_name: str = "submit_finance_report",
    no_tool_nudge: str | None = None,
    translate_think: bool = True,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    submit_max_tokens: int = _SUBMIT_MAX_TOKENS,
    reasoning_max_tokens: int = 256,
    reasoning_effort: str | None = "low",
) -> dict[str, Any]:
    """LLM 多轮选工具 → 执行 → 观察，直到 submit 或耗尽轮次。

    translate_think=False 时保留模型原始 reasoning（英文亦可），不额外调 LLM 翻译。
    DeepSeek：reasoning_effort 控思考深度；reasoning_max_tokens 仅 OpenRouter 有效。
    prefer_llm_submit：ready_to_submit 后额外给一轮真正的 submit；否则早退由调用方托底。
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    openai_tools = tools.openai_tools()
    turns: list[dict[str, Any]] = []
    empty_tool_retries = 0
    missing_think_retries = 0

    for turn in range(1, max_turns + 1):
        # 上一工具已标 ready_to_submit：默认不再烧 LLM。
        # prefer_llm_submit：额外给一轮真正的 submit_*。
        if state.get("ready_to_submit") and not state.get("finished"):
            if state.get("prefer_llm_submit") and not state.get("_llm_submit_attempted"):
                state["_llm_submit_attempted"] = True
                # 保持 ready_to_submit，并用 _force_submit_turn 抬高 submit_max_tokens；
                # 勿清 ready，否则收束轮仍用默认 2048，reasoning 易挤掉 tool arguments。
                state["_force_submit_turn"] = True
                messages.append(
                    {"role": "user", "content": _llm_submit_nudge(submit_tool_name)}
                )
                logger.info("react_loop prefer_llm_submit: forcing one submit turn")
            else:
                logger.info("react_loop early exit: ready_to_submit (skip further LLM turns)")
                return {
                    "ok": False,
                    "error": "rule_checks_ready",
                    "turns": turns,
                    "n_turns": turn - 1,
                    "ready_to_submit": True,
                    "state_keys": list(state.keys()),
                }

        turn_max_tokens = (
            submit_max_tokens
            if _is_submit_ready_turn(state, submit_tool_name)
            else max_tokens
        )
        t0 = time.time()
        resp = await llm.chat_completion(
            messages,
            temperature=0.0,
            enable_reasoning=enable_reasoning,
            reasoning_effort=reasoning_effort,
            max_tokens=turn_max_tokens,
            reasoning_max_tokens=reasoning_max_tokens,
            tools=openai_tools,
            tool_choice="auto",
        )
        duration_ms = int((time.time() - t0) * 1000)
        reasoning = resp.get("reasoning")
        content = resp.get("content") or ""
        finish_reason = resp.get("finish_reason")
        state["last_reasoning"] = reasoning
        state["last_reasoning_details"] = resp.get("reasoning_details")

        tool_calls = list(resp.get("tool_calls") or [])
        if not tool_calls:
            tool_calls = parse_json_action_fallback(content, submit_tool=submit_tool_name)

        # 中间轮有 tool 但真正缺 think（无 content/tool.reason）：单次轻量重试
        think_status, think_proxy = _resolve_think_status(reasoning, content, tool_calls)
        if (
            enable_reasoning
            and tool_calls
            and think_status == "reasoning_missing"
            and missing_think_retries < 1
            and not state.get("finished")
        ):
            missing_think_retries += 1
            messages.append({
                "role": "assistant",
                "content": content or "(工具调用但缺少 think)",
            })
            messages.append({"role": "user", "content": _MISSING_THINK_NUDGE})
            turns.append({
                "turn": turn,
                "status": "reasoning_missing_retry",
                "think_status": "reasoning_missing",
                "tool": (tool_calls[0] or {}).get("name"),
                "finish_reason": finish_reason,
            })
            logger.info("react_loop missing-think retry turn=%s", turn)
            if run_logger is not None:
                run_logger.react_turn(
                    turn=turn,
                    reasoning=None,
                    reasoning_display=None,
                    content=content,
                    tool_calls=[
                        {"name": t.get("name"), "arguments": t.get("arguments")}
                        for t in tool_calls
                    ],
                    duration_ms=duration_ms,
                    usage=resp.get("usage"),
                    model=(getattr(llm, "settings", {}) or {}).get("chat_model"),
                    think_status="reasoning_missing",
                )
            continue

        if think_status == "reasoning_missing" and tool_calls:
            think_status = "reasoning_missing_after_retry"

        # 默认：英文 think → 繁中混合展示；translate_think=False 时直接保留原文
        # think_from_content：用 content/tool.reason 作展示，不走翻译 LLM
        reasoning_display = None
        if think_status == "ok" and reasoning and str(reasoning).strip():
            if not translate_think:
                reasoning_display = str(reasoning)
            else:
                try:
                    from src.skills.think_translate import translate_think_to_hant_mixed

                    reasoning_display = await translate_think_to_hant_mixed(llm, str(reasoning))
                except Exception as exc:
                    logger.warning("think translate failed turn=%s: %s", turn, exc)
                    reasoning_display = str(reasoning)
        elif think_status == "think_from_content" and think_proxy:
            reasoning_display = think_proxy[:800]

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
                think_status=think_status,
            )

        if not tool_calls:
            truncated = finish_reason == "length" or bool(
                reasoning and str(reasoning).strip()
            )
            messages.append({"role": "assistant", "content": content or "(无输出)"})
            if truncated and empty_tool_retries < 1:
                empty_tool_retries += 1
                nudge = (
                    f"{_EMPTY_TOOL_RETRY_NUDGE} 结束工具名：{submit_tool_name}。"
                )
                messages.append({"role": "user", "content": nudge})
                turns.append({
                    "turn": turn,
                    "status": "no_tool_call_retry",
                    "content": content[:500],
                    "finish_reason": finish_reason,
                })
                logger.info(
                    "react_loop empty tool retry turn=%s finish_reason=%s",
                    turn,
                    finish_reason,
                )
                continue
            messages.append({
                "role": "user",
                "content": no_tool_nudge or (
                    "请通过 function/tool 调用继续：先 retrieve_finance → extract_metrics → "
                    "derive_gates，信息足够后调用 submit_finance_report。不要只输出自然语言。"
                ),
            })
            turns.append({
                "turn": turn,
                "status": "no_tool_call",
                "content": content[:500],
                "finish_reason": finish_reason,
            })
            continue

        # assistant message with tool_calls（DeepSeek 思考模式必须回传 reasoning_content）
        raw_msg = resp.get("raw_message") or {}
        if raw_msg.get("tool_calls"):
            messages.append(raw_msg)
        else:
            assistant_msg: dict[str, Any] = {
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
            }
            if reasoning and str(reasoning).strip():
                assistant_msg["reasoning_content"] = str(reasoning)
            messages.append(assistant_msg)

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
                "think_status": think_status,
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

            # 无缺口：prefer_llm_submit 则进入下一轮强制 submit；否则早退托底
            if state.get("ready_to_submit") and not state.get("finished"):
                if state.get("prefer_llm_submit") and not state.get(
                    "_llm_submit_attempted"
                ):
                    logger.info(
                        "react_loop will force llm submit after tool=%s turn=%s",
                        name,
                        turn,
                    )
                    break  # 跳出 tool_calls，进入下一 turn
                logger.info(
                    "react_loop ready_to_submit after tool=%s turn=%s",
                    name,
                    turn,
                )
                return {
                    "ok": False,
                    "error": "rule_checks_ready",
                    "turns": turns,
                    "n_turns": turn,
                    "ready_to_submit": True,
                    "state_keys": list(state.keys()),
                }

    # 超时未 submit：若有 metrics，尝试用规则兜底标记
    return {
        "ok": False,
        "error": "max_turns_exceeded_without_submit",
        "turns": turns,
        "n_turns": max_turns,
        "state_keys": list(state.keys()),
    }
