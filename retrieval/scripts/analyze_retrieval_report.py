#!/usr/bin/env python3
"""分析 Agent 检索结果 JSON，生成面向金融从业人员的 Markdown 汇报报告。

兼容两种 JSON：
  - ``--agent all`` → ``{finance: {...}, legal: {...}}``
  - ``--agent finance|legal`` → 根上即 agent 块（含 evidence_by_table / per_query）

财务 2.1–2.3 为整表召回时，按 TBL_IS / TBL_BS / TBL_CF 评估与展示。

Example:
  conda activate ipo-risk
  cd agents/ipo
  python scripts/analyze_retrieval_report.py \\
    --result .runtime/agent_retrieval_mixue.json \\
    --doc-name 蜜雪冰城 \\
    --out .runtime/reports/retrieval_quality_mixue.md
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 业务口径：理想证据来源（面向港股招股书，非硬编码页码）
# grade 用于自动打分：hit 中出现这些角色/形态即加分
# ---------------------------------------------------------------------------

# 2.1/2.2/2.3 现按表类型整表召回；字段级 META 保留供 covers_fields 说明与旧基线对照
TABLE_META: dict[str, dict[str, Any]] = {
    "TBL_IS": {
        "label": "综合损益表（整表）",
        "section": "2.1 损益表",
        "ideal": "附录一《综合损益表》全文；概要/财务资料讨论节同名表作交叉校验",
        "prefer_roles": ["appendix", "summary", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {27, 327, 428},
        "covers_hint": "REV / COGS / GP / GP_MARGIN / R&D_EXP / SG&A / NET_LOSS / ADJ_NET",
    },
    "TBL_BS": {
        "label": "综合财务状况表（整表）",
        "section": "2.2 资产负债表",
        "ideal": "附录一《综合财务状况表》全文；概要资产负债概要可校验",
        "prefer_roles": ["appendix", "summary", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {28, 346, 430, 441},
        "covers_hint": "TOTAL_ASSETS / TOTAL_LIAB / NET_ASSETS / CASH_EQ / CV_PREF / TRADE_*",
    },
    "TBL_CF": {
        "label": "综合现金流量表（整表）",
        "section": "2.3 现金流量表",
        "ideal": "附录一《综合现金流量表》全文；概要现金流概要可校验",
        "prefer_roles": ["appendix", "summary", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {29, 360, 437, 438},
        "covers_hint": "CFO / CFI / CFF / END_CASH",
    },
}

FIELD_META: dict[str, dict[str, Any]] = {
    # 2.1
    "REV": {
        "label": "营业收入",
        "section": "损益表",
        "ideal": "附录一《综合损益表》「收入」行；概要表可作交叉校验",
        "prefer_roles": ["appendix", "summary"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {27, 327, 428},
    },
    "COGS": {
        "label": "营业成本/销售成本",
        "section": "损益表",
        "ideal": "附录一损益表「销售成本」行；或财务资料讨论节对应表",
        "prefer_roles": ["appendix", "summary", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {27, 327, 428},
    },
    "GP": {
        "label": "毛利",
        "section": "损益表",
        "ideal": "合并损益表「毛利」行（非渠道/单店毛利拆分表）",
        "prefer_roles": ["appendix", "summary", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {27, 327, 428},
    },
    "GP_MARGIN": {
        "label": "毛利率",
        "section": "损益表",
        "ideal": "概要/财务资料中的毛利率披露；主表常无单独行",
        "prefer_roles": ["summary", "discussion"],
        "prefer_cats": ["table", "text"],
        "gold_hint_pages": {16, 21, 27, 327},
    },
    "R&D_EXP": {
        "label": "研发费用",
        "section": "损益表",
        "ideal": "损益表「研发开支」行",
        "prefer_roles": ["appendix", "summary", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {27, 327, 428},
    },
    "SG&A": {
        "label": "销售及行政费用",
        "section": "损益表",
        "ideal": "损益表「销售及分销开支」「行政开支」",
        "prefer_roles": ["appendix", "summary", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {27, 327, 428},
    },
    "NET_LOSS": {
        "label": "期内利润/亏损",
        "section": "损益表",
        "ideal": "损益表「年度/期间内利润」及归母利润",
        "prefer_roles": ["appendix", "summary"],
        "prefer_cats": ["table", "text"],
        "gold_hint_pages": {27, 28, 327, 428},
    },
    "ADJ_NET": {
        "label": "经调整净利润",
        "section": "损益表",
        "ideal": "非IFRS/经调整利润调节表（注意勿与备考有形资产净值混淆）",
        "prefer_roles": ["discussion", "summary"],
        "prefer_cats": ["table", "text"],
        "gold_hint_pages": {35, 369},
    },
    # 2.2
    "TOTAL_ASSETS": {
        "label": "总资产",
        "section": "资产负债表",
        "ideal": "附录一财务状况表「总资产」；概要资产负债概要",
        "prefer_roles": ["appendix", "summary"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {28, 346, 430, 441},
    },
    "TOTAL_LIAB": {
        "label": "总负债",
        "section": "资产负债表",
        "ideal": "财务状况表「总负债」行",
        "prefer_roles": ["appendix", "summary"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {28, 346, 430},
    },
    "NET_ASSETS": {
        "label": "净资产",
        "section": "资产负债表",
        "ideal": "资产净值/权益总额",
        "prefer_roles": ["appendix", "summary"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {28, 346, 430, 441},
    },
    "CASH_EQ": {
        "label": "现金及现金等价物",
        "section": "资产负债表",
        "ideal": "财务状况表或现金流量表期末现金",
        "prefer_roles": ["appendix", "summary"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {28, 29, 346, 440, 441},
    },
    "CV_PREF": {
        "label": "可转换可赎回优先股",
        "section": "资产负债表",
        "ideal": "有则取财务状况表优先股负债行；无则应低置信/空（勿硬凑）",
        "prefer_roles": ["appendix", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": set(),
        "allow_empty": True,
    },
    "TRADE_REC": {
        "label": "贸易应收款",
        "section": "资产负债表",
        "ideal": "财务状况表/附注贸易应收款项",
        "prefer_roles": ["appendix", "discussion", "summary"],
        "prefer_cats": ["table", "text"],
        "gold_hint_pages": {28, 339, 341, 346, 480},
    },
    "TRADE_PAY": {
        "label": "贸易应付款",
        "section": "资产负债表",
        "ideal": "财务状况表/附注贸易应付款项",
        "prefer_roles": ["appendix", "discussion", "summary"],
        "prefer_cats": ["table", "text"],
        "gold_hint_pages": {28, 347, 353, 441},
    },
    # 2.3
    "CFO": {
        "label": "经营活动现金流净额",
        "section": "现金流量表",
        "ideal": "附录一现金流量表经营分部净额；概要现金流概要可校验",
        "prefer_roles": ["appendix", "summary"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {29, 360, 437, 438},
    },
    "CFI": {
        "label": "投资活动现金流净额",
        "section": "现金流量表",
        "ideal": "现金流量表投资活动净额",
        "prefer_roles": ["appendix", "summary", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {29, 360, 437},
    },
    "CFF": {
        "label": "融资活动现金流净额",
        "section": "现金流量表",
        "ideal": "现金流量表融资活动净额",
        "prefer_roles": ["appendix", "summary", "discussion"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {29, 360, 437},
    },
    "END_CASH": {
        "label": "年末现金余额",
        "section": "现金流量表",
        "ideal": "期末现金及现金等价物",
        "prefer_roles": ["appendix", "summary"],
        "prefer_cats": ["table"],
        "gold_hint_pages": {29, 360, 437, 440, 441},
    },
    # legal
    "REDEMPTION_CLAUSE": {
        "label": "对赌/赎回条款",
        "section": "隐性风险",
        "ideal": "历史/投资协议特殊权利及上市前终止披露",
        "prefer_roles": ["other", "discussion", "summary"],
        "prefer_cats": ["text"],
        "gold_hint_pages": {186},
    },
    "RELATED_PARTY": {
        "label": "关联交易",
        "section": "隐性风险",
        "ideal": "关连交易/控股股东章节，非仅释义表",
        "prefer_roles": ["other", "discussion", "summary"],
        "prefer_cats": ["text", "table"],
        "gold_hint_pages": {189, 312},
    },
    "CONCENTRATION": {
        "label": "客户/供应商集中度",
        "section": "隐性风险",
        "ideal": "前五大客户/供应商收入或采购占比",
        "prefer_roles": ["summary", "discussion", "other"],
        "prefer_cats": ["text", "table"],
        "gold_hint_pages": {20, 269, 273},
    },
    "CASH_BURN_PRESSURE": {
        "label": "现金流消耗压力",
        "section": "隐性风险",
        "ideal": "营运资金、用途、杠杆与现金消耗相关叙述/表",
        "prefer_roles": ["summary", "discussion", "appendix"],
        "prefer_cats": ["text", "table"],
        "gold_hint_pages": {29, 31, 36, 360},
    },
    "PRE_IPO_VALUATION": {
        "label": "Pre-IPO估值",
        "section": "隐性风险",
        "ideal": "投前/投后估值、融资轮次金额（勿与金融工具公允价值附注混淆）",
        "prefer_roles": ["other", "summary", "discussion"],
        "prefer_cats": ["text", "table"],
        "gold_hint_pages": {185, 35},
    },
}

ROLE_CN = {
    "appendix": "附录一（会计师报告，终值优先）",
    "summary": "概要（交叉校验）",
    "discussion": "财务资料讨论节",
    "other": "其他章节",
}

GRADE_CN = {
    "A": "优秀 — 已定位到可抽取的主表/关键披露",
    "B": "可用 — 方向正确，但仍需人工或二次过滤",
    "C": "偏弱 — 证据包不完整或易混淆",
    "D": "跑偏 — 错表/错章节，不建议直接抽取",
}


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    """兼容 ``--agent all`` 与 ``--agent finance|legal`` 两种 JSON 形态。

    - all: ``{doc_id, finance: {...}, legal: {...}, summary}``
    - 单 agent: 根上即 agent 块（含 ``agent`` / ``evidence_by_*``）
    """
    if "finance" in result or "legal" in result:
        out = dict(result)
        out.setdefault("finance", {})
        out.setdefault("legal", {})
        out.setdefault("doc_id", (out.get("finance") or out.get("legal") or {}).get("doc_id"))
        return out

    agent = str(result.get("agent") or "")
    if agent == "finance":
        return {
            "doc_id": result.get("doc_id"),
            "issuer_type": result.get("issuer_type"),
            "finance": result,
            "legal": {},
            "summary": {
                "finance_fields": result.get("field_count"),
                "finance_tables": result.get("table_count"),
                "finance_hits": result.get("total_unique_hits"),
                "note": "结果仅含 finance（simulate 时 --agent finance）",
            },
        }
    if agent == "legal":
        return {
            "doc_id": result.get("doc_id"),
            "issuer_type": result.get("issuer_type"),
            "finance": {},
            "legal": result,
            "summary": {
                "legal_fields": result.get("field_count"),
                "legal_hits": result.get("total_unique_hits"),
                "note": "结果仅含 legal（simulate 时 --agent legal）",
            },
        }
    # 未知形态：尽量当 finance 用
    if result.get("evidence_by_table") or result.get("evidence_by_field") or result.get("per_query"):
        return {
            "doc_id": result.get("doc_id"),
            "finance": result,
            "legal": {},
            "summary": {"note": "未识别 agent 字段，已按 finance 块解析"},
        }
    return {"doc_id": result.get("doc_id"), "finance": {}, "legal": {}, "summary": {}}


def _hits_for_field(agent_block: dict[str, Any], field_code: str) -> list[dict[str, Any]]:
    ebf = agent_block.get("evidence_by_field") or {}
    ebt = agent_block.get("evidence_by_table") or {}
    return list(ebt.get(field_code) or ebf.get(field_code) or [])


def _excerpt_one_line(text: str, n: int = 60) -> str:
    s = (text or "").replace("\n", " ").replace("|", "/")
    s = " ".join(s.split())
    return s[:n] + ("…" if len(s) > n else "")


def _cell_text(raw: str) -> str:
    """HTML 单元格 → 单行纯文本（供 Markdown 表）。"""
    s = raw or ""
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    s = re.sub(r"\s+", " ", s).strip()
    # Markdown 表单元格内竖线需转义
    return s.replace("|", "\\|")


def _parse_html_table_grid(table_html: str) -> list[list[str]]:
    """把含 rowspan/colspan 的 HTML table 展开为矩形网格。"""
    rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.I | re.S)
    # grid[r][c] = text；先占位 None 表示未填
    grid: list[list[str | None]] = []
    # 跨行占用：row_idx -> {col: (remaining_rows, text)}
    carry: dict[int, tuple[int, str]] = {}

    for row_html in rows_html:
        # 本行先消化上一行 rowspan 留下的列
        cells: list[str | None] = []
        col = 0

        def _ensure_col(c: int) -> None:
            while len(cells) <= c:
                cells.append(None)

        # 先填入仍在跨行中的单元格
        while True:
            if col in carry:
                rem, text = carry[col]
                _ensure_col(col)
                cells[col] = text
                if rem > 1:
                    carry[col] = (rem - 1, text)
                else:
                    del carry[col]
                col += 1
                continue
            break

        # 解析本行 td/th
        for m in re.finditer(
            r"<(td|th)([^>]*)>(.*?)</\1>", row_html, flags=re.I | re.S
        ):
            attrs, inner = m.group(2), m.group(3)
            rs_m = re.search(r"rowspan\s*=\s*[\"']?(\d+)", attrs, flags=re.I)
            cs_m = re.search(r"colspan\s*=\s*[\"']?(\d+)", attrs, flags=re.I)
            rowspan = int(rs_m.group(1)) if rs_m else 1
            colspan = int(cs_m.group(1)) if cs_m else 1
            text = _cell_text(inner)

            # 跳过已被 carry 占用的列
            while col in carry:
                rem, ctext = carry[col]
                _ensure_col(col)
                cells[col] = ctext
                if rem > 1:
                    carry[col] = (rem - 1, ctext)
                else:
                    del carry[col]
                col += 1

            for dc in range(colspan):
                c = col + dc
                _ensure_col(c)
                cells[c] = text
                if rowspan > 1 and dc == 0:
                    # 仅主格登记跨行；横向复制格不重复登记
                    carry[c] = (rowspan - 1, text)
                elif rowspan > 1:
                    carry[c] = (rowspan - 1, text)
            col += colspan

        # 行尾若还有未消化的 carry（后续列）
        while any(c >= col for c in list(carry.keys())):
            if col in carry:
                rem, text = carry[col]
                _ensure_col(col)
                cells[col] = text
                if rem > 1:
                    carry[col] = (rem - 1, text)
                else:
                    del carry[col]
            else:
                _ensure_col(col)
                cells[col] = cells[col] or ""
            col += 1
            if col > 64:
                break

        grid.append(cells)

    # 对齐列数
    width = max((len(r) for r in grid), default=0)
    out: list[list[str]] = []
    for r in grid:
        row = [(c if c is not None else "") for c in r]
        while len(row) < width:
            row.append("")
        out.append(row[:width])
    return out


def _grid_to_markdown(grid: list[list[str]]) -> str:
    if not grid:
        return ""
    width = max(len(r) for r in grid)
    if width == 0:
        return ""

    def _pad(row: list[str]) -> list[str]:
        r = list(row) + [""] * (width - len(row))
        return [c if c else " " for c in r[:width]]

    lines: list[str] = []
    header = _pad(grid[0])
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in grid[1:]:
        lines.append("| " + " | ".join(_pad(row)) + " |")
    return "\n".join(lines)


def _normalize_table_html(html: str) -> str:
    """清理 table HTML，便于 MD 预览器直接渲染。"""
    s = html or ""
    # 去掉可能破坏文档的脚本/样式
    s = re.sub(r"<script[^>]*>.*?</script>", "", s, flags=re.I | re.S)
    s = re.sub(r"<style[^>]*>.*?</style>", "", s, flags=re.I | re.S)
    # 统一标签小写无关；保留 rowspan/colspan
    return s.strip()


def format_evidence_body(text: str, *, limit: int = 0) -> tuple[str, str]:
    """把证据原文格式化为可渲染内容。

    Returns:
        (body, mode)  mode in {\"md_table\", \"html_table\", \"text\"}
        - md_table: 标准 Markdown 表（预览直接渲染）
        - html_table: 内嵌 HTML table（保留 rowspan/colspan，多数预览器可渲染）
        - text: 纯文本
    """
    raw = text or ""
    if limit and limit > 0 and len(raw) > limit:
        raw = raw[:limit] + "…"

    tables = re.findall(r"<table[^>]*>.*?</table>", raw, flags=re.I | re.S)
    if tables:
        md_parts: list[str] = []
        html_parts: list[str] = []
        ok_md = True
        # 若有非 table 前缀文本（跨页 pack 常见：上半 text + 下半 table），一并保留
        prefix = re.split(r"<table\b", raw, maxsplit=1, flags=re.I)[0].strip()
        if prefix and "<!-- page_break -->" not in prefix:
            # 单段内的前缀；跨页拆分由上层处理
            pass
        for t in tables:
            grid = _parse_html_table_grid(t)
            if not grid or not any(any(c.strip() for c in row) for row in grid):
                ok_md = False
            else:
                md_parts.append(_grid_to_markdown(grid))
            # 同时准备 HTML：外包一层横向滚动，宽表可读
            cleaned = _normalize_table_html(t)
            html_parts.append(
                '<div class="ipo-evidence-table" style="overflow-x:auto;margin:0.5em 0;">\n'
                f"{cleaned}\n"
                "</div>"
            )
        # MD 表：预览器直接渲染；附 HTML 折叠块保留 rowspan/colspan
        if md_parts and html_parts:
            body = (
                "\n\n".join(md_parts)
                + "\n\n<details>\n<summary>原始 HTML 表（可展开，支持合并单元格）</summary>\n\n"
                + "\n\n".join(html_parts)
                + "\n\n</details>"
            )
            return body, "md_table"
        if ok_md and md_parts:
            return "\n\n".join(md_parts), "md_table"
        if html_parts:
            return "\n\n".join(html_parts), "html_table"

    return raw.strip() or "（空）", "text"


def _split_pack_excerpt(
    excerpt: str, pack_pages: list[int] | None, seed_page: int | None
) -> list[tuple[int | None, str]]:
    """按 page_break 拆成 (page, part_text)；页码与 pack_pages 对齐。"""
    raw = excerpt or ""
    parts = [p.strip() for p in re.split(r"\n*\s*<!--\s*page_break\s*-->\s*\n*", raw) if p.strip()]
    if not parts:
        return [(seed_page, raw)]
    pages = list(pack_pages or [])
    out: list[tuple[int | None, str]] = []
    for i, part in enumerate(parts):
        pg: int | None
        if i < len(pages):
            pg = int(pages[i])
        elif seed_page is not None and len(parts) == 1:
            pg = int(seed_page)
        else:
            pg = None
        out.append((pg, part))
    return out


def _render_pack_parts(
    excerpt: str,
    *,
    pack_pages: list[int] | None,
    seed_page: int | None,
    excerpt_limit: int,
) -> list[str]:
    """跨页 pack：每段标注真实页码，text 与 table 都展示（避免只渲染 HTML 导致页码错觉）。"""
    lines: list[str] = []
    parts = _split_pack_excerpt(excerpt, pack_pages, seed_page)
    multi = len(parts) > 1
    for pi, (pg, part) in enumerate(parts, 1):
        body, mode = format_evidence_body(part, limit=excerpt_limit)
        # 纯 text 段里若不含 table，format 返回 text；若误含 table 仍按表渲染
        has_table = bool(re.search(r"<table\b", part, flags=re.I))
        if not has_table and mode in ("md_table", "html_table"):
            # 不应发生；兜底
            mode = "text"
            body = part if not excerpt_limit else part[:excerpt_limit]
        mode_cn = {
            "md_table": "Markdown 表",
            "html_table": "HTML 表",
            "text": "文本",
        }.get(mode, mode)
        pg_s = str(pg) if pg is not None else "?"
        if multi:
            lines.append(f"- **跨页片段 {pi}/{len(parts)} · 第 {pg_s} 页** · 格式：{mode_cn}")
        else:
            lines.append(f"- **第 {pg_s} 页** · 格式：{mode_cn}")
        lines.append("")
        if mode in ("md_table", "html_table"):
            lines.append(body)
        else:
            # text 表体（解析误标）完整展示
            lines.append("```")
            lines.append(body or "（空）")
            lines.append("```")
        lines.append("")
    return lines


def _format_excerpt(text: str, limit: int = 0) -> str:
    """兼容旧调用：返回纯文本/MD 字符串。"""
    body, _mode = format_evidence_body(text, limit=limit)
    if _mode == "html_table":
        # 旧路径若只要文本，再抽一层
        grid_bits = []
        for t in re.findall(r"<table[^>]*>.*?</table>", text or "", flags=re.I | re.S):
            g = _parse_html_table_grid(t)
            if g:
                grid_bits.append(_grid_to_markdown(g))
        if grid_bits:
            return "\n\n".join(grid_bits)
    return body


def _render_field_topk_block(
    row: dict[str, Any],
    *,
    excerpt_limit: int,
    include_baseline: bool = True,
) -> list[str]:
    """单个字段/表类型的完整 Top-K 明细（Markdown 行列表）。"""
    lines: list[str] = []
    w = lines.append
    hits = row.get("hits") or []
    unit = row.get("recall_unit") or "field"
    unit_cn = "整表召回" if unit == "table" else "字段召回"
    w(f"### {row['label']}（`{row['field_code']}`）— 评级 **{row['grade']}** · {unit_cn}")
    w("")
    w(f"- **所属**：{row['section']}")
    w(f"- **理想来源**：{row['ideal']}")
    if row.get("covers_fields"):
        w(f"- **覆盖指标**：`{'` · `'.join(row['covers_fields'])}`")
    w(f"- **评语**：{'; '.join(row['reasons']) or '—'}")
    if include_baseline and row.get("base_pages") is not None:
        w(
            f"- **改进前页码**：{row['base_pages']}（{row['base_grade']}）→ "
            f"**改进后**：{row['pages']}（{row['improved'] or '—'}）"
        )
    else:
        w(f"- **本轮 Top 页码**：{row['pages'] or '—'}")
    w(f"- **召回条数**：{len(hits)}")
    roles = row.get("roles") or []
    if roles:
        role_cn = [ROLE_CN.get(str(r), str(r)) for r in roles]
        w(f"- **章节角色分布**：{', '.join(role_cn)}")
    w("")
    if not hits:
        w("_无候选证据。_")
        w("")
        return lines

    w("| # | 页码 | pack页 | 类型 | 章节角色 | 分数 | 通道 | 停止原因 | 展开自 |")
    w("|---|------|--------|------|----------|------|------|----------|--------|")
    for i, h in enumerate(hits, 1):
        src = ",".join(h.get("match_sources") or []) or "—"
        role = h.get("table_role") or "—"
        role_cn = ROLE_CN.get(role, role)
        stop = h.get("stop_reason") or "—"
        exp = h.get("expanded_from") or "—"
        if isinstance(exp, str) and len(exp) > 24:
            exp = "…" + exp[-18:]
        score = h.get("score")
        score_s = f"{score:.4f}" if isinstance(score, (int, float)) else "—"
        pack = h.get("pack_pages") or []
        pack_s = ",".join(str(p) for p in pack) if pack else "—"
        w(
            f"| {i} | {h.get('page', '—')} | {pack_s} | `{h.get('category', '—')}` | "
            f"{_md_escape(str(role_cn))} | {score_s} | `{_md_escape(src)}` | "
            f"`{stop}` | `{_md_escape(str(exp))}` |"
        )
    w("")
    w("**各条原文摘录：**" + ("（整表完整展示；跨页按真实页码分段）" if unit == "table" else "（完整展示）"))
    w("")
    for i, h in enumerate(hits, 1):
        raw = h.get("excerpt") or ""
        mq = h.get("matched_queries") or []
        mq_s = ", ".join(str(x) for x in mq) if mq else "—"
        pack = h.get("pack_pages") or []
        pack_s = f" · pack={pack}" if pack else ""
        w(
            f"**[{i}]** 种子页 **{h.get('page')}**{pack_s} · `{h.get('category')}` · "
            f"{ROLE_CN.get(h.get('table_role') or '', h.get('table_role') or '—')} · "
            f"匹配：{mq_s}"
        )
        w("")
        lines.extend(
            _render_pack_parts(
                raw,
                pack_pages=[int(x) for x in pack] if pack else None,
                seed_page=int(h["page"]) if h.get("page") is not None else None,
                excerpt_limit=excerpt_limit,
            )
        )
    return lines


def grade_field(field_code: str, hits: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """启发式业务打分（偏保守，避免汇报过度乐观）。返回 (等级, 理由列表)。"""
    meta = TABLE_META.get(field_code) or FIELD_META.get(field_code, {})
    reasons: list[str] = []
    if not hits:
        if meta.get("allow_empty"):
            return "B", ["无命中；若发行人确无该科目，属合理空结果"]
        return "D", ["无候选证据"]

    roles = [h.get("table_role") or "other" for h in hits]
    cats = [h.get("category") or "" for h in hits]
    pages = [int(h.get("page") or 0) for h in hits]
    prefer_roles = set(meta.get("prefer_roles") or [])
    prefer_cats = set(meta.get("prefer_cats") or [])
    gold = set(meta.get("gold_hint_pages") or [])
    wants_appendix = "appendix" in prefer_roles
    is_table_unit = field_code in TABLE_META

    top = hits[0]
    top_role = top.get("table_role") or "other"
    top_cat = top.get("category") or ""
    top_ex = top.get("excerpt") or ""

    has_pref_role_table = any(
        (h.get("table_role") in prefer_roles) and (h.get("category") == "table") for h in hits
    )
    has_appendix_table = any(
        h.get("table_role") == "appendix" and h.get("category") == "table" for h in hits
    )
    has_appendix_statement = any(
        h.get("table_role") == "appendix"
        and h.get("category") in ("table", "text")
        and (
            h.get("category") == "table"
            or (h.get("pack_pages") and len(h.get("pack_pages") or []) >= 1)
            or (h.get("matched_row_labels") and len(h.get("matched_row_labels") or []) >= 2)
        )
        for h in hits
    )
    has_summary_table = any(
        h.get("table_role") == "summary" and h.get("category") == "table" for h in hits
    )
    gold_hit = bool(gold and set(pages) & gold)
    title_heavy = cats.count("title") >= 2 and cats.count("table") == 0
    all_bodies = bool(hits) and all(c in ("table", "text") for c in cats)
    all_tables = bool(hits) and all(c == "table" for c in cats)

    score = 0
    if is_table_unit:
        if all_tables or all_bodies:
            score += 4
            if all_tables:
                reasons.append("召回结果均为整表（table）")
            else:
                reasons.append("召回结果为整表体（table/text；解析侧可能把主表落成 text）")
        if has_appendix_table or has_appendix_statement:
            score += 4
            reasons.append("含附录一主表候选")
        if has_summary_table:
            score += 2
            reasons.append("含概要表可交叉校验")
        if gold_hit:
            score += 2
            reasons.append("命中已知金标页附近")
        pack_pages = top.get("pack_pages") or [top.get("page")]
        if top_cat == "text" and top_role == "appendix" and (top.get("matched_row_labels") or pack_pages):
            reasons.append("Top-1 为 text 表体（允许：解析未打 table 标签）")
        elif top_cat not in ("table", "text"):
            score -= 3
            reasons.append("Top-1 不是表体，整表召回不完整")
        if score >= 8:
            return "A", reasons
        if score >= 5:
            return "B", reasons
        if score >= 2:
            return "C", reasons
        return "D", reasons or ["整表召回质量不足"]

    # --- field-level grading (legacy / legal / 2.4) ---
    if top_cat in prefer_cats:
        score += 2
        reasons.append(f"Top-1 类型为「{top_cat}」")
    if top_role in prefer_roles:
        score += 2
        reasons.append(f"Top-1 落在「{ROLE_CN.get(top_role, top_role)}」")
    if has_appendix_table and wants_appendix:
        score += 3
        reasons.append("候选中含附录一表格（适合作为终值来源）")
    elif has_summary_table:
        score += 2
        reasons.append("候选中含概要表格（可交叉校验）")
    elif has_pref_role_table:
        score += 1
        reasons.append("候选中含目标章节表格")
    if gold_hit:
        score += 2
        reasons.append(f"命中参考页 {sorted(set(pages) & gold)}")

    # 扣分 / 封顶规则
    if title_heavy:
        score -= 2
        reasons.append("多为标题、缺表体，难以直接抽数")
    if top_cat == "title":
        score -= 1
        reasons.append("Top-1 仍是标题，抽取前需展开到表体")

    if wants_appendix and not has_appendix_table:
        score -= 2
        reasons.append("缺少附录一主表，终值可靠度不足")

    if field_code == "CV_PREF":
        if any("公允" in (h.get("excerpt") or "") for h in hits[:3]):
            score -= 3
            reasons.append("疑似打中公允价值计量附注，而非优先股科目")
        if not has_appendix_table and not any(
            "優先股" in (h.get("excerpt") or "") or "优先股" in (h.get("excerpt") or "")
            for h in hits
        ):
            reasons.append("未见明确优先股行；消费股常无此科目，建议标空/低置信")

    if field_code == "GP" and pages and pages[0] < 25 and top_role != "appendix":
        if not has_appendix_table:
            score -= 2
            reasons.append("Top 偏前部运营/渠道表，需确认是否为合并毛利")

    if field_code == "GP_MARGIN":
        if top_role in ("summary", "other") and pages and pages[0] < 40:
            score -= 1
            reasons.append("毛利率多为运营拆分披露，合并主表常无独立行")

    if field_code == "ADJ_NET" and any(
        "有形資產" in (h.get("excerpt") or "") or "有形资产" in (h.get("excerpt") or "")
        for h in hits[:2]
    ):
        score -= 3
        reasons.append("疑似与「备考有形资产净值」混淆")

    if field_code == "PRE_IPO_VALUATION" and top_role == "appendix":
        score -= 2
        reasons.append("Top 落在附录公允价值计量，可能偏离投后估值披露")

    if field_code in ("TRADE_REC", "TRADE_PAY", "NET_ASSETS", "TOTAL_LIAB"):
        # 附录附注宽表常见：有 table+appendix 但未必是财务状况表主行
        if has_appendix_table and not gold_hit and pages and min(pages[:2]) >= 470:
            score -= 2
            reasons.append("附录命中页偏后，可能是附注明细/宽表，需核对科目行")

    if field_code in ("CFI", "CFF") and not has_appendix_table:
        score -= 1
        reasons.append("投资/融资现金流未稳落到附录现金流量表")

    if meta.get("allow_empty") and (
        "公允" in top_ex or score < 5
    ):
        return "C", reasons or ["发行人可能无此科目；当前命中偏噪声，建议标低置信"]

    # A 档门槛：对需要附录终值的字段，必须有 appendix table
    grade: str
    if score >= 8 and (has_appendix_table or not wants_appendix):
        grade = "A"
    elif score >= 7 and has_appendix_table:
        grade = "A"
    elif score >= 4:
        grade = "B"
    elif score >= 2:
        grade = "C"
    else:
        grade = "D"

    # 额外封顶
    if field_code == "GP_MARGIN" and grade == "A":
        grade = "B"
        reasons.append("评级封顶为可用：毛利率口径需人工确认")
    if field_code in ("CFI", "CFF") and not has_appendix_table and grade == "A":
        grade = "B"
        reasons.append("评级封顶为可用：缺附录现金流量表")
    if field_code == "ADJ_NET" and grade == "A":
        grade = "B"

    return grade, reasons


def _baseline_hits(baseline: dict[str, Any], agent: str, field_code: str) -> dict[str, Any] | None:
    block = (baseline.get(agent) or {}).get(field_code)
    return block


def _grade_baseline_simple(field_code: str, block: dict[str, Any] | None) -> str:
    if not block:
        return "—"
    pages = block.get("pages") or []
    cats = block.get("cats") or []
    meta = FIELD_META.get(field_code, {})
    gold = set(meta.get("gold_hint_pages") or [])
    has_table = "table" in cats
    gold_hit = bool(gold and set(pages) & gold)
    top_cat = cats[0] if cats else ""
    if field_code == "REV" and pages and pages[0] >= 480:
        return "D"
    if field_code == "GP" and pages and pages[0] <= 20 and not gold_hit:
        return "C"
    if top_cat == "title" and not has_table:
        return "C"
    if gold_hit and has_table:
        return "B"
    if gold_hit or has_table:
        return "B"
    if has_table:
        return "C"
    return "C"


def analyze_agent(
    agent_key: str,
    agent_block: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ebf = agent_block.get("evidence_by_field") or {}
    ebt = agent_block.get("evidence_by_table") or {}
    per_query = {q["field_code"]: q for q in (agent_block.get("per_query") or []) if q.get("field_code")}
    # preserve per_query order when available
    order = [q["field_code"] for q in agent_block.get("per_query") or []]
    if not order:
        order = list(ebt.keys()) + [k for k in ebf.keys() if k not in ebt]

    for fc in order:
        hits = list(ebt.get(fc) or []) or _hits_for_field(agent_block, fc)
        pq = per_query.get(fc) or {}
        grade, reasons = grade_field(fc, hits)
        meta = (
            TABLE_META.get(fc)
            or FIELD_META.get(fc)
            or {
                "label": pq.get("label") or fc,
                "section": pq.get("section") or "—",
                "ideal": "—",
            }
        )
        covers = pq.get("covers_fields") or []
        pages = [h.get("page") for h in hits]
        roles = [h.get("table_role") or "—" for h in hits]
        cats = [h.get("category") or "—" for h in hits]
        sources = sorted({s for h in hits for s in (h.get("match_sources") or [])})
        top_ex = _excerpt_one_line(hits[0].get("excerpt") or "") if hits else ""

        # 表级召回：旧字段基线不可直接对照，跳过升降箭头
        base = _baseline_hits(baseline, agent_key, fc) if baseline else None
        is_table_unit = (pq.get("recall_unit") == "table") or (fc in TABLE_META)
        if is_table_unit:
            base_grade = "—"
            base_pages = None
            improved = ""
            if covers:
                reasons = list(reasons) + [f"覆盖字段：{', '.join(covers)}"]
        else:
            base_grade = _grade_baseline_simple(fc, base) if baseline else "—"
            base_pages = (base or {}).get("pages") if base else None
            improved = ""
            if baseline and base_grade != "—":
                order_g = {"A": 4, "B": 3, "C": 2, "D": 1, "—": 0}
                if order_g.get(grade, 0) > order_g.get(base_grade, 0):
                    improved = "↑ 提升"
                elif order_g.get(grade, 0) < order_g.get(base_grade, 0):
                    improved = "↓ 回退"
                else:
                    improved = "→ 持平"

        rows.append(
            {
                "field_code": fc,
                "label": meta.get("label", fc),
                "section": meta.get("section", "—"),
                "ideal": meta.get("ideal", "—"),
                "grade": grade,
                "reasons": reasons,
                "pages": pages,
                "roles": roles,
                "cats": cats,
                "sources": sources,
                "top_excerpt": top_ex,
                "base_grade": base_grade,
                "base_pages": base_pages,
                "improved": improved,
                "hits": hits,
                "recall_unit": pq.get("recall_unit") or ("table" if fc in TABLE_META else "field"),
                "covers_fields": covers,
            }
        )
    return rows


def _grade_bar(counter: Counter) -> str:
    """简易文本条形图。"""
    total = sum(counter.values()) or 1
    parts = []
    for g in ("A", "B", "C", "D"):
        n = counter.get(g, 0)
        bar = "█" * n + "░" * max(0, 5 - n)
        pct = 100.0 * n / total
        parts.append(f"| {g} | {n} | {bar} | {pct:.0f}% | {GRADE_CN[g].split('—')[0].strip()} |")
    return "\n".join(parts)


def _md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|")


def build_report(
    result: dict[str, Any],
    *,
    doc_name: str,
    baseline: dict[str, Any] | None,
    result_path: Path,
    excerpt_limit: int = 0,
    detail_topk: bool = True,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    result = normalize_result(result)
    fin = result.get("finance") or {}
    leg = result.get("legal") or {}
    summary = result.get("summary") or {}

    fin_rows = analyze_agent("finance", fin, baseline) if fin else []
    leg_rows = analyze_agent("legal", leg, baseline) if leg else []

    fin_grades = Counter(r["grade"] for r in fin_rows)
    leg_grades = Counter(r["grade"] for r in leg_rows)

    page_roles = fin.get("page_roles") or leg.get("page_roles") or {}
    fusion = fin.get("fusion") or leg.get("fusion") or {}
    field_table_map = fin.get("field_table_map") or {}

    table_rows = [r for r in fin_rows if r.get("recall_unit") == "table"]
    field_fin_rows = [r for r in fin_rows if r.get("recall_unit") != "table"]
    weak_fin = [r for r in fin_rows if r["grade"] in ("C", "D")]
    watch_fin = [r for r in fin_rows if r["grade"] in ("B", "C", "D")]
    improved = [r for r in fin_rows if r["improved"] == "↑ 提升"]

    lines: list[str] = []
    w = lines.append

    w(f"# 港股IPO招股书检索效果汇报 — {doc_name}")
    w("")
    w(f"> 生成时间：{now}  \\")
    w(f"> 样本：`{doc_name}`（doc_id=`{result.get('doc_id', '')}`）  \\")
    w(f"> 结果文件：`{result_path}`  \\")
    w("> 读者对象：金融分析 / 风控 / 投行研究同事（非算法细节）")
    if summary.get("note"):
        w(f"> 说明：{summary['note']}")
    w("")
    w("---")
    w("")
    w("## 1. 一句话结论")
    w("")
    n_a = fin_grades.get("A", 0)
    n_b = fin_grades.get("B", 0)
    n_cd = fin_grades.get("C", 0) + fin_grades.get("D", 0)
    n_fin = len(fin_rows) or 1

    if not fin_rows and not leg_rows:
        w(
            "**未能从结果 JSON 解析出任何财务/法务召回项。** "
            "请确认已运行 `simulate_agent_retrieval.py`，且报告脚本能识别 "
            "`--agent all` 或 `--agent finance` 两种输出结构。"
        )
    elif table_rows:
        w(
            f"在 **{doc_name}** 招股书上，财务侧 **2.1/2.2/2.3 按三张主表整表召回**，"
            f"共评估 **{len(table_rows)}** 类表"
            + (f"（另含字段级 **{len(field_fin_rows)}** 项）" if field_fin_rows else "")
            + f"：**优秀 {n_a} / 可用 {n_b} / 偏弱或跑偏 {n_cd}**"
            f"（优秀+可用合计 **{(n_a + n_b) / n_fin:.0%}**）。"
        )
        w("")
        # 一句话点名每张表 Top 页
        bits = []
        for r in table_rows:
            top = r["pages"][0] if r["pages"] else "—"
            bits.append(f"**{r['label']}** Top1=p{top}（{r['grade']}）")
        w("本轮：" + "；".join(bits) + "。")
        w("")
        w(
            "策略：指标（REV/CFO 等）不再单独 Top-K；财务主表仅取附录一整表包"
            "（核心行名门控 + 跨页合并），抽数交给下游。"
        )
    else:
        w(
            f"在 **{doc_name}** 招股书上，财务指标共评估 **{len(fin_rows)}** 项："
            f"**优秀 {n_a} / 可用 {n_b} / 偏弱或跑偏 {n_cd}**"
            f"（优秀+可用合计 **{(n_a + n_b) / n_fin:.0%}**）。"
        )
    w("")
    w("---")
    w("")
    w("## 2. 我们在找什么？（业务视角）")
    w("")
    if table_rows:
        w(
            "检索目标不是「问答摘要」，而是：**为损益表 / 财务状况表 / 现金流量表 "
            "各召回 Top-K 张完整表格**，供下游从整表抽取 2.1–2.3 全部指标。"
        )
    else:
        w(
            "检索目标不是「问答摘要」，而是：**为每个财务/风险字段，"
            "找到能支撑后续抽取与核验的原文证据**。"
        )
    w("")
    w("| 证据层级 | 含义 | 抽取时怎么用 |")
    w("|----------|------|--------------|")
    w("| **附录一** | 会计师报告中的完整财务报表 | **终值优先**（签字审计口径） |")
    w("| **概要** | 招股书前部「历史财务资料概要」 | **交叉校验**（摘录自附录，较简） |")
    w("| **财务资料讨论** | MD&A 中的科目讨论与局部表 | 解释变动原因；数值弱于附录 |")
    w("| **其他** | 业务/风险/释义等 | 法务与定性风险为主 |")
    w("")
    if page_roles:
        w("本样本自动识别的章节页段：")
        w("")
        w(f"- 附录一：{page_roles.get('appendix_range')}")
        w(f"- 财务资料讨论：{page_roles.get('discussion_range')}")
        w(f"- 概要相关页数：{page_roles.get('summary_page_count')}")
        w("")
    w("当前检索链路：")
    w("")
    w(f"> {fusion.get('strategy', 'Grep ∪ BM25 ∪ 向量 → Top-K')}")
    w("")
    if field_table_map:
        w("字段 → 所属主表（`field_table_map`）：")
        w("")
        # 按表聚合展示
        by_tbl: dict[str, list[str]] = {}
        for fc, tc in field_table_map.items():
            by_tbl.setdefault(tc, []).append(fc)
        for tc, fcs in by_tbl.items():
            w(f"- `{tc}` ← {', '.join(f'`{x}`' for x in fcs)}")
        w("")
    w("---")
    w("")
    w("## 3. 财务检索总览")
    w("")
    if not fin_rows:
        w("_本次结果无财务召回项（可能只跑了 legal，或 JSON 未解析成功）。_")
        w("")
    else:
        w("### 3.1 质量分布")
        w("")
        w("| 等级 | 项数 | 分布 | 占比 | 含义 |")
        w("|------|------|------|------|------|")
        w(_grade_bar(fin_grades))
        w("")
        w("### 3.2 三类主表摘要" if table_rows else "### 3.2 关键指标摘要")
        w("")
        showcase = (
            ["TBL_IS", "TBL_BS", "TBL_CF"]
            if table_rows
            else ["REV", "GP", "CFO"]
        )
        shown = 0
        for fc in showcase:
            row = next((x for x in fin_rows if x["field_code"] == fc), None)
            if not row:
                continue
            shown += 1
            w(f"#### {row['label']}（`{fc}`）— **{row['grade']}**")
            w("")
            w(f"- **理想来源**：{row['ideal']}")
            if row.get("covers_fields"):
                w(f"- **覆盖指标**：{', '.join(f'`{x}`' for x in row['covers_fields'])}")
            if row["base_pages"] is not None:
                w(
                    f"- **改进前 Top 页**：{row['base_pages']} → 评级 **{row['base_grade']}**"
                )
            w(f"- **本轮 Top 页**：{row['pages']}")
            roles_cn = [
                ROLE_CN.get(str(r), str(r)) for r in (row.get("roles") or [])
            ]
            if roles_cn:
                w(f"- **角色**：{', '.join(roles_cn)}")
            w(f"- **为何这样评**：{'; '.join(row['reasons']) or '—'}")
            w(
                f"- **完整 Top-K** → [明细](#{row['field_code'].lower().replace('&', '')})"
            )
            w("")
        if shown == 0:
            w("_无摘要项（showcase 字段在结果中不存在）。_")
            w("")
            # 退而展示全部 fin_rows 一行摘要表
            w("| 代码 | 中文 | 评级 | Top 页码 |")
            w("|------|------|------|----------|")
            for r in fin_rows:
                pages_s = ",".join(str(p) for p in r["pages"][:5]) if r["pages"] else "—"
                w(
                    f"| `{r['field_code']}` | {r['label']} | **{r['grade']}** | {pages_s} |"
                )
            w("")

    if detail_topk and fin_rows:
        w("---")
        w("")
        sec4_title = (
            "分表类型 Top-K 证据明细（财务）"
            if table_rows
            else "分字段 Top-K 证据明细（财务）"
        )
        w(f"## 4. {sec4_title}")
        w("")
        unit_desc = "表类型" if table_rows else "字段"
        if excerpt_limit and excerpt_limit > 0:
            len_note = f"单条摘录上限 **{excerpt_limit}** 字（超出截断）。"
        else:
            len_note = (
                "**完整展示全部召回表格**："
                "HTML 已转为可渲染的 Markdown 表（并附原始 HTML 折叠块）。"
            )
        w(
            f"> 以下按{unit_desc}列出本轮召回的 **全部 Top-K**（共 **{len(fin_rows)}** 项）。"
            f"{len_note}"
        )
        w("")
        w("| 代码 | 中文 | 单元 | 评级 | Top 页码 | 跳转 |")
        w("|------|------|------|------|----------|------|")
        for r in fin_rows:
            pages_s = ",".join(str(p) for p in r["pages"]) if r["pages"] else "—"
            anchor = r["field_code"].lower().replace("&", "")
            unit = "整表" if r.get("recall_unit") == "table" else "字段"
            w(
                f"| `{r['field_code']}` | {r['label']} | {unit} | **{r['grade']}** | "
                f"{pages_s} | [明细](#{anchor}) |"
            )
        w("")
        for r in fin_rows:
            w(f'<a id="{r["field_code"].lower().replace("&", "")}"></a>')
            w("")
            lines.extend(
                _render_field_topk_block(
                    r, excerpt_limit=excerpt_limit, include_baseline=bool(baseline)
                )
            )

    if detail_topk:
        w("---")
        w("")
        w("## 5. 分字段 Top-K 证据明细（法务/隐性风险）")
        w("")
        if not leg_rows:
            w(
                "_本次结果无法务召回项。若需法务明细，请用 "
                "`--agent all` 或 `--agent legal` 重跑模拟检索。_"
            )
            w("")
        else:
            w("| 字段 | 中文 | 评级 | Top 页码 | 跳转 |")
            w("|------|------|------|----------|------|")
            for r in leg_rows:
                pages_s = ",".join(str(p) for p in r["pages"]) if r["pages"] else "—"
                anchor = r["field_code"].lower().replace("&", "")
                w(
                    f"| `{r['field_code']}` | {r['label']} | **{r['grade']}** | "
                    f"{pages_s} | [明细](#{anchor}) |"
                )
            w("")
            for r in leg_rows:
                w(f'<a id="{r["field_code"].lower().replace("&", "")}"></a>')
                w("")
                lines.extend(
                    _render_field_topk_block(
                        r,
                        excerpt_limit=excerpt_limit,
                        include_baseline=bool(baseline),
                    )
                )

    w("---")
    w("")
    w("## 6. 问题与观察（业务影响）")
    w("")
    if watch_fin:
        w("### 6.1 需人工复核 / 尚未达「可自动填数」")
        w("")
        w("| 项 | 等级 | 现象 | 若直接用会怎样 |")
        w("|----|------|------|----------------|")
        impact_map = {
            "TBL_IS": "Top 中可能混入渠道/附注表，抽数前需确认是否为合并损益表",
            "TBL_BS": "易混附注宽表（如权益/公允披露）；终值应优先附录财务状况表",
            "TBL_CF": "讨论节现金流表与附录主表需区分；终值优先附录",
            "GP_MARGIN": "可能抽到渠道/单店毛利率，与合并口径不一致",
            "ADJ_NET": "可能把备考净值当成经调整净利润（且常不在损益主表）",
            "CV_PREF": "可能把公允价值附注当成优先股（或发行人根本无此科目）",
            "CFI": "可能只有讨论/概要表，缺附录现金流量表终值",
            "CFF": "同上，融资现金流终值不稳",
            "TRADE_REC": "可能打中附注宽表，需核对是否为贸易应收科目行",
            "TRADE_PAY": "同上",
            "NET_ASSETS": "可能打中权益变动表而非财务状况表净值",
            "TOTAL_LIAB": "附录后部宽表需核对是否为负债合计行",
            "END_CASH": "需区分状况表现金行与现金流量表期末余额",
        }
        for r in watch_fin:
            impact = impact_map.get(
                r["field_code"],
                "证据需人工确认后再入报告，暂不建议全自动填数",
            )
            phen = "；".join(r["reasons"][:2]) or f"页码 {r['pages']}"
            w(
                f"| {r['label']} | **{r['grade']}** | {_md_escape(phen)} | "
                f"{_md_escape(impact)} |"
            )
        w("")
    elif fin_rows:
        w("财务侧本轮无 C/D 档；仍建议对附录附注宽表做抽数前校验。")
        w("")
    else:
        w("_无财务观察项。_")
        w("")

    w("### 6.2 共性问题")
    w("")
    if table_rows:
        w("1. **同名不同表**：表名线索（如「财务状况」）会打中附注宽表，需主表白名单降噪。")
        w("2. **概要 vs 附录**：概要表好读但简化；附录表完整——终值优先附录，概要交叉校验。")
        w("3. **跨页续表**：损益/现金流主表可能跨页，Top-K 中相邻页常为续表。")
        w("4. **非主表指标**：如 ADJ_NET（非IFRS）未必落在损益主表，需单独规则或允许空。")
    else:
        w("1. **同名不同表**：例如「收入」「毛利」既出现在合并损益表，也出现在渠道拆分表。")
        w("2. **概要 vs 附录**：概要表好读但简化；附录表完整但附注噪声多。")
        w("3. **行名相近**：如「确认为收入的政府补助」≠「营业收入」。")
        w("4. **无此科目**：消费股通常无优先股，应允许空结果。")
    w("")

    w("---")
    w("")
    w("## 7. 法务/隐性风险总览")
    w("")
    if not leg_rows:
        w("_无法务结果。_")
        w("")
    else:
        w("| 等级 | 字段数 | 分布 | 占比 | 含义 |")
        w("|------|--------|------|------|------|")
        w(_grade_bar(leg_grades))
        w("")
        w("| 风险点 | 字段 | 改进前 | 改进后 | Top 页 |")
        w("|--------|------|--------|--------|--------|")
        for r in leg_rows:
            pages_s = ",".join(str(p) for p in r["pages"][:4]) if r["pages"] else "—"
            w(
                f"| {_md_escape(r['label'])} | `{r['field_code']}` | "
                f"**{r['base_grade']}** | **{r['grade']}** | {pages_s} |"
            )
        w("")

    skipped = (fin.get("skipped_fields") or []) + (leg.get("skipped_fields") or [])
    if skipped:
        w("### 发行人门控（已跳过）")
        w("")
        w("本样本按 **非生物科技** 处理，以下 18A/管线类字段未检索：")
        w("")
        for s in skipped:
            w(f"- `{s.get('field_code')}`（{s.get('section')}）— {s.get('reason')}")
        w("")

    w("---")
    w("")
    w("## 8. 改进方向（按优先级）")
    w("")
    w("| 优先级 | 方向 | 解决什么问题 | 预期业务收益 |")
    w("|--------|------|--------------|--------------|")
    w(
        "| P0 | **主表白名单**（表名/title 同页共现） | "
        "附注宽表、渠道表抢分 | 终值更稳 |"
    )
    w(
        "| P0 | **抽取层读 `evidence_by_table`** | "
        "整表已召回但未抽数 | 字段落库 |"
    )
    w(
        "| P1 | **无科目 / 非主表指标低置信**（CV_PREF、ADJ_NET） | "
        "硬凑噪声 | 避免虚假风险 |"
    )
    w(
        "| P2 | **小样本人工标注集**（10–20 家 × 主表页码） | "
        "凭感觉迭代 | 可量化召回率 |"
    )
    w("")

    w("---")
    w("")
    w("## 9. 附录：理想来源速查")
    w("")
    w("| 代码 | 中文 | 理想证据 |")
    w("|------|------|----------|")
    for r in fin_rows + leg_rows:
        ideal = r.get("ideal") or "—"
        if r.get("covers_fields") and not ideal.endswith("）"):
            # keep ideal; covers already in detail
            pass
        w(f"| `{r['field_code']}` | {r['label']} | {_md_escape(ideal)} |")
    if not fin_rows and not leg_rows:
        for fc, meta in {**TABLE_META, **{k: v for k, v in FIELD_META.items() if k in ("REDEMPTION_CLAUSE",)}}.items():
            w(f"| `{fc}` | {meta.get('label', fc)} | {_md_escape(meta.get('ideal', '—'))} |")
    w("")
    w("---")
    w("")
    w("## 10. 统计摘要（给内部存档）")
    w("")
    w("```json")
    w(
        json.dumps(
            {
                "doc_name": doc_name,
                "doc_id": result.get("doc_id"),
                "finance_grade_counts": dict(fin_grades),
                "legal_grade_counts": dict(leg_grades),
                "finance_table_codes": [r["field_code"] for r in table_rows],
                "finance_A": [r["field_code"] for r in fin_rows if r["grade"] == "A"],
                "finance_weak": [
                    r["field_code"] for r in fin_rows if r["grade"] in ("C", "D")
                ],
                "improved_fields": [r["field_code"] for r in improved],
                "field_table_map": field_table_map,
                "top_pages": {
                    r["field_code"]: r["pages"] for r in fin_rows + leg_rows
                },
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    w("```")
    w("")
    w(
        "*本报告由 `scripts/analyze_retrieval_report.py` 自动生成；"
        "等级为启发式业务评估，最终以人工抽数复核为准。"
        "第 4–5 节含全部 Top-K 原文摘录。*"
    )
    w("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成检索质量 Markdown 汇报")
    parser.add_argument(
        "--result",
        type=Path,
        default=Path(".runtime/agent_retrieval_mixue.json"),
        help="simulate_agent_retrieval.py 输出的 JSON",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("configs/retrieval_eval_baseline_mixue_v0.json"),
        help="改进前快照 JSON（可选；不存在则跳过对比列）",
    )
    parser.add_argument("--doc-name", default="蜜雪冰城（mixue）")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".runtime/reports/retrieval_quality_mixue.md"),
    )
    parser.add_argument(
        "--excerpt-chars",
        type=int,
        default=0,
        help="每条摘录最大字符数；0=完整展示不截断（默认）",
    )
    parser.add_argument(
        "--no-detail-topk",
        action="store_true",
        help="不展开分字段 Top-K 明细（仅总览表）",
    )
    args = parser.parse_args()

    result_path = args.result
    if not result_path.is_file():
        # try relative to agents/ipo
        pkg = Path(__file__).resolve().parent.parent
        cand = pkg / result_path
        if cand.is_file():
            result_path = cand
        else:
            raise SystemExit(f"结果文件不存在: {args.result}")

    baseline = None
    baseline_path = args.baseline
    if not baseline_path.is_file():
        pkg = Path(__file__).resolve().parent.parent
        cand = pkg / baseline_path
        if cand.is_file():
            baseline_path = cand
    if baseline_path.is_file():
        baseline = _load_json(baseline_path)

    result = _load_json(result_path)
    md = build_report(
        result,
        doc_name=args.doc_name,
        baseline=baseline,
        result_path=result_path,
        excerpt_limit=args.excerpt_chars,
        detail_topk=not args.no_detail_topk,
    )

    out = args.out
    if not out.is_absolute():
        out = Path(__file__).resolve().parent.parent / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
