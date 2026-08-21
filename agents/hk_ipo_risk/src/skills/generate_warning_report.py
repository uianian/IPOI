from __future__ import annotations

from typing import Any

from src.models.master import MasterResult
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.embellishment_reporting import embellishment_enabled, render_embellishment_markdown


def render_master_markdown(result: MasterResult | dict[str, Any]) -> str:
    if isinstance(result, MasterResult):
        d = result.model_dump()
    else:
        d = dict(result)
    j = d.get("judgment") or {}
    emb = d.get("embellishment") or {}
    sections = d.get("report_sections") or {}
    lines = [
        "## 總控綜合判定",
        "",
        f"- 綜合風險分：`{j.get('overall_score')}`（{str(j.get('risk_level_http') or j.get('level') or '').upper()}）",
        f"- 置信度：`{j.get('confidence')}`",
        f"- 觸發條件：{', '.join(j.get('triggered_gates') or []) or '—'}",
        f"- 對照加權分：`{d.get('reference_fundamental_score')}`",
    ]
    if d.get("degraded"):
        lines.append(f"- 降級：`{d.get('degraded_reason')}`")
    if j.get("gate_warning"):
        lines.append(f"- gate_warning：{j.get('gate_warning')}")
    lines += [
        "",
        "### 終裁理由",
        "",
        str(sections.get("composite") or j.get("verdict_reasoning") or "—"),
        "",
    ]
    if embellishment_enabled(d):
        lines.extend(
            render_embellishment_markdown(
                emb,
                title="文本粉飾度專項分析",
                heading="###",
                top_n=10,
            ).splitlines()
        )
    lines += [
        "",
        "### 辯論摘要",
        "",
        str(sections.get("debate_summary") or "—"),
        "",
    ]
    hist = d.get("debate_history") or []
    if hist:
        for rnd in hist:
            lines.append(f"#### Round {rnd.get('round')}")
            for q in rnd.get("questions") or []:
                lines.append(f"- 問 {q.get('target_agent')}：{q.get('question')}")
            for r in rnd.get("replies") or []:
                lines.append(
                    f"  - 答 `{r.get('target_agent')}` [{r.get('status')}] {r.get('reply')}"
                )
            lines.append("")
    lines += [
        "### 證據置信度",
        "",
        str(sections.get("confidence_note") or j.get("score_explanation") or "—"),
        "",
        "### 預測時間窗（標籤兼容）",
        "",
    ]
    pw = d.get("predicted_windows") or {}
    lines.append(
        f"- 上市首日破發：{pw.get('ipo_day_break_risk')}；"
        f"5 日：{pw.get('d5_significant_downside_risk')}；"
        f"20 日：{pw.get('d20_downside_risk')}；"
        f"60 日：{pw.get('d60_downside_risk')}"
    )
    forecasts = d.get("price_path_forecast") or []
    if forecasts:
        lines += [
            "",
            "### 上市前走勢預判",
            "",
            "| 窗口 | 風險標籤 | 預期方向 | 走勢情景 | 波動/回撤 | 依據 |",
            "|---|---|---|---|---|---|",
        ]
        for item in forecasts:
            if not isinstance(item, dict):
                continue
            drivers = "；".join(str(x) for x in (item.get("key_drivers") or [])) or "—"
            lines.append(
                f"| {item.get('window') or '—'} | {item.get('risk_label') or '—'} | "
                f"{item.get('expected_direction') or '—'} | {item.get('expected_pattern') or '—'} | "
                f"{item.get('volatility_view') or '—'} | {drivers} |"
            )
    post = d.get("post_listing") or {}
    checkpoints = post.get("checkpoints") if isinstance(post, dict) else []
    lines += [
        "",
        "### 上市後真實行情驗證",
        "",
        f"- 狀態：`{post.get('status') or 'not_available'}`；"
        f"加權命中分：`{post.get('weighted_hit_score')}`；"
        f"D5重點預警：`{post.get('d5_priority_hit')}`",
        f"- 摘要：{post.get('forecast_alignment_summary') or post.get('summary') or '—'}",
        "",
    ]
    if checkpoints:
        lines += [
            "| 窗口 | 預測 | 真實嚴重度 | 對齊 | 日期 | 發行價收益 | 開盤基準收益 | 最大回撤 | 說明 |",
            "|---|---|---|---|---|---:|---:|---:|---|",
        ]
        for c in checkpoints:
            if not isinstance(c, dict):
                continue
            def pct(v: Any) -> str:
                try:
                    return f"{float(v):.2%}"
                except (TypeError, ValueError):
                    return "—"

            lines.append(
                f"| {c.get('window') or '—'} | {c.get('prediction_label') or '—'} | "
                f"{c.get('actual_severity') or '—'} | {c.get('alignment') or '—'} | "
                f"{c.get('observation_date') or '—'} | {pct(c.get('issue_price_return'))} | "
                f"{pct(c.get('cumulative_return_from_open'))} | {pct(c.get('max_drawdown_from_open'))} | "
                f"{c.get('note') or '—'} |"
            )
        lines.append("")
    limitations = post.get("limitations") if isinstance(post, dict) else []
    for limitation in limitations or []:
        lines.append(f"- 限制：{limitation}")
    if limitations:
        lines.append("")
    factors = d.get("risk_factors") or []
    if factors:
        lines.append("### 風險來源")
        lines.append("")
        for f in factors:
            lines.append(f"- **{f.get('title')}**（{f.get('source_agent')}）：{f.get('reason')}")
        lines.append("")
    return "\n".join(lines) + "\n"


class GenerateWarningReportSkill(BaseSkill):
    skill_name = "master_generate_report"
    version = "0.1.0"
    description = "把总控 JSON 排版为预警报告章节；不另起结论"

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        p = skill_input.params
        payload = p.get("master") or p
        md = render_master_markdown(payload)
        return SkillOutput(success=True, data={"report_markdown": md})
