from __future__ import annotations

import re
from typing import Any

from src.skills.analyze_finance import _normalize_risk_points, compose_from_llm
from src.skills.extract_financials import extract_financials_from_retrieval
from src.skills.finance_labels import (
    build_tables_detail_from_bundle,
    metric_name_zh,
    table_name_zh,
)
from src.skills.gates import compute_cash_burn, resolve_issuer_gates
from src.skills.score_finance import score_finance, score_to_level
from src.tools.retrieval_tool import retrieve_agent, retrieve_section_evidence
from src.tools.schemas import FINANCE_TOOL_SCHEMAS, ToolRegistry


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
    compact: list[dict[str, Any]] = []
    for hit in hits:
        compact.append(
            {
                "page": hit.get("page"),
                "section_id": hit.get("section_id"),
                "source_type": hit.get("source_type"),
                "score": hit.get("score"),
                "matched_terms": hit.get("matched_terms") or [],
                "excerpt": str(hit.get("excerpt") or "")[:excerpt_chars],
            }
        )
    return compact


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
    return {
        "ok": True,
        "metric_keys": list(state["metrics"].keys()),
        "metric_keys_zh": [
            {"code": k, "nameZh": metric_name_zh(k)} for k in state["metrics"].keys()
        ],
        "years": extracted.get("years"),
        "metrics_summary": summary_raw,
        "tables_detail": tables_from_meta or build_tables_detail_from_bundle(bundle),
        "metric_note": "期內虧損/利潤(NET_LOSS/NET_PROFIT_OR_LOSS)：正數=盈利，負數=虧損。",
        "bs_reconcile": {
            "changed": bool((extracted.get("bs_reconcile") or {}).get("changed")),
            "note": ((extracted.get("bs_reconcile") or {}).get("notes") or [None])[0],
        },
        "hint": "下一步可调用 derive_gates",
    }


async def _tool_derive_gates(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    metrics = state.get("metrics") or {}
    if not metrics:
        return {"ok": False, "error": "请先 extract_metrics"}
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
    return {
        "ok": True,
        "gates": slim,
        "fast_path": {
            "eligible": _healthy_profit_path(metrics, gates),
            "reason": "profitable_positive_cfo_stable_margin"
            if _healthy_profit_path(metrics, gates)
            else None,
        },
        "hint": (
            "fast_path.eligible=true：可直接 submit 低风险报告；"
            "仅当要分析加盟/供应链/融资依赖时再 retrieve_context_evidence。"
            if _healthy_profit_path(metrics, gates)
            else "若未盈利可 calc_cash_runway；非主表主题可 retrieve_context_evidence；否则 submit"
        ),
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
        },
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
        top_k=top_k,
        prefer_source_type=args.get("prefer_source_type") or "mixed",
    )
    state.setdefault("section_evidence_hits", []).extend(result.get("hits") or [])
    state.setdefault("section_routes", []).append(
        {
            "intent": intent,
            "query": query,
            "route": result.get("route") or [],
            "source": result.get("source"),
        }
    )
    return {
        "ok": result.get("ok", True),
        "doc_id": result.get("doc_id"),
        "intent": intent,
        "query": query,
        "n": result.get("n"),
        "route": result.get("route") or [],
        "hits": _compact_section_hits(result.get("hits") or []),
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
}


def _canonical_score_code(code: str) -> str:
    c = str(code or "").upper().strip()
    if c in _CODE_ALIASES:
        return _CODE_ALIASES[c]
    # 模糊归并模型自造 code
    if "CONTINUOUS" in c and "LOSS" in c:
        return "CONTINUOUS_LOSS"
    if c in {"CONT_LOSS", "CONTLOSS"} or (c.startswith("CONT") and "LOSS" in c):
        return "CONTINUOUS_LOSS"
    if "CFO" in c and ("NEG" in c or "NEGATIVE" in c or "QUALITY" in c):
        return "CFO_NEGATIVE"
    if "SINGLE" in c and "LOSS" in c:
        return "SINGLE_YEAR_LOSS"
    if c in {"NEG_CFO", "NEGCFO"}:
        return "CFO_NEGATIVE"
    return c


def _merge_rules_floor(
    report: dict[str, Any],
    state: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    """规则托底：硬门控触发时不允许空 breakdown / 虚假 0 分；同义 code 去重取较大 delta。"""
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
    by_code: dict[str, dict[str, Any]] = {}

    def _put(item: dict[str, Any], *, source: str) -> None:
        code = _canonical_score_code(str(item.get("code") or ""))
        if not code:
            return
        row = dict(item)
        row["code"] = code
        try:
            delta = float(row.get("delta") or 0)
        except (TypeError, ValueError):
            delta = 0.0
        row["delta"] = delta
        prev = by_code.get(code)
        if prev is None:
            if source == "rules":
                row["note"] = ((row.get("note") or "") + "（规则托底）").strip()
                warnings.append(f"rules_floor_added:{code}")
            by_code[code] = row
            return
        try:
            prev_delta = float(prev.get("delta") or 0)
        except (TypeError, ValueError):
            prev_delta = 0.0
        if delta > prev_delta:
            if source == "rules":
                row["note"] = ((row.get("note") or "") + "（规则托底上调）").strip()
                warnings.append(f"rules_floor_raised:{code}")
            by_code[code] = row

    for b in llm_bd:
        if isinstance(b, dict):
            _put(b, source="llm")
    for b in rules_bd:
        if isinstance(b, dict):
            _put(b, source="rules")

    # 已连续亏损时不再叠加「单年亏损」
    if "CONTINUOUS_LOSS" in by_code and "SINGLE_YEAR_LOSS" in by_code:
        by_code.pop("SINGLE_YEAR_LOSS", None)
        warnings.append("dedupe_drop:SINGLE_YEAR_LOSS")

    merged = list(by_code.values())
    report["score_breakdown"] = merged
    llm_score = 0.0
    try:
        llm_score = float(report.get("risk_score") or 0)
    except (TypeError, ValueError):
        llm_score = 0.0
    rules_score = float(rules_pack.get("risk_score") or 0)
    # 规则侧若含 SINGLE+CONTINUOUS，托底分按去重后的 breakdown 重算
    breakdown_sum = sum(float(b.get("delta") or 0) for b in merged)
    rules_score_adj = breakdown_sum  # 以合并去重后为准
    # 最终分：以去重 breakdown 为准；若模型分更高且 breakdown 已覆盖硬项则取 max
    hard = bool(
        gates.get("is_unprofitable")
        or gates.get("continuous_net_loss")
        or (rules_pack.get("flags") or {}).get("cfo_persistently_negative")
    )
    final = breakdown_sum
    if not hard:
        final = max(llm_score, breakdown_sum)
    final = max(0.0, min(100.0, final))

    if hard and final <= 0 and rules_score_adj > 0:
        final = rules_score_adj
        warnings.append("rules_floor_forced_nonzero")
    if hard and not merged and rules_bd:
        for b in rules_bd:
            if isinstance(b, dict):
                _put(b, source="rules")
        if "CONTINUOUS_LOSS" in by_code:
            by_code.pop("SINGLE_YEAR_LOSS", None)
        merged = list(by_code.values())
        report["score_breakdown"] = merged
        final = sum(float(b.get("delta") or 0) for b in merged)
        warnings.append("rules_floor_filled_empty_breakdown")

    report["risk_score"] = final
    report["risk_level"] = score_to_level(final)
    if not report.get("risk_points") and rules_pack.get("risk_points"):
        report["risk_points"] = rules_pack["risk_points"]
    report["rules_floor"] = {
        "rules_score": rules_score,
        "rules_score_deduped": rules_score_adj,
        "llm_score": llm_score,
        "final_score": final,
        "flags": rules_pack.get("flags") or {},
    }
    _align_narrative_to_level(report, warnings)
    return report


_UNDERSTATE_LOW_RE = re.compile(
    r"(财务|財務)?风险(较|很)?低|低风险|風險(較|很)?低|低風險|"
    r"风险处于可控的低|風險處於可控的低|中低风险|中低風險|"
    r"整体财务风险可控|整體財務風險可控|财务风险可控|財務風險可控",
)
_UNDERSTATE_MED_RE = re.compile(
    r"风险中等|風險中等|风险评级为中等|风险评级定为中等|風險評級為中等|風險評級定為中等",
)


def _align_narrative_to_level(report: dict[str, Any], warnings: list[str]) -> None:
    """规则托底后纠正 summary/reasoning 与最终等级明显不符的措辞。"""
    level = str(report.get("risk_level") or "")
    if level not in {"medium", "high", "very_high"}:
        return
    try:
        score = float(report.get("risk_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    note = (
        f"（注：规则托底后综合评分 {score:.0f}，等级 {level}，"
        f"叙述以该等级为准。）"
    )

    def _mismatch(text: str) -> bool:
        if _UNDERSTATE_LOW_RE.search(text):
            return True
        if level in {"high", "very_high"} and _UNDERSTATE_MED_RE.search(text):
            return True
        return False

    def _fix(text: str) -> str | None:
        if not text or "规则托底后" in text or "規則托底後" in text:
            return None
        if not _mismatch(text):
            return None
        return text.rstrip("。.") + note

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


def _validate_submit(report: dict[str, Any], state: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    gates = state.get("gates") or {}
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
    return warnings


async def _tool_submit_finance_report(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    report = dict(args)
    warnings = _validate_submit(report, state)
    extracted = state.get("extracted") or {"evidence": {}, "table_meta": {}}
    composed = compose_from_llm(
        report,
        extracted=extracted,
        model_think=state.get("last_reasoning"),
        reasoning_details=state.get("last_reasoning_details"),
    )
    # compose 可能再次用 llm risk_score；以托底后的 report 为准
    composed["risk_score"] = report.get("risk_score", composed.get("risk_score"))
    composed["risk_level"] = report.get("risk_level") or score_to_level(
        float(composed.get("risk_score") or 0)
    )
    composed["score_breakdown"] = report.get("score_breakdown") or composed.get(
        "score_breakdown"
    )
    if report.get("risk_points"):
        # submit args 可能含 LLM 自造 level（如 critical），须规范化
        composed["risk_points"] = _normalize_risk_points(list(report["risk_points"]))
    composed["scoring_mode"] = "react+rules_floor"
    composed["submit_warnings"] = warnings
    composed["rules_floor"] = report.get("rules_floor")
    state["final_report"] = composed
    state["finished"] = True
    return {
        "ok": True,
        "finished": True,
        "risk_score": composed.get("risk_score"),
        "risk_level": composed.get("risk_level"),
        "warnings": warnings,
        "summary": composed.get("summary"),
        "rules_floor": report.get("rules_floor"),
    }


def build_finance_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    handlers = {
        "retrieve_finance": _tool_retrieve_finance,
        "extract_metrics": _tool_extract_metrics,
        "derive_gates": _tool_derive_gates,
        "calc_cash_runway": _tool_calc_cash_runway,
        "retrieve_context_evidence": _tool_retrieve_context_evidence,
        "submit_finance_report": _tool_submit_finance_report,
    }
    by_name = {s["function"]["name"]: s for s in FINANCE_TOOL_SCHEMAS}
    for name, handler in handlers.items():
        reg.register(by_name[name], handler)
    return reg
