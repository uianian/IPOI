"""财务主表 / 指标编码 → 繁体中文名（对齐 dataset/招股书关键信息抽取与风险特征定义.md §二）。"""

from __future__ import annotations

from typing import Any

# 主表
TABLE_NAME_ZH: dict[str, str] = {
    "TBL_IS": "合併損益表",
    "TBL_BS": "合併資產負債表",
    "TBL_BS_COMPANY": "公司層面資產負債表",
    "TBL_CF": "合併現金流量表",
    "TBL_CI": "合併綜合收益表",
}

# 字段编码 → 指标名称（繁体）
METRIC_NAME_ZH: dict[str, str] = {
    "REV": "營業收入",
    "OTHER_INCOME": "其他收入及收益",
    "COGS": "營業成本",
    "GP": "毛利",
    "GP_MARGIN": "毛利率",
    "RD_EXP": "研發費用",
    "R&D_EXP": "研發費用",
    "SGA": "銷售及行政費用",
    "SG&A": "銷售及行政費用",
    "NET_LOSS": "期內虧損/利潤",
    "NET_PROFIT_OR_LOSS": "期內虧損/利潤",
    "ADJ_NET": "經調整淨利潤",
    "TOTAL_ASSETS": "總資產",
    "TOTAL_LIAB": "總負債",
    "NET_ASSETS": "淨資產",
    "CASH_EQ": "現金及現金等價物",
    "CV_PREF": "可轉換可贖回優先股",
    "TRADE_REC": "貿易應收款",
    "TRADE_PAY": "貿易應付款",
    "CFO": "經營活動現金流淨額",
    "CFI": "投資活動現金流淨額",
    "CFF": "融資活動現金流淨額",
    "END_CASH": "年末現金餘額",
    "CORE_PROD_CNT": "核心產品數量",
    "PROD_STAGE": "各核心產品研發階段",
    "PROD_IND": "各核心產品適應症",
    "PROD_MILESTONE": "核心產品預計里程碑",
    "PROD_R&D": "各核心產品研發開支",
    "BURN_RATE": "現金消耗率",
    "CASH_RUNWAY": "現金跑道",
    "PRE_IPO_FIN": "IPO前融資總額及輪數",
}

# 展示顺序（损益 → 资产负债 → 现金流 → 18A）
METRIC_DISPLAY_ORDER: tuple[str, ...] = (
    "REV",
    "OTHER_INCOME",
    "COGS",
    "GP",
    "GP_MARGIN",
    "RD_EXP",
    "SGA",
    "NET_LOSS",
    "NET_PROFIT_OR_LOSS",
    "ADJ_NET",
    "TOTAL_ASSETS",
    "TOTAL_LIAB",
    "NET_ASSETS",
    "CASH_EQ",
    "CV_PREF",
    "TRADE_REC",
    "TRADE_PAY",
    "CFO",
    "CFI",
    "CFF",
    "END_CASH",
    "BURN_RATE",
    "CASH_RUNWAY",
    "CORE_PROD_CNT",
)


def metric_name_zh(code: str) -> str:
    if not code:
        return ""
    if code in METRIC_NAME_ZH:
        return METRIC_NAME_ZH[code]
    # NET_PROFIT_OR_LOSS alias
    if code == "NET_PROFIT_OR_LOSS":
        return METRIC_NAME_ZH["NET_LOSS"]
    return code


def table_name_zh(code: str) -> str:
    return TABLE_NAME_ZH.get(code, code)


def _fmt_num(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f - round(f)) < 1e-9:
        return f"{int(round(f)):,}"
    return f"{f:,.2f}"


def format_series(series: dict[str, Any] | None) -> str:
    if not isinstance(series, dict) or not series:
        return "—"
    parts = []
    for y in sorted(series.keys(), key=lambda x: (0, int(x)) if str(x).isdigit() else (1, str(x))):
        parts.append(f"{y}={_fmt_num(series.get(y))}")
    return "；".join(parts)


def metrics_to_display(metrics: dict[str, Any] | None) -> list[dict[str, Any]]:
    """结构化指标列表，供 Thought.meta / result.agents.financial。"""
    metrics = metrics or {}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def _add(code: str, series: Any) -> None:
        if code in seen or not isinstance(series, dict):
            return
        # 统一 NET_LOSS 展示编码
        display_code = "NET_LOSS" if code in {"NET_LOSS", "NET_PROFIT_OR_LOSS"} else code
        if display_code in seen:
            return
        seen.add(display_code)
        out.append(
            {
                "code": display_code,
                "nameZh": metric_name_zh(display_code),
                "series": series,
                "seriesText": format_series(series),
            }
        )

    for code in METRIC_DISPLAY_ORDER:
        if code == "NET_PROFIT_OR_LOSS":
            continue
        if code == "NET_LOSS":
            series = metrics.get("NET_LOSS") or metrics.get("NET_PROFIT_OR_LOSS")
            _add("NET_LOSS", series)
            continue
        _add(code, metrics.get(code))

    for code, series in metrics.items():
        if code in {"cash_burn"}:
            continue
        if code in {"NET_LOSS", "NET_PROFIT_OR_LOSS"}:
            _add("NET_LOSS", series)
        else:
            _add(code, series)
    return out


def format_metrics_block(metrics: dict[str, Any] | None, *, max_lines: int = 24) -> str:
    rows = metrics_to_display(metrics)
    if not rows:
        return "（尚未抽到指標）"
    lines = ["【財務指標】"]
    for i, row in enumerate(rows):
        if i >= max_lines:
            lines.append(f"…共 {len(rows)} 項，其餘見 meta.metrics")
            break
        lines.append(f"- {row['nameZh']}（{row['code']}）：{row['seriesText']}")
    return "\n".join(lines)


def tables_to_display(tables_detail: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in tables_detail or []:
        if not isinstance(t, dict):
            continue
        code = str(t.get("code") or t.get("table") or "")
        out.append(
            {
                "code": code,
                "nameZh": t.get("nameZh") or table_name_zh(code),
                "page": t.get("page"),
                "sourceType": t.get("sourceType") or t.get("source_type"),
                "excerpt": t.get("excerpt") or "",
            }
        )
    return out


def format_tables_block(tables_detail: list[dict[str, Any]] | None) -> str:
    rows = tables_to_display(tables_detail)
    if not rows:
        return "（未定位到財務主表）"
    lines = ["【三張財務主表】"]
    for row in rows:
        page = row.get("page")
        page_s = f"p.{page}" if page is not None else "頁碼未知"
        lines.append(f"- {row['nameZh']}（{row['code']}）@ {page_s}")
    return "\n".join(lines)


def build_tables_detail_from_bundle(bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    """从 retrieve bundle.evidence_by_table 生成带中文名/页码的表清单。"""
    by_table = (bundle or {}).get("evidence_by_table") or {}
    preferred = ("TBL_IS", "TBL_BS", "TBL_CF", "TBL_BS_COMPANY", "TBL_CI")
    codes = [c for c in preferred if c in by_table] + [
        c for c in by_table.keys() if c not in preferred
    ]
    out: list[dict[str, Any]] = []
    for code in codes:
        hits = by_table.get(code) or []
        hit = hits[0] if isinstance(hits, list) and hits else {}
        if not isinstance(hit, dict):
            hit = {}
        excerpt = str(hit.get("excerpt") or hit.get("content") or "")
        out.append(
            {
                "code": code,
                "nameZh": table_name_zh(code),
                "page": hit.get("page"),
                "sourceType": hit.get("category") or hit.get("chunk_type") or hit.get("source_type"),
                "excerpt": excerpt[:200],
                "nHits": len(hits) if isinstance(hits, list) else 0,
            }
        )
    return out
