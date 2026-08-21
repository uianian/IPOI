#!/usr/bin/env python3
"""从运行结果 JSON 生成财务 / 法务 / 市场三份独立 Markdown 报告。

示例：
  cd agents/hk_ipo_risk
  python scripts/generate_analysis_report.py \\
    --result .runtime/mixue_finance_legal.json \\
    --doc-name 蜜雪集團 \\
    --pdf-name 02097_21-02-2025_蜜雪集團_全球發售.pdf \\
    --stock-code 02097 \\
    --finance-retrieval ../../retrieval/.runtime/agent_retrieval_mixue.json \\
    --legal-retrieval ../ipo/.runtime/agent_retrieval_mixue_legal.json \\
    --reports-dir reports
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


def _embellishment_report_md(embellishment: dict[str, Any] | None) -> str:
    if str(PKG_ROOT) not in sys.path:
        sys.path.insert(0, str(PKG_ROOT))
    from src.skills.embellishment_reporting import render_embellishment_markdown

    return render_embellishment_markdown(
        embellishment,
        title="四、文本粉饰度专项分析",
        heading="##",
        top_n=10,
    )


def _has_market_score(result: dict[str, Any]) -> bool:
    market = result.get("market")
    if not isinstance(market, dict) or not market:
        return False
    if (market.get("features") or {}).get("demo"):
        return False
    return market.get("risk_score") is not None


def _formula_label(result: dict[str, Any]) -> str:
    try:
        if str(PKG_ROOT) not in sys.path:
            sys.path.insert(0, str(PKG_ROOT))
        from src.skills.master_cards import reference_formula_label

        return reference_formula_label(has_market=_has_market_score(result))
    except Exception:
        return (
            "(legal×0.55 + finance×0.45)×0.65 + market×0.35"
            if _has_market_score(result)
            else "legal×0.55 + finance×0.45"
        )


def market_report_markdown(result: dict[str, Any]) -> str:
    market = result.get("market")
    if not isinstance(market, dict):
        return ""
    return str((market.get("features") or {}).get("sentiment_report_markdown") or "").strip()


def normalize_report_stock_code(raw: str | None) -> str:
    t = (raw or "").strip().upper().replace(" ", "").replace(".HK", "")
    if t.isdigit():
        return t.zfill(5)
    m = re.match(r"^(\d{1,5})", t)
    return m.group(1).zfill(5) if m else ""


def resolve_report_stock_code(
    result: dict[str, Any],
    *,
    stock_code: str | None = None,
    pdf_name: str = "",
) -> str:
    if stock_code:
        code = normalize_report_stock_code(stock_code)
        if code:
            return code
    for key in ("stock_code", "stockCode", "ticker"):
        code = normalize_report_stock_code(str(result.get(key) or ""))
        if code:
            return code
    code = normalize_report_stock_code(str(result.get("doc_id") or ""))
    if code:
        return code
    code = normalize_report_stock_code(pdf_name)
    if code:
        return code
    return "00000"


def report_paths(reports_dir: Path, stock_code: str) -> dict[str, Path]:
    code = normalize_report_stock_code(stock_code) or "00000"
    return {
        "finance": reports_dir / f"{code}_finance_report.md",
        "legal": reports_dir / f"{code}_legal_report.md",
        "market": reports_dir / f"{code}_market_report.md",
        "master": reports_dir / f"{code}_ipo_risk_warning_report.md",
    }


def sibling_market_report_path(out: Path) -> Path:
    """兼容旧调用；新入口请用 report_paths。"""
    stem = out.stem
    if stem.endswith("_finance_legal_report"):
        name = stem[: -len("_finance_legal_report")] + "_market_report" + out.suffix
        return out.with_name(name)
    if stem.endswith("_report"):
        return out.with_name(stem[: -len("_report")] + "_market_report" + out.suffix)
    return out.with_name(stem + "_market_report" + out.suffix)


def _load_json(path: Path | None) -> dict[str, Any] | list[Any] | None:
    if path is None or not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _clean_excerpt(text: str, max_len: int = 280) -> str:
    del max_len
    if not text:
        return ""
    t = html.unescape(text)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
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


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.2%}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_pct_point(v: Any) -> str:
    """格式化已经采用百分数口径的值，如 12.5 -> 12.5%。"""
    if v is None:
        return "—"
    text = str(v).strip()
    if not text:
        return "—"
    if text.endswith("%"):
        return text
    try:
        return f"{float(v):g}%"
    except (TypeError, ValueError):
        return text


_TRAILING_PUNCT_RE = re.compile(r"[。．.；;，,\s]+$")


def _strip_trailing_punct(text: Any) -> str:
    return _TRAILING_PUNCT_RE.sub("", str(text or "").strip())


def _clean_sentence(text: Any, fallback: str = "") -> str:
    raw = str(text or "").strip() or fallback
    if not raw:
        return ""
    return _strip_trailing_punct(_humanize_backend_terms(raw))


def _sentence(text: Any, fallback: str = "") -> str:
    body = _clean_sentence(text, fallback)
    return f"{body}。" if body else ""


def _clean_list_items(items: Any) -> list[str]:
    if isinstance(items, str):
        raw_items = [x for x in re.split(r"[；;\n]+", items) if x.strip()]
    else:
        raw_items = list(items or [])
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        body = _clean_sentence(item)
        if body and body not in seen:
            cleaned.append(body)
            seen.add(body)
    return cleaned


def _bullet_lines(items: Any, *, empty: str = "—") -> list[str]:
    cleaned = _clean_list_items(items)
    if not cleaned:
        return [f"- {empty}"]
    return [f"- {item}" for item in cleaned]


def _master_forecast_text(item: dict[str, Any]) -> str:
    parts = _clean_list_items(
        [
            item.get("expected_direction"),
            item.get("expected_pattern"),
            item.get("volatility_view"),
        ]
    )
    drivers = item.get("key_drivers") or []
    if drivers:
        parts.extend(_clean_list_items(drivers))
    return "；".join(parts)


def _predicted_label_for_window(pw: dict[str, Any], window: str) -> Any:
    field = _WINDOW_PREDICTED_FIELD.get(window.upper())
    return pw.get(field) if field else None


def _to_simplified(text: Any) -> str:
    raw = str(text or "")
    try:
        from zhconv import convert

        return str(convert(raw, "zh-cn"))
    except Exception:
        return raw


_RISK_LABEL_CN = {
    "very_high": "极高风险",
    "high": "高风险",
    "medium": "中等风险",
    "low": "低风险",
    "very_low": "极低风险",
    "VERY_HIGH": "极高风险",
    "HIGH": "高风险",
    "MEDIUM": "中等风险",
    "LOW": "低风险",
    "VERY_LOW": "极低风险",
}

_CONFIDENCE_CN = {
    "high": "高置信度",
    "medium": "中等置信度",
    "low": "低置信度",
}

_SEVERITY_CN = {
    "severe": "显著下跌或深度破发",
    "moderate": "中度承压",
    "benign": "表现相对平稳",
    "unknown": "真实表现暂不可判断",
}

_ALIGNMENT_CN = {
    "hit": "预警命中",
    "partial": "方向部分吻合",
    "miss": "预警偏离",
    "not_available": "暂无法验证",
}

_WINDOW_CN = {
    "D1": "上市首日",
    "D5": "上市后5个交易日内",
    "D20": "上市后20个交易日内",
    "D60": "上市后60个交易日内",
}

_WINDOW_PREDICTED_FIELD = {
    "D1": "ipo_day_break_risk",
    "D5": "d5_significant_downside_risk",
    "D20": "d20_downside_risk",
    "D60": "d60_downside_risk",
}

_WINDOW_DEFAULT_FORECAST_TEXT = {
    "D1": ("上市首日破发风险中等", "仅有标签级预测，未生成结构化走势文本", "波动风险中等"),
    "D5": ("上市后5个交易日显著下跌风险中等", "仅有标签级预测，未生成结构化走势文本", "波动风险中等"),
    "D20": ("上市后20个交易日下行风险中等", "仅有标签级预测，未生成结构化走势文本", "波动风险中等"),
    "D60": ("上市后60个交易日下行风险中等", "仅有标签级预测，未生成结构化走势文本", "波动风险中等"),
}


def _master_forecast_items(master: dict[str, Any], pw: dict[str, Any]) -> list[dict[str, Any]]:
    by_window: dict[str, dict[str, Any]] = {}
    for item in master.get("price_path_forecast") or []:
        if not isinstance(item, dict):
            continue
        window = str(item.get("window") or "").upper()
        if window in _WINDOW_PREDICTED_FIELD:
            by_window[window] = item

    out: list[dict[str, Any]] = []
    for window, field in _WINDOW_PREDICTED_FIELD.items():
        item = by_window.get(window) or {}
        direction, pattern, volatility = _WINDOW_DEFAULT_FORECAST_TEXT[window]
        out.append(
            {
                "window": window,
                "risk_label": item.get("risk_label") or item.get("riskLabel") or pw.get(field) or "medium",
                "expected_direction": item.get("expected_direction") or item.get("expectedDirection") or direction,
                "expected_pattern": item.get("expected_pattern") or item.get("expectedPattern") or pattern,
                "volatility_view": item.get("volatility_view") or item.get("volatilityView") or volatility,
                "key_drivers": item.get("key_drivers") or item.get("keyDrivers") or [],
                "confidence": item.get("confidence") or "medium",
            }
        )
    return out

_AGENT_CN = {
    "finance": "财务穿透智能体",
    "legal": "法务合规智能体",
    "market": "市场情绪智能体",
    "master": "总控决策智能体（文本粉饰度专项）",
    "embellishment": "总控决策智能体（文本粉饰度专项）",
}

_DEBATE_KIND_CN = {
    "conflict": "判断冲突",
    "resonance": "同向共振",
    "gap": "证据缺口",
    "evidence_gap": "证据缺口",
}

_PRIORITY_CN = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

_DEBATE_SEVERITY_CN = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "critical": "极高",
}

_DEBATE_THEME_CN = {
    "redemption": "对赌或赎回条款",
    "related_party": "关联交易",
    "cash_runway": "现金跑道与流动性",
    "valuation": "估值风险",
    "concentration": "客户或供应商集中度",
    "governance": "公司治理",
    "market": "市场情绪",
    "profitability": "盈利质量",
    "cash_flow": "经营现金流",
    "solvency": "偿债能力",
}

_TOOL_CN = {
    "calc_cash_runway": "现金跑道测算",
    "retrieve_finance": "财务证据检索",
    "extract_metrics": "财务指标抽取",
    "derive_gates": "财务门控判断",
    "run_finance_skill": "财务专项分析",
    "run_finance_rule_checks": "财务规则校验",
    "search_legal_evidence": "法务证据检索",
    "run_legal_skill": "法务专项分析",
    "run_legal_rule_checks": "法务规则校验",
}

_SKILL_CN = {
    "legal_contracts_and_ip": "重大合同与知识产权",
    "legal_governance": "公司治理",
    "legal_regulatory_litigation": "监管诉讼",
    "legal_related_party": "关联交易",
    "legal_shareholder_rights": "股东特殊权利",
}

_LEGAL_FEATURE_CN = {
    "ratio_pct": "占比",
    "ratio_source": "占比来源",
    "listing_rule_pct_max": "上市规则最高适用百分比率",
    "waiver_pct_threshold": "豁免门槛",
    "top1_customer_pct": "最大客户占比",
    "top5_customer_pct": "前五大客户占比",
    "top1_supplier_pct": "最大供应商占比",
    "top5_supplier_pct": "前五大供应商占比",
    "redemption_high": "赎回条款高风险",
    "redemption_medium": "赎回条款中风险",
    "related_party_ratio_gt_30": "关联交易占比超过30%",
    "concentration_high": "客户或供应商集中度高风险",
    "pipeline_high": "管线进度高风险",
    "stages_mentioned": "已披露研发阶段",
    "valuation_inversion": "估值倒挂",
    "owner": "责任主体",
    "reason": "原因",
}

_LEGAL_PERCENT_POINT_FIELDS = {
    "ratio_pct",
    "listing_rule_pct_max",
    "waiver_pct_threshold",
    "top1_customer_pct",
    "top5_customer_pct",
    "top1_supplier_pct",
    "top5_supplier_pct",
}

_METRIC_CN = {
    "REV": "营业收入",
    "COGS": "营业成本",
    "GP": "毛利",
    "GP_MARGIN": "毛利率",
    "R&D_EXP": "研发费用",
    "SG&A": "销售及营销费用",
    "NET_LOSS": "期内亏损/利润",
    "ADJ_NET": "经调整净利润",
    "TOTAL_ASSETS": "总资产",
    "TOTAL_LIAB": "总负债",
    "NET_ASSETS": "净资产",
    "CASH_EQ": "现金及现金等价物",
    "CV_PREF": "可转换可赎回优先股",
    "TRADE_REC": "贸易应收款",
    "TRADE_PAY": "贸易应付款",
    "CFO": "经营活动现金流净额",
    "CFI": "投资活动现金流净额",
    "CFF": "融资活动现金流净额",
    "END_CASH": "年末现金余额",
    "OTHER_INCOME": "其他收入及收益",
    "RD_EXP": "研发费用",
    "SGA": "销售及行政费用",
}

_STATUS_CN = {
    "ok": "正常",
    "think_from_content": "从模型内容恢复",
    "reasoning_missing": "未返回推理内容",
    "reasoning_missing_after_retry": "重试后仍未返回推理内容",
    "analyzed": "已分析",
    "verified": "已验证",
    "partially_accepted": "部分接受",
    "unresolved": "未解决",
}


def _risk_label_cn(value: Any) -> str:
    return _RISK_LABEL_CN.get(str(value or "").strip(), "中等风险")


def _confidence_cn(value: Any) -> str:
    return _CONFIDENCE_CN.get(str(value or "").strip().lower(), "中等置信度")


def _severity_cn(value: Any) -> str:
    return _SEVERITY_CN.get(str(value or "").strip().lower(), "真实表现暂不可判断")


def _alignment_cn(value: Any) -> str:
    return _ALIGNMENT_CN.get(str(value or "").strip().lower(), "暂无法验证")


def _risk_rank(value: Any) -> int | None:
    text = str(value or "").strip().lower()
    if text == "very_high":
        return 4
    if text == "high":
        return 3
    if text == "medium":
        return 2
    if text == "low":
        return 1
    if text == "very_low":
        return 0
    return None


def _derived_alignment(predicted: Any, actual: Any) -> str:
    p = _risk_rank(predicted)
    a = _risk_rank(actual)
    if p is None or a is None:
        return "not_available"
    if (p >= 3 and a >= 3) or p == a:
        return "hit"
    if abs(p - a) == 1:
        return "partial"
    return "miss"


def _window_cn(value: Any) -> str:
    return _WINDOW_CN.get(str(value or "").strip().upper(), str(value or "当前时间窗"))


def _postlisting_sidecar(stock_code: str) -> dict[str, Any]:
    code = normalize_report_stock_code(stock_code)
    if not code:
        return {}
    files = sorted(
        (PKG_ROOT / ".runtime" / "market").glob(f"*_{code}_postlisting.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        data = _load_json(path)
        if isinstance(data, dict) and isinstance(data.get("checkpoints"), list):
            return data
    return {}


def _humanize_backend_terms(text: Any) -> str:
    out = str(text or "")
    for src, (name, _definition) in sorted(
        globals().get("_RISK_TERM_DEFINITIONS", {}).items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        out = out.replace(src, name)
    replacements = {
        "CONCENTRATION_HIGH": "单一客户或供应商集中度高风险",
        "CONCENTRATION_TOP5": "前五大客户或供应商集中度风险",
        "VALUATION_INVERSION": "首次公开发售估值倒挂风险",
        "EMBELLISHMENT_HIGH": "文本粉饰度高风险",
        "historical_module": "历史校准风险分",
        "weight": "有效权重",
        "coverage": "数据覆盖率",
        "weighted_hit_score": "加权命中分",
        "business_value_score": "业务参考分",
        "d5_priority_hit": "上市后5个交易日内重点预警命中",
        "ipo_day_break_risk": "上市首日破发风险",
        "d5_significant_downside_risk": "上市后5个交易日内显著下跌风险",
        "d20_downside_risk": "上市后20个交易日内下跌风险",
        "d60_downside_risk": "上市后60个交易日内下跌风险",
        "price_path_forecast": "价格路径预测",
        "predicted_windows": "预测时间窗",
        "post_listing": "上市后验证",
        "rules floor": "规则托底分",
        "max_llm_and_rules_floor": "模型评分与规则托底取较高值",
        "redemption_high": "赎回条款高风险",
        "redemption_medium": "赎回条款中风险",
        "related_party_ratio_gt_30": "关联交易占比超过30%",
        "listing_rule_pct_ratio": "上市规则百分比率口径",
        "max_rounds": "已达到最大追问轮次",
        "score_breakdown": "得分分解",
        "rule_checks": "规则校验",
        "risk_level": "风险等级",
        "claim": "主张",
        "D1": "上市首日",
        "D5": "上市后5个交易日内",
        "D20": "上市后20个交易日内",
        "D60": "上市后60个交易日内",
        "HIGH": "高风险",
        "MEDIUM": "中等风险",
        "LOW": "低风险",
        "alignment=hit": "预警命中",
        "alignment=partial": "方向部分吻合",
        "alignment=miss": "预警偏离",
        "alignment=not_available": "暂无法验证",
        "high": "高风险",
        "medium": "中等风险",
        "low": "低风险",
        "severe": "显著下跌或深度破发",
        "moderate": "中度承压",
        "benign": "表现相对平稳",
        "not_available": "暂无法验证",
    }
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    out = re.sub(r"\[[A-Z][A-Z0-9_-]*(?:-[A-Z0-9]+)*\]", "", out)
    out = re.sub(r"\([A-Z][A-Z0-9_-]*(?:-[A-Z0-9]+)*\)", "", out)
    out = re.sub(r"\bOPINION-STATUS\b", "舆情可用性状态", out)
    return _to_simplified(out)


def _bool_cn(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "暂不可判断"


def _quote_excerpt(text: Any, max_len: int = 360) -> str:
    excerpt = _clean_excerpt(str(text or ""), max_len)
    if not excerpt:
        return ""
    return f"“{excerpt}”"


def _score_sentence(value: Any) -> str:
    score = _fmt_score(value)
    return "暂未形成有效评分" if score == "—" else f"{score}分（满分100分，分数越高表示风险越高）"


def _collect_score_evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for agent in ("finance", "legal", "market"):
        block = result.get(agent) if isinstance(result.get(agent), dict) else {}
        for item in (block.get("score_breakdown") or []):
            if not isinstance(item, dict):
                continue
            rows = [x for x in (item.get("evidence") or []) if isinstance(x, dict)]
            if not rows and item.get("evidence_page") is not None:
                rows = [
                    {
                        "page": item.get("evidence_page"),
                        "excerpt": item.get("note") or "",
                        "source_type": "text",
                    }
                ]
            for ev in rows:
                evidence.append(
                    {
                        "agent": agent,
                        "code": item.get("code"),
                        "title": item.get("note") or item.get("code"),
                        "page": ev.get("page") if ev.get("page") is not None else item.get("evidence_page"),
                        "excerpt": ev.get("excerpt") or item.get("note") or "",
                    }
                )
    return evidence


def _fallback_evidence_for_factor(
    factor: dict[str, Any],
    score_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source = str(factor.get("source_agent") or "")
    factor_pages = {
        ev.get("page")
        for ev in (factor.get("evidence") or [])
        if isinstance(ev, dict) and ev.get("page") is not None
    }
    if factor_pages:
        matched = [
            ev
            for ev in score_evidence
            if ev.get("agent") == source and ev.get("page") in factor_pages
        ]
        if matched:
            return matched
    title = str(factor.get("title") or factor.get("reason") or "")
    matched = [
        ev
        for ev in score_evidence
        if ev.get("agent") == source and str(ev.get("title") or "") and str(ev.get("title") or "") in title
    ]
    return matched


def _factor_evidence_paragraphs(
    factor: dict[str, Any],
    *,
    score_evidence: list[dict[str, Any]],
) -> list[str]:
    rows = [x for x in (factor.get("evidence") or []) if isinstance(x, dict)]
    if not rows:
        rows = _fallback_evidence_for_factor(factor, score_evidence)
    if not rows:
        return ["当前结构化结果没有提供可直接引用的原文片段，后续复核应回到招股书原文补证。"]
    parts: list[str] = []
    for ev in rows:
        page = ev.get("page")
        quote = _quote_excerpt(ev.get("excerpt"), max_len=100000)
        if page is None and not quote:
            parts.append("当前结构化结果缺少页码和可直接引用的原文片段。")
        elif page is None:
            parts.append(f"结构化结果未提供原 PDF 页码，但给出原文线索：{quote}。")
        elif quote:
            parts.append(f"原 PDF 第 {page} 页披露：{quote}。")
        else:
            parts.append(f"原 PDF 第 {page} 页有相关披露，但当前结构化结果仅提供页码，缺少可直接引用的原文片段。")
    return parts


def _is_embellishment_factor(factor: dict[str, Any]) -> bool:
    source = str(factor.get("source_agent") or "").lower()
    text = f"{factor.get('title') or ''} {factor.get('reason') or ''}".lower()
    return source in {"master", "embellishment"} or any(
        marker in text for marker in ("粉饰", "粉飾", "embellishment")
    )


def _normalize_embellishment_factor(
    factor: dict[str, Any],
    embellishment: dict[str, Any] | None,
) -> dict[str, Any]:
    """Correct legacy attribution and bind the factor to verified source excerpts."""
    normalized = dict(factor)
    if not _is_embellishment_factor(normalized):
        return normalized
    normalized["source_agent"] = "master"
    if str(PKG_ROOT) not in sys.path:
        sys.path.insert(0, str(PKG_ROOT))
    from src.skills.embellishment_reporting import embellishment_report_data

    verified = [
        {"page": item.get("page"), "excerpt": item.get("excerpt")}
        for item in embellishment_report_data(embellishment).get("highRiskExcerpts", [])
        if item.get("page") is not None and str(item.get("excerpt") or "").strip()
    ]
    if verified:
        normalized["evidence"] = verified[:3]
    return normalized


def _short_text(text: Any, max_len: int = 260) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _full_text(text: Any) -> str:
    return _humanize_backend_terms(re.sub(r"\s+", " ", str(text or "")).strip())


def _polish_inline_text(text: Any) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = cleaned.replace("。；", "。").replace("；。", "。")
    cleaned = re.sub(r"(?<=[\u4e00-\u9fff0-9A-Za-z)]),(?=[\u4e00-\u9fff])", "，", cleaned)
    return cleaned


def _expert_summary_sentence(text: Any, *, agent_key: str) -> str:
    body = _clean_sentence(_polish_inline_text(text))
    if not body:
        return ""
    return f"{body}。"


def _agent_level_cn(value: Any) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "very_high": "极高风险",
        "high": "高风险",
        "medium": "中等风险",
        "low": "低风险",
        "very_low": "极低风险",
    }
    return mapping.get(text, text or "暂未形成等级")


def _agent_score_summary(agent: str, block: dict[str, Any]) -> str:
    score = _fmt_score(block.get("risk_score"))
    level = _agent_level_cn(block.get("risk_level"))
    if score == "—":
        return f"{agent}暂未形成有效风险评分，当前等级为{level}。"
    return f"{agent}给出的风险分为{score}分，风险等级为{level}。"


_RISK_TERM_DEFINITIONS = {
    "CONTINUOUS_LOSS": (
        "业绩记录期连续亏损",
        "依据指标文档第二章“期内亏损/利润”口径，关注发行人在业绩记录期内净亏损是否持续存在及亏损规模变化；18A生物科技公司需重点关注亏损规模及变动趋势。",
    ),
    "SINGLE_YEAR_LOSS": (
        "最近完整年度亏损",
        "依据指标文档第二章“期内亏损/利润”口径，关注最近完整年度是否仍为净亏损。",
    ),
    "CFO_NEGATIVE": (
        "经营活动现金流持续为负",
        "依据指标文档第二章“经营活动现金流净额”口径，反映经营活动产生的现金净流入或净流出；持续为负说明主营经营尚未形成自我造血。",
    ),
    "CASH_RUNWAY_LT_12": (
        "现金跑道少于12个月",
        "依据指标文档第三章“现金流消耗压力”口径，现金跑道为现有资金可支撑运营月数；少于12个月属于高风险。",
    ),
    "CASH_RUNWAY_12_24": (
        "现金跑道12至24个月",
        "依据指标文档第三章“现金流消耗压力”口径，现金跑道为现有资金可支撑运营月数；12至24个月属于中风险。",
    ),
    "BURN_YOY_UP_30": (
        "现金消耗率同比扩大超过30%",
        "依据指标文档第三章“现金流消耗压力”口径，现金消耗率同比扩大超过30%属于高风险。",
    ),
    "CV_PREF_LIABILITY": (
        "可转换可赎回优先股或赎回负债压力",
        "依据指标文档第二章“可转换可赎回优先股”及第三章“对赌或赎回条款”口径，关注按公允价值计量的优先股负债及可能触发赎回的金额压力。",
    ),
    "RIGHTS_CLEANUP_INCOMPLETE": (
        "上市前特殊股东权利清理不彻底",
        "依据指标文档第三章“对赌或赎回条款”口径，关注优先认购权、共同出售权、领售权、回购权、赎回权等特殊权利是否在上市前彻底终止。",
    ),
    "REDEMPTION_HIGH": (
        "对赌或赎回条款高风险",
        "依据指标文档第三章“对赌或赎回条款”口径，触发期限在12个月以内、赎回金额占净资产比例超过50%或涉及重大赎回义务时属于高风险。",
    ),
    "REDEMPTION_MEDIUM": (
        "对赌或赎回条款中风险",
        "依据指标文档第三章“对赌或赎回条款”口径，关注上市失败、业绩未达承诺等触发条件及赎回价格、利率、涉及金额和剩余期限。",
    ),
    "RELATED_PARTY_HIGH": (
        "关联交易高风险",
        "依据指标文档第三章“关联交易”口径，关联交易占同类交易比例超过30%、存在未经独立股东批准的关联交易或金额逐年上升时应重点关注。",
    ),
    "RELATED_PARTY_UNFAIR": (
        "关联交易条款公允性风险",
        "依据指标文档第三章“关联交易”口径，关注交易类型、金额、占比、豁免状态及条款是否符合独立第三方商业条件。",
    ),
    "RELATED_PARTY_TREND": (
        "关联交易金额上升风险",
        "依据指标文档第三章“关联交易”口径，关联交易金额呈逐年上升趋势属于中风险信号。",
    ),
    "IP_PATENT_REJECTION": (
        "核心产品知识产权或专利审查风险",
        "依据指标文档第三章“核心产品/管线进度风险”口径，关注核心产品知识产权权属、授权来源、临床及监管进度对商业化前景的影响。",
    ),
    "MARKET_MACRO": (
        "宏观市场情绪评分",
        "衡量上市前恒指、恒生科技指数、成交额、南向资金、波动率及外部利率汇率环境对新股承接力的影响。",
    ),
    "MARKET_INDUSTRY": (
        "所属行业情绪评分",
        "衡量发行人所属行业近期涨跌、相对大盘表现、行业成交活跃度、资金流向及同行业新股历史表现。",
    ),
    "MARKET_IPO_MARKET": (
        "IPO市场供需评分",
        "衡量近期新股发行数量、首日和后续收益、破发率、最大回撤以及本次认购倍数等供需信号。",
    ),
}


def _risk_term_name_and_definition(code: Any, note: Any = "") -> tuple[str, str]:
    text = str(code or "").strip()
    if text in _RISK_TERM_DEFINITIONS:
        return _RISK_TERM_DEFINITIONS[text]
    if text.startswith("MARKET_"):
        return (
            "市场情绪评分项",
            "衡量上市前宏观、行业、IPO供需或舆情因素对新股破发风险和二级市场承接力的影响。",
        )
    label = _clean_sentence(note) or "未命名评分项"
    return label, "该项来自智能体结构化评分输出，当前指标文档未列出标准中文定义，报告保留其自然语言说明。"


def _risk_term_name(code: Any, note: Any = "") -> str:
    return _risk_term_name_and_definition(code, note)[0]


def _market_trigger_note(note: Any) -> str:
    text = str(note or "").strip()
    if not text:
        return ""
    pairs = dict(re.findall(r"([A-Za-z_]+)=([^,，;；]+)", text))
    labels = {
        "historical_module": "历史校准风险分",
        "weight": "有效权重",
        "coverage": "数据覆盖率",
    }
    if pairs:
        bits = []
        for key in ("historical_module", "weight", "coverage"):
            if key in pairs:
                bits.append(f"{labels[key]}为{pairs[key].strip()}")
        if bits:
            return "，".join(bits)
    return _full_text(text)


def _score_trigger_note(code: Any, note: Any) -> str:
    if str(code or "").startswith("MARKET_"):
        return _market_trigger_note(note)
    return _full_text(note)


def _debate_theme_cn(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未命名主题"
    return _DEBATE_THEME_CN.get(text.lower(), _full_text(text))


def _tool_cn(value: Any) -> str:
    text = str(value or "").strip()
    return _TOOL_CN.get(text, _full_text(text) or "—")


def _skill_cn(value: Any) -> str:
    text = str(value or "").strip()
    return _SKILL_CN.get(text, _full_text(text) or "—")


def _feature_value_cn(value: Any, *, field: str | None = None) -> str:
    if field in _LEGAL_PERCENT_POINT_FIELDS:
        return _fmt_pct_point(value)
    if value is True or value is False:
        return _bool_cn(value)
    return _full_text(value)


def _metric_cn(value: Any) -> str:
    text = str(value or "").strip()
    return _METRIC_CN.get(text, _full_text(text) or "—")


def _status_cn(value: Any) -> str:
    text = str(value or "").strip()
    return _STATUS_CN.get(text, _full_text(text) or "—")


def _top_agent_risk_items(block: dict[str, Any]) -> list[str]:
    items: list[str] = []
    source = block.get("score_breakdown") or block.get("risk_points") or []
    for item in source:
        if not isinstance(item, dict):
            continue
        code = item.get("code") or item.get("item") or "风险点"
        note = item.get("note") or item.get("description") or item.get("reason") or ""
        name, definition = _risk_term_name_and_definition(code, note)
        delta = item.get("delta")
        page = item.get("evidence_page")
        if page is None:
            evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            page = next((ev.get("page") for ev in evidence if isinstance(ev, dict) and ev.get("page") is not None), None)
        bits = []
        if delta is not None:
            bits.append(f"分值影响：+{_fmt_num(delta)}")
        if page is not None:
            bits.append(f"证据页：p{page}")
        meta = f"（{'；'.join(bits)}）" if bits else ""
        trigger_note = _score_trigger_note(code, note)
        suffix = f" 触发说明：{trigger_note}" if trigger_note else ""
        items.append(f"{name}{meta}：{definition}{suffix}")
    return items


def _agent_expert_judgment_md(result: dict[str, Any]) -> str:
    meta = [
        ("finance", "财务穿透智能体", "重点判断企业盈利质量、现金流、现金跑道、负债和融资依赖。"),
        ("legal", "法务合规智能体", "重点判断股权架构、特殊股东权利、关连交易、重大合同、知识产权和监管诉讼。"),
        ("market", "市场情绪智能体", "重点判断上市前宏观、行业、IPO 供需、舆情及历史首日破发校准。"),
    ]
    lines: list[str] = ["## 三、三位专家智能体的独立研判\n"]
    for key, title, scope in meta:
        block = result.get(key) if isinstance(result.get(key), dict) else {}
        lines.append(f"### {title}\n")
        if not block:
            lines.append(f"{title}本轮未返回结构化结果。")
            lines.append("")
            continue
        lines.append(scope)
        lines.append("")
        lines.append(_agent_score_summary(title, block))
        summary = _expert_summary_sentence(block.get("summary"), agent_key=key)
        if summary:
            lines.append(f"核心结论：{summary}")
        reasoning = _full_text(block.get("reasoning") or (block.get("trace") or {}).get("structured_reasoning"))
        if reasoning:
            lines.append("")
            lines.append("研判逻辑：")
            for item in _clean_list_items(re.split(r"(?<=[。；;])\s*", reasoning)):
                lines.append(f"- {_sentence(item)}")
        risks = _top_agent_risk_items(block)
        if risks:
            lines.append("")
            lines.append("评分抓手（指标释义）：")
            for item in risks:
                lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def _pages_from_evidence(evidence: Any) -> str:
    pages: list[str] = []
    for ev in evidence or []:
        if not isinstance(ev, dict):
            continue
        page = ev.get("page")
        if page is not None and str(page) not in pages:
            pages.append(str(page))
    return "、".join(pages) if pages else "未提供页码"


def _reply_status_cn(value: Any) -> str:
    mapping = {
        "verified": "已验证",
        "partially_accepted": "部分接受",
        "unresolved": "未解决",
        "rejected": "未采纳",
    }
    return mapping.get(str(value or "").strip(), str(value or "未标注"))


def _debate_kind_cn(value: Any) -> str:
    text = str(value or "").strip()
    return _DEBATE_KIND_CN.get(text.lower(), text or "未标注")


def _priority_cn(value: Any) -> str:
    text = str(value or "").strip()
    return _PRIORITY_CN.get(text.lower(), text or "未标注")


def _debate_severity_cn(value: Any) -> str:
    text = str(value or "").strip()
    return _DEBATE_SEVERITY_CN.get(text.lower(), text or "未标注")


def _clean_debate_continue_reason(value: Any) -> str:
    """移除模型臆造的“已达第 N 轮”表述，轮数由实际 history 负责展示。"""
    text = _full_text(value)
    return re.sub(
        r"已[达達]最大轮次\s*[（(]?\s*第?\s*\d+\s*轮\s*[）)]?\s*[，,。]?",
        "",
        text,
    ).strip()


def _master_debate_md(master: dict[str, Any], *, section_no: str = "六") -> str:
    conflicts = [x for x in (master.get("conflicts") or []) if isinstance(x, dict)]
    rounds = [x for x in (master.get("debate_history") or []) if isinstance(x, dict)]
    lines: list[str] = [f"## {section_no}、四 Agent 辩论过程与收束结论\n"]
    lines.append("该部分记录总控智能体对专家结论的质询，以及财务、法务、市场专家的答复。若某一专家未被直接质询，表示总控未发现需要其补证的关键冲突或证据缺口。")
    lines.append("")
    if conflicts:
        lines.append("### 辩论触发点\n")
        for item in conflicts:
            source_agents = "、".join(_AGENT_CN.get(str(x), str(x)) for x in (item.get("source_agents") or [])) or "未标注"
            kind = _debate_kind_cn(item.get("kind"))
            priority = _priority_cn(item.get("priority"))
            lines.append(f"- **{_debate_theme_cn(item.get('theme'))}**：{_full_text(item.get('description'))}")
            lines.append(f"  - 类型：{kind}；优先级：{priority}；涉及智能体：{source_agents}")
        lines.append("")
    else:
        lines.append("本轮总控未记录结构化冲突点，未触发实质辩论。")
        lines.append("")
    if rounds:
        asked_agents = {
            str(q.get("target_agent"))
            for r in rounds
            for q in (r.get("questions") or [])
            if isinstance(q, dict) and q.get("target_agent")
        }
        not_asked = [
            name
            for key, name in (("finance", "财务穿透智能体"), ("legal", "法务合规智能体"), ("market", "市场情绪智能体"))
            if key not in asked_agents
        ]
        if not_asked:
            lines.append("未被直接质询的专家：" + "、".join(not_asked) + "。")
            lines.append("")
        for r in rounds:
            round_no = r.get("round") or "?"
            lines.append(f"### 第 {round_no} 轮：总控质询与专家答复\n")
            questions = [q for q in (r.get("questions") or []) if isinstance(q, dict)]
            replies = [x for x in (r.get("replies") or []) if isinstance(x, dict)]
            if questions:
                lines.append("总控质询：")
                for q in questions:
                    target = _AGENT_CN.get(str(q.get("target_agent")), str(q.get("target_agent") or "专家"))
                    lines.append(f"- **问 {q.get('question_id') or ''}｜{target}**：{_full_text(q.get('question'))}")
            if replies:
                lines.append("")
                lines.append("专家答复：")
                for reply in replies:
                    target = _AGENT_CN.get(str(reply.get("target_agent")), str(reply.get("target_agent") or "专家"))
                    status = _reply_status_cn(reply.get("status"))
                    severity = _debate_severity_cn(reply.get("severity"))
                    confidence = reply.get("confidence")
                    evidence_pages = _pages_from_evidence(reply.get("evidence"))
                    confidence_text = _fmt_score(confidence) if confidence is not None else "—"
                    lines.append(f"- **{target}｜{status}**（风险强度：{severity}；置信度：{confidence_text}；证据页：{evidence_pages}）：{_full_text(reply.get('reply'))}")
                    uncertainty = _full_text(reply.get("remaining_uncertainty"))
                    if uncertainty:
                        lines.append(f"  - 保留不确定性：{uncertainty}")
            cont = r.get("continue_reason")
            if cont:
                lines.append("")
                decision = "继续追问" if r.get("continue_debate") else "停止追问"
                reason = _clean_debate_continue_reason(cont)
                lines.append(
                    f"本轮收束判断：{decision}。"
                    f"{_sentence(reason, '总控未提供额外收束理由')}"
                )
            lines.append("")
        last = rounds[-1]
        judgment = master.get("judgment") or {}
        verdict = (
            judgment.get("verdict_reasoning")
            or (master.get("report_sections") or {}).get("composite")
            or "总控未提供额外终裁理由"
        )
        score = _fmt_score(judgment.get("overall_score"))
        level = _agent_level_cn(
            judgment.get("risk_level_http") or judgment.get("level")
        )
        confidence = _confidence_cn(judgment.get("confidence"))
        lines.append("### 辩论结论\n")
        lines.append(
            f"总控最终判断："
            f"{'继续追问' if last.get('continue_debate') else '停止追问'}。"
            f"本次共完成{len(rounds)}轮辩论。"
        )
        lines.append(
            f"对终裁的影响：总控吸收上述质询与补证后，"
            f"最终判定为{score}分（{level}，{confidence}）。{_sentence(verdict)}"
        )
        lines.append("")
    return "\n".join(lines)


def _master_prediction_validation_md(master: dict[str, Any], *, stock_code: str = "") -> str:
    lines: list[str] = []
    pw = master.get("predicted_windows") if isinstance(master.get("predicted_windows"), dict) else {}
    lines.extend(["## 当前时间窗的风险预测\n"])
    if pw:
        lines.append("预测标签如下。该部分是上市前预警判断，不承诺精确目标价或收益率。")
        lines.append("")
        lines.append("| 时间窗 | 预测风险标签 |")
        lines.append("|---|---|")
        for window, field in _WINDOW_PREDICTED_FIELD.items():
            lines.append(f"| {_window_cn(window)} | {_risk_label_cn(pw.get(field))} |")
        lines.append("")
    forecasts = _master_forecast_items(master, pw)
    if forecasts:
        lines.append("逐时间窗走势预判如下。")
        lines.append("")
        for item in forecasts:
            lines.append(f"### {_window_cn(item.get('window'))}\n")
            lines.append(
                f"系统判断该时间窗为{_risk_label_cn(item.get('risk_label'))}，"
                f"置信度为{_confidence_cn(item.get('confidence'))}。"
            )
            lines.append("")
            lines.append("预测要点：")
            lines.append(f"- 方向：{_sentence(item.get('expected_direction'), '未给出明确方向描述')}")
            lines.append(f"- 走势：{_sentence(item.get('expected_pattern'), '未给出具体走势情景')}")
            lines.append(f"- 波动与回撤：{_sentence(item.get('volatility_view'), '未给出波动判断')}")
            drivers = _bullet_lines(item.get("key_drivers"), empty="未给出主要触发依据")
            lines.append("")
            lines.append("主要触发依据：")
            lines.extend(drivers)
            lines.append("")
    else:
        lines.append("本次结构化结果未提供逐时间窗走势文字，报告保留上述标签级预测。\n")

    post = master.get("post_listing") if isinstance(master.get("post_listing"), dict) else {}
    if not (post.get("checkpoints") if isinstance(post.get("checkpoints"), list) else []):
        sidecar = _postlisting_sidecar(stock_code)
        if sidecar:
            post = sidecar
    lines.extend(["## 上市后真实行情验证\n"])
    has_checkpoints = bool(post.get("checkpoints") if isinstance(post.get("checkpoints"), list) else [])
    lines.append(
        f"上市后验证状态为{'已完成' if has_checkpoints else '暂无法验证'}。"
        "数据来源为系统生成的上市后行情检查点数据。"
    )
    if any(post.get(k) is not None for k in ("weighted_hit_score", "business_value_score", "d5_priority_hit")):
        lines.append(
            f"综合命中分为{_fmt_score(post.get('weighted_hit_score'))}分，"
            f"业务参考分为{_fmt_score(post.get('business_value_score'))}分。"
            f"上市后5个交易日内重点预警是否命中：{_bool_cn(post.get('d5_priority_hit'))}。"
        )
    elif post.get("note") and not has_checkpoints:
        lines.append(_full_text(post.get("note")) + "。")
    summary = post.get("forecast_alignment_summary") or post.get("summary")
    if summary:
        lines.append("")
        lines.append("验证摘要：")
        lines.extend(_bullet_lines(summary))
    lines.append("")
    checkpoints = [x for x in (post.get("checkpoints") or []) if isinstance(x, dict)]
    if checkpoints:
        by_window: dict[str, dict[str, Any]] = {}
        for c in checkpoints:
            key = str(c.get("window") or c.get("checkpoint") or "").upper()
            if key in {"D1", "D5", "D20", "D60"} and key not in by_window:
                by_window[key] = c
        checkpoints = [by_window[w] for w in ("D1", "D5", "D20", "D60") if w in by_window] or checkpoints
        for c in checkpoints:
            raw_window = str(c.get("window") or c.get("checkpoint") or "")
            window = _window_cn(raw_window)
            predicted_label = c.get("prediction_label") or _predicted_label_for_window(pw, raw_window)
            actual_label = c.get("actual_severity") or c.get("risk_level")
            alignment = c.get("alignment") or _derived_alignment(predicted_label, actual_label)
            prediction_text = _full_text(c.get("prediction_text") or "")
            prediction_items = _clean_list_items(prediction_text)
            lines.append(f"### {window}验证\n")
            lines.append(
                f"上市前预测为{_risk_label_cn(predicted_label)}。"
            )
            lines.append("")
            if prediction_items:
                lines.append("预测文本：")
                lines.extend(_bullet_lines(prediction_items, empty="未提供预测文本"))
                lines.append("")
            lines.append(
                f"真实观察日期为{c.get('observation_date') or '暂不可得'}。"
                f"该时间窗真实风险等级为{_risk_label_cn(actual_label)}，"
                f"与上市前预警的关系为{_alignment_cn(alignment)}。"
            )
            lines.append("")
            lines.append("行情指标：")
            lines.append(f"- 收盘价是否低于发行价：{_bool_cn(c.get('below_issue_price'))}")
            lines.append(f"- 相对发行价收益：{_fmt_pct(c.get('issue_price_return'))}")
            lines.append(f"- 相对上市首日开盘价累计收益：{_fmt_pct(c.get('cumulative_return_from_open'))}")
            lines.append(f"- 区间最大回撤：{_fmt_pct(c.get('max_drawdown_from_open'))}")
            lines.append(f"- 真实风险分：{_score_sentence(c.get('realized_risk_score'))}")
            lines.append("")
        lines.append("")
    limitations = [str(x) for x in (post.get("limitations") or []) if x]
    if limitations:
        lines.append("### 数据限制\n")
        for item in limitations:
            lines.append(f"- {_humanize_backend_terms(item)}")
        lines.append("")
    return "\n".join(lines)


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
        # map keys carefully
        cells = [_metric_cn(field)]
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
    lines = ["| 评分项 | 加分 | 指标释义 | 指标值 | 触发说明 | 证据页 |", "|------|------|------|--------|------|--------|"]
    for b in breakdown:
        if not isinstance(b, dict):
            lines.append(f"| — | — | — | — | {str(b).replace('|', '/')} | — |")
            continue
        pages = sorted({e.get("page") for e in (b.get("evidence") or []) if isinstance(e, dict) and e.get("page") is not None})
        if b.get("evidence_page") is not None:
            pages = sorted(set(pages) | {b.get("evidence_page")})
        code = b.get("code") or b.get("item") or "ITEM"
        note = b.get("note") or b.get("description") or b.get("item") or "—"
        name, definition = _risk_term_name_and_definition(code, note)
        lines.append(
            "| {name} | +{delta} | {definition} | {mv} | {note} | {pages} |".format(
                name=str(name).replace("|", "/"),
                delta=b.get("delta"),
                definition=str(definition).replace("|", "/"),
                mv=str(
                    b.get("metric_display")
                    if b.get("metric_display") not in (None, "")
                    else b.get("metric_value")
                    if b.get("metric_value") is not None
                    else "—"
                ).replace("|", "/"),
                note=_score_trigger_note(code, note).replace("|", "/"),
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
        meta = [f"状态={_status_cn(status if status is not None else '—')}"]
        if score is not None:
            meta.append(f"分数={score}")
        parts.append(f"#### {_full_text(dim_id)} — {' · '.join(meta)}\n")
        if analysis:
            parts.append(f"{analysis}\n")
        findings = d.get("findings") or []
        if findings:
            for f in findings:
                if not isinstance(f, dict):
                    parts.append(f"- {f}")
                    continue
                parts.append(
                    f"- **{_risk_term_name(f.get('code'), f.get('description'))}**"
                    f"（{_risk_label_cn(f.get('level'))}）：{_full_text(f.get('description'))} "
                    f"| 指标={_full_text(f.get('metric_value'))} | p{f.get('evidence_page')}"
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
    lines = ["| 风险点 | 等级 | 说明 | 指标 | 页 |", "|------|------|------|------|----|"]
    for p in points:
        if not isinstance(p, dict):
            continue
        code = p.get("code") or p.get("item")
        note = p.get("description") or p.get("reason") or p.get("note") or ""
        lines.append(
            "| {code} | {level} | {desc} | {mv} | {page} |".format(
                code=_risk_term_name(code, note).replace("|", "/"),
                level=p.get("level") or "—",
                desc=_full_text(p.get("description") or "—").replace("|", "/"),
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
            bits.append(f"检索意图={_debate_theme_cn(args.get('intent'))}")
        if args.get("reason"):
            bits.append(_full_text(args.get("reason"))[:60])
        if obs.get("n") is not None:
            bits.append(f"命中数={obs.get('n')}")
        pages = []
        for h in (obs.get("hits") or [])[:3]:
            if isinstance(h, dict) and h.get("page") is not None:
                pages.append(str(h.get("page")))
        if pages:
            bits.append("p" + ",".join(pages))
        if obs.get("risk_score") is not None:
            bits.append(f"风险分={_fmt_score(obs.get('risk_score'))}")
        if c.get("status"):
            bits.append(_full_text(c.get("status")))
        lines.append(
            "| {turn} | `{tool}` | {think} | {bits} | {ms} |".format(
                turn=c.get("turn") if c.get("turn") is not None else "—",
                tool=_tool_cn(tool).replace("|", "/"),
                think=_status_cn(c.get("think_status") or "—"),
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
        notes.append(f"模型推理状态：{_status_cn(think_status)}（全文见推理日志）。")
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
                f"{_skill_cn(k)}({(v or {}).get('risk_point_count', 0)}点)"
                for k, v in sorted(skills.items())
            )
        )
    return notes


def _analyze_legal(legal: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    feats = legal.get("features") or {}
    score = legal.get("risk_score")
    notes.append(
        f"风险分 **{_fmt_score(score)}**（{_agent_level_cn(legal.get('risk_level'))}）。"
        f"打分来自披露基础分或规则命中，具体见得分分解。"
    )
    f31 = _legal_section_feat(legal, "3.1")
    f32 = _legal_section_feat(legal, "3.2")
    f33 = _legal_section_feat(legal, "3.3")
    notes.append(
        f"3.1 对赌/赎回：是否存在={_bool_cn(f31.get('exists'))}，证据强度={_full_text(f31.get('evidence_strength'))}"
    )
    notes.append(
        f"3.2 关联交易：是否存在={_bool_cn(f32.get('exists'))}，占比={_fmt_pct_point(f32.get('ratio_pct'))}。"
    )
    notes.append(
        f"3.3 集中度：是否存在={_bool_cn(f33.get('exists'))}，"
        f"证据页={legal.get('evidence_summary', {}).get('3.3_pages')}。"
    )
    if (_legal_section_feat(legal, "3.5") or {}).get("skipped"):
        notes.append("3.5 管线风险按 non-biotech 正确跳过。")
    skills = feats.get("skill_results") or {}
    if skills:
        notes.append(
            "法务 Skill："
            + "、".join(
                f"{_skill_cn(k)}({len((v or {}).get('risk_points') or [])}点)"
                for k, v in sorted(skills.items())
            )
        )
    return notes


def _agent_header(
    *,
    doc_name: str,
    agent_title: str,
    pdf_name: str,
    doc_id: Any,
    score: Any,
    level: Any,
    scoring_mode: Any,
    run_log_path: Any,
    note: Any,
    extra_lines: list[str] | None = None,
) -> list[str]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"# {doc_name} — {agent_title} 结果分析报告\n",
        f"- 生成时间：{now}",
        f"- 招股书：`{pdf_name}`",
        f"- doc_id：`{doc_id}`",
        f"- 本 Agent 风险分：`{_fmt_score(score)}`（{level or '—'}）",
        f"- 评分模式：`{scoring_mode or '—'}`",
    ]
    if run_log_path:
        parts.append(f"- 推理日志：`{run_log_path}`")
    parts.append(f"- 说明：{note or '—'}")
    for line in extra_lines or []:
        parts.append(line)
    parts.append("")
    return parts


def _footer() -> list[str]:
    return [
        "---\n",
        "_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_\n",
    ]


def build_finance_report(
    result: dict[str, Any],
    *,
    doc_name: str,
    pdf_name: str,
    finance_retrieval: dict[str, Any] | None,
) -> str:
    finance = result.get("finance") or {}
    if not isinstance(finance, dict) or not finance:
        return ""
    fin_ev = _collect_finance_evidence(finance, finance_retrieval)
    feats = finance.get("features") or {}
    mode = feats.get("scoring_mode") or (finance.get("trace") or {}).get("scoring_mode")
    run_log = feats.get("run_log") or {}
    parts = _agent_header(
        doc_name=doc_name,
        agent_title="财务穿透 Agent",
        pdf_name=pdf_name,
        doc_id=result.get("doc_id"),
        score=finance.get("risk_score"),
        level=finance.get("risk_level"),
        scoring_mode=mode,
        run_log_path=run_log.get("log"),
        note=result.get("note"),
    )

    parts.append("## 1. 总览\n")
    parts.append("| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |")
    parts.append("|-------|---------------------|------|------|")
    parts.append(
        f"| 财务穿透 | **{_fmt_score(finance.get('risk_score'))}** | {finance.get('risk_level')} | "
        f"{(finance.get('summary') or '').replace('|', '/')} |"
    )
    parts.append("")

    parts.append("## 2. 得分与分解\n")
    parts.append(_score_breakdown_md(finance.get("score_breakdown") or []))
    floor = feats.get("rules_floor") or (finance.get("trace") or {}).get("rules_floor")
    parts.append(_rules_floor_md(floor if isinstance(floor, dict) else None))
    parts.append("## 3. 风险点\n")
    risk_points = feats.get("risk_points") or finance.get("risk_points") or []
    parts.append(_risk_points_md(risk_points if isinstance(risk_points, list) else []))
    parts.append("## 4. 四维分析（LLM）\n")
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
    parts.append("## 5. 推理链\n")
    sr = (finance.get("trace") or {}).get("structured_reasoning") or (
        (feats.get("llm_analysis") or {}).get("reasoning")
    )
    if sr:
        parts.append("**[structured_reasoning]**\n")
        parts.append(f"{_full_text(sr)}\n")
    think_ex = feats.get("model_think_excerpt")
    if think_ex:
        parts.append("**[model_think 摘录]**（全文见 logs）\n")
        parts.append(f"> {_full_text(think_ex).replace(chr(10), ' ')}\n")
    elif feats.get("think_status") == "think_from_content":
        parts.append(
            "_模型提交轮未返回独立推理字段，已从输出内容和工具调用原因中恢复推理摘要。_\n"
        )
    elif feats.get("think_status") in {"reasoning_missing", "reasoning_missing_after_retry"}:
        parts.append(f"_模型提交轮推理状态：{_status_cn(feats.get('think_status'))}_\n")
    turn_think = feats.get("turn_think_status") or []
    if not turn_think:
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
                f"{_tool_cn(row.get('tool') or '—')} | {_status_cn(row.get('think_status') or '—')} |"
            )
        parts.append("")
    parts.append("## 6. 门控\n")
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
    parts.append("## 7. 抽取指标与现金消耗\n")
    parts.append(_metrics_table(finance.get("metrics") or {}))
    parts.append("**3.4 现金消耗（cash_burn）**\n")
    parts.append(_cash_burn_md(finance))
    parts.append("## 8. 召回证据（主表）\n")
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
    section_hits = (finance.get("evidence_summary") or {}).get("section_evidence_hits") or []
    section_routes = (finance.get("evidence_summary") or {}).get("section_routes") or []
    parts.append("### 8.1 章节化上下文证据\n")
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
    parts.append("## 9. 工具调用链（摘要）\n")
    parts.append(_tool_trace_summary_md(finance.get("trace") or {}))
    parts.append("## 10. 分析结论\n")
    for n in _analyze_finance(finance):
        parts.append(f"- {n}")
    parts.append("")
    nf_raw = feats.get("negative_findings") or []
    nf_kept, nf_dropped = _filter_negative_findings(
        nf_raw if isinstance(nf_raw, list) else [],
        finance.get("score_breakdown") or [],
    )
    parts.append("## 11. 阴性发现（已审查未见风险）\n")
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
        parts.append("## 12. 资产负债表交叉校验\n")
        for note in bs["notes"]:
            parts.append(f"- {note}")
        parts.append("")
    parts.extend(_footer())
    return "\n".join(parts)


def build_legal_report(
    result: dict[str, Any],
    *,
    doc_name: str,
    pdf_name: str,
    legal_retrieval: dict[str, Any] | None = None,
) -> str:
    del legal_retrieval  # 证据优先走 Agent 自带 snippets
    legal = result.get("legal") or {}
    if not isinstance(legal, dict) or not legal:
        return ""
    leg_ev = _collect_legal_evidence(legal)
    feats = legal.get("features") or {}
    mode = feats.get("scoring_mode") or (legal.get("trace") or {}).get("scoring_mode")
    run_log = feats.get("run_log") or {}
    parts = _agent_header(
        doc_name=doc_name,
        agent_title="法务合规 Agent",
        pdf_name=pdf_name,
        doc_id=result.get("doc_id"),
        score=legal.get("risk_score"),
        level=legal.get("risk_level"),
        scoring_mode=mode,
        run_log_path=run_log.get("log"),
        note=result.get("note"),
    )

    parts.append("## 1. 总览\n")
    parts.append("| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |")
    parts.append("|-------|---------------------|------|------|")
    parts.append(
        f"| 法务合规 | **{_fmt_score(legal.get('risk_score'))}** | {legal.get('risk_level')} | "
        f"{(legal.get('summary') or '').replace('|', '/')} |"
    )
    parts.append("")

    parts.append("## 2. 得分与分解\n")
    parts.append(_score_breakdown_md(legal.get("score_breakdown") or []))
    parts.append("## 3. 章节特征摘要\n")
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
                extra.append(
                    f"{_LEGAL_FEATURE_CN.get(k, _full_text(k))}="
                    f"{_feature_value_cn(feat.get(k), field=k)}"
                )
            elif feat.get(k) is False and k in {
                "redemption_high",
                "valuation_inversion",
                "pipeline_high",
                "related_party_ratio_gt_30",
                "concentration_high",
            }:
                extra.append(f"{_LEGAL_FEATURE_CN.get(k, _full_text(k))}=否")
        parts.append(
            f"| {sec} | {status} | {feat.get('evidence_strength') or '—'} | "
            f"{('; '.join(extra) if extra else '—')} |"
        )
    parts.append("")
    parts.append("## 4. 召回证据明细\n")
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

    parts.append("## 5. 计分证据\n")
    for b in legal.get("score_breakdown") or []:
        note = b.get("note") or b.get("description") or b.get("item") or ""
        name, definition = _risk_term_name_and_definition(b.get("code"), note)
        parts.append(f"#### {name}（+{b.get('delta')}）\n")
        parts.append(f"{definition}\n")
        if b.get("note"):
            parts.append(f"{_full_text(b.get('note'))}\n")
        for ev in b.get("evidence") or []:
            parts.append(
                f"- p{ev.get('page')}（{ev.get('source_type')}）："
                f"{_clean_excerpt(ev.get('excerpt') or '', 360)}"
            )
        parts.append("")

    parts.append("## 6. 工具调用链（摘要）\n")
    parts.append(_tool_trace_summary_md(legal.get("trace") or {}))
    parts.append("## 7. 分析结论\n")
    for n in _analyze_legal(legal):
        parts.append(f"- {n}")
    parts.append("")
    parts.extend(_footer())
    return "\n".join(parts)


def build_market_report(result: dict[str, Any]) -> str:
    return _humanize_backend_terms(market_report_markdown(result))


def build_master_report(
    result: dict[str, Any],
    *,
    doc_name: str,
    pdf_name: str,
) -> str:
    master = result.get("master") if isinstance(result.get("master"), dict) else {}
    if not master:
        return ""
    judgment = master.get("judgment") if isinstance(master.get("judgment"), dict) else {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    score_evidence = _collect_score_evidence(result)
    risk_level = _risk_label_cn(judgment.get("risk_level_http") or judgment.get("level"))
    confidence = _confidence_cn(judgment.get("confidence"))
    reference_score = result.get("reference_fundamental_score")
    if reference_score is None:
        reference_score = master.get("reference_fundamental_score")
    parts = [
        f"# {doc_name} IPO风险穿透预警报告\n",
        f"- 生成时间：{now}",
        f"- 招股书：`{pdf_name}`",
        f"- 任务编号：`{result.get('doc_id') or master.get('doc_id') or '—'}`",
        "",
        "## 一、报告口径说明\n",
        "本报告面向专家评委和证券从业人员，用于展示系统对单只港股新股的风险穿透判断、证据定位和上市后复盘验证。风险分采用0至100分口径，分数越高表示风险越高；风险标签分为高风险、中等风险、低风险；置信度表示系统对证据完整性、跨智能体一致性和市场数据可用性的综合把握，分为高置信度、中等置信度和低置信度。",
        "上市后验证中的“预警命中”表示上市前判断与真实表现高度一致；“方向部分吻合”表示方向一致但强弱程度存在差异；“预警偏离”表示上市前判断与真实表现明显不一致。报告引用的页码均按原 PDF 页码表述，不使用招股书目录页码。招股书原文证据保留繁体中文，并用引号标示。",
        "",
        "## 二、总控结论\n",
        (
            f"系统给出的总控风险分为{_score_sentence(judgment.get('overall_score'))}，"
            f"综合风险标签为{risk_level}，判断置信度为{confidence}。"
            f"用于对照的基础加权分为{_score_sentence(reference_score)}。"
        ),
        _full_text(((master.get("report_sections") or {}).get("composite")) or judgment.get("verdict_reasoning") or "当前结果未提供总控终裁说明。"),
        "",
        "评分说明：" + _full_text(((master.get("report_sections") or {}).get("confidence_note")) or judgment.get("score_explanation") or "当前结果未提供评分说明。"),
        "",
    ]
    parts.append(_agent_expert_judgment_md(result))
    if str(PKG_ROOT) not in sys.path:
        sys.path.insert(0, str(PKG_ROOT))
    from src.skills.embellishment_reporting import embellishment_enabled

    include_embellishment = embellishment_enabled(master)
    if include_embellishment:
        parts.append(_embellishment_report_md(master.get("embellishment")))
    factor_no = "五" if include_embellishment else "四"
    debate_no = "六" if include_embellishment else "五"
    prediction_no = "七" if include_embellishment else "六"
    postlisting_no = "八" if include_embellishment else "七"
    factors = [x for x in (master.get("risk_factors") or []) if isinstance(x, dict)]
    if factors:
        parts.extend([f"## {factor_no}、核心风险诱因与原文证据\n"])
        for idx, f in enumerate(factors, start=1):
            f = _normalize_embellishment_factor(f, master.get("embellishment"))
            source = _AGENT_CN.get(str(f.get("source_agent") or ""), "总控智能体")
            parts.append(f"### 诱因{idx}：{_full_text(f.get('title') or '未命名风险')}\n")
            reason = _sentence(f.get("reason"), "当前结构化结果未提供详细理由")
            parts.append(f"该诱因来自{source}。系统判断理由为：{reason}")
            for paragraph in _factor_evidence_paragraphs(f, score_evidence=score_evidence):
                parts.append(paragraph)
            parts.append("")
    else:
        parts.extend(
            [
                f"## {factor_no}、核心风险诱因与原文证据\n",
                "当前总控结果没有提供结构化风险因子，无法逐项映射原 PDF 证据段落。",
                "",
            ]
        )
    parts.append(_master_debate_md(master, section_no=debate_no))
    prediction_md = _master_prediction_validation_md(
        master,
        stock_code=resolve_report_stock_code(result, pdf_name=pdf_name),
    ).replace("## 当前时间窗的风险预测", f"## {prediction_no}、当前时间窗的风险预测").replace("## 上市后真实行情验证", f"## {postlisting_no}、上市后真实行情验证")
    parts.append(prediction_md)
    parts.extend(_footer())
    return "\n".join(parts)


def write_agent_reports(
    result: dict[str, Any],
    *,
    reports_dir: Path,
    stock_code: str,
    doc_name: str,
    pdf_name: str,
    finance_retrieval: dict[str, Any] | None = None,
    legal_retrieval: dict[str, Any] | None = None,
) -> dict[str, Path]:
    paths = report_paths(reports_dir, stock_code)
    reports_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    finance_md = build_finance_report(
        result,
        doc_name=doc_name,
        pdf_name=pdf_name,
        finance_retrieval=finance_retrieval,
    )
    if finance_md:
        paths["finance"].write_text(finance_md, encoding="utf-8")
        written["finance"] = paths["finance"]
    legal_md = build_legal_report(
        result,
        doc_name=doc_name,
        pdf_name=pdf_name,
        legal_retrieval=legal_retrieval,
    )
    if legal_md:
        paths["legal"].write_text(legal_md, encoding="utf-8")
        written["legal"] = paths["legal"]
    market_md = build_market_report(result)
    if market_md:
        text = market_md + ("" if market_md.endswith("\n") else "\n")
        paths["market"].write_text(text, encoding="utf-8")
        written["market"] = paths["market"]
    master_md = build_master_report(result, doc_name=doc_name, pdf_name=pdf_name)
    if master_md:
        paths["master"].write_text(master_md, encoding="utf-8")
        written["master"] = paths["master"]
    return written


def build_report(
    result: dict[str, Any],
    *,
    doc_name: str,
    pdf_name: str,
    finance_retrieval: dict[str, Any] | None,
    legal_retrieval: dict[str, Any] | None,
) -> str:
    """兼容旧测试：优先返回总控预警报告；无总控则返回法务/财务报告。"""
    master_md = build_master_report(result, doc_name=doc_name, pdf_name=pdf_name)
    if master_md:
        return master_md
    legal_md = build_legal_report(
        result, doc_name=doc_name, pdf_name=pdf_name, legal_retrieval=legal_retrieval
    )
    if legal_md:
        return legal_md
    return build_finance_report(
        result, doc_name=doc_name, pdf_name=pdf_name, finance_retrieval=finance_retrieval
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate split finance/legal/market markdown reports")
    parser.add_argument(
        "--result",
        type=Path,
        default=PKG_ROOT / ".runtime" / "mixue_finance_legal.json",
    )
    parser.add_argument("--doc-name", default="蜜雪集團")
    parser.add_argument("--pdf-name", default="02097_21-02-2025_蜜雪集團_全球發售.pdf")
    parser.add_argument("--stock-code", default="")
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
        "--reports-dir",
        type=Path,
        default=PKG_ROOT / "reports",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="已废弃：若传入且为目录则当作 --reports-dir；若为文件则取其父目录",
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

    reports_dir = args.reports_dir
    if args.out is not None:
        reports_dir = args.out if args.out.suffix == "" else args.out.parent
    stock_code = resolve_report_stock_code(
        result, stock_code=args.stock_code, pdf_name=args.pdf_name
    )
    written = write_agent_reports(
        result,
        reports_dir=reports_dir,
        stock_code=stock_code,
        doc_name=args.doc_name,
        pdf_name=args.pdf_name,
        finance_retrieval=fin_ret,
        legal_retrieval=leg_ret,
    )
    if not written:
        print("no reports written", file=sys.stderr)
        return 1
    for kind, path in written.items():
        print(f"Wrote {kind} {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
