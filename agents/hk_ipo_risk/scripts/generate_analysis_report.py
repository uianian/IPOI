#!/usr/bin/env python3
"""从 finance‖legal 运行结果 JSON 生成 Markdown 分析报告。

示例：
  cd agents/hk_ipo_risk
  python scripts/generate_analysis_report.py \\
    --result .runtime/mixue_finance_legal.json \\
    --doc-name 蜜雪集團 \\
    --pdf-name 02097_21-02-2025_蜜雪集團_全球發售.pdf \\
    --finance-retrieval ../../retrieval/.runtime/agent_retrieval_mixue.json \\
    --legal-retrieval ../ipo/.runtime/agent_retrieval_mixue_legal.json \\
    --out reports/mixue_finance_legal_report.md
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PKG_ROOT = Path(__file__).resolve().parent.parent


def _load_json(path: Path | None) -> dict[str, Any] | list[Any] | None:
    if path is None or not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _clean_excerpt(text: str, max_len: int = 280) -> str:
    if not text:
        return ""
    t = html.unescape(text)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _fmt_num(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        return f"{v:.2f}"
    return str(v)


def _metrics_table(metrics: dict[str, Any]) -> str:
    series_fields = {
        k: v
        for k, v in metrics.items()
        if isinstance(v, dict) and k != "cash_burn" and any(isinstance(x, (int, float)) for x in v.values())
    }
    if not series_fields:
        return "_无抽取到时间序列指标_\n"
    years: list[str] = []
    for ser in series_fields.values():
        for y in ser.keys():
            if y not in years:
                years.append(str(y))
    # prefer chronological: pure years first
    years_sorted = sorted(
        [y for y in years if str(y).isdigit()],
        key=lambda x: int(x),
    ) + [y for y in years if not str(y).isdigit()]

    lines = [
        "| 指标 | " + " | ".join(years_sorted) + " |",
        "|------|" + "|".join(["------"] * len(years_sorted)) + "|",
    ]
    for field, ser in series_fields.items():
        row = [field] + [_fmt_num(ser.get(y) if y in ser else ser.get(str(y))) for y in years_sorted]
        # map keys carefully
        cells = [field]
        for y in years_sorted:
            val = ser.get(y)
            if val is None and y.isdigit():
                val = ser.get(int(y)) if False else ser.get(y)
            cells.append(_fmt_num(val))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _collect_finance_evidence(
    finance: dict[str, Any],
    retrieval: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    # 优先 Agent 自带 snippets（改进后无需依赖 retrieval JSON）
    for sn in (finance.get("evidence_summary") or {}).get("snippets") or []:
        items.append(
            {
                "field_code": sn.get("field_code"),
                "page": sn.get("page"),
                "source_type": sn.get("source_type") or "unknown",
                "n_hits": None,
                "years": None,
                "excerpt": _clean_excerpt(sn.get("excerpt") or "", 400),
            }
        )
    if items:
        return items
    meta = ((finance.get("evidence_summary") or {}).get("table_meta") or {})
    by_table = (retrieval or {}).get("evidence_by_table") or {}
    for code, info in meta.items():
        hits = by_table.get(code) or []
        excerpt = info.get("excerpt") or ""
        page = info.get("page")
        if hits and not excerpt:
            excerpt = hits[0].get("excerpt") or hits[0].get("content") or ""
            page = hits[0].get("page") or page
        items.append(
            {
                "field_code": code,
                "page": page,
                "source_type": info.get("source_type") or info.get("category") or "table",
                "n_hits": info.get("n_hits"),
                "years": info.get("years"),
                "excerpt": _clean_excerpt(excerpt, 400),
            }
        )
    return items


def _collect_legal_evidence(legal: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    features = legal.get("features") or {}
    for sec, feat in features.items():
        if not isinstance(feat, dict):
            continue
        for ev in feat.get("evidence") or []:
            items.append(
                {
                    "section": sec,
                    "field_code": ev.get("field_code"),
                    "page": ev.get("page"),
                    "source_type": ev.get("source_type"),
                    "confidence": ev.get("confidence"),
                    "excerpt": _clean_excerpt(ev.get("excerpt") or "", 320),
                    "exists": feat.get("exists"),
                    "skipped": feat.get("skipped"),
                    "strength": feat.get("evidence_strength"),
                }
            )
        if feat.get("skipped"):
            items.append(
                {
                    "section": sec,
                    "field_code": None,
                    "page": None,
                    "source_type": "—",
                    "confidence": None,
                    "excerpt": f"（已跳过：{feat.get('reason') or feat.get('skipped')}）",
                    "exists": feat.get("exists"),
                    "skipped": True,
                    "strength": None,
                }
            )
        elif feat.get("exists") is False and sec.startswith("3."):
            items.append(
                {
                    "section": sec,
                    "field_code": None,
                    "page": None,
                    "source_type": "—",
                    "confidence": None,
                    "excerpt": "未召回强证据 / 判定不存在",
                    "exists": False,
                    "skipped": False,
                    "strength": feat.get("evidence_strength"),
                }
            )
    return items


def _score_breakdown_md(breakdown: list[dict[str, Any]]) -> str:
    if not breakdown:
        return "_无扣分项（未触发风险规则，或证据不足未计分）_\n"
    lines = ["| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |", "|------|------|------|--------|------|--------|"]
    for b in breakdown:
        if not isinstance(b, dict):
            lines.append(f"| — | — | — | — | {str(b).replace('|', '/')} | — |")
            continue
        pages = sorted({e.get("page") for e in (b.get("evidence") or []) if isinstance(e, dict) and e.get("page") is not None})
        if b.get("evidence_page") is not None:
            pages = sorted(set(pages) | {b.get("evidence_page")})
        code = b.get("code") or b.get("item") or "ITEM"
        note = b.get("note") or b.get("description") or b.get("item") or "—"
        lines.append(
            "| {code} | +{delta} | {ref} | {mv} | {note} | {pages} |".format(
                code=str(code).replace("|", "/"),
                delta=b.get("delta"),
                ref=b.get("rule_ref") or "llm",
                mv=str(b.get("metric_value") if b.get("metric_value") is not None else "—").replace("|", "/"),
                note=str(note).replace("|", "/"),
                pages=", ".join(str(p) for p in pages) or "—",
            )
        )
    return "\n".join(lines) + "\n"


def _dimensions_md(dimensions: list[dict[str, Any]]) -> str:
    """兼容 pipeline schema (id/status/findings) 与 ReAct submit (dimension/analysis)。"""
    if not dimensions:
        return "_无四维分析输出（可能为规则兜底路径）_\n"
    parts: list[str] = []
    for d in dimensions:
        if not isinstance(d, dict):
            parts.append(f"- {d}\n")
            continue
        dim_id = d.get("id") or d.get("dimension") or d.get("name") or "unknown"
        status = d.get("status")
        score = d.get("dimension_score")
        analysis = d.get("analysis") or d.get("summary") or d.get("text")
        # ReAct 精简格式：只有 narrative，无 status/score → 标为 analyzed
        if status is None and analysis:
            status = "analyzed"
        meta = [f"status=`{status if status is not None else '—'}`"]
        if score is not None:
            meta.append(f"score=`{score}`")
        parts.append(f"#### `{dim_id}` — {' · '.join(meta)}\n")
        if analysis:
            parts.append(f"{analysis}\n")
        findings = d.get("findings") or []
        if findings:
            for f in findings:
                if not isinstance(f, dict):
                    parts.append(f"- {f}")
                    continue
                parts.append(
                    f"- **{f.get('code')}** ({f.get('level')}): {f.get('description')} "
                    f"| metric=`{f.get('metric_value')}` | p`{f.get('evidence_page')}`"
                )
            parts.append("")
        elif not analysis:
            parts.append("_无 findings_\n")
        else:
            parts.append("")
    return "\n".join(parts) + "\n"


def _analyze_finance(finance: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    gates = finance.get("gates") or {}
    metrics = finance.get("metrics") or {}
    feats = finance.get("features") or {}
    score = finance.get("risk_score")
    mode = feats.get("scoring_mode") or (finance.get("trace") or {}).get("scoring_mode") or "unknown"
    notes.append(
        f"评分模式 **{mode}**；风险分 **{score}**（{finance.get('risk_level')}）。"
        f"门控：未盈利=`{gates.get('is_unprofitable')}`，"
        f"跳过3.4=`{gates.get('skip_3_4')}`（{gates.get('skip_3_4_reason')}），"
        f"跳过2.4=`{gates.get('skip_2_4')}`（{gates.get('skip_2_4_reason')}）。"
    )
    think_status = feats.get("think_status")
    if think_status:
        notes.append(f"模型 think 状态：`{think_status}`（全文见推理日志 `[model_think]`）。")
    sr = (finance.get("trace") or {}).get("structured_reasoning")
    if sr:
        notes.append(f"结构化推理摘要：{sr}")
    llm = feats.get("llm_analysis") or {}
    if llm.get("summary"):
        notes.append(f"LLM 摘要：{llm.get('summary')}")
    net = gates.get("net_series") or metrics.get("NET_LOSS") or {}
    if net:
        notes.append(
            "期内利润（NET_LOSS 字段存利润序列，正数=盈利）："
            + "、".join(f"{y}={_fmt_num(v)}" for y, v in sorted(net.items(), key=lambda x: str(x[0])))
            + "。"
        )
    rev = metrics.get("REV") or {}
    gp_m = metrics.get("GP_MARGIN") or {}
    if rev:
        years = sorted([y for y in rev if str(y).isdigit()], key=lambda x: int(x))
        if years:
            y0, y1 = years[0], years[-1]
            notes.append(
                f"收入与毛利率：{y0}–{y1} 收入 {_fmt_num(rev.get(y0))}→{_fmt_num(rev.get(y1))}（千元），"
                f"毛利率 {_fmt_num(gp_m.get(y0))}%→{_fmt_num(gp_m.get(y1))}%。"
            )
    meta = (finance.get("evidence_summary") or {}).get("table_meta") or {}
    if meta:
        pages = ", ".join(f"{k}@p{v.get('page')}" for k, v in meta.items())
        notes.append(f"主表证据定位：{pages}。")
    run_log = feats.get("run_log") or (finance.get("evidence_summary") or {}).get("run_log") or {}
    if run_log.get("log"):
        notes.append(f"推理日志：`{run_log.get('log')}`")
    return notes


def _tool_trace_md(trace: dict[str, Any]) -> str:
    calls = trace.get("tool_calls") or []
    if not calls:
        return "_无工具调用记录_\n"
    lines = [f"- 耗时：`{trace.get('elapsed_sec')}s`", ""]
    for i, c in enumerate(calls, 1):
        tool = c.get("tool")
        detail = {k: v for k, v in c.items() if k != "tool"}
        lines.append(f"{i}. **`{tool}`**")
        lines.append(f"   ```json\n   {json.dumps(detail, ensure_ascii=False)}\n   ```")
    return "\n".join(lines) + "\n"


def _analyze_legal(legal: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    feats = legal.get("features") or {}
    score = legal.get("risk_score")
    notes.append(
        f"风险分 **{score}**（{legal.get('risk_level')}）。"
        f"打分来自披露基础分或规则命中（见 score_breakdown）。"
    )
    f31 = feats.get("3.1") or {}
    f32 = feats.get("3.2") or {}
    f33 = feats.get("3.3") or {}
    notes.append(
        f"3.1 对赌/赎回：exists=`{f31.get('exists')}`，证据强度=`{f31.get('evidence_strength')}`"
    )
    notes.append(
        f"3.2 关联交易：exists=`{f32.get('exists')}`，占比=`{f32.get('ratio_pct')}`。"
    )
    notes.append(
        f"3.3 集中度：exists=`{f33.get('exists')}`，"
        f"证据页={legal.get('evidence_summary', {}).get('3.3_pages')}。"
    )
    if (feats.get("3.5") or {}).get("skipped"):
        notes.append("3.5 管线风险按 non-biotech 正确跳过。")
    return notes


def _improvements(result: dict[str, Any]) -> list[str]:
    """改进建议会随代码演进；已落地项标记 [已做]。"""
    tips: list[str] = []
    tips.append(
        "**[已做] 财务 LLM 主路径**：retrieve → extract_metrics → gates → analyze_finance(单次四维 LLM) → 可解释评分；"
        "规则打分降为 fallback（`--finance-rules-only`）。"
    )
    tips.append(
        "**[已做] Gemma4 reasoning**：OpenRouter `reasoning.enabled`；日志区分 `[model_think]` / `[structured_reasoning]`。"
    )
    tips.append(
        "**[已做] 推理日志落盘**：`logs/{doc}_{agent}_{ts}.log` + `.jsonl`（时间/文档/流程/工具skills/过程/结果/推理链）。"
    )
    tips.append(
        "**[已做] 财务 BS 交叉校验**：若 TOTAL_ASSETS < NET_ASSETS，用 NET+LIAB 回填。"
    )
    tips.append(
        "**法务检索源**：可用 `--use-live-retrieval`；`--use-llm` 做法务结构化增强。"
    )
    return tips


def build_report(
    result: dict[str, Any],
    *,
    doc_name: str,
    pdf_name: str,
    finance_retrieval: dict[str, Any] | None,
    legal_retrieval: dict[str, Any] | None,
) -> str:
    finance = result.get("finance") or {}
    legal = result.get("legal") or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fin_ev = _collect_finance_evidence(finance, finance_retrieval)
    leg_ev = _collect_legal_evidence(legal)
    feats = finance.get("features") or {}
    mode = feats.get("scoring_mode") or (finance.get("trace") or {}).get("scoring_mode")

    parts: list[str] = []
    parts.append(f"# {doc_name} — 财务/法务 Agent 结果分析报告\n")
    parts.append(f"- 生成时间：{now}")
    parts.append(f"- 招股书：`{pdf_name}`")
    parts.append(f"- doc_id：`{result.get('doc_id')}`")
    parts.append(
        f"- 参考基本面融合分：`{result.get('reference_fundamental_score')}` "
        f"（legal×0.45 + finance×0.55；总控未启用）"
    )
    parts.append(f"- 财务评分模式：`{mode or '—'}`")
    run_log = feats.get("run_log") or {}
    if run_log.get("log"):
        parts.append(f"- 推理日志：`{run_log.get('log')}`")
    parts.append(f"- 说明：{result.get('note') or '—'}\n")

    parts.append("## 1. 总览\n")
    parts.append("| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |")
    parts.append("|-------|---------------------|------|------|")
    parts.append(
        f"| 财务穿透 | **{finance.get('risk_score')}** | {finance.get('risk_level')} | "
        f"{(finance.get('summary') or '').replace('|', '/')} |"
    )
    if legal:
        parts.append(
            f"| 法务合规 | **{legal.get('risk_score')}** | {legal.get('risk_level')} | "
            f"{(legal.get('summary') or '').replace('|', '/')} |"
        )
    parts.append("")

    # ---------- Finance ----------
    parts.append("## 2. 财务穿透 Agent\n")
    parts.append("### 2.1 得分与分解\n")
    parts.append(_score_breakdown_md(finance.get("score_breakdown") or []))
    parts.append("### 2.2 四维分析（LLM）\n")
    parts.append(_dimensions_md(feats.get("dimensions") or []))
    parts.append("### 2.3 推理链\n")
    sr = (finance.get("trace") or {}).get("structured_reasoning") or (
        (feats.get("llm_analysis") or {}).get("reasoning")
    )
    if sr:
        parts.append("**[structured_reasoning]**\n")
        parts.append(f"{sr}\n")
    think_ex = feats.get("model_think_excerpt")
    if think_ex:
        parts.append("**[model_think 摘录]**（全文见 logs）\n")
        parts.append(f"> {think_ex.replace(chr(10), ' ')}\n")
    elif feats.get("think_status") == "reasoning_missing":
        parts.append("_provider 未返回 message.reasoning（reasoning_missing）_\n")
    parts.append("### 2.4 门控\n")
    gates = finance.get("gates") or {}
    parts.append("```json")
    parts.append(
        json.dumps(
            {k: gates[k] for k in gates if k != "net_series"},
            ensure_ascii=False,
            indent=2,
        )
    )
    parts.append("```\n")
    parts.append("### 2.5 抽取指标\n")
    parts.append(_metrics_table(finance.get("metrics") or {}))
    cb = (finance.get("metrics") or {}).get("cash_burn") or {}
    parts.append(
        f"3.4 现金消耗：skipped=`{cb.get('skipped')}`，reason=`{cb.get('reason')}`，"
        f"runway=`{cb.get('CASH_RUNWAY_MONTHS')}`\n"
    )
    parts.append("### 2.6 召回证据（主表）\n")
    if fin_ev:
        parts.append("| 表/字段 | 页码 | 类型 | 命中数 | 年份列 | 摘录 |")
        parts.append("|--------|------|------|--------|--------|------|")
        for e in fin_ev:
            parts.append(
                "| {fc} | {page} | {st} | {n} | {years} | {ex} |".format(
                    fc=e.get("field_code"),
                    page=e.get("page") if e.get("page") is not None else "—",
                    st=e.get("source_type"),
                    n=e.get("n_hits") if e.get("n_hits") is not None else "—",
                    years=",".join(str(x) for x in (e.get("years") or [])) or "—",
                    ex=(e.get("excerpt") or "—").replace("|", "/"),
                )
            )
        parts.append("")
    else:
        parts.append("_无主表证据元数据_\n")
    section_hits = (finance.get("evidence_summary") or {}).get(
        "section_evidence_hits"
    ) or []
    section_routes = (finance.get("evidence_summary") or {}).get(
        "section_routes"
    ) or []
    parts.append("#### 2.6.1 章节化上下文证据\n")
    if section_routes:
        for route in section_routes:
            route_names = ", ".join(
                f"{item.get('section_id')}@p{item.get('start_page')}-{item.get('end_page')}"
                for item in route.get("route") or []
            )
            parts.append(
                f"- intent=`{route.get('intent')}` query=`{route.get('query')}` → "
                f"{route_names or '无可用章节'}"
            )
        parts.append("")
    if section_hits:
        parts.append("| 意图章节 | 页码 | 类型 | 分数 | 匹配词 | 摘录 |")
        parts.append("|---|---:|---|---:|---|---|")
        for hit in section_hits:
            excerpt = re.sub(r"\s+", " ", str(hit.get("excerpt") or ""))[:240]
            parts.append(
                "| {section} | {page} | {source_type} | {score} | {terms} | {excerpt} |".format(
                    section=hit.get("section_id") or hit.get("section_title") or "—",
                    page=hit.get("page") if hit.get("page") is not None else "—",
                    source_type=hit.get("source_type") or "—",
                    score=hit.get("score") if hit.get("score") is not None else "—",
                    terms=", ".join(str(x) for x in (hit.get("matched_terms") or [])) or "—",
                    excerpt=excerpt.replace("|", "/"),
                )
            )
        parts.append("")
    else:
        parts.append("_本次未调用章节化上下文检索，或未命中证据。_\n")
    parts.append("### 2.7 工具调用链\n")
    parts.append(_tool_trace_md(finance.get("trace") or {}))
    parts.append("### 2.8 分析结论\n")
    for n in _analyze_finance(finance):
        parts.append(f"- {n}")
    parts.append("")
    nf = feats.get("negative_findings") or []
    if nf:
        parts.append("### 2.9 阴性发现（低风险说明）\n")
        for item in nf:
            if isinstance(item, dict):
                parts.append(
                    f"- **{item.get('code')}**（{item.get('rule_ref')}）：{item.get('description')}"
                )
            else:
                parts.append(f"- {item}")
        parts.append("")
    bs = feats.get("bs_reconcile") or {}
    if bs.get("notes"):
        parts.append("### 2.10 资产负债表交叉校验\n")
        for note in bs["notes"]:
            parts.append(f"- {note}")
        parts.append("")

    # ---------- Legal ----------
    if legal:
        parts.append("## 3. 法务合规 Agent\n")
        parts.append("### 3.1 得分与分解\n")
        parts.append(_score_breakdown_md(legal.get("score_breakdown") or []))
        parts.append("### 3.2 章节特征摘要\n")
        parts.append("| 章节 | exists/skipped | 强度 | 关键字段 |")
        parts.append("|------|----------------|------|----------|")
        for sec in ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6"):
            feat = (legal.get("features") or {}).get(sec) or {}
            status = (
                f"skipped={feat.get('skipped')}"
                if feat.get("skipped")
                else f"exists={feat.get('exists')}"
            )
            extra = []
            for k in (
                "ratio_pct",
                "top1_customer_pct",
                "top5_customer_pct",
                "redemption_high",
                "owner",
                "reason",
            ):
                if feat.get(k) not in (None, False, ""):
                    extra.append(f"{k}={feat.get(k)}")
            parts.append(
                f"| {sec} | {status} | {feat.get('evidence_strength') or '—'} | "
                f"{('; '.join(extra) if extra else '—')} |"
            )
        parts.append("")
        parts.append("### 3.3 召回证据明细\n")
        if leg_ev:
            parts.append("| 章节 | 页码 | 类型 | 置信度 | 摘录 |")
            parts.append("|------|------|------|--------|------|")
            for e in leg_ev:
                parts.append(
                    "| {sec} | {page} | {st} | {conf} | {ex} |".format(
                        sec=e.get("section"),
                        page=e.get("page") if e.get("page") is not None else "—",
                        st=e.get("source_type") or "—",
                        conf=_fmt_num(e.get("confidence")) if e.get("confidence") is not None else "—",
                        ex=(e.get("excerpt") or "—").replace("|", "/"),
                    )
                )
            parts.append("")
        else:
            parts.append("_无法务证据_\n")

        parts.append("### 3.4 计分证据（score_breakdown）\n")
        for b in legal.get("score_breakdown") or []:
            parts.append(f"#### `{b.get('code')}`（+{b.get('delta')}，{b.get('rule_ref')}）\n")
            if b.get("note"):
                parts.append(f"{b.get('note')}\n")
            for ev in b.get("evidence") or []:
                parts.append(
                    f"- p{ev.get('page')}（{ev.get('source_type')}）："
                    f"{_clean_excerpt(ev.get('excerpt') or '', 360)}"
                )
            parts.append("")

        parts.append("### 3.5 工具调用链\n")
        parts.append(_tool_trace_md(legal.get("trace") or {}))
        parts.append("### 3.6 分析结论\n")
        for n in _analyze_legal(legal):
            parts.append(f"- {n}")
        parts.append("")

    # ---------- Improvements ----------
    parts.append("## 4. 改进建议\n")
    for i, tip in enumerate(_improvements(result), 1):
        parts.append(f"{i}. {tip}")
    parts.append("")
    parts.append("---\n")
    parts.append("_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_\n")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate finance/legal analysis markdown report")
    parser.add_argument(
        "--result",
        type=Path,
        default=PKG_ROOT / ".runtime" / "mixue_finance_legal.json",
    )
    parser.add_argument("--doc-name", default="蜜雪集團")
    parser.add_argument("--pdf-name", default="02097_21-02-2025_蜜雪集團_全球發售.pdf")
    parser.add_argument(
        "--finance-retrieval",
        type=Path,
        default=PKG_ROOT.parent.parent / "retrieval" / ".runtime" / "agent_retrieval_mixue.json",
    )
    parser.add_argument(
        "--legal-retrieval",
        type=Path,
        default=PKG_ROOT.parent / "ipo" / ".runtime" / "agent_retrieval_mixue_legal.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PKG_ROOT / "reports" / "mixue_finance_legal_report.md",
    )
    args = parser.parse_args()

    result = _load_json(args.result)
    if not isinstance(result, dict):
        print(f"invalid result json: {args.result}", file=sys.stderr)
        return 1

    fin_ret = _load_json(args.finance_retrieval)
    leg_ret = _load_json(args.legal_retrieval)
    if not isinstance(fin_ret, dict):
        fin_ret = None
    if not isinstance(leg_ret, dict):
        leg_ret = None

    md = build_report(
        result,
        doc_name=args.doc_name,
        pdf_name=args.pdf_name,
        finance_retrieval=fin_ret,
        legal_retrieval=leg_ret,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"Wrote {args.out} ({len(md)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
