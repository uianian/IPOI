from __future__ import annotations

from typing import Any

from src.models.master import MasterResult
from src.skills.base import BaseSkill, SkillInput, SkillOutput


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
        "### 文本粉飾度",
        "",
        f"- 分數：`{emb.get('score')}` / 10（{emb.get('level')}）",
        str(sections.get("embellishment") or emb.get("reason") or "—"),
        "",
    ]
    hits = emb.get("hits") or []
    if hits:
        lines.append("| 頁碼 | 維度 | 原文 |")
        lines.append("|------|------|------|")
        for h in hits[:8]:
            if not isinstance(h, dict):
                continue
            lines.append(
                f"| {h.get('page') if h.get('page') is not None else '—'} | "
                f"{h.get('dimension') or '—'} | {(h.get('excerpt') or '')[:120]} |"
            )
        lines.append("")
    lines += [
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
        "### 預測時間窗（定性，未接 EOD）",
        "",
    ]
    pw = d.get("predicted_windows") or {}
    lines.append(
        f"- 上市首日破發：{pw.get('ipo_day_break_risk')}；"
        f"5 日：{pw.get('d5_significant_downside_risk')}；"
        f"20 日：{pw.get('d20_downside_risk')}；"
        f"60 日：{pw.get('d60_downside_risk')}"
    )
    post = d.get("post_listing") or {}
    lines += [
        "",
        "### 上市後驗證（空欄）",
        "",
        f"- day1/5/20/60：{post.get('day1')}/{post.get('day5')}/{post.get('day20')}/{post.get('day60')}；"
        f"hit={post.get('hit')}；{post.get('note') or ''}",
        "",
    ]
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
