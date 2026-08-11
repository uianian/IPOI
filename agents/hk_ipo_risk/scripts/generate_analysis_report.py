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


def _fmt_score(v: Any) -> str:
    """风险分展示统一保留 1 位小数（与 Agent 日志 risk_score:.1f 对齐）。"""
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
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
    # ReAct：章节在 rule_features；规则链：直接挂在 features 顶层
    section_map: dict[str, Any] = {}
    rule_features = features.get("rule_features") or {}
    if isinstance(rule_features, dict):
        for sec, feat in rule_features.items():
            if isinstance(feat, dict):
                section_map[str(sec)] = feat
    for sec, feat in features.items():
        if not isinstance(feat, dict):
            continue
        if str(sec).startswith("3.") and sec not in section_map:
            section_map[str(sec)] = feat
    seen: set[tuple[Any, Any, str]] = set()
    for sec, feat in section_map.items():
        for ev in feat.get("evidence") or []:
            excerpt = _clean_excerpt(ev.get("excerpt") or "", 320)
            key = (sec, ev.get("page"), excerpt[:80])
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "section": sec,
                    "field_code": ev.get("field_code"),
                    "page": ev.get("page"),
                    "source_type": ev.get("source_type"),
                    "confidence": ev.get("confidence"),
                    "excerpt": excerpt,
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
        elif feat.get("exists") is False and str(sec).startswith("3."):
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


def _legal_section_feat(legal: dict[str, Any], sec: str) -> dict[str, Any]:
    """读取法务 3.x 章节特征：兼容 ReAct(rule_features) 与规则链(顶层)。"""
    features = legal.get("features") or {}
    direct = features.get(sec)
    if isinstance(direct, dict) and (
        "exists" in direct
        or "skipped" in direct
        or "evidence" in direct
        or "evidence_strength" in direct
        or "owner" in direct
        or "valuation_inversion" in direct
    ):
        return direct
    nested = (features.get("rule_features") or {}).get(sec)
    return nested if isinstance(nested, dict) else {}


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


def _dimensions_md(
    dimensions: list[dict[str, Any]],
    *,
    submit_recovered: bool = False,
    think_status: str | None = None,
    rules_floor: dict[str, Any] | None = None,
) -> str:
    """兼容 pipeline schema (id/status/findings) 与 ReAct submit (dimension/analysis)。"""
    if not dimensions:
        if submit_recovered:
            return (
                "_四维分析由服务端在 submit 截断后恢复（`submit_recovered`）；"
                "完整模型 think 见推理日志。_\n"
            )
        if rules_floor:
            return (
                "_无四维分析输出：分数来自 `rules_floor` 主题合并；"
                "详见得分分解与推理日志。_\n"
            )
        if think_status == "ok":
            return (
                "_无四维分析输出：模型有 think 但 submit 参数为空/截断；"
                "分数可能来自规则托底，详见 `rules_floor` / 推理日志。_\n"
            )
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
        elif analysis:
            parts.append("")
        # 有 analysis 无 findings 时不写噪音「无 findings」
    return "\n".join(parts) + "\n"


def _rules_floor_md(floor: dict[str, Any] | None) -> str:
    if not floor:
        return ""
    flags = floor.get("flags") or {}
    flag_bits = ", ".join(
        f"{k}={v}"
        for k, v in flags.items()
        if v not in (None, False, "", [])
    ) or "—"
    return (
        f"- rules_floor：llm=`{_fmt_score(floor.get('llm_score'))}` / "
        f"rules=`{_fmt_score(floor.get('rules_score'))}` / "
        f"deduped=`{_fmt_score(floor.get('rules_score_deduped'))}` / "
        f"final=`{_fmt_score(floor.get('final_score'))}` / "
        f"theme_merge=`{floor.get('theme_merge')}`\n"
        f"- flags：{flag_bits}\n"
    )


def _risk_points_md(points: list[Any]) -> str:
    if not points:
        return "_无独立风险点列表_\n"
    lines = ["| 代码 | 等级 | 说明 | 指标 | 页 |", "|------|------|------|------|----|"]
    for p in points:
        if not isinstance(p, dict):
            continue
        lines.append(
            "| {code} | {level} | {desc} | {mv} | {page} |".format(
                code=str(p.get("code") or "—").replace("|", "/"),
                level=p.get("level") or "—",
                desc=str(p.get("description") or "—").replace("|", "/"),
                mv=str(p.get("metric_value") if p.get("metric_value") is not None else p.get("value") or "—").replace("|", "/"),
                page=p.get("evidence_page")
                if p.get("evidence_page") is not None
                else (
                    (p.get("evidence") or [{}])[0].get("page")
                    if p.get("evidence")
                    else "—"
                ),
            )
        )
    return "\n".join(lines) + "\n"


def _cash_burn_md(finance: dict[str, Any]) -> str:
    feats = finance.get("features") or {}
    metrics = finance.get("metrics") or {}
    cb = (
        feats.get("cash_burn")
        or metrics.get("cash_burn")
        or {}
    )
    if not cb:
        # 从工具链 observation 回填
        for t in (finance.get("trace") or {}).get("tool_calls") or []:
            if t.get("tool") == "calc_cash_runway":
                obs = t.get("observation") or {}
                cb = obs.get("cash_burn") or cb
    if not cb:
        return "_无 cash_burn 结果_\n"
    return (
        f"- skipped=`{cb.get('skipped')}` reason=`{cb.get('reason')}`\n"
        f"- END_CASH=`{_fmt_num(cb.get('END_CASH'))}` "
        f"BURN_RATE_MONTHLY=`{_fmt_num(cb.get('BURN_RATE_MONTHLY'))}` "
        f"runway=`{_fmt_num(cb.get('CASH_RUNWAY_MONTHS'))}` 月 "
        f"burn_basis=`{cb.get('burn_basis') or '—'}`\n"
        f"- burn_yoy_up_gt_30=`{cb.get('burn_yoy_up_gt_30')}` "
        f"basis=`{cb.get('burn_yoy_basis') or '—'}` "
        f"growth_full=`{_fmt_num(cb.get('burn_yoy_growth_full'))}` "
        f"growth_interim=`{_fmt_num(cb.get('burn_yoy_growth_interim'))}`\n"
    )


def _tool_trace_summary_md(trace: dict[str, Any]) -> str:
    calls = trace.get("tool_calls") or []
    if not calls:
        return "_无工具调用记录_\n"
    lines = [
        f"- 耗时：`{trace.get('elapsed_sec')}s` · 轮次：`{trace.get('n_turns') or '—'}`",
        "",
        "| 轮次 | 工具 | think | 要点 | 耗时ms |",
        "|------|------|-------|------|--------|",
    ]
    for c in calls:
        tool = c.get("tool") or c.get("status") or "—"
        args = c.get("arguments") or {}
        obs = c.get("observation") or {}
        bits: list[str] = []
        if args.get("intent"):
            bits.append(f"intent={args.get('intent')}")
        if args.get("reason"):
            bits.append(str(args.get("reason"))[:60])
        if obs.get("n") is not None:
            bits.append(f"hits={obs.get('n')}")
        pages = []
        for h in (obs.get("hits") or [])[:3]:
            if isinstance(h, dict) and h.get("page") is not None:
                pages.append(str(h.get("page")))
        if pages:
            bits.append("p" + ",".join(pages))
        if obs.get("risk_score") is not None:
            bits.append(f"score={_fmt_score(obs.get('risk_score'))}")
        if c.get("status"):
            bits.append(str(c.get("status")))
        lines.append(
            "| {turn} | `{tool}` | {think} | {bits} | {ms} |".format(
                turn=c.get("turn") if c.get("turn") is not None else "—",
                tool=str(tool).replace("|", "/"),
                think=c.get("think_status") or "—",
                bits=("；".join(bits) or "—").replace("|", "/"),
                ms=c.get("duration_ms") if c.get("duration_ms") is not None else "—",
            )
        )
    return "\n".join(lines) + "\n"


def _dedupe_section_hits_for_display(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[Any, str], dict[str, Any]] = {}
    for h in hits:
        if not isinstance(h, dict):
            continue
        key = (h.get("page"), str(h.get("source_type") or "text"))
        prev = best.get(key)
        if prev is None or float(h.get("score") or 0) > float(prev.get("score") or 0):
            best[key] = h
    return sorted(best.values(), key=lambda x: -float(x.get("score") or 0))


def _filter_negative_findings(
    items: list[Any],
    score_breakdown: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    risk_codes = {
        str(b.get("code") or "").upper()
        for b in score_breakdown
        if isinstance(b, dict)
    }
    kept: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        if not isinstance(item, dict):
            dropped += 1
            continue
        code = str(item.get("code") or "").upper()
        if code in risk_codes:
            dropped += 1
            continue
        kept.append(item)
    return kept, dropped


def _analyze_finance(finance: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    gates = finance.get("gates") or {}
    metrics = finance.get("metrics") or {}
    feats = finance.get("features") or {}
    score = finance.get("risk_score")
    mode = feats.get("scoring_mode") or (finance.get("trace") or {}).get("scoring_mode") or "unknown"
    notes.append(
        f"评分模式 **{mode}**；风险分 **{_fmt_score(score)}**（{finance.get('risk_level')}）。"
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
    skills = feats.get("skill_results") or {}
    if skills:
        notes.append(
            "财务 Skill："
            + "、".join(
                f"`{k}`({(v or {}).get('risk_point_count', 0)}点)"
                for k, v in sorted(skills.items())
            )
        )
    dossier = feats.get("debate_dossier_path") or (
        (finance.get("trace") or {}).get("debate_dossier_path")
    )
    if dossier:
        notes.append(f"辩论素材包：`{dossier}`")
    return notes


def _analyze_legal(legal: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    feats = legal.get("features") or {}
    score = legal.get("risk_score")
    notes.append(
        f"风险分 **{_fmt_score(score)}**（{legal.get('risk_level')}）。"
        f"打分来自披露基础分或规则命中（见 score_breakdown）。"
    )
    f31 = _legal_section_feat(legal, "3.1")
    f32 = _legal_section_feat(legal, "3.2")
    f33 = _legal_section_feat(legal, "3.3")
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
    if (_legal_section_feat(legal, "3.5") or {}).get("skipped"):
        notes.append("3.5 管线风险按 non-biotech 正确跳过。")
    skills = feats.get("skill_results") or {}
    if skills:
        notes.append(
            "法务 Skill："
            + "、".join(
                f"`{k}`({len((v or {}).get('risk_points') or [])}点)"
                for k, v in sorted(skills.items())
            )
        )
    return notes


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
        f"- 参考基本面融合分：`{_fmt_score(result.get('reference_fundamental_score'))}` "
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
        f"| 财务穿透 | **{_fmt_score(finance.get('risk_score'))}** | {finance.get('risk_level')} | "
        f"{(finance.get('summary') or '').replace('|', '/')} |"
    )
    if legal:
        parts.append(
            f"| 法务合规 | **{_fmt_score(legal.get('risk_score'))}** | {legal.get('risk_level')} | "
            f"{(legal.get('summary') or '').replace('|', '/')} |"
        )
    parts.append("")

    # ---------- Finance ----------
    parts.append("## 2. 财务穿透 Agent\n")
    parts.append("### 2.1 得分与分解\n")
    parts.append(_score_breakdown_md(finance.get("score_breakdown") or []))
    floor = feats.get("rules_floor") or (finance.get("trace") or {}).get("rules_floor")
    parts.append(_rules_floor_md(floor if isinstance(floor, dict) else None))
    parts.append("### 2.2 风险点\n")
    risk_points = (
        feats.get("risk_points")
        or finance.get("risk_points")
        or []
    )
    parts.append(_risk_points_md(risk_points if isinstance(risk_points, list) else []))
    parts.append("### 2.3 四维分析（LLM）\n")
    if feats.get("submit_composed_from_skills"):
        parts.append(
            "> 注：本次由服务端用 skill 结果拼装四维/reasoning（`submit_composed_from_skills`），"
            "非模型 submit 原文。\n"
        )
    elif feats.get("submit_recovered"):
        parts.append(
            "> 注：本次 submit 参数不完整，已由服务端恢复四维草稿与规则分（`submit_recovered`）。\n"
        )
    parts.append(
        _dimensions_md(
            feats.get("dimensions") or [],
            submit_recovered=bool(feats.get("submit_recovered")),
            think_status=feats.get("think_status"),
            rules_floor=floor if isinstance(floor, dict) else None,
        )
    )
    parts.append("### 2.4 推理链\n")
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
    elif feats.get("think_status") == "think_from_content":
        parts.append(
            "_submit 轮无 message.reasoning，已用 content/tool.reason 降级为 `think_from_content`_\n"
        )
    elif feats.get("think_status") in {"reasoning_missing", "reasoning_missing_after_retry"}:
        parts.append(f"_submit 轮 think 状态：`{feats.get('think_status')}`_\n")
    turn_think = feats.get("turn_think_status") or []
    if not turn_think:
        # 从工具链回填
        for t in (finance.get("trace") or {}).get("tool_calls") or []:
            if isinstance(t, dict) and (t.get("think_status") or t.get("status")):
                turn_think.append(
                    {
                        "turn": t.get("turn"),
                        "tool": t.get("tool"),
                        "think_status": t.get("think_status") or t.get("status"),
                    }
                )
    if turn_think:
        parts.append("**逐轮 think 状态**\n")
        parts.append("| 轮次 | 工具 | 状态 |")
        parts.append("|------|------|------|")
        for row in turn_think:
            parts.append(
                f"| {row.get('turn') if row.get('turn') is not None else '—'} | "
                f"`{row.get('tool') or '—'}` | `{row.get('think_status') or '—'}` |"
            )
        parts.append("")
    parts.append("### 2.5 门控\n")
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
    parts.append("### 2.6 抽取指标与现金消耗\n")
    parts.append(_metrics_table(finance.get("metrics") or {}))
    parts.append("**3.4 现金消耗（cash_burn）**\n")
    parts.append(_cash_burn_md(finance))
    parts.append("### 2.7 召回证据（主表）\n")
    if fin_ev:
        parts.append("| 表/字段 | 页码 | 类型 | 命中数 | 年份列 | 摘录 |")
        parts.append("|--------|------|------|--------|--------|------|")
        for e in fin_ev:
            excerpt = _clean_excerpt(e.get("excerpt") or "—", 180)
            parts.append(
                "| {fc} | {page} | {st} | {n} | {years} | {ex} |".format(
                    fc=e.get("field_code"),
                    page=e.get("page") if e.get("page") is not None else "—",
                    st=e.get("source_type"),
                    n=e.get("n_hits") if e.get("n_hits") is not None else "—",
                    years=",".join(str(x) for x in (e.get("years") or [])) or "—",
                    ex=excerpt.replace("|", "/"),
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
    parts.append("#### 2.7.1 章节化上下文证据\n")
    if section_routes:
        for route in section_routes:
            route_bits = []
            for item in route.get("route") or []:
                sid = item.get("section_id")
                span = f"{sid}@p{item.get('start_page')}-{item.get('end_page')}"
                if item.get("contributed_hits") is False:
                    span += "（未贡献命中）"
                route_bits.append(span)
            parts.append(
                f"- intent=`{route.get('intent')}` query=`{route.get('query')}` → "
                f"{', '.join(route_bits) or '无可用章节'}"
            )
        parts.append("")
    display_hits = _dedupe_section_hits_for_display(
        [h for h in section_hits if isinstance(h, dict)]
    )
    if display_hits:
        parts.append("| 意图章节 | 页码 | 类型 | 分数 | 匹配词 | 摘录 |")
        parts.append("|---|---:|---|---:|---|---|")
        for hit in display_hits:
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
    parts.append("### 2.8 工具调用链（摘要）\n")
    parts.append(_tool_trace_summary_md(finance.get("trace") or {}))
    parts.append("### 2.9 分析结论\n")
    for n in _analyze_finance(finance):
        parts.append(f"- {n}")
    parts.append("")
    nf_raw = feats.get("negative_findings") or []
    nf_kept, nf_dropped = _filter_negative_findings(
        nf_raw if isinstance(nf_raw, list) else [],
        finance.get("score_breakdown") or [],
    )
    parts.append("### 2.10 阴性发现（已审查未见风险）\n")
    if nf_kept:
        for item in nf_kept:
            parts.append(
                f"- **{item.get('code')}**（{item.get('rule_ref')}）：{item.get('description')}"
            )
        parts.append("")
    else:
        msg = "_无合格阴性发现_"
        if nf_dropped:
            msg += f"（已忽略 {nf_dropped} 条与扣分码冲突的语义反转项）"
        parts.append(msg + "\n")
    bs = feats.get("bs_reconcile") or {}
    if bs.get("notes"):
        parts.append("### 2.11 资产负债表交叉校验\n")
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
            feat = _legal_section_feat(legal, sec)
            status = (
                f"skipped={feat.get('skipped')}"
                if feat.get("skipped")
                else f"exists={feat.get('exists')}"
            )
            extra = []
            for k in (
                "ratio_pct",
                "ratio_source",
                "listing_rule_pct_max",
                "waiver_pct_threshold",
                "top1_customer_pct",
                "top5_customer_pct",
                "top1_supplier_pct",
                "top5_supplier_pct",
                "redemption_high",
                "redemption_medium",
                "related_party_ratio_gt_30",
                "concentration_high",
                "pipeline_high",
                "stages_mentioned",
                "valuation_inversion",
                "owner",
                "reason",
            ):
                if feat.get(k) not in (None, False, "", []):
                    extra.append(f"{k}={feat.get(k)}")
                elif feat.get(k) is False and k in {
                    "redemption_high",
                    "valuation_inversion",
                    "pipeline_high",
                    "related_party_ratio_gt_30",
                    "concentration_high",
                }:
                    extra.append(f"{k}=False")
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

        parts.append("### 3.5 工具调用链（摘要）\n")
        parts.append(_tool_trace_summary_md(legal.get("trace") or {}))
        parts.append("### 3.6 分析结论\n")
        for n in _analyze_legal(legal):
            parts.append(f"- {n}")
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
