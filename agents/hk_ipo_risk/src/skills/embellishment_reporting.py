from __future__ import annotations

import html
import re
from typing import Any

DIMENSION_NAMES = {
    "marketing_language": "过度营销语言",
    "ranking_manipulation": "行业排名操纵",
    "concept_packaging": "概念包装",
    "obscurity": "表述晦涩与风险弱化",
    "key_info_postponed": "关键信息后置",
}
STATUS_NAMES = {
    "complete": "分析完成",
    "partial": "部分完成",
    "not_available": "无法评估",
}
SUPPORT_NAMES = {
    "supported": "有充分支撑",
    "weakly_supported": "支撑不足",
    "unsupported": "无充分支撑",
    "contradictory": "与其他证据矛盾",
    "unknown": "支撑状态未知",
}


def _clean(value: Any, limit: int = 600) -> str:
    text = html.unescape(str(value or ""))
    # Prospectus excerpts may be truncated in the middle of a raw HTML table.
    # Remove both complete and unterminated tags before writing Markdown; an
    # unterminated <table> would otherwise swallow every following section.
    text = re.sub(r"<[^>]*(?:>|$)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _page_ranges(values: Any) -> str:
    pages: list[int] = []
    for raw in values or []:
        try:
            pages.append(int(raw))
        except (TypeError, ValueError):
            continue
    pages = sorted(set(pages))
    if not pages:
        return "—"
    groups: list[str] = []
    start = previous = pages[0]
    for page in pages[1:]:
        if page == previous + 1:
            previous = page
            continue
        groups.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = page
    groups.append(str(start) if start == previous else f"{start}-{previous}")
    return "、".join(groups)


def embellishment_enabled(master: dict[str, Any] | None) -> bool:
    data = master if isinstance(master, dict) else {}
    options = data.get("analysis_options") if isinstance(data.get("analysis_options"), dict) else {}
    if "embellishment_enabled" in options:
        return bool(options.get("embellishment_enabled"))
    return True


def sort_high_risk_excerpts(embellishment: dict[str, Any]) -> list[dict[str, Any]]:
    values = [item for item in (embellishment.get("high_risk_excerpts") or embellishment.get("highRiskExcerpts") or []) if isinstance(item, dict)]
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        values,
        key=lambda item: (
            severity_rank.get(str(item.get("severity") or "low"), 3),
            0 if str(item.get("section") or "") == "risk_factors" else 1,
            -int(item.get("score_contribution") or item.get("scoreContribution") or 0),
            confidence_rank.get(str(item.get("confidence") or "low"), 3),
            int(item.get("page") or 10**9),
            str(item.get("candidate_id") or item.get("candidateId") or ""),
        ),
    )


def embellishment_report_data(embellishment: dict[str, Any] | None) -> dict[str, Any]:
    emb = embellishment if isinstance(embellishment, dict) else {}
    coverage = emb.get("coverage") if isinstance(emb.get("coverage"), dict) else {}
    raw_dimensions = emb.get("dimensions") if isinstance(emb.get("dimensions"), dict) else {}
    dimensions: list[dict[str, Any]] = []
    for dimension_id, name in DIMENSION_NAMES.items():
        raw = raw_dimensions.get(dimension_id)
        if isinstance(raw, dict):
            score = raw.get("score") or 0
            finding = raw.get("finding") or ""
            evidence_ids = raw.get("evidence_ids") or raw.get("evidenceIds") or []
        else:
            score = 0
            finding = str(raw or "")
            evidence_ids = []
        dimensions.append({"id": dimension_id, "name": name, "score": int(score or 0), "finding": finding, "evidenceIds": evidence_ids})

    excerpts: list[dict[str, Any]] = []
    for item in sort_high_risk_excerpts(emb):
        excerpts.append(
            {
                "candidateId": item.get("candidate_id") or item.get("candidateId") or "",
                "dimension": item.get("dimension") or "",
                "tactic": item.get("tactic") or "",
                "section": item.get("section") or "",
                "page": item.get("page"),
                "excerpt": item.get("excerpt") or "",
                "context": item.get("context") or "",
                "reason": item.get("reason") or "",
                "supportStatus": item.get("support_status") or item.get("supportStatus") or "unknown",
                "scoreContribution": int(item.get("score_contribution") or item.get("scoreContribution") or 0),
                "severity": item.get("severity") or "low",
                "confidence": item.get("confidence") or "low",
                "crossEvidence": item.get("cross_evidence") or item.get("crossEvidence") or [],
            }
        )
    if emb.get("status"):
        status = str(emb.get("status"))
    elif coverage.get("pages_analyzed") or coverage.get("pagesAnalyzed"):
        status = "complete"
    elif emb.get("score") is not None and emb.get("reason"):
        # 旧结果仅分析前五页且没有覆盖元数据，不能冒充新版完整分析。
        status = "partial"
    else:
        status = "not_available"
    return {
        "status": status,
        "score": int(emb.get("score") or 0),
        "level": emb.get("level") or "low",
        "summary": emb.get("reason") or "",
        "coverage": {
            "firstPages": coverage.get("first_pages") or coverage.get("firstPages") or [],
            "sections": coverage.get("sections") or [],
            "pagesAnalyzed": coverage.get("pages_analyzed") or coverage.get("pagesAnalyzed") or [],
            "riskFactorPages": coverage.get("risk_factor_pages") or coverage.get("riskFactorPages") or [],
            "candidateCount": int(coverage.get("candidate_count") or coverage.get("candidateCount") or 0),
            "evaluatedCandidateCount": int(coverage.get("evaluated_candidate_count") or coverage.get("evaluatedCandidateCount") or 0),
            "verifiedExcerptCount": int(coverage.get("verified_excerpt_count") or coverage.get("verifiedExcerptCount") or len(excerpts)),
        },
        "dimensions": dimensions,
        "highRiskExcerpts": excerpts,
        "limitations": emb.get("limitations") or [],
    }


def render_embellishment_markdown(
    embellishment: dict[str, Any] | None,
    *,
    title: str = "文本粉饰度专项分析",
    heading: str = "##",
    top_n: int = 10,
) -> str:
    data = embellishment_report_data(embellishment)
    coverage = data["coverage"]
    lines = [f"{heading} {title}", ""]
    lines.append(
        f"- 分数：`{data['score']}` / 10（{str(data['level']).upper()}）"
        f"；状态：{STATUS_NAMES.get(data['status'], data['status'])}"
    )
    lines.append(f"- 结论：{_clean(data['summary'], 1000) or '—'}")
    lines.append(
        f"- 全书扫描页：{_page_ranges(coverage['pagesAnalyzed'])}；"
        f"风险因素页：{_page_ranges(coverage['riskFactorPages'])}；"
        f"候选复核：{coverage['evaluatedCandidateCount']}/{coverage['candidateCount']}"
    )
    lines.append(f"- 重点章节：{'、'.join(str(item) for item in coverage['sections']) or '—'}")
    subheading = heading + "#"
    lines.extend(["", f"{subheading} 五维评分", "", "| 维度 | 分值 | 研判 |", "|---|---:|---|"])
    for item in data["dimensions"]:
        lines.append(f"| {item['name']} | {item['score']} | {_clean(item['finding'], 240).replace('|', '/')} |")

    excerpts = data["highRiskExcerpts"][: max(0, int(top_n))]
    lines.extend(["", f"{subheading} 高粉饰度原文切片（Top {top_n}）", ""])
    if excerpts:
        for index, item in enumerate(excerpts, start=1):
            support = SUPPORT_NAMES.get(str(item.get("supportStatus") or "unknown"), str(item.get("supportStatus") or "unknown"))
            lines.append(
                f"{subheading}# {index}. p.{item.get('page') if item.get('page') is not None else '—'} "
                f"{item.get('section') or '—'}｜{DIMENSION_NAMES.get(str(item.get('dimension') or ''), item.get('dimension') or '—')}"
            )
            lines.append(f"> {_clean(item.get('excerpt'), 600)}")
            lines.append("")
            lines.append(
                f"判定：{_clean(item.get('reason'), 600) or '—'}；策略 `{item.get('tactic') or '—'}`；"
                f"证据状态：{support}；计分 +{item.get('scoreContribution') or 0}。"
            )
            lines.append("")
    else:
        lines.append("本次没有通过原文回查且同时达到高严重度、高置信度门槛的切片。")
        lines.append("")
    for limitation in data["limitations"]:
        lines.append(f"- 分析限制：{_clean(limitation, 500)}")
    return "\n".join(lines).rstrip() + "\n"
