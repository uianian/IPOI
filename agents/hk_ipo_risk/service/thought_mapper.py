"""内部 Agent 事件 → 契约 Thought（繁体 content + 双语 reasoning + meta）。"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

try:
    import zhconv
except ImportError:  # pragma: no cover
    zhconv = None  # type: ignore

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def to_zh_hant(text: str) -> str:
    if not text:
        return ""
    if zhconv is None:
        return text
    try:
        return zhconv.convert(text, "zh-hant")
    except Exception:
        return text


def _mostly_english(text: str) -> bool:
    if not text or not text.strip():
        return False
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if latin == 0:
        return False
    return latin >= max(12, cjk * 2)


def _norm_cmp(a: str | None, b: str | None) -> bool:
    """比较两段文案是否实质相同（忽略空白与简繁）。"""
    if not a or not b:
        return False
    sa = re.sub(r"\s+", "", to_zh_hant(a.strip()))
    sb = re.sub(r"\s+", "", to_zh_hant(b.strip()))
    return bool(sa) and sa == sb


def _agent_id(raw: str | None) -> str:
    a = (raw or "").lower()
    if a in {"finance", "financial"}:
        return "financial"
    if a == "legal":
        return "legal"
    if a == "market":
        return "market"
    if a in {"orchestrator", "master"}:
        return "orchestrator"
    return a or "financial"


def category_for_agent_id(agent_id: str) -> str:
    return {
        "financial": "finance",
        "legal": "legal",
        "market": "market",
        "orchestrator": "master",
    }.get(agent_id, agent_id)


def _labels():
    """延迟导入，避免 service 启动时 path 未就绪。"""
    try:
        from src.skills.finance_labels import (
            format_metrics_block,
            format_tables_block,
            metrics_to_display,
            tables_to_display,
        )

        return format_metrics_block, format_tables_block, metrics_to_display, tables_to_display
    except Exception:
        return None, None, None, None


def _snip_evidence(items: list[dict[str, Any]] | None, limit: int = 12) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        st = it.get("sourceType") or it.get("source_type") or "unknown"
        if st not in {"table", "text", "title", "unknown"}:
            st = "unknown"
        out.append(
            {
                "page": it.get("page"),
                "excerpt": it.get("excerpt") or it.get("content") or "",
                "sourceType": st,
                "category": it.get("category"),
                "fieldCode": it.get("fieldCode") or it.get("field_code"),
                "sectionId": it.get("sectionId") or it.get("section_id") or it.get("section"),
                "confidence": it.get("confidence") or it.get("score"),
            }
        )
        if len(out) >= limit:
            break
    return out


def new_thought(
    *,
    agent_id: str,
    typ: str,
    content: str,
    ref: str | None = None,
    meta: dict[str, Any] | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    t: dict[str, Any] = {
        "id": f"th_{uuid.uuid4().hex[:12]}",
        "agentId": _agent_id(agent_id),
        "type": typ,
        "content": to_zh_hant(content),
        "timestamp": int(time.time() * 1000),
    }
    if ref:
        t["ref"] = ref
    if meta:
        t["meta"] = meta
    if category:
        t["category"] = category
    return t


# 兼容旧名
_new_thought = new_thought


def _tool_reason(args: Any) -> str | None:
    if isinstance(args, dict):
        for k in ("reason", "query", "intent"):
            v = args.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _bilingual_think(
    *,
    turn: Any,
    tool_names: list[str],
    reasoning: str,
    reason_zh: str | None,
    reasoning_display: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    模型内部 reasoning → 前端 Thought.content：

    - content = rawThink 展示版（英翻中：繁体为主 + 英文术语保留）
    - meta.rawThink = 英文/原文
    - 不再用「第 N 輪 / tool reason」模板顶替思考内容
    """
    meta: dict[str, Any] = {"kind": "model_think"}
    raw = (reasoning or "").strip()
    display = (reasoning_display or "").strip()

    if raw:
        meta["rawThink"] = raw

    # 优先：ReAct 已完成的英翻中混合文案
    if display:
        return to_zh_hant(display), meta

    # 中文思考：转繁体即可
    if raw and not _mostly_english(raw):
        return to_zh_hant(raw), meta

    # 英文但翻译失败：兜底「繁体意图 + 英文原文」
    if raw and _mostly_english(raw):
        reason_hant = to_zh_hant(reason_zh) if reason_zh else None
        if reason_hant and not _norm_cmp(reason_hant, raw):
            return f"{reason_hant}\n\n{raw}", meta
        return raw, meta

    tools_s = "、".join(tool_names) if tool_names else "後續工具"
    reason_hant = to_zh_hant(reason_zh) if reason_zh else None
    if reason_hant:
        return reason_hant, meta
    return f"第 {turn} 輪推理：計劃調用 {tools_s}", meta


def _format_gates_block(gates: dict[str, Any] | None) -> str:
    if not isinstance(gates, dict) or not gates:
        return ""
    labels = {
        "is_unprofitable": "是否未盈利",
        "continuous_net_loss": "是否連續虧損",
        "latest_full_year_loss": "最近完整年度是否虧損",
        "skip_3_4": "是否跳過現金跑道評估",
        "skip_3_4_reason": "跳過原因",
        "issuer_type": "發行人類型",
        "is_biotech_18a": "是否18A生物科技",
        "profitability_status": "盈利狀態",
        "profitability_basis": "盈利判定依據",
    }
    lines = ["【門控結果】"]
    for k, lab in labels.items():
        if k not in gates:
            continue
        v = gates[k]
        if isinstance(v, bool):
            v = "是" if v else "否"
        lines.append(f"- {lab}（{k}）：{v}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _format_cash_runway(out: dict[str, Any]) -> str:
    lines = ["【現金跑道】"]
    cb = out.get("cash_burn") if isinstance(out.get("cash_burn"), dict) else out
    mapping = [
        ("CASH_RUNWAY_MONTHS", "現金跑道（月）"),
        ("runway_months", "現金跑道（月）"),
        ("BURN_RATE_MONTHLY", "月均現金消耗"),
        ("burn_rate_monthly", "月均現金消耗"),
        ("END_CASH", "期末現金"),
        ("cash_eq", "現金及現金等價物"),
        ("skipped", "是否跳過"),
        ("reason", "說明"),
        ("method", "測算方法"),
    ]
    seen_labs: set[str] = set()
    for key, lab in mapping:
        if key not in cb or cb[key] is None:
            continue
        if lab in seen_labs:
            continue
        seen_labs.add(lab)
        val = cb[key]
        if key == "skipped" and isinstance(val, bool):
            val = "是" if val else "否"
        lines.append(f"- {lab}：{val}")
    return "\n".join(lines) if len(lines) > 1 else "現金跑道計算完成"


def _finance_tool_content(
    name: str,
    status: str,
    out: Any,
    reason: str | None,
) -> tuple[str, dict[str, Any]]:
    """
    工具步骤 content：动作摘要 + 结构化结果（不把 reason 再写一遍）。
    额外字段放入 extra_meta（tables/metrics）。
    """
    extra: dict[str, Any] = {}
    fmt_metrics, fmt_tables, metrics_to_disp, tables_to_disp = _labels()

    if status == "running":
        # reason 只放 toolArgs，不进 content，避免与 model_think 重复
        return f"正在調用工具 `{name}`…", extra

    if not isinstance(out, dict):
        return f"工具 `{name}` 完成（{status}）", extra

    if name == "retrieve_finance":
        detail = out.get("tables_detail") or []
        if tables_to_disp:
            extra["tables"] = tables_to_disp(detail)
        if fmt_tables:
            block = fmt_tables(detail)
        else:
            codes = out.get("tables") or [t.get("code") for t in detail]
            block = "定位主表：" + "、".join(str(c) for c in codes if c)
        return f"`retrieve_finance` 完成\n{block}", extra

    if name == "extract_metrics":
        raw = out.get("metrics_summary") if isinstance(out.get("metrics_summary"), dict) else {}
        # 兼容旧字段 / 别名
        if "NET_PROFIT_OR_LOSS" in raw and "NET_LOSS" not in raw:
            raw = {**raw, "NET_LOSS": raw["NET_PROFIT_OR_LOSS"]}
        if metrics_to_disp and raw:
            extra["metrics"] = metrics_to_disp(raw)
        detail = out.get("tables_detail")
        if detail and tables_to_disp:
            extra["tables"] = tables_to_disp(detail)
        if fmt_metrics and raw:
            block = fmt_metrics(raw)
        else:
            keys = out.get("metric_keys_zh") or out.get("metric_keys") or []
            if isinstance(keys, list) and keys and isinstance(keys[0], dict):
                block = "已抽取：" + "、".join(
                    f"{k.get('nameZh')}({k.get('code')})" for k in keys[:16]
                )
            else:
                block = f"已抽取 {len(keys)} 項指標"
        note = out.get("metric_note")
        if note:
            block = f"{block}\n（{to_zh_hant(str(note))}）"
        return f"`extract_metrics` 完成\n{block}", extra

    if name == "derive_gates":
        gates = out.get("gates") if isinstance(out.get("gates"), dict) else out
        block = _format_gates_block(gates if isinstance(gates, dict) else {})
        extra["gates"] = gates if isinstance(gates, dict) else None
        fp = out.get("fast_path") if isinstance(out.get("fast_path"), dict) else None
        if fp:
            elig = fp.get("eligible")
            block = (block + "\n" if block else "") + (
                f"【快捷路徑】eligible={'是' if elig else '否'}"
                + (f"：{fp.get('reason')}" if fp.get("reason") else "")
            )
        return f"`derive_gates` 完成\n{block or '門控已計算'}", extra

    if name == "calc_cash_runway":
        block = _format_cash_runway(out)
        cb = out.get("cash_burn") if isinstance(out.get("cash_burn"), dict) else out
        extra["cashRunway"] = cb
        return f"`calc_cash_runway` 完成\n{block}", extra

    if name == "submit_finance_report":
        score = out.get("risk_score")
        level = out.get("risk_level")
        summary = out.get("summary")
        parts = [f"`submit_finance_report` 完成"]
        if score is not None:
            parts.append(f"風險分 {score}" + (f"（{level}）" if level else ""))
        if summary:
            parts.append(to_zh_hant(str(summary)))
        return "\n".join(parts), extra

    if name == "run_finance_skill":
        skill = out.get("skill") or ""
        n = out.get("risk_point_count")
        parts = ["`run_finance_skill` 完成"]
        if skill:
            parts.append(f"skill=`{skill}`")
        if n is not None:
            parts.append(f"風險點 {n}")
        return "\n".join(parts), extra

    if name == "run_finance_rule_checks":
        score = out.get("risk_score")
        hints = out.get("coverage_hints") or []
        parts = ["`run_finance_rule_checks` 完成"]
        if score is not None:
            parts.append(f"參考分 {score}")
        if hints:
            parts.append(f"覆蓋缺口 {len(hints)}")
        elif out.get("ready_to_submit") or out.get("finished"):
            parts.append("無缺口／可交卷")
        return "\n".join(parts), extra

    hint = out.get("hint") or out.get("summary")
    if hint and not (reason and _norm_cmp(str(hint), reason)):
        return f"工具 `{name}` 完成（{status}）\n{to_zh_hant(str(hint))}", extra
    return f"工具 `{name}` 完成（{status}）", extra


def map_finance_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    """财务 AgentRunLogger jsonl 事件 → Thought[]。"""
    thoughts: list[dict[str, Any]] = []
    agent_id = "financial"
    ev = event.get("event")

    if ev == "react_turn":
        turn = event.get("turn") or event.get("step_index") or "?"
        reasoning = (event.get("reasoning") or "").strip()
        reasoning_display = (event.get("reasoning_display") or "").strip() or None
        tool_calls = event.get("tool_calls") or []
        tool_names = [
            (tc.get("name") if isinstance(tc, dict) else None) for tc in tool_calls
        ]
        tool_names = [n for n in tool_names if n]
        reason_zh = None
        for tc in tool_calls:
            if isinstance(tc, dict):
                reason_zh = _tool_reason(tc.get("arguments"))
                if reason_zh:
                    break
        content, meta = _bilingual_think(
            turn=turn,
            tool_names=tool_names,
            reasoning=reasoning,
            reason_zh=reason_zh,
            reasoning_display=reasoning_display,
        )
        thoughts.append(
            _new_thought(agent_id=agent_id, typ="thinking", content=content, meta=meta)
        )
        return thoughts

    if ev == "step":
        name = event.get("name") or "tool"
        status = event.get("status") or "ok"
        kind = "tool_result" if status != "running" else "tool_call"
        inp = event.get("input_summary")
        reason = _tool_reason(inp) if isinstance(inp, dict) else None
        out = event.get("output")
        content, extra = _finance_tool_content(name, status, out, reason)
        meta: dict[str, Any] = {
            "kind": kind,
            "toolName": name,
            "toolArgs": inp if isinstance(inp, dict) else None,
            "toolStatus": "ok" if status in {"ok", "success"} else (
                "error" if status in {"error", "failed"} else status
            ),
            "durationMs": event.get("duration_ms"),
        }
        meta.update({k: v for k, v in extra.items() if v is not None})
        thoughts.append(
            _new_thought(
                agent_id=agent_id,
                typ="thinking",
                content=str(content),
                meta=meta,
            )
        )

        # 主表 / 指标：额外 finding，方便前端单独渲染卡片
        if status != "running" and isinstance(out, dict):
            if name == "retrieve_finance" and (out.get("tables_detail") or out.get("tables")):
                fmt_metrics, fmt_tables, _, tables_to_disp = _labels()
                detail = out.get("tables_detail") or []
                block = fmt_tables(detail) if fmt_tables else None
                pages = [t.get("page") for t in detail if isinstance(t, dict) and t.get("page") is not None]
                thoughts.append(
                    _new_thought(
                        agent_id=agent_id,
                        typ="finding",
                        content=block or f"已定位 {len(out.get('tables') or detail)} 張財務主表",
                        ref=f"p.{pages[0]}" if pages else (
                            (detail[0].get("code") if detail else None)
                        ),
                        meta={
                            "kind": "finance_tables",
                            "tables": tables_to_disp(detail) if tables_to_disp else detail,
                            "toolName": name,
                        },
                    )
                )
            if name == "extract_metrics":
                fmt_metrics, _, metrics_to_disp, tables_to_disp = _labels()
                raw = out.get("metrics_summary") if isinstance(out.get("metrics_summary"), dict) else {}
                if "NET_PROFIT_OR_LOSS" in raw and "NET_LOSS" not in raw:
                    raw = {**raw, "NET_LOSS": raw["NET_PROFIT_OR_LOSS"]}
                metrics_list = metrics_to_disp(raw) if metrics_to_disp and raw else []
                block = fmt_metrics(raw) if fmt_metrics and raw else None
                thoughts.append(
                    _new_thought(
                        agent_id=agent_id,
                        typ="finding",
                        content=block or f"已抽取 {len(out.get('metric_keys') or [])} 項財務指標",
                        meta={
                            "kind": "finance_metrics",
                            "metrics": metrics_list,
                            "tables": tables_to_disp(out.get("tables_detail"))
                            if tables_to_disp and out.get("tables_detail")
                            else None,
                            "toolName": name,
                        },
                    )
                )

        # 从 output 抽证据
        evidence_src: list[dict[str, Any]] = []
        if isinstance(out, dict):
            for key in ("hits", "section_evidence_hits", "evidence", "snippets"):
                val = out.get(key)
                if isinstance(val, list):
                    evidence_src.extend([x for x in val if isinstance(x, dict)])
        if evidence_src:
            snips = _snip_evidence(evidence_src)
            if snips:
                pages = [s["page"] for s in snips if s.get("page") is not None]
                ref = f"p.{pages[0]}" if pages else None
                thoughts.append(
                    _new_thought(
                        agent_id=agent_id,
                        typ="finding",
                        content=f"檢索到 {len(snips)} 條原文證據"
                        + (f"（頁碼 {', '.join(str(p) for p in pages[:5])}）" if pages else ""),
                        ref=ref,
                        meta={"kind": "evidence", "evidence": snips, "toolName": name},
                    )
                )
        return thoughts

    if ev == "result":
        payload = event.get("payload") or {}
        summary = payload.get("summary")
        score = payload.get("risk_score")
        level = payload.get("risk_level")
        if summary or score is not None:
            parts = []
            if score is not None:
                parts.append(f"財務風險分 {score}" + (f"（{level}）" if level else ""))
            if summary:
                parts.append(str(summary))
            thoughts.append(
                _new_thought(
                    agent_id=agent_id,
                    typ="conclusion",
                    content="\n".join(parts),
                    meta={"kind": "model_think"},
                )
            )
        for rp in payload.get("risk_points") or []:
            if not isinstance(rp, dict):
                continue
            evs = _snip_evidence(rp.get("evidence") or [])
            page = None
            if evs and evs[0].get("page") is not None:
                page = evs[0]["page"]
            thoughts.append(
                _new_thought(
                    agent_id=agent_id,
                    typ="finding",
                    content=str(rp.get("description") or rp.get("code") or "風險點"),
                    ref=f"p.{page}" if page is not None else None,
                    meta={"kind": "risk_point", "evidence": evs or None},
                )
            )
        return thoughts

    return thoughts


def _legal_tool_content(
    name: str,
    status: str,
    out: Any,
    reason: str | None,
) -> tuple[str, dict[str, Any]]:
    """法务工具步骤 content（ReAct + 规则流水线共用）。"""
    extra: dict[str, Any] = {}
    if status == "running":
        return f"正在執行 `{name}`…", extra
    if not isinstance(out, dict):
        return f"`{name}` 完成（{status}）", extra

    if name == "score_legal" or name == "run_rule_checks":
        score = out.get("risk_score")
        level = out.get("risk_level")
        if score is not None:
            return (
                f"`{name}` 完成：參考分 {score}"
                + (f"（{level}）" if level else ""),
                extra,
            )
        hints = out.get("coverage_hints") or []
        if hints:
            return f"`{name}` 完成，覆蓋缺口 {len(hints)} 項", extra

    if name == "run_legal_skill":
        skill = out.get("skill") or (reason or "")
        n = out.get("risk_point_count")
        if n is None and isinstance(out.get("risk_points"), list):
            n = len(out["risk_points"])
        return f"`run_legal_skill` 完成（{skill or 'skill'}，風險點 {n or 0}）", extra

    if name == "retrieve_legal":
        n = out.get("grep_hits")
        if n is None:
            hits = out.get("hits")
            n = len(hits) if isinstance(hits, list) else hits
        return f"`retrieve_legal` 完成，基線命中 {n or 0} 條", extra

    if name == "submit_legal_report":
        score = out.get("risk_score")
        level = out.get("risk_level")
        summary = out.get("summary")
        parts = ["`submit_legal_report` 完成"]
        if score is not None:
            parts.append(f"風險分 {score}" + (f"（{level}）" if level else ""))
        if summary:
            parts.append(to_zh_hant(str(summary)))
        return "\n".join(parts), extra

    hits_val = out.get("hits")
    if hits_val is not None:
        n = len(hits_val) if isinstance(hits_val, list) else hits_val
        return f"`{name}` 完成，命中 {n} 條", extra

    hint = out.get("hint") or out.get("summary")
    if hint:
        return f"`{name}` 完成（{status}）\n{to_zh_hant(str(hint))}", extra
    return f"`{name}` 完成（{status}）", extra


def map_legal_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    """法务 AgentRunLogger / on_progress 事件 → Thought[]（含 ReAct react_turn）。"""
    thoughts: list[dict[str, Any]] = []
    agent_id = "legal"
    ev = event.get("event")

    if ev == "react_turn":
        turn = event.get("turn") or event.get("step_index") or "?"
        reasoning = (event.get("reasoning") or "").strip()
        reasoning_display = (event.get("reasoning_display") or "").strip() or None
        tool_calls = event.get("tool_calls") or []
        tool_names = [
            (tc.get("name") if isinstance(tc, dict) else None) for tc in tool_calls
        ]
        tool_names = [n for n in tool_names if n]
        reason_zh = None
        for tc in tool_calls:
            if isinstance(tc, dict):
                reason_zh = _tool_reason(tc.get("arguments"))
                if reason_zh:
                    break
        content, meta = _bilingual_think(
            turn=turn,
            tool_names=tool_names,
            reasoning=reasoning,
            reason_zh=reason_zh,
            reasoning_display=reasoning_display,
        )
        thoughts.append(
            _new_thought(agent_id=agent_id, typ="thinking", content=content, meta=meta)
        )
        return thoughts

    if ev == "step":
        name = event.get("name") or "tool"
        status = event.get("status") or "ok"
        kind = "tool_call" if status == "running" else "tool_result"
        inp = event.get("input_summary")
        reason = _tool_reason(inp) if isinstance(inp, dict) else None
        out = event.get("output")
        if name == "score_legal" and event.get("summary") and status != "running":
            content = str(event["summary"])
            extra: dict[str, Any] = {}
        else:
            content, extra = _legal_tool_content(name, status, out, reason)
        thoughts.append(
            _new_thought(
                agent_id=agent_id,
                typ="thinking" if name != "score_legal" or status == "running" else "conclusion",
                content=content,
                meta={
                    "kind": kind if name != "score_legal" or status == "running" else "model_think",
                    "toolName": name,
                    "toolArgs": inp if isinstance(inp, dict) else None,
                    "toolStatus": "ok" if status in {"ok", "success"} else (
                        "error" if status in {"error", "failed"} else status
                    ),
                    **{k: v for k, v in extra.items() if v is not None},
                },
            )
        )

        # 证据：pipeline 顶层 evidence_hits；ReAct 则在 output.hits/evidence 等
        evidence_src: list[dict[str, Any]] = []
        if status != "running":
            for key in ("evidence_hits", "evidence"):
                val = event.get(key)
                if isinstance(val, list):
                    evidence_src.extend([x for x in val if isinstance(x, dict)])
            if isinstance(out, dict):
                for key in (
                    "hits",
                    "evidence",
                    "snippets",
                    "section_evidence_hits",
                ):
                    val = out.get(key)
                    # pipeline 常把 hits 写成计数 int，仅接受 list[dict]
                    if isinstance(val, list):
                        evidence_src.extend([x for x in val if isinstance(x, dict)])
        if evidence_src:
            snips = _snip_evidence(evidence_src)
            if snips:
                pages = [s["page"] for s in snips if s.get("page") is not None]
                thoughts.append(
                    _new_thought(
                        agent_id=agent_id,
                        typ="finding",
                        content=f"法務證據 {len(snips)} 條"
                        + (f"（頁碼 {', '.join(str(p) for p in pages[:8])}）" if pages else ""),
                        ref=f"p.{pages[0]}" if pages else None,
                        meta={"kind": "evidence", "evidence": snips, "toolName": name},
                    )
                )

        # 风险点：顶层 event.risk_points + output.risk_points（ReAct skill 观察）
        risk_points: list[dict[str, Any]] = []
        for src in (event.get("risk_points"), (out or {}).get("risk_points") if isinstance(out, dict) else None):
            if isinstance(src, list):
                risk_points.extend([x for x in src if isinstance(x, dict)])
        seen_rp: set[str] = set()
        for rp in risk_points:
            key = str(rp.get("code") or rp.get("description") or id(rp))
            if key in seen_rp:
                continue
            seen_rp.add(key)
            evs = _snip_evidence(rp.get("evidence") or [])
            if not evs and rp.get("evidence_page") is not None:
                evs = _snip_evidence(
                    [
                        {
                            "page": rp.get("evidence_page"),
                            "excerpt": str(rp.get("description") or "")[:120],
                            "source_type": "text",
                        }
                    ]
                )
            page = evs[0]["page"] if evs and evs[0].get("page") is not None else None
            if page is None and rp.get("evidence_page") is not None:
                page = rp.get("evidence_page")
            thoughts.append(
                _new_thought(
                    agent_id=agent_id,
                    typ="finding",
                    content=str(rp.get("description") or rp.get("code") or "風險點"),
                    ref=f"p.{page}" if page is not None else None,
                    meta={"kind": "risk_point", "evidence": evs or None},
                )
            )
        return thoughts

    if ev == "result":
        payload = event.get("payload") or {}
        summary = payload.get("summary")
        score = payload.get("risk_score")
        level = payload.get("risk_level")
        if summary or score is not None:
            parts = []
            if score is not None:
                parts.append(f"法務風險分 {score}" + (f"（{level}）" if level else ""))
            if summary:
                parts.append(str(summary))
            thoughts.append(
                _new_thought(
                    agent_id=agent_id,
                    typ="conclusion",
                    content="\n".join(parts),
                    meta={"kind": "model_think"},
                )
            )
        for rp in payload.get("risk_points") or []:
            if not isinstance(rp, dict):
                continue
            evs = _snip_evidence(rp.get("evidence") or [])
            page = None
            if evs and evs[0].get("page") is not None:
                page = evs[0]["page"]
            thoughts.append(
                _new_thought(
                    agent_id=agent_id,
                    typ="finding",
                    content=str(rp.get("description") or rp.get("code") or "風險點"),
                    ref=f"p.{page}" if page is not None else None,
                    meta={"kind": "risk_point", "evidence": evs or None},
                )
            )
        return thoughts

    return thoughts


_MARKET_STEP_LABELS = {
    "load_market_snapshot": "加载市场数据",
    "inspect_public_opinion": "检查本地舆情",
    "collect_sina_news": "检索新浪财经舆情",
    "firecrawl_public_opinion": "检索 Firecrawl 舆情",
    "validate_public_opinion": "校验上市前舆情",
    "analyze_market_dimensions": "分析市场维度",
    "validate_llm_assessment": "校验模型市场判断",
    "score_market_rules": "计算市场风险分",
    "build_market_report": "生成市场情绪报告",
}


def map_market_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    """市场 AgentRunLogger / on_progress 事件 → Thought[]。

    Market uses the same public ``meta.kind`` vocabulary as legal. News
    fields remain optional metadata so structured evidence can be displayed
    without copying article bodies into the event stream.
    """
    ev = event.get("event")
    if ev == "react_turn":
        tool_calls = event.get("tool_calls") or []
        tool_names = [
            tc.get("name") for tc in tool_calls
            if isinstance(tc, dict) and tc.get("name")
        ]
        reason_zh = None
        for tc in tool_calls:
            if isinstance(tc, dict):
                reason_zh = _tool_reason(tc.get("arguments"))
                if reason_zh:
                    break
        content, meta = _bilingual_think(
            turn=event.get("turn") or event.get("step_index") or "?",
            tool_names=tool_names,
            reasoning=str(event.get("reasoning") or ""),
            reason_zh=reason_zh,
            reasoning_display=event.get("reasoning_display"),
        )
        return [new_thought(agent_id="market", typ="thinking", content=content, meta=meta)]

    if ev == "step":
        name = str(event.get("name") or "market_tool")
        status = str(event.get("status") or "ok")
        output = event.get("output")
        normalized_status = {
            "success": "ok",
            "completed": "ok",
            "failed": "error",
        }.get(status, status)
        action = "正在执行" if normalized_status == "running" else (
            "已降级" if normalized_status == "degraded" else
            "已跳过" if normalized_status == "skipped" else
            "发生错误" if normalized_status == "error" else "已完成"
        )
        label = _MARKET_STEP_LABELS.get(name, name)
        content = f"{label}：{action}"
        if isinstance(output, dict):
            hint = (
                output.get("summary")
                or output.get("hint")
                or output.get("reason")
                or output.get("error")
            )
            if hint:
                content += "\n" + str(hint)
        terminal = normalized_status != "running"
        is_conclusion = terminal and name in {
            "score_market_rules",
            "build_market_report",
            "submit_market_report",
        }
        thought_type = (
            "conclusion" if is_conclusion else
            "finding" if normalized_status in {"degraded", "error"} else
            "thinking"
        )
        thoughts = [
            new_thought(
                agent_id="market",
                typ=thought_type,
                content=content,
                meta={
                    "kind": "tool_call" if not terminal else (
                        "model_think" if is_conclusion else "tool_result"
                    ),
                    "toolName": name,
                    "toolStatus": normalized_status,
                    "toolArgs": event.get("input_summary"),
                    "durationMs": event.get("duration_ms"),
                },
            )
        ]

        evidence_src: list[dict[str, Any]] = []
        for key in ("evidence_hits", "evidence"):
            value = event.get(key)
            if isinstance(value, list):
                evidence_src.extend(x for x in value if isinstance(x, dict))
        if isinstance(output, dict):
            for key in ("evidence_hits", "evidence", "evidence_ledger", "hits", "articles"):
                value = output.get(key)
                if isinstance(value, list):
                    evidence_src.extend(x for x in value if isinstance(x, dict))
        if evidence_src and terminal:
            snips = _snip_evidence(evidence_src)
            for source, snip in zip(evidence_src, snips):
                for source_key, meta_key in (
                    ("title", "title"),
                    ("url", "url"),
                    ("published_at", "date"),
                    ("publication_date", "date"),
                    ("date", "date"),
                ):
                    if source.get(source_key) is not None and meta_key not in snip:
                        snip[meta_key] = source[source_key]
            pages = [s.get("page") for s in snips if s.get("page") is not None]
            thoughts.append(
                new_thought(
                    agent_id="market",
                    typ="finding",
                    content=f"市场证据 {len(snips)} 条",
                    ref=f"p.{pages[0]}" if pages else None,
                    meta={
                        "kind": "evidence",
                        "evidence": snips,
                        "toolName": name,
                        "toolStatus": normalized_status,
                    },
                )
            )

        risk_points: list[dict[str, Any]] = []
        for value in (
            event.get("risk_points"),
            output.get("risk_points") if isinstance(output, dict) else None,
        ):
            if isinstance(value, list):
                risk_points.extend(x for x in value if isinstance(x, dict))
        for risk_point in risk_points:
            evidence = risk_point.get("evidence") or []
            snippets = _snip_evidence(evidence) if isinstance(evidence, list) else []
            page = snippets[0].get("page") if snippets else risk_point.get("evidence_page")
            thoughts.append(
                new_thought(
                    agent_id="market",
                    typ="finding",
                    content=str(risk_point.get("description") or risk_point.get("code") or "市场风险点"),
                    ref=f"p.{page}" if page is not None else None,
                    meta={
                        "kind": "risk_point",
                        "toolName": name,
                        "toolStatus": normalized_status,
                        "code": risk_point.get("code"),
                        "level": risk_point.get("level"),
                        "value": risk_point.get("value"),
                        "evidence": snippets or None,
                    },
                )
            )
        return thoughts

    if ev == "result":
        payload = event.get("payload") or {}
        thoughts = [
            new_thought(
                agent_id="market",
                typ="conclusion",
                content=(
                    f"上市首日破发风险分 {payload.get('risk_score')}。"
                    + str(payload.get("summary") or "")
                ),
                meta={"kind": "model_think"},
            )
        ]
        for risk_point in payload.get("risk_points") or []:
            if not isinstance(risk_point, dict):
                continue
            evidence = risk_point.get("evidence") or []
            snippets = _snip_evidence(evidence) if isinstance(evidence, list) else []
            page = snippets[0].get("page") if snippets else risk_point.get("evidence_page")
            thoughts.append(
                new_thought(
                    agent_id="market",
                    typ="finding",
                    content=str(risk_point.get("description") or risk_point.get("code") or "市场风险点"),
                    ref=f"p.{page}" if page is not None else None,
                    meta={"kind": "risk_point", "evidence": snippets or None},
                )
            )
        return thoughts
    return []


def map_debate_expert_event(event: dict[str, Any], *, with_category: bool = True) -> list[dict[str, Any]]:
    """辩论补证/作答 → 专家 Thought（finance/legal/market），不记成 orchestrator。"""
    ev = str(event.get("event") or "")
    target = event.get("target_agent") or event.get("agent") or "finance"
    agent_id = _agent_id(str(target))
    category = category_for_agent_id(agent_id) if with_category else None
    thoughts: list[dict[str, Any]] = []
    rnd = event.get("round")
    qid = event.get("question_id") or ""

    if ev == "debate_search":
        tools = event.get("tool_calls") or []
        names = []
        pages_hint: list[Any] = []
        for tc in tools:
            if not isinstance(tc, dict):
                continue
            names.append(str(tc.get("name") or "search_standalone"))
            args = tc.get("arguments") or {}
            if isinstance(args, dict):
                pages_hint.extend(args.get("pages") or [])
        query_bits = []
        for tc in tools:
            if isinstance(tc, dict) and isinstance(tc.get("arguments"), dict):
                q = tc["arguments"].get("query")
                kind = tc["arguments"].get("kind")
                if q:
                    query_bits.append(f"{kind or 'keyword'}={q}")
        content = to_zh_hant(
            "辯論補證："
            + ("、".join(query_bits) or "、".join(names) or "search")
        )
        if pages_hint:
            content += to_zh_hant(f"（prefer_pages={pages_hint}）")
        thoughts.append(
            new_thought(
                agent_id=agent_id,
                typ="thinking",
                content=content,
                category=category,
                meta={
                    "kind": "tool_call",
                    "toolName": names[0] if names else "search_standalone",
                    "toolStatus": "running",
                    "round": rnd,
                    "questionId": qid,
                    "targetAgent": target,
                    "toolCalls": tools,
                    "preferPages": pages_hint or None,
                },
            )
        )
        evidence = event.get("evidence") or []
        if evidence:
            snips = _snip_evidence(evidence if isinstance(evidence, list) else [])
            page = snips[0].get("page") if snips else None
            thoughts.append(
                new_thought(
                    agent_id=agent_id,
                    typ="finding",
                    content=to_zh_hant(
                        f"檢索命中 {event.get('search_hit_count') or len(snips)} 條"
                    ),
                    ref=f"p.{page}" if page is not None else None,
                    category=category,
                    meta={"kind": "evidence", "evidence": snips, "toolStatus": "ok"},
                )
            )
        else:
            thoughts.append(
                new_thought(
                    agent_id=agent_id,
                    typ="thinking",
                    content="檢索未命中（禁止編造頁碼）",
                    category=category,
                    meta={"kind": "tool_result", "toolStatus": "ok", "searchHitCount": 0},
                )
            )
        return thoughts

    if ev == "debate_reply":
        content = str(event.get("utterance") or "專家作答")
        reasoning = str(event.get("reasoning") or "").strip()
        meta: dict[str, Any] = {
            "kind": "model_think",
            "round": rnd,
            "questionId": qid,
            "targetAgent": target,
            "status": event.get("status"),
            "confidence": event.get("confidence"),
        }
        if reasoning:
            meta["rawThink"] = reasoning
        thoughts.append(
            new_thought(
                agent_id=agent_id,
                typ="conclusion",
                content=content,
                category=category,
                meta=meta,
            )
        )
        evs = event.get("evidence") or []
        if evs:
            snips = _snip_evidence(evs if isinstance(evs, list) else [])
            page = snips[0].get("page") if snips else None
            thoughts.append(
                new_thought(
                    agent_id=agent_id,
                    typ="finding",
                    content=to_zh_hant("辯論證據"),
                    ref=f"p.{page}" if page is not None else None,
                    category=category,
                    meta={"kind": "evidence", "evidence": snips},
                )
            )
        return thoughts
    return thoughts


def debate_message_from_event(event: dict[str, Any], *, with_category: bool = True) -> dict[str, Any] | None:
    ev = str(event.get("event") or "")
    ts = int(time.time() * 1000)
    if ev == "debate_question":
        target = event.get("target_agent") or "finance"
        msg = {
            "id": f"deb-{event.get('question_id') or uuid.uuid4().hex[:8]}",
            "agentId": "orchestrator",
            "round": int(event.get("round") or 1),
            "type": "question",
            "content": to_zh_hant(str(event.get("utterance") or "")),
            "targetAgentId": _agent_id(str(target)),
            "timestamp": ts,
        }
        if with_category:
            msg["category"] = "master"
        return msg
    if ev == "debate_reply":
        target = event.get("target_agent") or "finance"
        agent_id = _agent_id(str(target))
        msg = {
            "id": f"deb-r-{event.get('question_id') or uuid.uuid4().hex[:8]}",
            "agentId": agent_id,
            "round": int(event.get("round") or 1),
            "type": "response",
            "content": to_zh_hant(str(event.get("utterance") or "")),
            "targetAgentId": None,
            "timestamp": ts,
        }
        if with_category:
            msg["category"] = category_for_agent_id(agent_id)
        return msg
    if ev in {"debate_plan", "debate_followup"}:
        msg_type = "opening" if ev == "debate_plan" else "summary"
        msg = {
            "id": f"deb-{ev}-{uuid.uuid4().hex[:8]}",
            "agentId": "orchestrator",
            "round": int(event.get("round") or 1),
            "type": msg_type,
            "content": to_zh_hant(str(event.get("utterance") or ev)),
            "targetAgentId": None,
            "timestamp": ts,
        }
        if with_category:
            msg["category"] = "master"
        return msg
    return None


def map_master_event(event: dict[str, Any], *, in_debate: bool = False) -> list[dict[str, Any]]:
    """总控 jsonl → Thought。辩论补证/作答改映射到专家；仅 in_debate 时加 category。"""
    ev = str(event.get("event") or "")
    if ev in {"run_start", "run_end", "result", "step"}:
        return []
    if ev in {"debate_search", "debate_reply"}:
        return map_debate_expert_event(event, with_category=in_debate)

    reasoning = str(event.get("reasoning") or "").strip()
    utterance = str(event.get("utterance") or "").strip()
    target = event.get("target_agent")
    qid = event.get("question_id") or ""
    rnd = event.get("round")
    category = "master" if in_debate else None

    if ev == "debate_question":
        content = utterance or "總控質詢"
        meta: dict[str, Any] = {
            "kind": "model_think",
            "round": rnd,
            "questionId": qid,
            "targetAgent": target,
        }
        if reasoning:
            meta["rawThink"] = reasoning
        return [
            new_thought(
                agent_id="orchestrator",
                typ="thinking",
                content=content,
                category=category,
                meta=meta,
            )
        ]

    # conflict_detection / embellishment / fusion / debate_plan / debate_followup
    use_category = category if ev in {"debate_plan", "debate_followup"} else None
    if ev in {"debate_plan", "debate_followup"} and in_debate:
        use_category = "master"
    content = utterance or ev
    meta = {"kind": "model_think", "event": ev}
    if reasoning:
        meta["rawThink"] = reasoning
    extra = {
        k: event.get(k)
        for k in ("need_debate", "score", "level", "overall_score", "gate_warning", "degraded")
        if event.get(k) is not None
    }
    if extra:
        meta.update(extra)
    typ = "conclusion" if ev == "fusion" else "thinking"
    return [
        new_thought(
            agent_id="orchestrator",
            typ=typ,
            content=content,
            category=use_category,
            meta=meta,
        )
    ]


def score_to_risk_level(score: float) -> str:
    s = float(score)
    if s >= 60:
        return "HIGH"
    if s >= 30:
        return "MEDIUM"
    return "LOW"


def _finance_detail_from_agent_result(agent_result: dict[str, Any]) -> dict[str, Any]:
    """从 AgentResult 抽出前端可直接渲染的三表 + 指标。"""
    fmt_metrics, fmt_tables, metrics_to_disp, tables_to_disp = _labels()
    metrics = agent_result.get("metrics") or {}
    # cash_burn 可能嵌在 metrics 里
    metrics_only = {k: v for k, v in metrics.items() if k != "cash_burn" and isinstance(v, dict)}
    evidence = agent_result.get("evidence_summary") or {}
    table_meta = evidence.get("table_meta") or {}
    tables_detail = []
    try:
        from src.skills.finance_labels import table_name_zh

        for code, info in table_meta.items():
            if not isinstance(info, dict):
                continue
            tables_detail.append(
                {
                    "code": code,
                    "nameZh": table_name_zh(code),
                    "page": info.get("page"),
                    "sourceType": info.get("source_type") or info.get("category"),
                    "excerpt": (info.get("excerpt") or "")[:200],
                }
            )
    except Exception:
        tables_detail = [
            {"code": c, "page": (i or {}).get("page") if isinstance(i, dict) else None}
            for c, i in table_meta.items()
        ]

    metrics_list = metrics_to_disp(metrics_only) if metrics_to_disp else []
    tables_list = tables_to_disp(tables_detail) if tables_to_disp else tables_detail
    return {
        "tables": tables_list,
        "tablesText": fmt_tables(tables_detail) if fmt_tables else None,
        "metrics": metrics_list,
        "metricsText": fmt_metrics(metrics_only) if fmt_metrics else None,
        "gates": agent_result.get("gates"),
        "cashBurn": metrics.get("cash_burn"),
    }


_LEGAL_SKILL_ORDER = (
    "legal_governance",
    "legal_shareholder_rights",
    "legal_related_party",
    "legal_contracts_and_ip",
    "legal_regulatory_litigation",
)


def _rules_floor_shell(features: dict[str, Any] | None) -> dict[str, Any] | None:
    """前端外壳摘要：财务/法务 rules_floor 字段不对称，一律可选。"""
    rf = (features or {}).get("rules_floor")
    if not isinstance(rf, dict) or not rf:
        return None
    out: dict[str, Any] = {}
    for src, dst in (
        ("final_score", "finalScore"),
        ("rules_score", "rulesScore"),
        ("llm_score", "llmScore"),
        ("saturated_score", "saturatedScore"),
        ("rules_substantive_score", "rulesSubstantiveScore"),
        ("flags", "flags"),
    ):
        if src in rf and rf[src] is not None:
            out[dst] = rf[src]
    return out or None


def _legal_detail_from_agent_result(agent_result: dict[str, Any]) -> dict[str, Any]:
    """5 Skill 压缩摘要，供前端无需深挖 agentResult.features.skill_results。"""
    features = agent_result.get("features") or {}
    skill_results = features.get("skill_results") or {}
    skills: list[dict[str, Any]] = []
    for name in _LEGAL_SKILL_ORDER:
        data = skill_results.get(name) if isinstance(skill_results, dict) else None
        if not isinstance(data, dict):
            skills.append({"name": name, "nRiskPoints": 0, "confidence": None, "exists": None})
            continue
        points = data.get("risk_points") or []
        skills.append(
            {
                "name": name,
                "nRiskPoints": len(points) if isinstance(points, list) else int(
                    data.get("risk_point_count") or 0
                ),
                "confidence": data.get("confidence"),
                "exists": data.get("exists"),
            }
        )
    risk_points = agent_result.get("risk_points") or []
    return {
        "skills": skills,
        "riskPointCount": len(risk_points) if isinstance(risk_points, list) else 0,
    }


def agent_bundle_from_result(
    *,
    agent_key: str,
    agent_result: dict[str, Any],
    report_markdown: str,
    log_text: str,
    log_events: list[dict[str, Any]],
) -> dict[str, Any]:
    features = agent_result.get("features") or {}
    if not isinstance(features, dict):
        features = {}
    scoring_mode = features.get("scoring_mode") or (agent_result.get("trace") or {}).get(
        "scoring_mode"
    )
    bundle: dict[str, Any] = {
        "agentId": (
            "financial"
            if agent_key == "finance"
            else ("market" if agent_key == "market" else "legal")
        ),
        "riskScore": agent_result.get("risk_score"),
        "riskLevel": agent_result.get("risk_level"),
        "summary": to_zh_hant(str(agent_result.get("summary") or "")),
        "reportMarkdown": report_markdown,
        "logText": log_text,
        "logEvents": log_events,
        "scoringMode": scoring_mode,
        "rulesFloor": _rules_floor_shell(features),
        "agentResult": agent_result,
    }
    if agent_key == "finance":
        bundle["financeDetail"] = _finance_detail_from_agent_result(agent_result)
    elif agent_key == "legal":
        bundle["legalDetail"] = _legal_detail_from_agent_result(agent_result)
    elif agent_key == "market":
        bundle["marketDetail"] = {
            "deterministicScore": features.get("deterministic_score"),
            "llmScore": features.get("llm_score"),
            "sentimentAnalysis": features.get("sentiment_analysis"),
            "evidenceCatalog": (
                features.get("evidence_catalog")
                or (features.get("sentiment_analysis") or {}).get("evidence_ledger")
            ),
            "debateDossierPath": features.get("debate_dossier_path"),
        }
    return bundle
