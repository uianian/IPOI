from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from src.models.debate import DebateClaim, DebateDossier, save_dossier
from src.models.evidence import EvidenceRef
from src.skills.analyze_finance import _normalize_risk_points, compose_from_llm
from src.skills.base import SkillInput
from src.skills.evidence_utils import compact_hits, hit_pages, normalize_query_record
from src.skills.extract_financials import extract_financials_from_retrieval
from src.skills.finance_labels import (
    build_tables_detail_from_bundle,
    metric_name_zh,
    table_name_zh,
)
from src.skills.finance_presets import FINANCE_SKILL_NAMES, build_finance_skills
from src.skills.gates import compute_cash_burn, resolve_issuer_gates
from src.skills.score_finance import score_finance, score_to_level
from src.tools.retrieval_tool import retrieve_agent, retrieve_section_evidence
from src.tools.schemas import FINANCE_TOOL_SCHEMAS, ToolRegistry

logger = logging.getLogger(__name__)

PKG_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEBATE_DIR = PKG_ROOT / ".runtime" / "debate"

_SEARCH_QUOTA_DEFAULT = 2
_SEARCH_QUOTA_WITH_GAPS = 3

_CODE_TO_SKILL = {
    "CONTINUOUS_LOSS": "finance_profitability",
    "SINGLE_YEAR_LOSS": "finance_profitability",
    "GP_MARGIN_DROP": "finance_profitability",
    "CFO_NEGATIVE": "finance_cash_flow",
    "CASH_RUNWAY_LT_12": "finance_cash_flow",
    "CASH_RUNWAY_12_24": "finance_cash_flow",
    "BURN_YOY_UP_30": "finance_cash_flow",
    "CV_PREF_LIABILITY": "finance_solvency",
}


_KEY_METRICS_FOR_LLM = (
    "REV",
    "OTHER_INCOME",
    "GP",
    "GP_MARGIN",
    "NET_LOSS",
    "CFO",
    "CASH_EQ",
    "END_CASH",
    "TOTAL_ASSETS",
    "TOTAL_LIAB",
    "NET_ASSETS",
)


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Small observation for the LLM; full metrics stay in state."""
    out: dict[str, Any] = {}
    for key in _KEY_METRICS_FOR_LLM:
        if not isinstance(metrics.get(key), dict):
            continue
        display_key = "NET_PROFIT_OR_LOSS" if key == "NET_LOSS" else key
        out[display_key] = metrics[key]
    return out


def _compact_section_hits(hits: list[dict[str, Any]], *, excerpt_chars: int = 120) -> list[dict[str, Any]]:
    return compact_hits(hits, excerpt_chars=excerpt_chars)


def _healthy_profit_path(metrics: dict[str, Any], gates: dict[str, Any]) -> bool:
    if gates.get("is_unprofitable") or not gates.get("skip_3_4"):
        return False
    net = metrics.get("NET_LOSS") or {}
    cfo = metrics.get("CFO") or {}
    gp_margin = metrics.get("GP_MARGIN") or {}
    if not net or not cfo:
        return False
    profits_ok = all(float(v) > 0 for v in net.values() if v is not None)
    cfo_ok = all(float(v) > 0 for v in cfo.values() if v is not None)
    margin_values = [float(v) for v in gp_margin.values() if v is not None]
    margin_ok = (
        len(margin_values) < 2
        or (margin_values[-1] - margin_values[0]) > -5.0
    )
    return profits_ok and cfo_ok and margin_ok


async def _tool_retrieve_finance(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    bundle = await retrieve_agent(
        "finance",
        state["doc_id"],
        issuer_type=state.get("issuer_type") or "general",
        top_k=state.get("top_k"),
        offline_json=state.get("retrieval_json"),
    )
    state["bundle"] = bundle
    tables_detail = build_tables_detail_from_bundle(bundle)
    tables = [t["code"] for t in tables_detail] or list(
        (bundle.get("evidence_by_table") or {}).keys()
    )
    return {
        "ok": True,
        "source": bundle.get("_source"),
        "tables": tables,
        "tables_detail": tables_detail,
        "skipped_fields": len(bundle.get("skipped_fields") or []),
        "hint": "下一步可调用 extract_metrics",
    }


async def _tool_extract_metrics(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    bundle = state.get("bundle")
    if not bundle:
        return {"ok": False, "error": "请先调用 retrieve_finance"}
    extracted = extract_financials_from_retrieval(bundle)
    state["extracted"] = extracted
    state["metrics"] = extracted.get("metrics") or {}
    state["metrics_extracted"] = True
    summary_raw = _compact_metrics(state["metrics"])
    table_meta = extracted.get("table_meta") or {}
    tables_from_meta = [
        {
            "code": code,
            "nameZh": table_name_zh(code),
            "page": (info or {}).get("page") if isinstance(info, dict) else None,
            "sourceType": (info or {}).get("source_type") if isinstance(info, dict) else None,
            "excerpt": ((info or {}).get("excerpt") or "")[:160] if isinstance(info, dict) else "",
        }
        for code, info in table_meta.items()
    ]
    empty = not state["metrics"]
    missing_is = "TBL_IS" not in table_meta
    hint = "下一步可调用 derive_gates"
    if empty or missing_is:
        hint = (
            "metrics 为空或未召回 TBL_IS：请 search_finance_evidence / retrieve_context_evidence "
            "补损益表后再 extract_metrics；若仍空可 derive_gates（将标记 metrics_empty）"
        )
    return {
        "ok": True,
        "metric_keys": list(state["metrics"].keys()),
        "metric_keys_zh": [
            {"code": k, "nameZh": metric_name_zh(k)} for k in state["metrics"].keys()
        ],
        "years": extracted.get("years"),
        "metrics_summary": summary_raw,
        "metrics_empty": empty,
        "missing_tbl_is": missing_is,
        "tables_detail": tables_from_meta or build_tables_detail_from_bundle(bundle),
        "metric_note": "期內虧損/利潤(NET_LOSS/NET_PROFIT_OR_LOSS)：正數=盈利，負數=虧損。",
        "bs_reconcile": {
            "changed": bool((extracted.get("bs_reconcile") or {}).get("changed")),
            "note": ((extracted.get("bs_reconcile") or {}).get("notes") or [None])[0],
        },
        "hint": hint,
    }


async def _tool_derive_gates(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("metrics_extracted") and "extracted" not in state:
        return {"ok": False, "error": "请先 extract_metrics"}
    metrics = state.get("metrics") or {}
    metrics_empty = not metrics
    gates = resolve_issuer_gates(state.get("issuer_type") or "general", metrics)
    state["gates"] = gates
    slim = {
        k: gates[k]
        for k in (
            "is_unprofitable",
            "continuous_net_loss",
            "latest_full_year_loss",
            "skip_3_4",
            "skip_3_4_reason",
            "skip_2_4",
            "issuer_type",
            "is_biotech_18a",
            "net_series",
            "profitability_basis",
            "profitability_known",
            "profitability_status",
        )
        if k in gates
    }
    if metrics_empty:
        hint = (
            "metrics_empty：已 extract 但无时间序列。"
            "请优先 search 补 TBL_IS/NET_LOSS；勿交 very_low=0。"
        )
    elif _healthy_profit_path(metrics, gates):
        hint = (
            "fast_path.eligible=true：可直接 submit 低风险报告；"
            "仅当要分析加盟/供应链/融资依赖时再 retrieve_context_evidence。"
        )
    else:
        hint = (
            "若未盈利可 calc_cash_runway；非主表主题可 retrieve_context_evidence；否则 submit"
        )
    return {
        "ok": True,
        "gates": slim,
        "metrics_empty": metrics_empty,
        "fast_path": {
            "eligible": (not metrics_empty) and _healthy_profit_path(metrics, gates),
            "reason": "profitable_positive_cfo_stable_margin"
            if (not metrics_empty) and _healthy_profit_path(metrics, gates)
            else None,
        },
        "hint": hint,
    }


async def _tool_calc_cash_runway(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    metrics = state.get("metrics") or {}
    gates = state.get("gates")
    if not gates:
        gates = resolve_issuer_gates(state.get("issuer_type") or "general", metrics)
        state["gates"] = gates
    cash_burn = compute_cash_burn(metrics, gates)
    state["cash_burn"] = cash_burn
    return {
        "ok": True,
        "cash_burn": {
            "skipped": cash_burn.get("skipped"),
            "reason": cash_burn.get("reason"),
            "CASH_RUNWAY_MONTHS": cash_burn.get("CASH_RUNWAY_MONTHS"),
            "BURN_RATE_MONTHLY": cash_burn.get("BURN_RATE_MONTHLY"),
            "END_CASH": cash_burn.get("END_CASH"),
            "burn_basis": cash_burn.get("burn_basis"),
            "burn_yoy_up_gt_30": cash_burn.get("burn_yoy_up_gt_30"),
            "burn_yoy_basis": cash_burn.get("burn_yoy_basis"),
            "burn_yoy_growth_full": cash_burn.get("burn_yoy_growth_full"),
            "burn_yoy_growth_interim": cash_burn.get("burn_yoy_growth_interim"),
        },
        "hint": (
            "若 burn_yoy_up_gt_30=true，submit 可用规范码 BURN_YOY_UP_30(+15)；"
            "若有 CV_PREF 实质余额可用 CV_PREF_LIABILITY(+10)"
        ),
    }


async def _tool_retrieve_context_evidence(
    args: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query 必填"}
    intent = (args.get("intent") or "business_context").strip()
    top_k = int(args.get("top_k") or 5)
    parse_json = state.get("parse_json")
    if not parse_json:
        return {
            "ok": False,
            "error": "缺少 full_parse.json，无法执行章节化全书检索",
        }
    result = await retrieve_section_evidence(
        doc_id=state["doc_id"],
        intent=intent,
        query=query,
        parse_json=parse_json,
        section_hint=args.get("section_hint"),
        top_k=max(top_k * 2, top_k),  # 多取再去重/多样性裁剪
        prefer_source_type=args.get("prefer_source_type") or "mixed",
    )
    from src.tools.retrieval_tool import diversify_section_hits

    hits = diversify_section_hits(result.get("hits") or [], top_k=top_k)
    route = result.get("route") or []
    hit_sections = {str(h.get("section_id") or "") for h in hits}
    route_contrib = []
    for item in route:
        sid = str(item.get("section_id") or "")
        route_contrib.append(
            {
                **item,
                "contributed_hits": sid in hit_sections,
            }
        )
    state.setdefault("section_evidence_hits", []).extend(hits)
    state.setdefault("section_routes", []).append(
        {
            "intent": intent,
            "query": query,
            "route": route_contrib,
            "source": result.get("source"),
        }
    )
    state.setdefault("queries_used", []).append(
        normalize_query_record(
            tool="retrieve_context_evidence",
            intent=intent,
            query=query,
            section_hint=args.get("section_hint"),
            hits=len(hits),
            pages=hit_pages(hits),
        )
    )
    return {
        "ok": result.get("ok", True),
        "doc_id": result.get("doc_id"),
        "intent": intent,
        "query": query,
        "n": len(hits),
        "route": route_contrib,
        "hits": _compact_section_hits(hits),
        "hint": "完整证据已保存到 state；submit 时引用 page/section/excerpt 即可",
    }


# 模型自定义 code → 规则规范 code（避免 CONTINUOUS_NET_LOSS + CONTINUOUS_LOSS 双计）
_CODE_ALIASES: dict[str, str] = {
    "CONTINUOUS_NET_LOSS": "CONTINUOUS_LOSS",
    "NET_LOSS_CONTINUOUS": "CONTINUOUS_LOSS",
    "SINGLE_YEAR_NET_LOSS": "SINGLE_YEAR_LOSS",
    "LATEST_YEAR_LOSS": "SINGLE_YEAR_LOSS",
    "NEGATIVE_CFO": "CFO_NEGATIVE",
    "CFO_PERSISTENTLY_NEGATIVE": "CFO_NEGATIVE",
    "CFO_QUALITY": "CFO_NEGATIVE",
    "CASHFLOW_001": "CFO_NEGATIVE",
    "CASH_FLOW_NEGATIVE": "CFO_NEGATIVE",
    "PROFIT_001": "CONTINUOUS_LOSS",
    "GP_MARGIN_DROP_GT_5PP": "GP_MARGIN_DROP",
    "GP_DROP": "GP_MARGIN_DROP",
    "BURN_YOY": "BURN_YOY_UP_30",
    "BURN_YOY_UP": "BURN_YOY_UP_30",
    "OTHER_SOLVENCY_RISK": "CV_PREF_LIABILITY",
    "OTHER_SOLVENCY": "CV_PREF_LIABILITY",
    "PREFERRED_LIABILITY": "CV_PREF_LIABILITY",
    "CV_PREF": "CV_PREF_LIABILITY",
    "REDEEM_LIABILITY": "CV_PREF_LIABILITY",
    "REDEMPTION_LIABILITY": "CV_PREF_LIABILITY",
}

# 规范码 → 主题桶（同主题只保留一项）
_CODE_THEME: dict[str, str] = {
    "CONTINUOUS_LOSS": "loss",
    "SINGLE_YEAR_LOSS": "loss",
    "CFO_NEGATIVE": "cfo",
    "GP_MARGIN_DROP": "gp_margin",
    "CASH_RUNWAY_LT_12": "runway",
    "CASH_RUNWAY_12_24": "runway",
    "RUNWAY_UNCERTAIN": "runway",
    "BURN_YOY_UP_30": "burn_yoy",
    "CV_PREF_LIABILITY": "cv_pref",
}

_RULE_CODES = frozenset(_CODE_THEME)


def _runway_canonical_from_state(state: dict[str, Any]) -> str | None:
    cash = state.get("cash_burn") or {}
    if cash.get("skipped"):
        return None
    try:
        months = float(cash.get("CASH_RUNWAY_MONTHS"))
    except (TypeError, ValueError):
        return None
    if months < 12:
        return "CASH_RUNWAY_LT_12"
    if months < 24:
        return "CASH_RUNWAY_12_24"
    return None


def _canonical_score_code(code: str, state: dict[str, Any] | None = None) -> str:
    c = str(code or "").upper().strip()
    if not c:
        return ""
    if c in _CODE_ALIASES:
        c = _CODE_ALIASES[c]
    # 跑道无法测算：保留 uncertainty，禁止发明 12_24
    if c in {"RUNWAY_UNCERTAIN", "CASH_RUNWAY_UNCERTAIN", "RUNWAY_UNKNOWN"}:
        return "RUNWAY_UNCERTAIN"
    # 跑道类：一律映射到规则档位（以 cash_burn 为准，防 LLM +20 再叠规则 +10）
    if (
        c.startswith("CASH_RUNWAY")
        or c in {"SHORT_CASH_RUNWAY", "RUNWAY", "RUNWAY_SHORT"}
        or ("RUNWAY" in c and "BURN" not in c)
    ):
        mapped = _runway_canonical_from_state(state or {})
        if mapped:
            return mapped
        return "RUNWAY_UNCERTAIN"
    if c.startswith("PROFIT_") or (
        "LOSS" in c and "SINGLE" not in c and "GP" not in c
        and (c.startswith("PROFIT") or "CONTINUOUS" in c or c.startswith("CONT"))
    ):
        return "CONTINUOUS_LOSS"
    if "CONTINUOUS" in c and "LOSS" in c:
        return "CONTINUOUS_LOSS"
    if c in {"CONT_LOSS", "CONTLOSS"} or (c.startswith("CONT") and "LOSS" in c):
        return "CONTINUOUS_LOSS"
    if c.startswith("CASHFLOW") or (
        "CFO" in c and ("NEG" in c or "NEGATIVE" in c or "QUALITY" in c or c.endswith("_001"))
    ):
        return "CFO_NEGATIVE"
    if "SINGLE" in c and "LOSS" in c:
        return "SINGLE_YEAR_LOSS"
    if c in {"NEG_CFO", "NEGCFO"}:
        return "CFO_NEGATIVE"
    if (
        c.startswith("OTHER_SOLVENCY")
        or "PREFERRED" in c
        or "CV_PREF" in c
        or ("REDEEM" in c and "RUNWAY" not in c)
    ):
        return "CV_PREF_LIABILITY"
    return c


def _theme_of_code(code: str) -> str:
    return _CODE_THEME.get(code, "other")


def _fill_display_fields(keep: dict[str, Any], donor: dict[str, Any]) -> None:
    """规则锚定时从 LLM 同行回填展示字段。"""
    for key in ("metric_value", "evidence_page", "evidence"):
        if keep.get(key) in (None, "", [], {}):
            if donor.get(key) not in (None, "", [], {}):
                keep[key] = donor.get(key)
    # note：保留规则托底后缀，但补上 LLM 说明
    donor_note = str(donor.get("note") or "").strip()
    keep_note = str(keep.get("note") or "").strip()
    if donor_note and donor_note not in keep_note and "规则托底" in keep_note:
        keep["note"] = f"{donor_note}；{keep_note}"


def _merge_by_theme(
    items: list[tuple[dict[str, Any], str]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    """同主题取 max(delta)；有规则命中时保留规则 code/rule_ref（规则为锚）。

    跑道主题例外：一旦规则命中，delta 固定为规则档（勿让 LLM 把 12–24 月抬到 +20）。
    """
    buckets: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    for row, source in items:
        code = str(row.get("code") or "")
        theme = _theme_of_code(code) if code in _RULE_CODES else f"other:{code}"
        try:
            delta = float(row.get("delta") or 0)
        except (TypeError, ValueError):
            delta = 0.0
        prev = buckets.get(theme)
        if prev is None:
            buckets[theme] = dict(row)
            sources[theme] = source
            continue
        try:
            prev_delta = float(prev.get("delta") or 0)
        except (TypeError, ValueError):
            prev_delta = 0.0
        prev_src = sources.get(theme) or "llm"
        if source == "rules" and prev_src != "rules":
            keep = dict(row)
            if theme == "runway":
                keep["delta"] = delta  # 规则档位
                warnings.append(f"theme_runway_anchor:{keep.get('code')}:{delta:g}")
            else:
                keep["delta"] = max(delta, prev_delta)
                if delta < prev_delta:
                    keep["note"] = (
                        (keep.get("note") or "") + f"（主题max取LLMΔ{prev_delta:g}）"
                    ).strip()
                warnings.append(f"theme_max_anchor:{theme}:{keep.get('code')}")
            _fill_display_fields(keep, prev)
            buckets[theme] = keep
            sources[theme] = "rules"
        elif source == "rules" and prev_src == "rules":
            if delta > prev_delta:
                buckets[theme] = dict(row)
        else:
            if prev_src == "rules":
                if theme == "runway":
                    _fill_display_fields(prev, row)
                    continue  # 规则已锚定跑道档，忽略 LLM 加高
                if delta > prev_delta:
                    prev = dict(prev)
                    prev["delta"] = delta
                    prev["note"] = (
                        (prev.get("note") or "") + f"（主题max取LLMΔ{delta:g}）"
                    ).strip()
                    _fill_display_fields(prev, row)
                    buckets[theme] = prev
                    warnings.append(f"theme_max_llm_raise:{theme}:{prev.get('code')}")
                else:
                    _fill_display_fields(prev, row)
                    buckets[theme] = prev
            elif delta > prev_delta:
                buckets[theme] = dict(row)
                sources[theme] = source
    return list(buckets.values())


def _merge_rules_floor(
    report: dict[str, Any],
    state: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    """规则托底：规范码归并 + 主题 max（规则为锚）；最终分=主题胜出之和。"""
    metrics = state.get("metrics") or {}
    gates = state.get("gates") or {}
    cash_burn = state.get("cash_burn") or {"skipped": True, "reason": "not_computed"}
    if not cash_burn or cash_burn.get("skipped") is True:
        cash_burn = compute_cash_burn(metrics, gates)
        state["cash_burn"] = cash_burn
    extracted = state.get("extracted") or {"evidence": {}, "table_meta": {}}
    rules_pack = score_finance(metrics, gates, cash_burn, extracted)
    rules_bd = list(rules_pack.get("score_breakdown") or [])
    llm_bd = list(report.get("score_breakdown") or [])

    staged: list[tuple[dict[str, Any], str]] = []
    for b in llm_bd:
        if not isinstance(b, dict):
            continue
        code = _canonical_score_code(str(b.get("code") or ""), state)
        if not code:
            continue
        row = dict(b)
        row["code"] = code
        try:
            row["delta"] = float(row.get("delta") or 0)
        except (TypeError, ValueError):
            row["delta"] = 0.0
        if not row.get("rule_ref"):
            row["rule_ref"] = "llm"
        staged.append((row, "llm"))
    for b in rules_bd:
        if not isinstance(b, dict):
            continue
        code = _canonical_score_code(str(b.get("code") or ""), state)
        if not code:
            continue
        row = dict(b)
        row["code"] = code
        try:
            row["delta"] = float(row.get("delta") or 0)
        except (TypeError, ValueError):
            row["delta"] = 0.0
        if not row.get("rule_ref"):
            row["rule_ref"] = "doc"
        row["note"] = ((row.get("note") or "") + "（规则托底）").strip()
        staged.append((row, "rules"))

    merged = _merge_by_theme(staged, warnings)

    codes = {str(x.get("code") or "") for x in merged}
    if "CONTINUOUS_LOSS" in codes and "SINGLE_YEAR_LOSS" in codes:
        merged = [x for x in merged if str(x.get("code") or "") != "SINGLE_YEAR_LOSS"]
        warnings.append("dedupe_drop:SINGLE_YEAR_LOSS")

    report["score_breakdown"] = merged
    llm_score = 0.0
    try:
        llm_score = float(report.get("risk_score") or 0)
    except (TypeError, ValueError):
        llm_score = 0.0
    rules_score = float(rules_pack.get("risk_score") or 0)
    breakdown_sum = sum(float(b.get("delta") or 0) for b in merged)
    hard = bool(
        gates.get("is_unprofitable")
        or gates.get("continuous_net_loss")
        or (rules_pack.get("flags") or {}).get("cfo_persistently_negative")
    )
    final = breakdown_sum
    if not hard:
        final = max(llm_score, breakdown_sum)
    final = max(0.0, min(100.0, final))

    if hard and final <= 0:
        from_flags = _breakdown_from_flags(state)
        if from_flags:
            merged = _merge_by_theme(
                [(dict(x), "rules") for x in from_flags],
                warnings,
            )
            report["score_breakdown"] = merged
            final = sum(float(b.get("delta") or 0) for b in merged)
            warnings.append("rules_floor_forced_nonzero")
    if hard and not merged and rules_bd:
        staged_r: list[tuple[dict[str, Any], str]] = []
        for b in rules_bd:
            if isinstance(b, dict):
                code = _canonical_score_code(str(b.get("code") or ""), state)
                row = dict(b)
                row["code"] = code
                staged_r.append((row, "rules"))
        merged = _merge_by_theme(staged_r, warnings)
        report["score_breakdown"] = merged
        final = sum(float(b.get("delta") or 0) for b in merged)
        warnings.append("rules_floor_filled_empty_breakdown")

    report["risk_score"] = final
    report["risk_level"] = score_to_level(final)
    if not report.get("risk_points") and rules_pack.get("risk_points"):
        report["risk_points"] = rules_pack["risk_points"]
    report["rules_floor"] = {
        "rules_score": rules_score,
        "rules_score_deduped": breakdown_sum,
        "llm_score": llm_score,
        "final_score": final,
        "flags": rules_pack.get("flags") or {},
        "theme_merge": True,
    }
    # 叙事对齐改在 DATA_INSUFFICIENT 等最终抬分之后（见 finalize_finance_report）
    return report


_UNDERSTATE_LOW_RE = re.compile(
    r"(财务|財務)?风险(较|很)?低|低风险|風險(較|很)?低|低風險|"
    r"风险处于可控的低|風險處於可控的低|中低风险|中低風險|"
    r"整体财务风险可控|整體財務風險可控|财务风险可控|財務風險可控|"
    r"屬低[-–]?中風險|属低[-–]?中风险|屬低風險|属低风险|"
    r"財務風險屬中低|财务风险属中低|風險屬中低|风险属中低|"
    r"定為低|定为低|評為低|评为低",
)
_DINGWEI_LOW_RE = re.compile(r"(定為|定为|評為|评为|屬|属)低(?![-–]?中)")
_PAREN_LABEL_LEVEL = (
    ("极低", "very_low"),
    ("極低", "very_low"),
    ("中低", "low"),
    ("低中", "low"),
    ("中等", "medium"),
    ("中级", "medium"),
    ("中級", "medium"),
    ("极高", "very_high"),
    ("極高", "very_high"),
    ("低", "low"),
    ("中", "medium"),
    ("高", "high"),
)
_UNDERSTATE_MED_RE = re.compile(
    r"风险中等|風險中等|风险评级为中等|风险评级定为中等|風險評級為中等|風險評級定為中等",
)
_SCORE_MENTION_RE = re.compile(
    r"(綜合風險分|综合风险分|總風險分|总风险分|風險分數|风险分数|風險分|风险分|"
    r"規則打分|规则打分|綜合風險等級為|综合风险等级为)"
    r"\s*[為为:]?\s*(\d+(?:\.\d+)?)\s*(?:分)?"
    r"(?:\s*[（(]\s*([^）)]*?)\s*[）)])?",
)
# 康灃/永泰：「中級（40分）」「綜合風險等級為中等（40分）」
_PAREN_SCORE_RE = re.compile(
    r"([中高高低极極]+[等級级]?)\s*[（(]\s*(\d+(?:\.\d+)?)\s*分\s*[）)]"
)
_LEVEL_ZH = {
    "very_low": "极低",
    "low": "低",
    "medium": "中等",
    "high": "高",
    "very_high": "极高",
}


def _align_narrative_to_level(report: dict[str, Any], warnings: list[str]) -> None:
    """最终分确定后纠正 summary/reasoning 中残留的旧分数/等级措辞。"""
    level = str(report.get("risk_level") or "")
    try:
        score = float(report.get("risk_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    level_zh = _LEVEL_ZH.get(level, level)
    note = (
        f"（注：规则托底后综合评分 {score:.0f}，等级 {level}，"
        f"叙述以该等级为准。）"
    )
    score_token = f"{score:.0f}"

    def _rewrite_score_mentions(text: str) -> tuple[str, bool]:
        changed = False

        def _repl(m: re.Match[str]) -> str:
            nonlocal changed
            label = m.group(1)
            try:
                old = float(m.group(2))
            except (TypeError, ValueError):
                return m.group(0)
            paren = (m.group(3) or "").strip() if m.lastindex and m.lastindex >= 3 else ""
            score_mismatch = abs(old - score) >= 0.5
            level_mismatch = bool(paren) and paren not in {
                level,
                level_zh,
                f"{level_zh}风险",
                f"{level_zh}風險",
            }
            if not score_mismatch and not level_mismatch:
                return m.group(0)
            changed = True
            return f"{label}{score_token}（{level_zh}）"

        new = _SCORE_MENTION_RE.sub(_repl, text)

        def _paren_label_level(label: str) -> str | None:
            s = (label or "").strip()
            for tok, lv in _PAREN_LABEL_LEVEL:
                if tok in s:
                    return lv
            return None

        def _paren_repl(m: re.Match[str]) -> str:
            nonlocal changed
            try:
                old = float(m.group(2))
            except (TypeError, ValueError):
                return m.group(0)
            mapped = _paren_label_level(m.group(1))
            score_mismatch = abs(old - score) >= 0.5
            level_mismatch = mapped is not None and mapped != level
            if not score_mismatch and not level_mismatch:
                return m.group(0)
            changed = True
            return f"{level_zh}（{score_token}分）"

        new = _PAREN_SCORE_RE.sub(_paren_repl, new)
        if level in {"medium", "high", "very_high"}:
            new2, n = _DINGWEI_LOW_RE.subn(rf"\g<1>{level_zh}", new)
            if n:
                changed = True
                new = new2
        return new, changed

    def _mismatch_level_words(text: str) -> bool:
        if level in {"medium", "high", "very_high"} and _UNDERSTATE_LOW_RE.search(text):
            return True
        if level in {"high", "very_high"} and _UNDERSTATE_MED_RE.search(text):
            return True
        return False

    def _fix(text: str) -> str | None:
        if not text:
            return None
        new, score_changed = _rewrite_score_mentions(text)
        need_note = _mismatch_level_words(new)
        if not score_changed and not need_note:
            return None
        if need_note and "规则托底后" not in new and "規則托底後" not in new:
            new = new.rstrip("。.") + note
        return new

    for key in ("summary", "reasoning"):
        fixed = _fix(str(report.get(key) or ""))
        if fixed:
            report[key] = fixed
            warnings.append(f"narrative_aligned:{key}")
    for dim in report.get("dimensions") or []:
        if not isinstance(dim, dict):
            continue
        fixed = _fix(str(dim.get("analysis") or ""))
        if fixed:
            dim["analysis"] = fixed
            warnings.append(f"narrative_aligned:dim:{dim.get('dimension')}")

def _metric_series_brief(metrics: dict[str, Any], code: str) -> str:
    series = metrics.get(code) if isinstance(metrics.get(code), dict) else None
    if not series:
        return "無"
    parts = [f"{y}={v}" for y, v in list(series.items())[:4]]
    return "；".join(parts)


_SKILL_TO_DIMENSION: dict[str, str] = {
    "finance_profitability": "profitability_growth",
    "finance_cash_flow": "cash_flow",
    "finance_solvency": "solvency",
    "finance_business_context": "business_context",
}


def _points_brief(points: list[Any], *, limit: int = 4) -> str:
    parts: list[str] = []
    for p in points[:limit]:
        if not isinstance(p, dict):
            continue
        code = str(p.get("code") or "").strip()
        desc = str(p.get("description") or p.get("note") or "").strip()[:80]
        if code and desc:
            parts.append(f"{code}：{desc}")
        elif code:
            parts.append(code)
        elif desc:
            parts.append(desc)
    return "；".join(parts)


def _draft_finance_dimensions_metrics(state: dict[str, Any]) -> list[dict[str, Any]]:
    """仅用 metrics/gates/cash_burn 拼四维短草稿（按 issuer 分支）。"""
    metrics = state.get("metrics") or {}
    gates = state.get("gates") or {}
    cash = state.get("cash_burn") or {}
    issuer = str(gates.get("issuer_type") or state.get("issuer_type") or "general").lower()
    is_biotech = bool(gates.get("is_biotech_18a")) or issuer in {"18a", "biotech", "18c"}

    net = _metric_series_brief(metrics, "NET_LOSS")
    cfo = _metric_series_brief(metrics, "CFO")
    assets = _metric_series_brief(metrics, "NET_ASSETS")
    liab = _metric_series_brief(metrics, "TOTAL_LIAB")
    runway = cash.get("CASH_RUNWAY_MONTHS")
    runway_txt = f"{runway}" if runway is not None else "未測算"

    if is_biotech:
        biz = (
            "18A/生物科技：主表顯示無產品收入（OTHER_INCOME 非產品收入）；"
            f"未盈利={gates.get('is_unprofitable')}，現金跑道約 {runway_txt} 個月；"
            "商業模式按未商業化管線/融資依賴理解；未強制檢索加盟/傳統業務模式。"
        )
        biz_status = "analyzed"
    else:
        biz = "非主表商業模式證據不足或未檢索，標記 skipped/證據較弱。"
        biz_status = "skipped"

    return [
        {
            "dimension": "profitability_growth",
            "status": "analyzed",
            "analysis": f"期內利潤/虧損序列：{net}。未盈利={gates.get('is_unprofitable')}，連續虧損={gates.get('continuous_net_loss')}。",
            "source": "metrics_draft",
        },
        {
            "dimension": "cash_flow",
            "status": "analyzed",
            "analysis": f"CFO：{cfo}。現金跑道約 {runway_txt} 個月（僅未盈利時評估）。",
            "source": "metrics_draft",
        },
        {
            "dimension": "solvency",
            "status": "analyzed",
            "analysis": f"淨資產：{assets}；總負債：{liab}。",
            "source": "metrics_draft",
        },
        {
            "dimension": "business_context",
            "status": biz_status,
            "analysis": biz,
            "source": "metrics_draft",
        },
    ]


def _compose_finance_dimensions_from_skills(state: dict[str, Any]) -> list[dict[str, Any]]:
    """用 skill_results（reasoning + 风险点）叠加 metrics 草稿，拼完整四维。"""
    base = {
        d["dimension"]: dict(d)
        for d in _draft_finance_dimensions_metrics(state)
        if isinstance(d, dict) and d.get("dimension")
    }
    skill_results = state.get("skill_results") or {}
    used_skill = False
    for skill_name, dim_name in _SKILL_TO_DIMENSION.items():
        data = skill_results.get(skill_name) or {}
        if not isinstance(data, dict) or not data:
            continue
        parts: list[str] = []
        metric_line = str((base.get(dim_name) or {}).get("analysis") or "").strip()
        if metric_line:
            parts.append(metric_line)
        reasoning = str(data.get("reasoning") or "").strip()
        if reasoning:
            parts.append(reasoning)
            used_skill = True
        points_txt = _points_brief(list(data.get("risk_points") or []))
        if points_txt:
            parts.append(f"風險點：{points_txt}")
            used_skill = True
        neg_txt = _points_brief(list(data.get("negative_findings") or []), limit=2)
        if neg_txt:
            parts.append(f"陰性：{neg_txt}")
            used_skill = True
        if not parts:
            continue
        has_signal = bool(
            reasoning
            or data.get("risk_points")
            or data.get("evidence")
            or data.get("negative_findings")
        )
        base[dim_name] = {
            "dimension": dim_name,
            "status": "analyzed" if has_signal else (base.get(dim_name) or {}).get("status") or "analyzed",
            "analysis": " ".join(parts)[:1400],
            "source": "skill+metrics" if has_signal else "metrics_draft",
            "skill": skill_name,
        }
    order = [
        "profitability_growth",
        "cash_flow",
        "solvency",
        "business_context",
    ]
    out = [base[k] for k in order if k in base]
    if used_skill:
        for d in out:
            d.setdefault("composed", True)
    return out


def _compose_finance_reasoning_from_skills(
    state: dict[str, Any],
    pack: dict[str, Any] | None = None,
) -> str:
    pack = pack or state.get("rule_pack") or {}
    skill_results = state.get("skill_results") or {}
    lines = [
        f"依 skill 結果彙總：規則參考分 {pack.get('risk_score')}（{pack.get('risk_level')}）；"
        f"已完成 {len(skill_results)}/{len(FINANCE_SKILL_NAMES)} skill。"
    ]
    for name in FINANCE_SKILL_NAMES:
        data = skill_results.get(name) or {}
        n = len((data or {}).get("risk_points") or [])
        reason = str((data or {}).get("reasoning") or "").strip()
        if reason:
            lines.append(f"- {name}：{n} 點；{reason[:320]}")
        elif n:
            brief = _points_brief(list((data or {}).get("risk_points") or []), limit=3)
            lines.append(f"- {name}：{n} 點；{brief}")
        elif name in skill_results:
            lines.append(f"- {name}：已執行，無額外風險點（見指標草稿）")
    think = str(state.get("last_reasoning") or "").strip()
    if think:
        lines.append("")
        lines.append("[model_think]")
        lines.append(think[:1200])
    return "\n".join(lines)


def _enrich_score_breakdown_from_skills(
    report: dict[str, Any],
    state: dict[str, Any],
) -> None:
    """把 skill/风险点描述与 metric_value 回填到 score_breakdown。"""
    by_code: dict[str, dict[str, Any]] = {}
    for p in report.get("risk_points") or []:
        if isinstance(p, dict) and p.get("code"):
            by_code[str(p["code"]).upper()] = p
    for data in (state.get("skill_results") or {}).values():
        for p in (data or {}).get("risk_points") or []:
            if not isinstance(p, dict) or not p.get("code"):
                continue
            code = str(p["code"]).upper()
            by_code.setdefault(code, p)
    cash = state.get("cash_burn") or {}
    metrics = state.get("metrics") or {}
    for b in report.get("score_breakdown") or []:
        if not isinstance(b, dict):
            continue
        code = str(b.get("code") or "").upper()
        p = by_code.get(code) or {}
        note = str(b.get("note") or "")
        weak = (not note) or ("规则托底" in note) or ("規則托底" in note) or note == code
        if weak and p.get("description"):
            b["note"] = str(p.get("description"))
        if b.get("metric_value") is None:
            mv = p.get("metric_value")
            if mv is None and code in {"CASH_RUNWAY_LT_12", "CASH_RUNWAY_12_24"}:
                mv = cash.get("CASH_RUNWAY_MONTHS")
            if mv is None and code == "CV_PREF_LIABILITY":
                cv = metrics.get("CV_PREF")
                if isinstance(cv, dict) and cv:
                    mv = list(cv.values())[-1]
                else:
                    mv = cv
            if mv is not None:
                b["metric_value"] = mv


def _compose_finance_submit_payload(
    state: dict[str, Any],
    pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """服务端交卷：用 rule_pack + skill_results 拼完整 submit 参数。"""
    pack = pack or state.get("rule_pack") or {}
    skill_points = _collect_skill_points(state)
    dimensions = _compose_finance_dimensions_from_skills(state)
    # 若有模型 think，附加到 business_context / 总 reasoning
    think = str(state.get("last_reasoning") or "").strip()
    if think:
        for d in dimensions:
            if d.get("dimension") == "business_context":
                d["analysis"] = (
                    str(d.get("analysis") or "")
                    + " [model_think摘录] "
                    + think[:500]
                )[:1400]
                d["source"] = "skill+metrics+think"
                break
    reasoning = _compose_finance_reasoning_from_skills(state, pack)
    score = pack.get("risk_score")
    level = pack.get("risk_level")
    summary = (
        f"財務規則參考分 {score}（{level}）；"
        f"四維由 {len(state.get('skill_results') or {})} 個 skill + 指標彙總"
        + ("；含模型 think" if think else "")
    )
    negatives: list[dict[str, Any]] = []
    for data in (state.get("skill_results") or {}).values():
        for n in (data or {}).get("negative_findings") or []:
            negatives.append(n if isinstance(n, dict) else {"description": str(n)})
    if not negatives:
        negatives = list(pack.get("negative_findings") or [])
    payload = {
        "risk_score": score,
        "risk_level": level,
        "score_breakdown": [dict(b) for b in (pack.get("score_breakdown") or []) if isinstance(b, dict)],
        "risk_points": skill_points or pack.get("risk_points") or [],
        "negative_findings": negatives,
        "dimensions": dimensions,
        "reasoning": reasoning,
        "summary": summary,
        "submit_composed_from_skills": True,
    }
    _enrich_score_breakdown_from_skills(payload, state)
    return payload


def _draft_finance_dimensions(state: dict[str, Any]) -> list[dict[str, Any]]:
    """空 submit 时优先 skill 拼装，否则回退 metrics 草稿。"""
    if state.get("skill_results"):
        return _compose_finance_dimensions_from_skills(state)
    return _draft_finance_dimensions_metrics(state)


def _breakdown_from_flags(state: dict[str, Any]) -> list[dict[str, Any]]:
    """无表证据时仍按 flags + score_rules 生成 breakdown（供 submit 截断恢复）。"""
    from src.config import load_score_rules
    from src.skills.score_finance import _cfo_persistently_negative

    metrics = state.get("metrics") or {}
    gates = state.get("gates") or {}
    cash_burn = state.get("cash_burn") or {"skipped": True}
    from src.skills.score_finance import cv_pref_material

    flags = {
        "continuous_net_loss": bool(gates.get("continuous_net_loss")),
        "latest_full_year_loss": bool(gates.get("latest_full_year_loss"))
        and bool(gates.get("is_unprofitable")),
        "cfo_persistently_negative": _cfo_persistently_negative(metrics),
        "gp_margin_drop_gt_5pp": False,
        "runway_lt_12": (cash_burn.get("CASH_RUNWAY_MONTHS") or 999) < 12
        and not cash_burn.get("skipped"),
        "runway_12_24": 12 <= (cash_burn.get("CASH_RUNWAY_MONTHS") or -1) < 24
        and not cash_burn.get("skipped"),
        "burn_yoy_up_gt_30": bool(cash_burn.get("burn_yoy_up_gt_30"))
        and not cash_burn.get("skipped"),
        "cv_pref_material": cv_pref_material(metrics),
    }

    out: list[dict[str, Any]] = []
    for rule in ((load_score_rules().get("finance") or {}).get("rules") or []):
        when = rule.get("when")
        if not when or not flags.get(when):
            continue
        if rule.get("require_gate") == "unprofitable" and gates.get("skip_3_4"):
            continue
        if when == "latest_full_year_loss" and flags.get("continuous_net_loss"):
            continue
        out.append(
            {
                "code": rule.get("code"),
                "delta": float(rule.get("delta") or 0),
                "rule_ref": rule.get("rule_ref"),
                "note": f"触发 {when}（submit 恢复，无表证据页）",
                "metric_value": None,
                "evidence": [],
            }
        )
    return out


def _recover_empty_finance_submit(report: dict[str, Any], state: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """submit arguments 空/残缺时，用规则分+四维草稿恢复，避免 llm_score 恒为 0 且无叙述。"""
    missing_score = report.get("risk_score") is None or report.get("risk_score") == ""
    empty_bd = not report.get("score_breakdown")
    empty_dim = not report.get("dimensions")
    if not (missing_score or empty_bd or empty_dim or not report.get("summary")):
        return report

    metrics = state.get("metrics") or {}
    gates = state.get("gates") or {}
    cash_burn = state.get("cash_burn") or {"skipped": True, "reason": "not_computed"}
    if cash_burn.get("skipped") is True and gates.get("is_unprofitable"):
        cash_burn = compute_cash_burn(metrics, gates)
        state["cash_burn"] = cash_burn
    extracted = state.get("extracted") or {"evidence": {}, "table_meta": {}}
    rules_pack = score_finance(metrics, gates, cash_burn, extracted)

    if empty_bd:
        bd = list(rules_pack.get("score_breakdown") or [])
        if not bd:
            bd = _breakdown_from_flags(state)
            if bd:
                warnings.append("submit_recovered:breakdown_from_flags")
        report["score_breakdown"] = bd
    if missing_score or float(report.get("risk_score") or 0) == 0:
        score = float(rules_pack.get("risk_score") or 0)
        if score <= 0 and report.get("score_breakdown"):
            score = sum(float(b.get("delta") or 0) for b in report["score_breakdown"])
        if report.get("risk_score") in (None, "", 0, 0.0) and score > 0:
            report["risk_score"] = score
            report["risk_level"] = score_to_level(score)
    if empty_dim:
        report["dimensions"] = _draft_finance_dimensions(state)
        if state.get("skill_results"):
            warnings.append("submit_composed_from_skills:dimensions")
            report["submit_composed_from_skills"] = True
    if not report.get("summary"):
        lvl = report.get("risk_level") or score_to_level(float(report.get("risk_score") or 0))
        if state.get("skill_results"):
            report["summary"] = (
                f"財務風險分 {float(report.get('risk_score') or 0):.1f}（{lvl}；"
                f"由 skill+規則彙總）"
            )
        else:
            report["summary"] = f"財務風險分 {float(report.get('risk_score') or 0):.1f}（{lvl}；submit 截斷後服務端恢復）"
    if not report.get("reasoning"):
        if state.get("skill_results"):
            report["reasoning"] = _compose_finance_reasoning_from_skills(state, rules_pack)
            report["submit_composed_from_skills"] = True
            warnings.append("submit_composed_from_skills:reasoning")
        else:
            report["reasoning"] = "submit 參數不完整，已按 metrics/gates/規則引擎恢復可解釋評分與四維草稿。"
    if not report.get("risk_points") and rules_pack.get("risk_points"):
        report["risk_points"] = list(rules_pack["risk_points"])

    report["submit_recovered"] = True
    warnings.append("submit_recovered:empty_or_partial_args")
    return report


_RISK_NEGATIVE_CODES = frozenset(_CODE_THEME) | {
    "PROFIT_001",
    "CASHFLOW_001",
    "CONT_LOSS",
    "NEG_CFO",
    "OTHER_SOLVENCY_RISK",
    "ASSET_EROSION",
}


def _sanitize_negative_findings(
    report: dict[str, Any],
    state: dict[str, Any],
    warnings: list[str],
) -> None:
    """negative_findings = 已审查未见风险；丢弃与扣分码冲突的语义反转项。"""
    bd_codes = {
        str(b.get("code") or "").upper()
        for b in (report.get("score_breakdown") or [])
        if isinstance(b, dict)
    }
    raw = list(report.get("negative_findings") or [])
    kept: list[dict[str, Any]] = []
    dropped = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").upper().strip()
        canon = _canonical_score_code(code, state) if code else ""
        if code in bd_codes or canon in bd_codes or code in _RISK_NEGATIVE_CODES or (
            canon in _RULE_CODES
        ):
            dropped += 1
            continue
        desc = str(item.get("description") or "")
        # 描述像风险加分项时也丢弃
        if any(
            k in desc
            for k in ("虧損擴大", "亏损扩大", "持續為負", "持续为负", "跑道不足", "流動負債淨額")
        ) and code in bd_codes | _RISK_NEGATIVE_CODES:
            dropped += 1
            continue
        kept.append(item)
    if dropped:
        warnings.append(f"negative_findings_dropped:{dropped}")
    try:
        score = float(report.get("risk_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    if not kept and score < 40:
        from src.skills.score_finance import _build_negative_findings

        metrics = state.get("metrics") or {}
        gates = state.get("gates") or {}
        cash_burn = state.get("cash_burn") or {"skipped": True}
        flags = (report.get("rules_floor") or {}).get("flags") or {}
        extracted = state.get("extracted") or {"evidence": {}, "table_meta": {}}
        kept = _build_negative_findings(metrics, gates, cash_burn, flags, extracted)
        if kept:
            warnings.append("negative_findings_backfilled")
    report["negative_findings"] = kept


def _validate_submit(report: dict[str, Any], state: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    gates = state.get("gates") or {}
    _recover_empty_finance_submit(report, state, warnings)
    if gates.get("skip_3_4"):
        for b in report.get("score_breakdown") or []:
            code = str(b.get("code") or "").upper()
            note = str(b.get("note") or "")
            if "RUNWAY" in code or "跑道" in note or "现金跑道" in note:
                warnings.append("skip_3_4=true，已剔除 runway 相关扣分")
                b["delta"] = 0
                b["note"] = (b.get("note") or "") + "（门控跳过，不计分）"
    if not state.get("metrics"):
        warnings.append("尚未 extract_metrics，报告可信度下降")
    if gates.get("profitability_status") == "unknown":
        warnings.append("profitability_unknown：勿宣称已盈利")
    _merge_rules_floor(report, state, warnings)
    _apply_18a_data_insufficient_guard(report, state, warnings)
    _sanitize_negative_findings(report, state, warnings)
    # 须在所有分数地板/抬升之后，避免「风险分25」与最终 40 残留不一致
    _align_narrative_to_level(report, warnings)
    return warnings


def _apply_18a_data_insufficient_guard(
    report: dict[str, Any],
    state: dict[str, Any],
    warnings: list[str],
) -> None:
    """18A 缺 NET_LOSS/空指标时禁止 silent very_low=0，保守抬至关注档。"""
    gates = state.get("gates") or {}
    metrics = state.get("metrics") or {}
    issuer = str(
        gates.get("issuer_type") or state.get("issuer_type") or ""
    ).lower()
    is_18a = issuer in {"18a", "biotech"} or bool(gates.get("is_biotech_18a"))
    if not is_18a:
        return
    net = metrics.get("NET_LOSS") or {}
    has_loss = isinstance(net, dict) and any(v is not None for v in net.values())
    if has_loss:
        return
    try:
        score = float(report.get("risk_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 40:
        warnings.append("data_insufficient:missing_NET_LOSS_but_score_ok")
        return
    floor = 40.0
    bd = [b for b in (report.get("score_breakdown") or []) if isinstance(b, dict)]
    if not any(str(b.get("code") or "") == "DATA_INSUFFICIENT_IS" for b in bd):
        bd.append(
            {
                "code": "DATA_INSUFFICIENT_IS",
                "delta": round(max(0.0, floor - score), 1),
                "rule_ref": "llm§data_gap",
                "note": (
                    "18A 主表/NET_LOSS 抽取不足，禁止 silent very_low=0；"
                    "保守抬至关注档，请复核损益表召回"
                ),
                "metric_value": None,
                "evidence": [],
            }
        )
    report["score_breakdown"] = bd
    report["risk_score"] = max(score, floor)
    report["risk_level"] = score_to_level(float(report["risk_score"]))
    warnings.append("data_insufficient:18a_missing_NET_LOSS_floor40")


def _finance_skills(state: dict[str, Any]) -> dict[str, Any]:
    if "_skills" not in state:
        state["_skills"] = build_finance_skills()
    return state["_skills"]


def _collect_skill_points(state: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for data in (state.get("skill_results") or {}).values():
        for p in data.get("risk_points") or []:
            if isinstance(p, dict) and p.get("code"):
                points.append(dict(p))
    return points


def _normalize_level(level: Any) -> str:
    lv = str(level or "medium").lower()
    if lv in {"very_high", "critical"}:
        return "high"
    if lv in {"very_low"}:
        return "low"
    return lv if lv in {"high", "medium", "low"} else "medium"


def _point_to_evidence_refs(point: dict[str, Any], state: dict[str, Any]) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    page = point.get("evidence_page")
    try:
        page = int(page) if page is not None else None
    except (TypeError, ValueError):
        page = None
    excerpt = str(point.get("evidence_excerpt") or "").strip()
    if page is not None or excerpt:
        refs.append(
            EvidenceRef(
                page=page,
                excerpt=excerpt[:200],
                source_type="table" if point.get("skill") != "finance_business_context" else "text",
                field_code=str(point.get("code") or "") or None,
                confidence=0.7 if page is not None else 0.4,
            )
        )
    for e in point.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        if e.get("page") is not None and e.get("page") != page and len(refs) < 3:
            refs.append(
                EvidenceRef(
                    page=e.get("page"),
                    excerpt=str(e.get("excerpt") or "")[:200],
                    source_type=e.get("source_type") or "table",
                    field_code=e.get("field_code"),
                    confidence=float(e.get("confidence") or 0.5),
                )
            )
    skill = point.get("skill")
    data = (state.get("skill_results") or {}).get(skill) or {}
    for e in (data.get("evidence") or [])[:4]:
        if e.get("page") is not None and e.get("page") != page and len(refs) < 3:
            refs.append(
                EvidenceRef(
                    page=e.get("page"),
                    excerpt=str(e.get("excerpt") or "")[:200],
                    source_type=e.get("source_type") or "text",
                    field_code=e.get("field_code"),
                    confidence=float(e.get("confidence") or 0.5),
                )
            )
    return refs


def build_finance_debate_dossier(
    state: dict[str, Any],
    report: dict[str, Any],
) -> DebateDossier:
    claims: list[DebateClaim] = []
    skill_results = state.get("skill_results") or {}
    seen_codes: set[str] = set()

    def _add_claim(p: dict[str, Any], *, default_skill: str | None = None) -> None:
        code = str(p.get("code") or "").upper()
        if not code or code in seen_codes:
            return
        seen_codes.add(code)
        skill = p.get("skill") or default_skill or _CODE_TO_SKILL.get(code) or "finance_business_context"
        data = skill_results.get(skill) or {}
        claims.append(
            DebateClaim(
                agent="finance",
                skill=skill,
                code=code,
                level=_normalize_level(p.get("level")),
                confidence=str(p.get("confidence") or "medium"),
                statement=str(p.get("description") or p.get("note") or code),
                metric_value=p.get("metric_value") if p.get("metric_value") is not None else p.get("value"),
                reasoning=str(data.get("reasoning") or report.get("reasoning") or ""),
                evidence_refs=_point_to_evidence_refs(p, state),
                retrieval_queries=[
                    q
                    for q in (state.get("queries_used") or [])
                    if q.get("skill") == skill
                ][:4],
            )
        )

    for p in report.get("risk_points") or []:
        if isinstance(p, dict):
            _add_claim(p)
    for b in report.get("score_breakdown") or []:
        if not isinstance(b, dict):
            continue
        try:
            delta = float(b.get("delta") or 0)
        except (TypeError, ValueError):
            delta = 0.0
        if delta <= 0:
            continue
        _add_claim(
            {
                "code": b.get("code"),
                "level": "high" if delta >= 20 else "medium",
                "description": b.get("note") or b.get("code"),
                "metric_value": b.get("metric_value"),
                "evidence_page": b.get("evidence_page"),
                "evidence": b.get("evidence") or [],
                "skill": _CODE_TO_SKILL.get(str(b.get("code") or "").upper()),
            }
        )
    for dim in report.get("dimensions") or []:
        if not isinstance(dim, dict):
            continue
        name = str(dim.get("dimension") or "")
        analysis = str(dim.get("analysis") or "").strip()
        if not analysis:
            continue
        skill = {
            "profitability_growth": "finance_profitability",
            "cash_flow": "finance_cash_flow",
            "solvency": "finance_solvency",
            "business_context": "finance_business_context",
        }.get(name)
        if not skill:
            continue
        claims.append(
            DebateClaim(
                agent="finance",
                skill=skill,
                code=f"DIM_{name.upper()}",
                level="low",
                confidence="medium",
                statement=analysis[:400],
                reasoning=analysis[:400],
                evidence_refs=[],
                retrieval_queries=[
                    q for q in (state.get("queries_used") or []) if q.get("skill") == skill
                ][:2],
            )
        )

    # section_routes → queries_used 回填（若未记录）
    queries = list(state.get("queries_used") or [])
    if not queries:
        for route in state.get("section_routes") or []:
            queries.append(
                normalize_query_record(
                    tool="retrieve_context_evidence",
                    intent=route.get("intent"),
                    query=route.get("query"),
                    hits=0,
                    pages=[],
                )
            )

    return DebateDossier(
        agent="finance",
        doc_id=state.get("doc_id") or "",
        doc_name=state.get("doc_name"),
        issuer_type=state.get("issuer_type") or "general",
        client_project_id=state.get("client_project_id"),
        task_id=state.get("task_id") or state.get("doc_id"),
        analysis_id=state.get("analysis_id"),
        risk_score=float(report.get("risk_score") or 0),
        risk_level=str(report.get("risk_level") or "very_low"),
        summary=str(report.get("summary") or ""),
        reasoning=str(report.get("reasoning") or ""),
        claims=claims,
        negative_findings=list(report.get("negative_findings") or []),
        rule_flags=(state.get("rule_pack") or {}).get("flags") or {},
        retrieval_queries=queries,
        run_log=state.get("run_log_paths") or {},
    )


async def _tool_run_finance_skill(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    skill_name = (args.get("skill_name") or "").strip()
    if skill_name not in FINANCE_SKILL_NAMES:
        return {
            "ok": False,
            "error": f"未知 skill_name={skill_name}；可选：{FINANCE_SKILL_NAMES}",
        }
    skills = _finance_skills(state)
    skill = skills[skill_name]
    out = await skill.execute(SkillInput(doc_id=state.get("doc_id") or "", params={"state": state}))
    if not out.success:
        return {"ok": False, "error": out.error, "skill": skill_name}
    data = out.data or {}
    state.setdefault("skill_results", {})[skill_name] = data
    for q in data.get("queries_used") or []:
        state.setdefault("queries_used", []).append(q)
    done = sorted((state.get("skill_results") or {}).keys())
    remain = [n for n in FINANCE_SKILL_NAMES if n not in done]
    return {
        "ok": True,
        "skill": skill_name,
        "risk_point_count": len(data.get("risk_points") or []),
        "risk_points": [
            {
                "code": p.get("code"),
                "level": p.get("level"),
                "description": (p.get("description") or "")[:160],
                "evidence_page": p.get("evidence_page"),
                "confidence": p.get("confidence"),
            }
            for p in (data.get("risk_points") or [])[:6]
        ],
        "confidence": data.get("confidence"),
        "skills_done": done,
        "skills_remaining": remain,
        "hint": (
            f"已完成 {len(done)}/4 skill；继续 run_finance_skill 未完成项"
            if remain
            else "4 个 skill 已齐；可 run_finance_rule_checks 后 submit"
        ),
    }


async def search_finance_evidence_standalone(
    *,
    doc_id: str,
    query: str,
    intent: str = "business_context",
    parse_json: Path | str | None = None,
    section_hint: Any = None,
    top_k: int = 6,
    prefer_pages: list[int] | None = None,
) -> dict[str, Any]:
    """供总控辩论按 dossier.retrieval_queries 增量补财务证据（无 ReAct state）。"""
    if not parse_json:
        return {"ok": False, "error": "缺少 parse_json", "hits": []}
    result = await retrieve_section_evidence(
        doc_id=doc_id,
        intent=intent,
        query=query,
        parse_json=parse_json,
        section_hint=section_hint,
        top_k=top_k,
        prefer_source_type="mixed",
        prefer_pages=prefer_pages,
    )
    hits = [h for h in (result.get("hits") or []) if isinstance(h, dict)]
    return {
        "ok": bool(result.get("ok", True)),
        "doc_id": doc_id,
        "intent": intent,
        "query": query,
        "n": len(hits),
        "hits": hits,
        "compact_hits": _compact_section_hits(hits),
        "query_record": normalize_query_record(
            tool="search_finance_evidence_standalone",
            intent=intent,
            query=query,
            section_hint=section_hint,
            hits=len(hits),
            pages=hit_pages(hits),
        ),
    }


async def _tool_search_finance_evidence(
    args: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    state.setdefault("search_quota", _SEARCH_QUOTA_DEFAULT)
    state.setdefault("search_used", 0)
    quota = int(state.get("search_quota") or 0)
    used = int(state.get("search_used") or 0)
    if used >= quota:
        return {
            "ok": False,
            "error": f"search_finance_evidence 配额已用尽（used={used}, quota={quota}）",
            "hint": "请继续 run_finance_rule_checks 或 submit_finance_report",
            "search_quota": quota,
            "search_used": used,
        }
    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query 必填"}
    intent = (args.get("intent") or "business_context").strip()
    parse_json = state.get("parse_json")
    if not parse_json:
        return {"ok": False, "error": "缺少 full_parse.json"}
    top_k = int(args.get("top_k") or 6)
    result = await retrieve_section_evidence(
        doc_id=state.get("doc_id") or "",
        intent=intent,
        query=query,
        parse_json=parse_json,
        section_hint=args.get("section_hint"),
        top_k=top_k,
        prefer_source_type="mixed",
    )
    hits = [h for h in (result.get("hits") or []) if isinstance(h, dict)]
    state["search_used"] = used + 1
    state.setdefault("section_evidence_hits", []).extend(hits)
    state.setdefault("evidence_log", []).extend(hits)
    rec = normalize_query_record(
        tool="search_finance_evidence",
        intent=intent,
        query=query,
        section_hint=args.get("section_hint"),
        hits=len(hits),
        pages=hit_pages(hits),
    )
    state.setdefault("queries_used", []).append(rec)
    remain = max(0, quota - state["search_used"])
    return {
        "ok": True,
        "n": len(hits),
        "hits": _compact_section_hits(hits),
        "search_quota": quota,
        "search_used": state["search_used"],
        "hint": (
            f"补证完成，剩余 search 配额 {remain}；信息足够则 run_finance_rule_checks / submit"
            if remain
            else "配额已用尽，下一动作必须 run_finance_rule_checks 或 submit_finance_report"
        ),
    }


async def _tool_run_finance_rule_checks(
    args: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    if not state.get("metrics"):
        return {"ok": False, "error": "请先 extract_metrics"}
    if not state.get("gates"):
        return {"ok": False, "error": "请先 derive_gates"}
    metrics = state["metrics"]
    gates = state["gates"]
    cash_burn = state.get("cash_burn")
    if cash_burn is None:
        cash_burn = compute_cash_burn(metrics, gates)
        state["cash_burn"] = cash_burn
    extracted = state.get("extracted") or {"evidence": {}, "table_meta": {}}
    pack = score_finance(metrics, gates, cash_burn, extracted)
    state["rule_pack"] = pack

    coverage_hints: list[str] = []
    skill_results = state.get("skill_results") or {}
    for name in FINANCE_SKILL_NAMES:
        if name not in skill_results:
            coverage_hints.append(f"missing_skill:{name}")
    if gates.get("is_unprofitable") and not gates.get("skip_3_4"):
        if cash_burn.get("skipped") and "finance_cash_flow" in skill_results:
            coverage_hints.append("cash_runway_not_computed")
        if cash_burn.get("CASH_RUNWAY_MONTHS") is None and not cash_burn.get("skipped"):
            coverage_hints.append("runway_null_need_search")
            flags = pack.get("flags") or {}
            if flags.get("runway_uncertain"):
                coverage_hints.append("runway_uncertain:search_finance_evidence")

    if coverage_hints:
        state["search_quota"] = max(
            int(state.get("search_quota") or 0),
            _SEARCH_QUOTA_WITH_GAPS,
        )
        used = int(state.get("search_used") or 0)
        remain = max(0, int(state["search_quota"]) - used)
        hint = (
            f"存在覆盖缺口（{len(coverage_hints)}）：search 配额已升至 "
            f"{state['search_quota']}（剩余 {remain}）；补检后必须 submit_finance_report"
        )
        ready = False
    else:
        hint = "无覆盖缺口。下一动作必须 submit_finance_report，禁止再 search。"
        ready = len(skill_results) >= len(FINANCE_SKILL_NAMES)
        if ready:
            # 不直接服务端交卷：标记 prefer_llm_submit，由 react_loop 再叫一轮真正的 submit
            state["ready_to_submit"] = True
            state["prefer_llm_submit"] = True
            return {
                "ok": True,
                "risk_score": pack.get("risk_score"),
                "risk_level": pack.get("risk_level"),
                "flags": pack.get("flags"),
                "coverage_hints": [],
                "hint": (
                    "rule_checks_ready：下一动作必须 submit_finance_report"
                    "（系统将优先让模型填写完整 dimensions/reasoning）"
                ),
                "ready_to_submit": True,
                "prefer_llm_submit": True,
                "skills_done": sorted(skill_results.keys()),
                "search_quota": state.get("search_quota", _SEARCH_QUOTA_DEFAULT),
            }

    return {
        "ok": True,
        "risk_score": pack.get("risk_score"),
        "risk_level": pack.get("risk_level"),
        "flags": pack.get("flags"),
        "n_breakdown": len(pack.get("score_breakdown") or []),
        "coverage_hints": coverage_hints,
        "skills_done": sorted(skill_results.keys()),
        "search_quota": state.get("search_quota", _SEARCH_QUOTA_DEFAULT),
        "hint": hint,
        "ready_to_submit": ready and not coverage_hints,
    }


async def _tool_submit_finance_report(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    report = dict(args or {})
    warnings: list[str] = []
    composed_flag = bool(report.pop("submit_composed_from_skills", False))

    if not state.get("rule_pack") and state.get("metrics") and state.get("gates"):
        auto = await _tool_run_finance_rule_checks({}, state)
        if auto.get("finished"):
            return auto
        if auto.get("ok"):
            warnings.append("rule_checks_auto_run")

    skill_points = _collect_skill_points(state)
    submitted_points = [p for p in (report.get("risk_points") or []) if isinstance(p, dict)]
    if not submitted_points and skill_points:
        report["risk_points"] = [dict(p) for p in skill_points]
        warnings.append("skill_results_filled_empty_submit")

    if not report.get("negative_findings"):
        negatives: list[dict[str, Any]] = []
        for data in (state.get("skill_results") or {}).values():
            for n in data.get("negative_findings") or []:
                negatives.append(n if isinstance(n, dict) else {"description": str(n)})
        if negatives:
            report["negative_findings"] = negatives
            warnings.append("skill_results_filled_negatives")

    # 空 dimensions/reasoning：优先用 skill 拼装，避免仅 metrics 弱草稿
    if not report.get("dimensions") and state.get("skill_results"):
        report["dimensions"] = _compose_finance_dimensions_from_skills(state)
        composed_flag = True
        warnings.append("skill_results_filled_dimensions")
    if not report.get("reasoning") and state.get("skill_results"):
        report["reasoning"] = _compose_finance_reasoning_from_skills(
            state, state.get("rule_pack")
        )
        composed_flag = True
        warnings.append("skill_results_filled_reasoning")

    _enrich_score_breakdown_from_skills(report, state)
    warnings.extend(_validate_submit(report, state))
    _enrich_score_breakdown_from_skills(report, state)
    extracted = state.get("extracted") or {"evidence": {}, "table_meta": {}}
    composed = compose_from_llm(
        report,
        extracted=extracted,
        model_think=state.get("last_reasoning"),
        reasoning_details=state.get("last_reasoning_details"),
    )
    composed["risk_score"] = report.get("risk_score", composed.get("risk_score"))
    composed["risk_level"] = report.get("risk_level") or score_to_level(
        float(composed.get("risk_score") or 0)
    )
    composed["score_breakdown"] = report.get("score_breakdown") or composed.get(
        "score_breakdown"
    )
    composed["dimensions"] = report.get("dimensions") or composed.get("dimensions") or []
    composed["negative_findings"] = report.get("negative_findings") or []
    if report.get("risk_points"):
        composed["risk_points"] = _normalize_risk_points(list(report["risk_points"]))
    composed["scoring_mode"] = "react+rules_floor"
    composed["submit_warnings"] = list(report.get("submit_warnings") or []) + warnings
    composed["rules_floor"] = report.get("rules_floor")
    composed["submit_recovered"] = bool(report.get("submit_recovered"))
    composed["submit_composed_from_skills"] = bool(
        composed_flag or report.get("submit_composed_from_skills")
    )
    if report.get("reasoning"):
        composed["reasoning"] = report["reasoning"]

    try:
        dossier = build_finance_debate_dossier(state, composed)
        debate_dir = state.get("debate_dir") or DEFAULT_DEBATE_DIR
        dossier_path = save_dossier(dossier, debate_dir)
        composed["debate_dossier_path"] = str(dossier_path)
        state["debate_dossier"] = dossier.model_dump()
        state["debate_dossier_path"] = str(dossier_path)
    except Exception as exc:
        logger.warning("build/save finance debate dossier failed: %s", exc)
        composed["submit_warnings"] = list(composed.get("submit_warnings") or []) + [
            f"dossier_failed:{exc}"
        ]

    state["final_report"] = composed
    state["finished"] = True
    return {
        "ok": True,
        "finished": True,
        "risk_score": composed.get("risk_score"),
        "risk_level": composed.get("risk_level"),
        "warnings": composed.get("submit_warnings"),
        "summary": composed.get("summary"),
        "rules_floor": report.get("rules_floor"),
        "submit_recovered": composed.get("submit_recovered"),
        "debate_dossier_path": composed.get("debate_dossier_path"),
    }


def build_finance_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    handlers = {
        "retrieve_finance": _tool_retrieve_finance,
        "extract_metrics": _tool_extract_metrics,
        "derive_gates": _tool_derive_gates,
        "calc_cash_runway": _tool_calc_cash_runway,
        "retrieve_context_evidence": _tool_retrieve_context_evidence,
        "run_finance_skill": _tool_run_finance_skill,
        "search_finance_evidence": _tool_search_finance_evidence,
        "run_finance_rule_checks": _tool_run_finance_rule_checks,
        "submit_finance_report": _tool_submit_finance_report,
    }
    by_name = {s["function"]["name"]: s for s in FINANCE_TOOL_SCHEMAS}
    for name, handler in handlers.items():
        if name not in by_name:
            logger.error("missing schema for finance tool %s", name)
            continue
        reg.register(by_name[name], handler)
    return reg
