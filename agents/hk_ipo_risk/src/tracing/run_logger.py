from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


EventCallback = Callable[[dict[str, Any]], None]


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", (text or "doc").strip(), flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_") or "doc"
    return s[:max_len]


def _trunc(obj: Any, max_chars: int = 2000) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        t = obj
    else:
        try:
            t = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        except TypeError:
            t = str(obj)
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


class AgentRunLogger:
    """人类可读 .log + 结构化 .jsonl，覆盖赛题推理链路审计。"""

    def __init__(
        self,
        *,
        agent: str,
        doc_id: str,
        log_dir: Path | str,
        issuer_type: str = "general",
        doc_name: str | None = None,
        pdf_name: str | None = None,
        max_segment_chars: int = 2000,
        on_event: EventCallback | None = None,
    ) -> None:
        self.agent = agent
        self.doc_id = doc_id
        self.issuer_type = issuer_type
        self.doc_name = doc_name
        self.pdf_name = pdf_name
        self.max_segment_chars = max_segment_chars
        self.on_event = on_event
        self.run_id = str(uuid.uuid4())
        self.started_at = datetime.now()
        self._steps: list[dict[str, Any]] = []
        self._closed = False

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        ts = self.started_at.strftime("%Y%m%d_%H%M%S")
        slug = _slug(doc_name or doc_id)
        stem = f"{slug}_{agent}_{ts}"
        self.log_path = self.log_dir / f"{stem}.log"
        self.jsonl_path = self.log_dir / f"{stem}.jsonl"

        self._log_fp = self.log_path.open("w", encoding="utf-8")
        self._jsonl_fp = self.jsonl_path.open("w", encoding="utf-8")
        self._write_header()

    def _emit(self, event: dict[str, Any], text_block: str) -> None:
        event = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "run_id": self.run_id,
            "agent": self.agent,
            "doc_id": self.doc_id,
            **event,
        }
        self._jsonl_fp.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        self._jsonl_fp.flush()
        self._log_fp.write(text_block)
        if not text_block.endswith("\n"):
            self._log_fp.write("\n")
        self._log_fp.flush()
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:
                pass

    def _write_header(self) -> None:
        lines = [
            f"# Agent Run Log — {self.agent}",
            "",
            "## 时间",
            f"- run_id: `{self.run_id}`",
            f"- started_at: `{self.started_at.isoformat(timespec='seconds')}`",
            "",
            "## 文档基本信息",
            f"- doc_id: `{self.doc_id}`",
            f"- issuer_type: `{self.issuer_type}`",
            f"- doc_name: `{self.doc_name or '—'}`",
            f"- pdf_name: `{self.pdf_name or '—'}`",
            "",
            "## Agent 处理流程",
            "预期步骤: retrieve → extract_metrics → gates → analyze_finance(LLM|rules) → compose_result",
            "",
            "---",
            "",
        ]
        self._emit(
            {
                "event": "run_start",
                "doc_name": self.doc_name,
                "pdf_name": self.pdf_name,
                "issuer_type": self.issuer_type,
            },
            "\n".join(lines),
        )

    def step(
        self,
        name: str,
        *,
        kind: str = "skill",
        status: str = "ok",
        input_summary: Any = None,
        output: Any = None,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        """记录工具 / skill / helper 一步。"""
        idx = len(self._steps) + 1
        rec = {
            "event": "step",
            "step_index": idx,
            "name": name,
            "kind": kind,
            "status": status,
            "duration_ms": duration_ms,
            "error": error,
            "input_summary": input_summary,
            "output": output,
        }
        self._steps.append(rec)
        block = [
            f"### [{idx}] {kind}: `{name}` — {status}",
            f"- time: `{datetime.now().isoformat(timespec='seconds')}`",
        ]
        if duration_ms is not None:
            block.append(f"- duration_ms: `{duration_ms}`")
        if error:
            block.append(f"- error: {error}")
        if input_summary is not None:
            block.append("- 入参摘要:")
            block.append("```")
            block.append(_trunc(input_summary, self.max_segment_chars))
            block.append("```")
        if output is not None:
            block.append("- 过程输出:")
            block.append("```")
            block.append(_trunc(output, self.max_segment_chars))
            block.append("```")
        block.append("")
        self._emit(rec, "\n".join(block))

    def react_turn(
        self,
        *,
        turn: int,
        reasoning: str | None = None,
        reasoning_display: str | None = None,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        duration_ms: int | None = None,
        usage: dict[str, Any] | None = None,
        model: str | None = None,
        think_status: str | None = None,
    ) -> None:
        """记录 ReAct 一轮：thought + 拟调用工具。"""
        idx = len(self._steps) + 1
        if think_status is None:
            if reasoning:
                think_status = "ok"
            elif content and str(content).strip():
                think_status = "think_from_content"
            else:
                # tool.reason 兜底
                has_reason = False
                for tc in tool_calls or []:
                    args = (tc or {}).get("arguments") if isinstance(tc, dict) else None
                    if isinstance(args, dict) and any(
                        str(args.get(k) or "").strip() for k in ("reason", "thinking", "rationale")
                    ):
                        has_reason = True
                        break
                think_status = "think_from_content" if has_reason else "reasoning_missing"
        rec = {
            "event": "react_turn",
            "step_index": idx,
            "turn": turn,
            "kind": "react",
            "think_status": think_status,
            "model": model,
            "duration_ms": duration_ms,
            "usage": usage,
            "content": content,
            "reasoning": reasoning,
            "reasoning_display": reasoning_display,
            "tool_calls": tool_calls or [],
        }
        self._steps.append(rec)
        block = [
            f"### [{idx}] react turn={turn} (think={think_status})",
            f"- time: `{datetime.now().isoformat(timespec='seconds')}`",
            f"- model: `{model or '—'}`",
        ]
        if duration_ms is not None:
            block.append(f"- duration_ms: `{duration_ms}`")
        if usage:
            block.append(f"- usage: `{json.dumps(usage, ensure_ascii=False)}`")
        block.append("")
        block.append("##### [model_think]")
        if reasoning:
            block.append("```")
            block.append(reasoning)
            block.append("```")
        elif think_status == "think_from_content":
            block.append("_think_from_content（无 message.reasoning，见 content / tool.reason）_")
        else:
            block.append("_reasoning_missing_")
        if reasoning_display:
            block.append("")
            block.append("##### [model_think_display 繁英混合]")
            block.append("```")
            block.append(reasoning_display)
            block.append("```")
        block.append("")
        block.append("##### planned tool_calls")
        block.append("```json")
        block.append(_trunc(tool_calls or [], self.max_segment_chars))
        block.append("```")
        if content:
            block.append("")
            block.append("##### content")
            block.append("```")
            block.append(_trunc(content, self.max_segment_chars))
            block.append("```")
        block.append("")
        self._emit(rec, "\n".join(block))

    def llm_turn(
        self,
        *,
        model: str | None = None,
        prompt_chars: int | None = None,
        content: str | None = None,
        reasoning: str | None = None,
        reasoning_details: Any = None,
        structured_reasoning: str | None = None,
        duration_ms: int | None = None,
        usage: dict[str, Any] | None = None,
        status: str = "ok",
        error: str | None = None,
    ) -> None:
        """记录 LLM 调用与推理链（区分 model_think / structured_reasoning）。"""
        idx = len(self._steps) + 1
        think_status = "ok" if reasoning else "reasoning_missing"
        rec = {
            "event": "llm_turn",
            "step_index": idx,
            "name": "analyze_finance_llm",
            "kind": "llm",
            "status": status,
            "think_status": think_status,
            "model": model,
            "duration_ms": duration_ms,
            "usage": usage,
            "error": error,
            "prompt_chars": prompt_chars,
            "content": content,
            "reasoning": reasoning,
            "reasoning_details": reasoning_details,
            "structured_reasoning": structured_reasoning,
        }
        self._steps.append(rec)
        block = [
            f"### [{idx}] llm: `analyze_finance` — {status} (think={think_status})",
            f"- time: `{datetime.now().isoformat(timespec='seconds')}`",
            f"- model: `{model or '—'}`",
        ]
        if duration_ms is not None:
            block.append(f"- duration_ms: `{duration_ms}`")
        if usage:
            block.append(f"- usage: `{json.dumps(usage, ensure_ascii=False)}`")
        if prompt_chars is not None:
            block.append(f"- prompt_chars: `{prompt_chars}`")
        if error:
            block.append(f"- error: {error}")

        block.append("")
        block.append("#### 过程输出 (model content)")
        block.append("```")
        block.append(_trunc(content or "", self.max_segment_chars * 2))
        block.append("```")

        block.append("")
        block.append("#### 推理链输出")
        block.append("")
        block.append("##### [model_think]（OpenRouter message.reasoning）")
        if reasoning:
            block.append("```")
            block.append(reasoning)  # 全文，不截断
            block.append("```")
        else:
            block.append("_reasoning_missing：provider 未返回 message.reasoning_")

        if reasoning_details:
            block.append("")
            block.append("##### [reasoning_details]")
            block.append("```json")
            block.append(_trunc(reasoning_details, self.max_segment_chars * 2))
            block.append("```")

        block.append("")
        block.append("##### [structured_reasoning]（JSON 内 reasoning 字段）")
        if structured_reasoning:
            block.append("```")
            block.append(structured_reasoning)
            block.append("```")
        else:
            block.append("_无 structured_reasoning_")
        block.append("")
        self._emit(rec, "\n".join(block))

    def debate_question(
        self,
        *,
        round: int,
        question_id: str,
        target_agent: str,
        utterance: str,
        claim_id: str | None = None,
        theme: str = "",
        duration_ms: int | None = None,
        reasoning: str | None = None,
        usage: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> None:
        rec = {
            "event": "debate_question",
            "round": round,
            "question_id": question_id,
            "target_agent": target_agent,
            "claim_id": claim_id,
            "theme": theme,
            "utterance": utterance,
            "duration_ms": duration_ms,
            "reasoning": reasoning,
            "think_status": "ok" if reasoning else "think_from_content",
            "usage": usage,
            "model": model,
        }
        block = [
            f"### debate_question r{round} → {target_agent} `{question_id}`",
            f"- duration_ms: `{duration_ms}`",
            "",
            utterance,
            "",
        ]
        if reasoning:
            block.extend(["##### [model_think]", "```", reasoning, "```", ""])
        self._emit(rec, "\n".join(block))

    def debate_search(
        self,
        *,
        round: int,
        question_id: str,
        target_agent: str,
        tool_calls: list[dict[str, Any]],
        evidence: list[dict[str, Any]] | None = None,
        duration_ms: int | None = None,
        search_hit_count: int = 0,
    ) -> None:
        rec = {
            "event": "debate_search",
            "round": round,
            "question_id": question_id,
            "target_agent": target_agent,
            "tool_calls": tool_calls,
            "evidence": evidence or [],
            "duration_ms": duration_ms,
            "search_hit_count": search_hit_count,
        }
        block = [
            f"### debate_search r{round} {target_agent} hits={search_hit_count} `{duration_ms}ms`",
            "```json",
            _trunc(tool_calls, self.max_segment_chars),
            "```",
            "",
        ]
        self._emit(rec, "\n".join(block))

    def debate_reply(
        self,
        *,
        round: int,
        question_id: str,
        target_agent: str,
        utterance: str,
        status: str = "unresolved",
        confidence: float | None = None,
        duration_ms: int | None = None,
        reasoning: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        new_queries: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> None:
        rec = {
            "event": "debate_reply",
            "round": round,
            "question_id": question_id,
            "target_agent": target_agent,
            "utterance": utterance,
            "status": status,
            "confidence": confidence,
            "duration_ms": duration_ms,
            "reasoning": reasoning,
            "think_status": "ok" if reasoning else ("think_from_content" if utterance else "reasoning_missing"),
            "tool_calls": tool_calls or [],
            "evidence": evidence or [],
            "new_queries": new_queries or [],
            "usage": usage,
            "model": model,
        }
        block = [
            f"### debate_reply r{round} {target_agent} status={status} `{duration_ms}ms`",
            utterance or "_empty reply_",
            "",
        ]
        if reasoning:
            block.extend(["##### [model_think]", "```", reasoning, "```", ""])
        self._emit(rec, "\n".join(block))

    def master_step(
        self,
        *,
        event: str,
        utterance: str = "",
        duration_ms: int | None = None,
        reasoning: str | None = None,
        usage: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> None:
        rec = {
            "event": event,
            "utterance": utterance,
            "duration_ms": duration_ms,
            "reasoning": reasoning,
            "think_status": "ok" if reasoning else ("think_from_content" if utterance else "reasoning_missing"),
            "usage": usage,
            "model": model,
            **(extra or {}),
        }
        block = [
            f"### {event} `{duration_ms}ms`",
            utterance[:2000] if utterance else "",
            "",
        ]
        if reasoning:
            block.extend(["##### [model_think]", "```", reasoning, "```", ""])
        self._emit(rec, "\n".join(block))

    def result(self, payload: dict[str, Any]) -> None:
        """结果输出区块。"""
        rec = {"event": "result", "payload": payload}
        block = [
            "## 结果输出",
            f"- time: `{datetime.now().isoformat(timespec='seconds')}`",
            "```json",
            _trunc(payload, self.max_segment_chars * 2),
            "```",
            "",
        ]
        self._emit(rec, "\n".join(block))

    def close(self, *, final_summary: str | None = None) -> Path:
        if self._closed:
            return self.log_path
        ended = datetime.now()
        elapsed = (ended - self.started_at).total_seconds()
        block = [
            "---",
            "",
            "## 结束",
            f"- ended_at: `{ended.isoformat(timespec='seconds')}`",
            f"- elapsed_sec: `{elapsed:.3f}`",
            f"- steps: `{len(self._steps)}`",
        ]
        if final_summary:
            block.append(f"- summary: {final_summary}")
        block.append("")
        block.append(f"_log_path: `{self.log_path}`_")
        block.append(f"_jsonl_path: `{self.jsonl_path}`_")
        block.append("")
        self._emit(
            {
                "event": "run_end",
                "elapsed_sec": elapsed,
                "steps": len(self._steps),
                "summary": final_summary,
                "log_path": str(self.log_path),
                "jsonl_path": str(self.jsonl_path),
            },
            "\n".join(block),
        )
        self._log_fp.close()
        self._jsonl_fp.close()
        self._closed = True
        return self.log_path

    @property
    def paths(self) -> dict[str, str]:
        return {"log": str(self.log_path), "jsonl": str(self.jsonl_path)}
