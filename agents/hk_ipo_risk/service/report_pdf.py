"""从 ReportData 渲染 PDF 二进制（与 JSON 同一口径）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

_FONT_CANDIDATES = [
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _find_cjk_font() -> str | None:
    for p in _FONT_CANDIDATES:
        if Path(p).is_file():
            return p
    return None


def render_report_pdf(
    report: dict[str, Any],
    *,
    ticker: str = "",
) -> bytes:
    from fpdf import FPDF

    font_path = _find_cjk_font()
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    if font_path:
        pdf.add_font("cjk", fname=font_path)
        pdf.set_font("cjk", size=14)
    else:
        pdf.set_font("Helvetica", size=14)

    title = f"IPO风险报告 {ticker}".strip()
    pdf.multi_cell(0, 10, title)
    pdf.set_font("cjk" if font_path else "Helvetica", size=11)
    pdf.ln(2)
    lines = [
        f"综合评分：{report.get('overallScore')}  {report.get('riskLevel')}（{report.get('riskLabel')}）",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "执行摘要：",
        str(report.get("executiveSummary") or "—"),
        "",
        "维度分数：",
    ]
    for d in report.get("dimensions") or []:
        if isinstance(d, dict):
            lines.append(f"- {d.get('name')}: {d.get('score')}")
    lines.append("")
    embellishment = report.get("embellishmentAnalysis") if isinstance(report.get("embellishmentAnalysis"), dict) else {}
    if embellishment:
        lines.append("文本粉饰度专项分析：")
        lines.append(
            f"- 分数：{embellishment.get('score', 0)}/10（{embellishment.get('level') or '—'}）；"
            f"状态：{embellishment.get('status') or 'not_available'}"
        )
        coverage = embellishment.get("coverage") if isinstance(embellishment.get("coverage"), dict) else {}
        lines.append(
            f"- 全书扫描页数：{len(coverage.get('pagesAnalyzed') or [])}；"
            f"风险因素页数：{len(coverage.get('riskFactorPages') or [])}；"
            f"候选复核：{coverage.get('evaluatedCandidateCount') or 0}/{coverage.get('candidateCount') or 0}"
        )
        if embellishment.get("summary"):
            lines.append(f"- 结论：{embellishment.get('summary')}")
        lines.append("- 五维评分：")
        for dimension in embellishment.get("dimensions") or []:
            if isinstance(dimension, dict):
                lines.append(f"  · {dimension.get('name')}: {dimension.get('score')}；{dimension.get('finding') or '—'}")
        excerpts = [item for item in (embellishment.get("highRiskExcerpts") or []) if isinstance(item, dict)][:10]
        lines.append("- 高粉饰度原文切片（Top 10）：")
        if excerpts:
            for index, item in enumerate(excerpts, start=1):
                lines.append(
                    f"  {index}. p.{item.get('page') if item.get('page') is not None else '—'} "
                    f"{item.get('section') or '—'} [{item.get('tactic') or '—'}]"
                )
                lines.append(f"     原文：{item.get('excerpt') or '—'}")
                lines.append(
                    f"     判定：{item.get('reason') or '—'}；证据状态：{item.get('supportStatus') or 'unknown'}；"
                    f"计分 +{item.get('scoreContribution') or 0}"
                )
        else:
            lines.append("  本次没有通过原文回查且达到高严重度、高置信度门槛的切片。")
        for limitation in embellishment.get("limitations") or []:
            lines.append(f"- 分析限制：{limitation}")
        lines.append("")
    lines.append("风险来源：")
    for f in report.get("riskFactors") or []:
        if isinstance(f, dict):
            page = f.get("evidencePage")
            page_s = f" p.{page}" if page is not None else ""
            lines.append(f"- {f.get('title')}（{f.get('sourceAgent')}）{page_s}: {f.get('reason')}")
    lines.append("")
    lines.append("时间窗：")
    for w in report.get("riskTimeline") or []:
        if isinstance(w, dict):
            lines.append(f"- {w.get('label')}: {w.get('risk')}")
    if report.get("degraded"):
        lines.append("")
        lines.append("（本报告含降级标记，非正式终裁）")
    if report.get("gateWarning"):
        lines.append(f"gate_warning: {report.get('gateWarning')}")

    body = "\n".join(lines)
    pdf.multi_cell(0, 7, body)
    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin-1")
