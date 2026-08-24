"""将完整 ReportData 渲染为适合决策阅读的 PDF。"""

from __future__ import annotations

from datetime import datetime
import html
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any, Iterable

_FONT_CANDIDATES = [
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

_NAVY = (25, 45, 72)
_BLUE = (52, 104, 164)
_GOLD = (196, 145, 52)
_ORANGE = (207, 111, 45)
_PINK = (166, 76, 105)
_INK = (37, 48, 61)
_MUTED = (98, 111, 126)
_PALE = (242, 245, 248)
_LINE = (216, 223, 231)
_WHITE = (255, 255, 255)

_WINDOW_CN = {
    "D1": "上市首日",
    "D5": "上市后5个交易日",
    "D20": "上市后20个交易日",
    "D60": "上市后60个交易日",
}

_HISTORICAL_FIELD_CN = {
    "HIST-HSI-RET-5D": "恒生指数5日走势",
    "HIST-HSI-RET-20D": "恒生指数20日走势",
    "HIST-HSI-RET-60D": "恒生指数60日走势",
    "HIST-HSTECH-RET-5D": "恒生科技指数5日走势",
    "HIST-HSTECH-RET-20D": "恒生科技指数20日走势",
    "HIST-MKT-TURNOVER-CHG-20D": "全市场成交额20日变化",
    "HIST-SOUTHBOUND-NET-20D": "南向资金20日净流入",
    "HIST-VHSI-AVG-5D": "香港恒生波动率指数5日均值",
    "HIST-HSI-VOL-20D": "恒生指数20日实现波动率",
    "HIST-DXY-RET-20D": "美元指数20日走势",
    "HIST-US10Y-CHG-20D": "美国10年期国债收益率20日变化",
    "HIST-DFF-CHG-30CD": "美国联邦基金利率30日变化",
    "HIST-IND-RET-20D": "行业20日收益",
    "HIST-IND-EXCESS-20D": "行业相对恒生指数20日超额收益",
    "HIST-IND-AMOUNT-CHG-20D": "行业成交额20日变化",
    "HIST-IND-NEWHIGH-RATIO": "行业创新高比例",
    "HIST-IND-NET-INFLOW-20D": "行业20日资金净流入",
    "HIST-IND-AVG-DAY1-RETURN-365D": "行业新股首日平均收益",
    "HIST-IND-BREAK-RATE-365D": "行业新股破发率",
    "HIST-IPO-COUNT-30D": "近30日新股数量",
    "HIST-IPO-COUNT-90D": "近90日新股数量",
    "HIST-AVG-DAY1-RETURN-60D": "近期新股首日平均收益",
    "HIST-AVG-DAY5-RETURN-60D": "近期新股5日平均收益",
    "HIST-AVG-DAY20-RETURN-60D": "近期新股20日平均收益",
    "HIST-BREAK-RATE-60D": "近期新股破发率",
    "HIST-AVG-MDD20-60D": "近期新股20日平均最大回撤",
    "HIST-SUBSCRIPTION-MULTIPLE": "整体超额认购倍数",
    "HIST-PUBLIC-OFFER-MULTIPLE": "公开发售认购倍数",
    "HIST-INTERNATIONAL-PLACING-MULTIPLE": "国际配售认购倍数",
    "OPINION-STATUS": "舆情数据可用状态",
}


def _markdown_section(markdown: Any, *titles: str) -> str:
    """Extract one final-report section while preserving its paragraph content."""
    source = str(markdown or "")
    wanted = {_plain_text(title).replace(" ", "") for title in titles}
    lines = source.splitlines()
    start = -1
    level = 0
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        heading = _plain_text(match.group(2)).replace(" ", "")
        if any(title in heading for title in wanted):
            start = index + 1
            level = len(match.group(1))
            break
    if start < 0:
        return ""
    selected: list[str] = []
    for line in lines[start:]:
        match = re.match(r"^\s*(#{1,6})\s+", line)
        if match and len(match.group(1)) <= level:
            break
        selected.append(line)
    return _plain_text("\n".join(selected))


def _executive_conclusion(report: dict[str, Any]) -> str:
    conclusion = _markdown_section(report.get("masterReportMarkdown"), "总控结论", "终裁理由", "最终结论")
    master = report.get("masterConclusion") if isinstance(report.get("masterConclusion"), dict) else {}
    conclusion = conclusion or _plain_text(master.get("verdictReasoning") or report.get("executiveSummary"))
    return re.sub(
        r"三位专家的对照加权分为[^。；]*分[；;][^。]*。",
        "",
        conclusion,
    ).strip()


def _validation_narrative(validation: dict[str, Any]) -> str:
    """Turn structured post-listing validation fields into reader-facing prose."""
    checkpoints = [item for item in (validation.get("checkpoints") or []) if isinstance(item, dict)]
    windows = [_text(item.get("window")) for item in checkpoints if item.get("window")]
    parts: list[str] = []
    if windows:
        window_text = windows[0] if len(windows) == 1 else "、".join(windows[:-1]) + "和" + windows[-1]
        parts.append(f"本次上市后验证覆盖{window_text}，共{len(windows)}个检查点")
    score = validation.get("weightedHitScore")
    if score is not None:
        parts.append(f"整体加权命中分为{_number(score)}分")
    overview = "，".join(parts) + "。" if parts else ""

    d5 = next((item for item in checkpoints if str(item.get("window") or "").upper() == "D5"), None)
    if d5:
        alignment = {
            "hit": "预测与实际表现一致",
            "aligned": "预测与实际表现一致",
            "partial": "预测与实际表现部分一致",
            "miss": "预测与实际表现存在明显偏离",
        }.get(str(d5.get("alignment") or "").lower(), "预测与实际表现暂无法判断")
        priority = validation.get("d5PriorityHit")
        priority_text = "重点预警命中" if priority is True else "重点预警未命中" if priority is False else "重点预警结果暂不可用"
        overview += f"其中，上市后5个交易日的{alignment}，{priority_text}。"
    return overview or _text(validation.get("summary"))


def _score_color(score: Any, maximum: float = 10.0) -> tuple[int, int, int]:
    try:
        ratio = float(score) / maximum
    except (TypeError, ValueError, ZeroDivisionError):
        return _MUTED
    if ratio >= 0.8:
        return _PINK
    if ratio >= 0.6:
        return _ORANGE
    if ratio >= 0.3:
        return _GOLD
    return _BLUE


def _expert_score(markdown: str) -> float | None:
    patterns = (
        r"本\s*Agent\s*风险分[：:]\s*`?([0-9]+(?:\.[0-9]+)?)",
        r"最终首日破发风险分[：:]\s*\**([0-9]+(?:\.[0-9]+)?)",
        r"风险分[：:]\s*`?([0-9]+(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, markdown, flags=re.I)
        if match:
            return float(match.group(1))
    return None


def _expert_breakdown(markdown: str) -> list[dict[str, Any]]:
    """Extract score-contribution rows from an expert report for a visual overview."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in markdown.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0] or set(cells[0]) <= {"-", ":"}:
            continue
        match = re.fullmatch(r"\**`?\+?([0-9]+(?:\.[0-9]+)?)`?\**", cells[1])
        if not match:
            continue
        name = _plain_text(cells[0])
        value = float(match.group(1))
        if name and name not in seen and 0 < value <= 100:
            seen.add(name)
            items.append({"name": name, "score": value})
        if len(items) >= 8:
            break
    return items


def _find_cjk_font() -> str | None:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


class _ReadableHTMLParser(HTMLParser):
    _BLOCK_TAGS = {"p", "div", "section", "article", "li", "br", "tr", "table", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._cell_index = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self.parts.append("\n")
            self._cell_index = 0
        elif tag in {"td", "th"}:
            if self._cell_index:
                self.parts.append(" ｜ ")
            self._cell_index += 1
        elif tag == "li":
            self.parts.append("\n— ")
        elif tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: Any) -> str:
    raw = html.unescape(str(value or ""))
    protected_paths: dict[str, str] = {}

    def protect_path(match: re.Match[str]) -> str:
        key = f"§路径{len(protected_paths)}§"
        protected_paths[key] = match.group(0)
        return key

    raw = re.sub(r"(?:(?:[A-Za-z]:)?/)?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_./-]+", protect_path, raw)
    if "<" in raw and ">" in raw:
        parser = _ReadableHTMLParser()
        try:
            parser.feed(raw)
            raw = "".join(parser.parts)
        except Exception:
            raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", raw)
    raw = raw.replace("**", "").replace("__", "").replace("`", "")
    raw = raw.replace("•", "—").replace("−", "-")
    raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
    raw = re.sub(r" *\n *", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    try:
        from zhconv import convert

        raw = str(convert(raw, "zh-cn"))
    except Exception:
        pass
    replacements = {
        "TBL_BS_COMPANY": "公司资产负债表",
        "TBL_IS": "合并损益表",
        "TBL_BS": "合并资产负债表",
        "TBL_CF": "合并现金流量表",
        "CV_PREF": "可转换可赎回优先股",
        "NET_LOSS": "期内亏损或利润",
        "CFO": "经营活动现金流净额",
        "CFI": "投资活动现金流净额",
        "CFF": "融资活动现金流净额",
        "CASH_EQ": "现金及现金等价物",
        "TOTAL_ASSETS": "总资产",
        "TOTAL_LIAB": "总负债",
        "NET_ASSETS": "净资产",
        "REDEMPTION_HIGH": "对赌或赎回条款高风险",
        "REDEMPTION_MEDIUM": "对赌或赎回条款中等风险",
        "CASH_RUNWAY_12_24": "现金跑道为12至24个月",
        "CASH_RUNWAY_LT_12": "现金跑道不足12个月",
        "BURN_YOY_UP_30": "现金消耗同比上升超过30%",
        "EMBELLISHMENT_HIGH": "文本粉饰度高风险",
        "exists": "存在状态",
        "skipped": "跳过状态",
        "True": "是",
        "False": "否",
        "None": "无",
        "not_available": "暂无数据",
        "completed": "已完成",
        "verified": "已核验",
        "partial": "部分一致",
        "aligned": "一致",
        "alignment": "对齐程度",
        "risk_factors": "风险因子汇总",
        "risk_score": "风险分",
        "summary": "摘要汇总",
        "weighted_hit_score": "加权命中分",
        "business_value_score": "业务价值分",
        "rules_floor": "规则托底分",
        "deterministic_score": "历史校准分",
        "llm_score": "模型判断分",
        "evidence_gap": "证据缺口",
        "resonance": "风险共振",
        "other": "其他议题",
        "market_data": "市场数据",
        "calibration_statistics": "历史校准统计",
        "news_evidence": "新闻证据",
        "market_field": "市场字段",
        "evidence_id": "证据编号",
        "as_of_date": "数据截止日",
        "field_code": "字段代码",
        "field": "字段",
        "value": "数值",
        "source_type": "证据来源类型",
        "page_excerpt": "招股书页码与原文",
        "financial_table": "财务表格",
        "contract_clause": "合同条款",
        "business_context": "业务背景",
        "keyword": "关键词检索",
        "VHSI": "香港恒生波动率指数",
        "hsi_ret_5d": "恒生指数5日走势",
        "hsi_ret_20d": "恒生指数20日走势",
        "hsi_ret_60d": "恒生指数60日走势",
        "hstech_ret_5d": "恒生科技指数5日走势",
        "hstech_ret_20d": "恒生科技指数20日走势",
        "mkt_turnover_chg_20d": "全市场成交额20日变化",
        "southbound_net_20d": "南向资金20日净流入",
        "vhsi_avg_5d": "香港恒生波动率指数5日均值",
        "dxy_ret_20d": "美元指数20日走势",
        "us10y_chg_20d": "美国10年期国债收益率20日变化",
        "dff_chg_30cd": "美国联邦基金利率30日变化",
        "ind_ret_20d": "行业20日收益",
        "ind_excess_20d": "行业相对恒生指数20日超额收益",
        "ind_amount_chg_20d": "行业成交额20日变化",
        "ind_newhigh_ratio": "行业创新高比例",
        "ind_net_inflow_20d": "行业20日资金净流入",
        "ind_avg_day1_return_365d": "行业新股首日平均收益",
        "ind_break_rate_365d": "行业新股破发率",
        "ipo_count_30d": "近30日新股数量",
        "ipo_count_90d": "近90日新股数量",
        "avg_day1_return_60d": "近期新股首日平均收益",
        "avg_day5_return_60d": "近期新股5日平均收益",
        "avg_day20_return_60d": "近期新股20日平均收益",
        "break_rate_60d": "近期新股破发率",
        "avg_mdd20_60d": "近期新股20日平均最大回撤",
        "subscription_multiple": "整体超额认购倍数",
        "public_offer_multiple": "公开发售认购倍数",
        "international_placing_multiple": "国际配售认购倍数",
        "FRANCHISE_DEPENDENCY": "加盟体系依赖风险",
        "partially_accepted": "部分接受",
        "market_react+historical_rules_floor": "市场智能体研判加历史规则托底",
        "max_llm_and_rules_floor": "模型判断分与规则托底分取较高值",
        "final_score": "最终分",
        "score_reconciliation": "评分校准",
        "overall_net_support": "综合净支持率",
        "macro": "宏观模块",
        "industry": "行业模块",
        "ipo_market": "新股市场模块",
        "public_opinion": "公众舆情模块",
        "percentile": "历史百分位",
        "risk_direction": "风险方向",
        "configured_weight": "配置权重",
        "effective_weight": "有效权重",
        "historical-v1": "历史校准第一版",
        "MarketAgent": "市场智能体",
        "市场Agent": "市场智能体",
        "FinanceAgent": "财务智能体",
        "财务Agent": "财务智能体",
        "LegalAgent": "法务智能体",
        "法务Agent": "法务智能体",
        "CONCENTRATION_HIGH": "单一客户或供应商集中度高风险",
        "CONCENTRATION_TOP5": "前五大客户或供应商集中度风险",
        "VALUATION_INVERSION": "首次公开发售估值倒挂风险",
        "EMBELLISHMENT_HIGH": "文本粉饰度高风险",
    }
    for source, target in sorted(_HISTORICAL_FIELD_CN.items(), key=lambda item: len(item[0]), reverse=True):
        raw = raw.replace(source, target)
    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        raw = raw.replace(source, target)
    tool_translations = {
        "submit_finance_report": "提交财务报告",
        "submit_legal_report": "提交法务报告",
        "submit_market_report": "提交市场报告",
        "retrieve_finance": "检索财务证据",
        "extract_metrics": "抽取财务指标",
        "derive_gates": "判断财务门控",
        "calc_cash_runway": "测算现金跑道",
        "run_finance_skill": "执行财务专项分析",
        "run_finance_rule_checks": "执行财务规则校验",
        "search_finance_evidence": "补充检索财务证据",
        "retrieve_legal": "检索法务证据",
        "run_legal_skill": "执行法务专项分析",
        "run_legal_rule_checks": "执行法务规则校验",
        "run_rule_checks": "执行规则校验",
        "search_legal_evidence": "补充检索法务证据",
    }
    for source, target in sorted(tool_translations.items(), key=lambda item: len(item[0]), reverse=True):
        raw = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(source)}(?![A-Za-z0-9_]|\s+{re.escape(target)})",
            f"{source} {target}",
            raw,
        )
    for source, target in _WINDOW_CN.items():
        raw = re.sub(rf"(?<![A-Za-z0-9]){source}(?![A-Za-z0-9])", target, raw)
    raw = re.sub(r"MARKET-SCORE-(\d+)", r"市场评分证据\1", raw)
    raw = re.sub(r"MACRO-HSI-(\d+)D", r"恒生指数\1日市场证据", raw)
    raw = re.sub(r"MACRO-HSTECH-(\d+)D", r"恒生科技指数\1日市场证据", raw)
    raw = re.sub(r"MACRO-VHSI-(\d+)D", r"香港恒生波动率指数\1日市场证据", raw)
    raw = re.sub(r"MACRO-香港恒生波动率指数-(\d+)D", r"香港恒生波动率指数\1日市场证据", raw)
    agent_names = {"financial": "财务智能体", "finance": "财务智能体", "legal": "法务智能体", "market": "市场智能体", "orchestrator": "总控智能体"}
    for source, target in agent_names.items():
        raw = re.sub(rf"(?<![A-Za-z0-9_]){source}(?![A-Za-z0-9_])", target, raw, flags=re.I)
    raw = re.sub(r"(?<![A-Za-z])medium(?![A-Za-z])", "中等风险", raw, flags=re.I)
    raw = re.sub(r"(?<![A-Za-z])high(?![A-Za-z])", "高风险", raw, flags=re.I)
    raw = re.sub(r"(?<![A-Za-z])low(?![A-Za-z])", "低风险", raw, flags=re.I)
    raw = re.sub(r"(?<![A-Za-z])Agent(?![A-Za-z])", "智能体", raw, flags=re.I)

    for key, path in protected_paths.items():
        raw = raw.replace(key, path)

    def break_token(match: re.Match[str]) -> str:
        token = match.group(0)
        token = re.sub(r"([/_:.-])", r"\1 ", token)
        if " " not in token and len(token) > 20:
            token = " ".join(token[i : i + 16] for i in range(0, len(token), 16))
        return token

    return re.sub(r"[A-Za-z0-9_./:-]{22,}", break_token, raw)


def _text(value: Any, fallback: str = "—") -> str:
    if value is None:
        return fallback
    value = _plain_text(value)
    return value or fallback


def _stock_code(value: Any) -> str:
    raw = str(value or "")
    match = re.search(r"(?<!\d)(\d{1,5})(?:\.HK)?(?!\d)", raw, flags=re.I)
    return match.group(1).zfill(5) if match else _text(value, "未提供")


def _display_datetime(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        return _text(raw)


def _number(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.2f}%"
    except (TypeError, ValueError):
        return "—"


def _confidence_cn(value: Any) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(str(value or "").lower(), _text(value))


def _yes_no(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "—"


def _risk_cn(value: Any) -> str:
    return {
        "high": "高风险",
        "medium": "中风险",
        "low": "低风险",
        "benign": "温和",
        "severe": "严重",
        "partial": "部分一致",
        "aligned": "一致",
        "miss": "未命中",
        "verified": "已核验",
    }.get(str(value or "").lower(), _text(value))


class _ReportPDF:
    """Small fpdf2 façade with consistent typography, pagination and charts."""

    def __init__(self, font_path: str | None):
        from fpdf import FPDF

        class Document(FPDF):
            def header(inner):
                if inner.page_no() <= 1:
                    return
                inner.set_draw_color(*_LINE)
                inner.set_text_color(*_MUTED)
                inner.set_font(inner.report_font, size=8)
                half = (inner.w - inner.l_margin - inner.r_margin) / 2
                inner.cell(half, 5, "IPO风险穿透预警报告", align="L")
                inner.cell(half, 5, f"第 {inner.page_no()} 页", align="R", new_x="LMARGIN", new_y="NEXT")
                inner.line(inner.l_margin, 14, inner.w - inner.r_margin, 14)
                inner.ln(3)

            def footer(inner):
                inner.set_y(-10)
                inner.set_text_color(*_MUTED)
                inner.set_font(inner.report_font, size=7)
                inner.cell(0, 5, "本报告基于自动化风险分析结果，仅供研究与风险识别，不构成投资建议。", align="C")

        self.pdf = Document(format="A4")
        self.pdf.set_margins(16, 16, 16)
        self.pdf.set_auto_page_break(auto=True, margin=16)
        if font_path:
            self.pdf.add_font("cjk", fname=font_path)
            self.pdf.add_font("cjk", style="B", fname=font_path)
            self.font = "cjk"
        else:
            self.font = "Helvetica"
        self.pdf.report_font = self.font
        self.links: dict[str, int] = {}
        self.section_pages: dict[str, int] = {}

    def link(self, anchor: str) -> int:
        if anchor not in self.links:
            self.links[anchor] = self.pdf.add_link()
        return self.links[anchor]

    @property
    def content_width(self) -> float:
        return self.pdf.w - self.pdf.l_margin - self.pdf.r_margin

    def add_page(self) -> None:
        self.pdf.add_page()

    def ensure(self, height: float) -> None:
        if self.pdf.get_y() + height > self.pdf.h - self.pdf.b_margin:
            self.add_page()

    def section(self, number: str, title: str, note: str = "", *, anchor: str | None = None) -> None:
        self.ensure(24)
        self.pdf.ln(4)
        if anchor:
            self.pdf.set_link(self.link(anchor), y=self.pdf.get_y(), page=self.pdf.page_no())
            self.section_pages[anchor] = self.pdf.page_no()
        self.pdf.set_fill_color(*_NAVY)
        self.pdf.set_text_color(*_WHITE)
        self.pdf.set_font(self.font, "B", 12)
        self.pdf.cell(13, 9, number, fill=True, align="C")
        self.pdf.set_text_color(*_INK)
        self.pdf.cell(self.content_width - 13, 9, f"  {title}", new_x="LMARGIN", new_y="NEXT")
        if note:
            self.pdf.set_text_color(*_MUTED)
            self.pdf.set_font(self.font, size=8)
            self.pdf.multi_cell(0, 4.5, _text(note))
        self.pdf.ln(2)

    def flow_text(self, content: Any, *, width: float, line: float, x_offset: float = 0) -> None:
        from fpdf.enums import MethodReturnValue

        value = _text(content)
        lines = self.pdf.multi_cell(
            width,
            line,
            value,
            dry_run=True,
            output=MethodReturnValue.LINES,
        )
        for rendered_line in lines:
            self.ensure(line + 0.5)
            self.pdf.set_x(self.pdf.l_margin + x_offset)
            self.pdf.multi_cell(
                width,
                line,
                rendered_line,
                new_x="LMARGIN",
                new_y="NEXT",
            )

    def subheading(self, title: str) -> None:
        self.ensure(12)
        self.pdf.set_x(self.pdf.l_margin)
        self.pdf.set_text_color(*_NAVY)
        self.pdf.set_font(self.font, "B", 10)
        self.pdf.multi_cell(0, 6, _text(title))
        self.pdf.ln(1)

    def paragraph(self, content: Any, *, color: tuple[int, int, int] = _INK, size: float = 9, line: float = 5.2) -> None:
        value = _text(content)
        self.pdf.set_x(self.pdf.l_margin)
        self.pdf.set_text_color(*color)
        self.pdf.set_font(self.font, size=size)
        self.flow_text(value, width=self.content_width, line=line)
        self.pdf.ln(1)

    def bullet(self, content: Any, *, indent: float = 4, color: tuple[int, int, int] = _INK) -> None:
        self.pdf.set_x(self.pdf.l_margin + indent)
        self.pdf.set_text_color(*color)
        self.pdf.set_font(self.font, size=8.5)
        self.flow_text(f"— {_text(content)}", width=self.content_width - indent, line=4.8, x_offset=indent)

    def callout(self, title: str, content: Any, *, accent: tuple[int, int, int] = _BLUE) -> None:
        self.ensure(25)
        x, y = self.pdf.get_x(), self.pdf.get_y()
        self.pdf.set_fill_color(*_PALE)
        self.pdf.set_draw_color(*_LINE)
        self.pdf.rect(x, y, self.content_width, 2.5, style="F")
        self.pdf.set_y(y + 5)
        self.pdf.set_x(x + 4)
        self.pdf.set_text_color(*accent)
        self.pdf.set_font(self.font, "B", 9)
        self.pdf.cell(self.content_width - 8, 5, _text(title), new_x="LMARGIN", new_y="NEXT")
        self.pdf.set_x(x + 4)
        self.pdf.set_text_color(*_INK)
        self.pdf.set_font(self.font, size=8.5)
        self.flow_text(content, width=self.content_width - 8, line=4.8, x_offset=4)
        self.pdf.set_x(self.pdf.l_margin)
        self.pdf.ln(3)

    def key_values(self, rows: Iterable[tuple[str, Any]], *, columns: int = 2) -> None:
        rows = list(rows)
        cell_w = self.content_width / columns
        for start in range(0, len(rows), columns):
            chunk = rows[start : start + columns]
            self.ensure(15)
            y = self.pdf.get_y()
            for col, (label, value) in enumerate(chunk):
                x = self.pdf.l_margin + col * cell_w
                self.pdf.set_fill_color(*_PALE)
                self.pdf.set_draw_color(*_LINE)
                self.pdf.rect(x, y, cell_w - 2, 13, style="DF")
                self.pdf.set_xy(x + 3, y + 2)
                self.pdf.set_text_color(*_MUTED)
                self.pdf.set_font(self.font, "B", 7)
                self.pdf.cell(cell_w - 8, 4, _text(label))
                self.pdf.set_xy(x + 3, y + 6)
                self.pdf.set_text_color(*_INK)
                self.pdf.set_font(self.font, "B", 9)
                self.pdf.cell(cell_w - 8, 5, _text(value))
            self.pdf.set_y(y + 16)

    def score_bars(self, dimensions: list[dict[str, Any]], *, label_width: float | None = None) -> None:
        from fpdf.enums import MethodReturnValue

        palette = [_BLUE, _GOLD, _ORANGE, _PINK]
        for index, item in enumerate(dimensions):
            if not isinstance(item, dict):
                continue
            is_embellishment = item.get("id") == "embellishment"
            maximum = 10.0 if is_embellishment else 100.0
            try:
                score = max(0.0, min(maximum, float(item.get("score") or 0)))
            except (TypeError, ValueError):
                score = 0.0
            label = _text(item.get("name"))
            self.pdf.set_font(self.font, size=7.5)
            # A fixed label column keeps every bar on the same vertical axis.
            # Long risk names wrap inside the column instead of pushing the bar right.
            default_label_w = min(58.0, self.content_width * 0.34)
            label_w = max(24.0, min(float(label_width), default_label_w)) if label_width is not None else default_label_w
            score_w = 19.0
            gap = 2.0 if label_width is not None else 3.0
            bar_w = self.content_width - label_w - score_w - gap * 2
            line_h = 4.0
            label_lines = self.pdf.multi_cell(
                label_w,
                line_h,
                label,
                dry_run=True,
                output=MethodReturnValue.LINES,
            )
            label_h = max(line_h, len(label_lines) * line_h)
            row_h = max(8.0, label_h + 2.0)
            self.ensure(row_h + 2)
            y = self.pdf.get_y()
            center_y = y + row_h / 2
            self.pdf.set_text_color(*_INK)
            self.pdf.set_font(self.font, size=7.5)
            self.pdf.set_xy(self.pdf.l_margin, center_y - label_h / 2)
            self.pdf.multi_cell(label_w, line_h, label)
            bar_x = self.pdf.l_margin + label_w + gap
            bar_y = center_y - 2.0
            self.pdf.set_fill_color(231, 235, 240)
            self.pdf.rect(bar_x, bar_y, bar_w, 4, style="F")
            self.pdf.set_fill_color(*palette[index % len(palette)])
            self.pdf.rect(bar_x, bar_y, bar_w * score / maximum, 4, style="F")
            self.pdf.set_xy(bar_x + bar_w + gap, center_y - 2.5)
            suffix = "/10" if is_embellishment else "/100"
            self.pdf.set_font(self.font, "B", 8)
            self.pdf.cell(score_w, 5, f"{score:g}{suffix}", align="R")
            self.pdf.set_y(y + row_h + 1)
        self.pdf.ln(2)

    def signed_bars(self, checkpoints: list[dict[str, Any]]) -> None:
        """Discrete checkpoint comparison; four anchors do not justify a trend line."""
        values: list[tuple[str, float, float]] = []
        for item in checkpoints:
            try:
                ret = float(item.get("issuePriceReturn")) * 100
            except (TypeError, ValueError):
                ret = 0.0
            try:
                drawdown = float(item.get("maxDrawdownFromOpen")) * 100
            except (TypeError, ValueError):
                drawdown = 0.0
            values.append((_text(item.get("window")), ret, drawdown))
        if not values:
            self.paragraph("尚无可绘制的上市后验证数据。", color=_MUTED)
            return
        extent = max(10.0, max(abs(value) for _, ret, dd in values for value in (ret, dd)))
        half = (self.content_width - 36) / 2
        center = self.pdf.l_margin + 31 + half
        self.pdf.set_text_color(*_MUTED)
        self.pdf.set_font(self.font, size=7)
        self.pdf.cell(31, 5, "检查点")
        self.pdf.cell(half, 5, "负向 / 最大回撤", align="R")
        self.pdf.cell(half, 5, "发行价收益 / 正向", align="L", new_x="LMARGIN", new_y="NEXT")
        for window, ret, drawdown in values:
            self.ensure(14)
            y = self.pdf.get_y()
            self.pdf.set_draw_color(*_LINE)
            self.pdf.line(center, y, center, y + 9)
            self.pdf.set_text_color(*_INK)
            self.pdf.set_font(self.font, "B", 8)
            self.pdf.set_xy(self.pdf.l_margin, y + 1)
            self.pdf.cell(28, 5, window)
            if drawdown < 0:
                width = half * min(abs(drawdown) / extent, 1)
                self.pdf.set_fill_color(*_ORANGE)
                self.pdf.rect(center - width, y + 1, width, 3, style="F")
            if ret >= 0:
                width = half * min(ret / extent, 1)
                self.pdf.set_fill_color(*_BLUE)
                self.pdf.rect(center, y + 5, width, 3, style="F")
            else:
                width = half * min(abs(ret) / extent, 1)
                self.pdf.set_fill_color(*_GOLD)
                self.pdf.rect(center - width, y + 5, width, 3, style="F")
            self.pdf.set_text_color(*_MUTED)
            self.pdf.set_font(self.font, size=6.5)
            self.pdf.set_xy(self.pdf.l_margin + 8, y + 7)
            self.pdf.cell(50, 4, f"回撤 {drawdown:+.2f}%")
            self.pdf.set_xy(center + 2, y + 7)
            self.pdf.cell(50, 4, f"发行价收益 {ret:+.2f}%")
            self.pdf.set_y(y + 13)
        self.pdf.ln(2)


def _render_cover(doc: _ReportPDF, report: dict[str, Any], ticker: str, company_name: str) -> None:
    pdf = doc.pdf
    doc.add_page()
    pdf.set_fill_color(*_NAVY)
    pdf.rect(0, 0, pdf.w, 67, style="F")
    pdf.set_xy(16, 17)
    pdf.set_text_color(*_WHITE)
    pdf.set_font(doc.font, "B", 22)
    pdf.multi_cell(0, 12, "IPO风险穿透预警报告")
    pdf.set_x(pdf.l_margin)
    pdf.set_font(doc.font, size=12)
    pdf.cell(0, 7, f"公司名称：{_text(company_name, '未提供')}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(doc.font, size=10)
    pdf.cell(0, 7, f"股票代码：{_stock_code(ticker)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(77)
    score = report.get("overallScore")
    master = report.get("masterConclusion") if isinstance(report.get("masterConclusion"), dict) else {}
    doc.key_values(
        [
            ("综合风险评分", f"{_number(score)}/100"),
            ("风险等级", _text(report.get("riskLabel") or _risk_cn(report.get("riskLevel")))),
            ("终裁置信度", _confidence_cn(master.get("confidence"))),
            ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ]
    )
    pdf.set_link(doc.link("summary"), y=pdf.get_y(), page=pdf.page_no())
    doc.section_pages["summary"] = pdf.page_no()
    doc.subheading("执行摘要")
    conclusion_color = _score_color(report.get("overallScore"), 100)
    doc.callout("总控最终判断", _executive_conclusion(report), accent=conclusion_color)
    if master.get("scoreExplanation"):
        doc.subheading("评分与等级依据")
        doc.paragraph(master.get("scoreExplanation"))
    factors = [item for item in (report.get("riskFactors") or []) if isinstance(item, dict)]
    if factors:
        doc.subheading("需优先关注的风险")
        for index, factor in enumerate(factors[:3], 1):
            title = _text(factor.get("title"), "未命名风险")
            reason = _text(factor.get("reason"))
            doc.callout(f"{index}. {title}", reason or "总控未提供补充说明。", accent=_ORANGE)
    forecasts = [item for item in (report.get("pricePathForecast") or []) if isinstance(item, dict)]
    validation = report.get("postListingValidation") if isinstance(report.get("postListingValidation"), dict) else {}
    outlook = []
    for item in forecasts:
        window = _text(item.get("window"))
        direction = _text(item.get("expectedDirection"))
        if window and direction:
            outlook.append(f"{window}：{direction}")
    validation_summary = _validation_narrative(validation)
    if outlook or validation_summary:
        doc.subheading("上市后行情判断与验证")
        if outlook:
            for item in outlook:
                doc.bullet(item, indent=6)
        if validation_summary:
            doc.paragraph(validation_summary, color=_MUTED, size=8)
    if report.get("degraded"):
        doc.callout("降级提示", (report.get("masterConclusion") or {}).get("degradedReason") or "本次结果带有降级标记，需谨慎解释。", accent=_ORANGE)
    if report.get("gateWarning"):
        doc.callout("门控提示", report.get("gateWarning"), accent=_ORANGE)


def _render_master(doc: _ReportPDF, report: dict[str, Any]) -> None:
    master = report.get("masterConclusion") if isinstance(report.get("masterConclusion"), dict) else {}
    doc.section("01", "总控终裁", "总控评分是正式结论；参考基本面分仅作为对照，不替代终裁。", anchor="master")
    debate = report.get("debate") if isinstance(report.get("debate"), dict) else {}
    rounds = int(debate.get("rounds") or len(debate.get("history") or []))
    debate_status = f"已开展（{rounds}轮）" if rounds else "未触发"
    doc.key_values(
        [
            ("正式评分", f"{_number(master.get('overallScore', report.get('overallScore')))}/100"),
            ("风险等级", _text(master.get("riskLabel") or report.get("riskLabel"))),
            ("终裁置信度", _confidence_cn(master.get("confidence"))),
            ("辩论状态", debate_status),
        ]
    )
    doc.subheading("终裁理由")
    doc.paragraph(master.get("verdictReasoning") or report.get("executiveSummary"))
    if master.get("scoreExplanation"):
        doc.subheading("评分解释")
        doc.paragraph(master.get("scoreExplanation"))
    gates = master.get("triggeredGates") or []
    doc.subheading("触发门控")
    if gates:
        for gate in gates:
            doc.bullet(gate)
    else:
        doc.paragraph("未记录触发门控。", color=_MUTED)


def _render_dimensions(doc: _ReportPDF, report: dict[str, Any]) -> None:
    doc.section("02", "风险维度与评分分布", "横向条形图用于比较类别强弱；文本粉饰维度采用 0–10 分，其余维度采用 0–100 分。", anchor="dimensions")
    dimensions = [item for item in (report.get("dimensions") or []) if isinstance(item, dict)]
    doc.score_bars(dimensions, label_width=30.0)
    doc.paragraph("分数越高表示风险越高。各分项是总控判断的证据输入，不应被机械相加解释为正式综合分。", color=_MUTED, size=8)


def _render_risk_factors(doc: _ReportPDF, report: dict[str, Any]) -> None:
    doc.section("03", "核心风险因子与证据", "逐项给出来源智能体、判断理由及可用的原文页码/片段。", anchor="risk_factors")
    factors = [item for item in (report.get("riskFactors") or []) if isinstance(item, dict)]
    if not factors:
        doc.paragraph("总控结果未提供结构化风险因子。", color=_MUTED)
        return
    for index, factor in enumerate(factors, 1):
        doc.subheading(f"{index}. {_text(factor.get('title'), '未命名风险')}")
        doc.key_values([("来源智能体", factor.get("sourceAgent"))], columns=1)
        doc.paragraph(factor.get("reason"))
        evidence = [item for item in (factor.get("evidence") or []) if isinstance(item, dict)]
        if evidence:
            for item in evidence:
                page = item.get("page")
                prefix = f"原文 p.{page}" if page is not None else "结构化证据"
                doc.callout(prefix, item.get("excerpt"), accent=_GOLD)
        elif factor.get("evidenceExcerpt"):
            page = factor.get("evidencePage")
            doc.callout(f"原文 p.{page}" if page is not None else "结构化证据", factor.get("evidenceExcerpt"), accent=_GOLD)


def _render_debate(doc: _ReportPDF, report: dict[str, Any], *, section_no: str = "04") -> None:
    debate = report.get("debate") if isinstance(report.get("debate"), dict) else {}
    history = [item for item in (debate.get("history") or []) if isinstance(item, dict)]
    doc.section(section_no, "多智能体辩论与结论收束", "完整保留逐轮问题、专家回复、修订理由与剩余不确定性；未开辩时明确标记。", anchor="debate")
    doc.key_values([("辩论轮数", debate.get("rounds") or len(history)), ("完成时间", _display_datetime(debate.get("completedAt")))])
    conflicts = [item for item in (debate.get("conflicts") or []) if isinstance(item, dict)]
    if conflicts:
        doc.subheading("开辩前识别的冲突")
        for index, item in enumerate(conflicts, 1):
            kind = _text(item.get("kind") or item.get("theme") or "待核议题")
            priority = {"high": "高", "medium": "中", "low": "低"}.get(str(item.get("priority") or "").lower(), _text(item.get("priority")))
            agents = "、".join(_text(agent) for agent in (item.get("source_agents") or []))
            title = f"冲突 {index} · {kind} · {priority}优先级"
            body = _text(item.get("description") or item.get("reason"))
            if agents:
                body = f"涉及智能体：{agents}\n{body}"
            doc.callout(title, body, accent=_ORANGE)
    if not history:
        doc.paragraph("本次总控未触发实质辩论，专家结论直接进入终裁。", color=_MUTED)
        return
    for round_item in history:
        round_no = round_item.get("round") or "—"
        doc.subheading(f"第 {round_no} 轮")
        questions = [item for item in (round_item.get("questions") or []) if isinstance(item, dict)]
        replies = [item for item in (round_item.get("replies") or []) if isinstance(item, dict)]
        replies_by_id = {item.get("question_id"): item for item in replies}
        for index, question in enumerate(questions, 1):
            qid = question.get("question_id")
            target = question.get("target_agent") or "expert"
            doc.callout(f"问题 {index} · {target} · {_text(question.get('priority'))}", question.get("question"), accent=_BLUE)
            required = question.get("required_evidence_types") or []
            if required:
                doc.bullet("要求证据类型：" + "、".join(map(str, required)), color=_MUTED)
            reply = replies_by_id.get(qid)
            if not reply:
                doc.bullet("未收到对应回复。", color=_ORANGE)
                continue
            doc.callout(
                f"专家回复 · {_risk_cn(reply.get('status'))} · 置信度 {_number(reply.get('confidence'), 2)}",
                reply.get("reply"),
                accent=_GOLD,
            )
            if reply.get("revision_reason"):
                doc.bullet("修订理由：" + _text(reply.get("revision_reason")))
            if reply.get("remaining_uncertainty"):
                doc.bullet("剩余不确定性：" + _text(reply.get("remaining_uncertainty")), color=_ORANGE)
            for evidence in [item for item in (reply.get("evidence") or []) if isinstance(item, dict)]:
                page = evidence.get("page")
                label = f"补充证据 p.{page}" if page is not None else "补充结构化证据"
                doc.callout(label, evidence.get("excerpt"), accent=_GOLD)
        if round_item.get("continue_reason"):
            doc.paragraph("本轮收束：" + _text(round_item.get("continue_reason")), color=_MUTED, size=8)


def _render_embellishment(doc: _ReportPDF, report: dict[str, Any], section_no: str) -> None:
    data = report.get("embellishmentAnalysis")
    if not isinstance(data, dict):
        return
    doc.section(section_no, "文本粉饰度专项分析", "本章节仅在启用粉饰分析时出现；评分为 0–10 分，高分表示更强的粉饰风险信号。", anchor="embellishment")
    coverage = data.get("coverage") if isinstance(data.get("coverage"), dict) else {}
    doc.key_values(
        [
            ("粉饰评分", f"{_number(data.get('score'))}/10"),
            ("等级 / 状态", f"{_risk_cn(data.get('level'))} / {_text(data.get('status'))}"),
            ("扫描页数", len(coverage.get("pagesAnalyzed") or [])),
            ("候选复核", f"{coverage.get('evaluatedCandidateCount') or 0}/{coverage.get('candidateCount') or 0}"),
        ]
    )
    doc.paragraph(data.get("summary"))
    dimensions = [item for item in (data.get("dimensions") or []) if isinstance(item, dict)]
    if dimensions:
        doc.subheading("五维评分与发现")
        doc.score_bars([{**item, "id": "embellishment"} for item in dimensions])
        for item in dimensions:
            color = _score_color(item.get("score"), 10)
            doc.callout(f"{_text(item.get('name'))} · {_number(item.get('score'))}/10", item.get("finding"), accent=color)
    excerpts = [item for item in (data.get("highRiskExcerpts") or []) if isinstance(item, dict)]
    doc.subheading(f"高风险原文切片（共 {len(excerpts)} 条）")
    if not excerpts:
        doc.paragraph("没有通过原文回查且达到门槛的高风险切片。", color=_MUTED)
    for index, item in enumerate(excerpts, 1):
        page = item.get("page")
        title = f"{index}. p.{page if page is not None else '—'} · {_text(item.get('section'))} · {_text(item.get('tactic'))}"
        content = f"原文：{_text(item.get('excerpt'))}\n判定：{_text(item.get('reason'))}\n证据状态：{_text(item.get('supportStatus'))}；计分贡献：+{item.get('scoreContribution') or 0}"
        doc.callout(title, content, accent=_PINK)
    for limitation in data.get("limitations") or []:
        doc.bullet("分析限制：" + _text(limitation), color=_ORANGE)


def _render_forecast(doc: _ReportPDF, report: dict[str, Any], section_no: str) -> None:
    doc.section(section_no, "上市后行情预测", "D1/D5/D20/D60 是离散决策检查点；逐窗展示方向、形态、波动、驱动与置信度。", anchor="forecast")
    forecasts = [item for item in (report.get("pricePathForecast") or []) if isinstance(item, dict)]
    if not forecasts:
        doc.paragraph("未生成结构化行情预测。", color=_MUTED)
        return
    for item in forecasts:
        doc.subheading(f"{_text(item.get('window'))} · {_risk_cn(item.get('riskLabel'))} · 置信度 {_confidence_cn(item.get('confidence'))}")
        doc.callout("预期方向", item.get("expectedDirection"), accent=_BLUE)
        doc.paragraph("走势形态：" + _text(item.get("expectedPattern")))
        doc.paragraph("波动判断：" + _text(item.get("volatilityView")))
        drivers = item.get("keyDrivers") or []
        if drivers:
            for driver in drivers:
                doc.bullet(driver)


def _render_validation(doc: _ReportPDF, report: dict[str, Any], section_no: str) -> None:
    validation = report.get("postListingValidation") if isinstance(report.get("postListingValidation"), dict) else {}
    doc.section(section_no, "上市后行情验证", "离散检查点对照预测与真实表现；图中蓝色表示相对发行价收益，橙色表示从开盘计算的最大回撤。", anchor="validation")
    doc.key_values(
        [
            ("验证状态", validation.get("status")),
            ("加权命中分", _number(validation.get("weightedHitScore"))),
            ("业务价值分", _number(validation.get("businessValueScore"))),
            ("D5 重点预警命中", _yes_no(validation.get("d5PriorityHit"))),
        ]
    )
    doc.paragraph(_validation_narrative(validation))
    checkpoints = [item for item in (validation.get("checkpoints") or []) if isinstance(item, dict)]
    doc.subheading("真实收益与最大回撤")
    doc.signed_bars(checkpoints)
    for item in checkpoints:
        doc.subheading(f"{_text(item.get('window'))} · 观察日 {_text(item.get('observationDate'))}")
        doc.key_values(
            [
                ("预测风险", _risk_cn(item.get("predictionLabel"))),
                ("实际严重度", _risk_cn(item.get("actualSeverity"))),
                ("是否命中", _yes_no(item.get("hit"))),
                ("对齐程度", _risk_cn(item.get("alignment"))),
                ("发行价收益", _percent(item.get("issuePriceReturn"))),
                ("开盘累计收益", _percent(item.get("cumulativeReturnFromOpen"))),
                ("最大回撤", _percent(item.get("maxDrawdownFromOpen"))),
                ("实际风险分", _number(item.get("realizedRiskScore"))),
            ]
        )
        doc.paragraph("原预测：" + _text(item.get("predictionText")))
        if item.get("note"):
            doc.paragraph("验证说明：" + _text(item.get("note")), color=_MUTED, size=8)
    for limitation in validation.get("limitations") or []:
        doc.bullet("验证限制：" + _text(limitation), color=_ORANGE)


def _render_actions(doc: _ReportPDF, report: dict[str, Any], section_no: str) -> None:
    doc.section(section_no, "后续关注事项与使用边界", "将剩余不确定性转化为可执行的复核清单。", anchor="actions")
    debate = report.get("debate") if isinstance(report.get("debate"), dict) else {}
    uncertainties: list[str] = []
    for round_item in debate.get("history") or []:
        if not isinstance(round_item, dict):
            continue
        for reply in round_item.get("replies") or []:
            if isinstance(reply, dict) and reply.get("remaining_uncertainty"):
                value = _text(reply.get("remaining_uncertainty"))
                if value not in uncertainties:
                    uncertainties.append(value)
    if uncertainties:
        doc.subheading("建议优先复核")
        for item in uncertainties:
            doc.bullet(item)
    else:
        doc.paragraph("当前结构化结果未记录额外的剩余不确定性。", color=_MUTED)
    doc.subheading("报告边界")
    doc.bullet("风险评分用于识别和比较风险，不等同于收益预测或投资评级。")
    doc.bullet("行情预测基于分析时点可得信息；市场状态、发行条款和资金面变化可能使结论失效。")
    doc.bullet("上市后验证用于校准模型和复盘判断，不应被倒推为事前确定性结论。")
    if report.get("degraded"):
        doc.bullet("本次分析含降级标记，应结合人工复核后使用。", color=_ORANGE)


def _has_debate(report: dict[str, Any]) -> bool:
    debate = report.get("debate") if isinstance(report.get("debate"), dict) else {}
    return bool(int(debate.get("rounds") or 0) > 0 or (debate.get("history") or []))


def _render_markdown_report(doc: _ReportPDF, markdown: str) -> None:
    if not str(markdown or "").strip():
        doc.paragraph("本次分析未生成该专家的独立报告。", color=_MUTED)
        return
    lines = str(markdown).splitlines()
    paragraph: list[str] = []
    table_rows: list[list[str]] = []

    def flush_paragraph() -> None:
        if paragraph:
            doc.paragraph("\n".join(part.strip() for part in paragraph if part.strip()))
            paragraph.clear()

    def flush_table() -> None:
        if not table_rows:
            return
        rows = [row for row in table_rows if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)]
        table_rows.clear()
        if not rows:
            return
        headers = [_plain_text(cell) for cell in rows[0]]
        for row in rows[1:]:
            title = _plain_text(row[0]) or "明细"
            details = []
            for index, cell in enumerate(row[1:], 1):
                value = _plain_text(cell)
                if not value:
                    continue
                label = headers[index] if index < len(headers) else f"字段{index}"
                details.append(f"{label}：{value}")
            doc.callout(title, "\n".join(details) or "—", accent=_BLUE)

    in_code = False
    code_lines: list[str] = []
    first_heading = True
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("```"):
            flush_paragraph()
            if in_code and code_lines:
                doc.callout("结构化分析数据", _plain_text("\n".join(code_lines)), accent=_MUTED)
                code_lines.clear()
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        if line.startswith("|") and line.endswith("|"):
            flush_paragraph()
            table_rows.append([cell.strip() for cell in line.strip("|").split("|")])
            continue
        if table_rows:
            flush_table()
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            if first_heading:
                first_heading = False
            else:
                doc.subheading(heading.group(2))
            continue
        quote = re.match(r"^>\s*(.*)$", line)
        if quote:
            flush_paragraph()
            doc.callout("专家说明", quote.group(1), accent=_GOLD)
            continue
        bullet = re.match(r"^[-*+]\s+(.+)$", line)
        if bullet:
            flush_paragraph()
            doc.bullet(bullet.group(1))
            continue
        ordered = re.match(r"^\d+[.)]\s+(.+)$", line)
        if ordered:
            flush_paragraph()
            doc.bullet(ordered.group(1))
            continue
        if not line or line == "---":
            flush_paragraph()
            continue
        paragraph.append(line)
    flush_paragraph()
    flush_table()
    if code_lines:
        doc.callout("结构化分析数据", _plain_text("\n".join(code_lines)), accent=_MUTED)


def _render_expert_appendix(doc: _ReportPDF, *, anchor: str, number: str, title: str, markdown: str) -> None:
    doc.add_page()
    doc.section(number, title, "本章将专家独立分析转换为统一的图表、风险卡片和证据说明。", anchor=anchor)
    score = _expert_score(markdown)
    if score is not None:
        doc.callout("专家独立风险判断", f"风险分：{score:g}/100。分数越高，表示该专业维度识别出的风险越高。", accent=_score_color(score, 100))
        doc.score_bars([{"name": title.replace("独立报告", "风险分"), "score": score}])
    breakdown = _expert_breakdown(markdown)
    if breakdown:
        doc.subheading("主要风险贡献")
        doc.paragraph("下图按专家报告中的评分分解展示主要风险来源；用于解释专家独立评分，不代表总控权重。", color=_MUTED, size=8)
        doc.score_bars(breakdown)
    doc.subheading("独立分析正文")
    _render_markdown_report(doc, markdown)


def _toc_entries(report: dict[str, Any]) -> list[tuple[str, str, str]]:
    entries = [
        ("summary", "摘要", "执行摘要"),
        ("master", "01", "总控终裁"),
        ("dimensions", "02", "风险维度与评分分布"),
        ("risk_factors", "03", "核心风险因子与证据"),
    ]
    number = 4
    if _has_debate(report):
        entries.append(("debate", f"{number:02d}", "多智能体辩论与结论收束"))
        number += 1
    if isinstance(report.get("embellishmentAnalysis"), dict):
        entries.append(("embellishment", f"{number:02d}", "文本粉饰度专项分析"))
        number += 1
    entries.extend([
        ("forecast", f"{number:02d}", "上市后行情预测"),
        ("validation", f"{number + 1:02d}", "上市后行情验证"),
        ("actions", f"{number + 2:02d}", "后续关注事项与使用边界"),
        ("appendix_financial", "附录A", "财务专家独立报告"),
        ("appendix_legal", "附录B", "法务专家独立报告"),
        ("appendix_market", "附录C", "市场专家独立报告"),
    ])
    return entries


def _render_toc(doc: _ReportPDF, entries: list[tuple[str, str, str]], page_numbers: dict[str, int] | None) -> None:
    doc.add_page()
    pdf = doc.pdf
    pdf.set_text_color(*_NAVY)
    pdf.set_font(doc.font, "B", 18)
    pdf.cell(0, 12, "目录", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_MUTED)
    pdf.set_font(doc.font, size=8)
    pdf.multi_cell(0, 5, "点击任一章节可直接跳转到对应页面。")
    pdf.ln(5)
    for anchor, number, title in entries:
        link = doc.link(anchor) if page_numbers is not None else ""
        page = str((page_numbers or {}).get(anchor) or "—")
        y = pdf.get_y()
        pdf.set_draw_color(*_LINE)
        pdf.line(pdf.l_margin, y + 9, pdf.w - pdf.r_margin, y + 9)
        pdf.set_text_color(*_INK)
        pdf.set_font(doc.font, "B", 10)
        pdf.cell(19, 10, number, link=link)
        pdf.set_font(doc.font, size=10)
        pdf.cell(doc.content_width - 37, 10, title, link=link)
        pdf.set_text_color(*_BLUE)
        pdf.set_font(doc.font, "B", 9)
        pdf.cell(18, 10, page, align="R", link=link, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_fill_color(*_PALE)
    pdf.set_text_color(*_MUTED)
    pdf.set_font(doc.font, size=8)
    pdf.multi_cell(0, 5, "提示：不同 PDF 阅读器对内部链接的视觉样式可能不同；目录行本身均可点击。", fill=True)


def _render_document(report: dict[str, Any], *, ticker: str, company_name: str, page_numbers: dict[str, int] | None) -> _ReportPDF:
    doc = _ReportPDF(_find_cjk_font())
    entries = _toc_entries(report)
    for anchor, _number, _title in entries:
        link = doc.link(anchor)
        if page_numbers and page_numbers.get(anchor):
            doc.pdf.set_link(link, y=0, page=page_numbers[anchor])
    _render_cover(doc, report, ticker, company_name)
    _render_toc(doc, entries, page_numbers)
    doc.add_page()
    _render_master(doc, report)
    _render_dimensions(doc, report)
    _render_risk_factors(doc, report)
    section = 4
    if _has_debate(report):
        _render_debate(doc, report, section_no=f"{section:02d}")
        section += 1
    if isinstance(report.get("embellishmentAnalysis"), dict):
        doc.add_page()
        _render_embellishment(doc, report, f"{section:02d}")
        section += 1
    _render_forecast(doc, report, f"{section:02d}")
    section += 1
    _render_validation(doc, report, f"{section:02d}")
    section += 1
    _render_actions(doc, report, f"{section:02d}")
    expert_reports = report.get("expertReports") if isinstance(report.get("expertReports"), dict) else {}
    _render_expert_appendix(doc, anchor="appendix_financial", number="附录A", title="财务专家独立报告", markdown=str(expert_reports.get("financial") or ""))
    _render_expert_appendix(doc, anchor="appendix_legal", number="附录B", title="法务专家独立报告", markdown=str(expert_reports.get("legal") or ""))
    _render_expert_appendix(doc, anchor="appendix_market", number="附录C", title="市场专家独立报告", markdown=str(expert_reports.get("market") or ""))
    return doc


def render_report_pdf(report: dict[str, Any], *, ticker: str = "", company_name: str = "") -> bytes:
    """Render complete ReportData into a styled PDF with a linked table of contents."""
    layout = _render_document(report, ticker=ticker, company_name=company_name, page_numbers=None)
    doc = _render_document(report, ticker=ticker, company_name=company_name, page_numbers=layout.section_pages)
    output = doc.pdf.output()
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)
    return str(output).encode("latin-1")
