from __future__ import annotations

"""法务 ReAct 工具箱：retrieve_legal / run_legal_skill / search_legal_evidence /
run_rule_checks / submit_legal_report。

Tool = 原子能力（检索/规则/提交）；Skill（legal_presets.LegalSkill）= 检索策略+
LLM抽取+阈值判定的业务包，经 `run_legal_skill` 暴露给 ReAct 循环。

`search_legal_evidence`（函数版 `search_legal_evidence_standalone`）同时供
未来总控辩论阶段复用：法务证据不充分时按 dossier 记录的 query 增量补证据。
"""

import logging
from pathlib import Path
from typing import Any

from src.config import load_score_rules
from src.models.debate import DebateClaim, DebateDossier, save_dossier
from src.models.evidence import EvidenceRef
from src.skills.base import SkillInput
from src.skills.extract_legal import enrich_rule_features_from_skills, extract_legal_features
from src.skills.legal_point_kind import classify_legal_point_kind, is_disclosure_rule_code
from src.skills.legal_presets import LEGAL_SKILL_NAMES, build_legal_skills
from src.skills.score_finance import score_to_level
from src.skills.score_legal import score_legal
from src.tools.parse_grep import grep_parse_json, merge_hits
from src.tools.retrieval_tool import retrieve_agent, retrieve_section_evidence
from src.tools.schemas import LEGAL_TOOL_SCHEMAS, ToolRegistry

logger = logging.getLogger(__name__)

# 二阶段 search 配额：起步 2；rule_checks 有覆盖缺口时升至最多 3（相对原 0/1 略放宽）
_SEARCH_QUOTA_DEFAULT = 2
_SEARCH_QUOTA_WITH_GAPS = 3

PKG_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEBATE_DIR = PKG_ROOT / ".runtime" / "debate"

# 全书 grep 基线（覆盖 5 个 skill 的主题；skill 内部再做定向章节检索）
LEGAL_BASELINE_GREP_KEYWORDS = [
    # 3.1 对赌赎回 / 3.2 关连交易（含专章比率口径）
    "關連交易", "关联交易", "持續關連", "持续关连", "關連交易豁免",
    "關連人士", "关联人士", "百分比率", "年度上限", "歷史交易總額", "历史交易总额",
    "贖回", "赎回", "對賭", "对赌", "優先股", "优先股",
    "可轉換可贖回", "可转换可赎回", "股東協議", "股东协议", "特別權利",
    # 3.3 集中度
    "前五大客戶", "前五大客户", "五大客戶", "最大客戶",
    "前五大供應商", "供應商", "供应商", "佔總採購", "佔總收入",
    # 治理
    "控股股東", "控股股东", "實際控制人", "实际控制人", "一致行動", "一致行动",
    # 合同与IP
    "獨家", "独家", "特許經營", "特许经营", "專利", "专利", "知識產權", "知识产权",
    # 监管与诉讼
    "處罰", "处罚", "調查", "调查", "訴訟", "诉讼", "仲裁", "牌照", "許可證", "许可证",
]

_LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2}


def _compact_hits(hits: list[dict[str, Any]], *, excerpt_chars: int = 120) -> list[dict[str, Any]]:
    return [
        {
            "page": h.get("page"),
            "section_id": h.get("section_id"),
            "source_type": h.get("source_type"),
            "matched_terms": h.get("matched_terms") or [],
            "excerpt": str(h.get("excerpt") or h.get("content") or "")[:excerpt_chars],
        }
        for h in hits
    ]


def _known_pages(state: dict[str, Any]) -> set[int]:
    pages: set[int] = set()

    def _collect(items: list[dict[str, Any]] | None) -> None:
        for h in items or []:
            p = h.get("page") or h.get("page_number") or h.get("evidence_page")
            try:
                if p is not None:
                    pages.add(int(p))
            except (TypeError, ValueError):
                continue

    _collect(state.get("extra_hits"))
    _collect(state.get("evidence_log"))
    for data in (state.get("skill_results") or {}).values():
        _collect(data.get("evidence"))
        _collect(data.get("risk_points"))
    for sec in (state.get("rule_features") or {}).values():
        if isinstance(sec, dict):
            _collect(sec.get("evidence"))
    return pages


# ---------- tools ----------


async def _tool_retrieve_legal(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    bundle = await retrieve_agent(
        "legal",
        state["doc_id"],
        issuer_type=state.get("issuer_type") or "general",
        top_k=state.get("top_k"),
        offline_json=state.get("retrieval_json"),
    )
    state["bundle"] = bundle
    extra_hits: list[dict[str, Any]] = []
    parse_json = state.get("parse_json")
    if parse_json:
        try:
            grep_hits = grep_parse_json(parse_json, LEGAL_BASELINE_GREP_KEYWORDS, top_k=60)
            extra_hits = merge_hits(grep_hits, top_k=60)
        except Exception as exc:
            logger.warning("legal baseline grep failed: %s", exc)
    state["extra_hits"] = extra_hits
    # 二阶段：search 硬配额（默认 2；有缺口时可升到 3）
    state.setdefault("search_quota", _SEARCH_QUOTA_DEFAULT)
    state.setdefault("search_used", 0)
    has_field_index = bool(bundle.get("evidence_by_field"))
    return {
        "ok": True,
        "source": bundle.get("_source"),
        "fields": list((bundle.get("evidence_by_field") or {}).keys())[:20],
        "grep_hits": len(extra_hits),
        "grep_pages_sample": sorted(
            {h.get("page") for h in extra_hits[:20] if h.get("page") is not None}
        )[:12],
        # stream/mapper 用：list[dict]，与 grep_hits 计数并存
        "hits": _compact_hits(extra_hits[:12]),
        "has_evidence_by_field": has_field_index,
        "skills_available": LEGAL_SKILL_NAMES,
        "search_quota": state.get("search_quota", _SEARCH_QUOTA_DEFAULT),
        "search_used": state.get("search_used", 0),
        "hint": (
            f"下一步逐个调用 run_legal_skill（共5个）；"
            f"search_legal_evidence 全程配额≤{state.get('search_quota')} 次，"
            "证据不足时精选补检，rule_checks 后尽快 submit"
        ),
    }


async def _tool_run_legal_skill(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    skill_name = str(args.get("skill_name") or "").strip()
    skills = state.get("_skills")
    if not skills:
        skills = build_legal_skills()
        state["_skills"] = skills
    if skill_name not in skills:
        return {"ok": False, "error": f"unknown skill: {skill_name}，可选：{LEGAL_SKILL_NAMES}"}
    if not state.get("bundle"):
        return {"ok": False, "error": "请先调用 retrieve_legal"}

    skill = skills[skill_name]
    output = await skill.execute(
        SkillInput(
            doc_id=state.get("doc_id") or "",
            params={
                "state": state,
                "llm": state.get("_llm"),
                "focus_hint": args.get("focus_hint"),
            },
        )
    )
    data = output.data or {}
    state.setdefault("skill_results", {})[skill_name] = {
        **data,
        "success": output.success,
        "degraded": output.degraded,
        "degraded_reason": output.degraded_reason,
    }
    for q in data.get("queries_used") or []:
        state.setdefault("queries_used", []).append({**q, "skill": skill_name})

    points = data.get("risk_points") or []
    skill_evidence = data.get("evidence") or []
    compact_evidence = _compact_hits(skill_evidence[:8])
    compact_points = []
    for p in points:
        page = p.get("evidence_page")
        excerpt = ""
        # 优先用风险点自带 evidence；否则从 skill evidence 按页码对齐一条
        rp_ev = p.get("evidence") if isinstance(p.get("evidence"), list) else []
        if rp_ev:
            pe = _compact_hits(rp_ev[:2])
        else:
            pe = []
            for e in skill_evidence:
                if page is not None and e.get("page") == page:
                    pe = _compact_hits([e])
                    break
            if not pe and page is not None:
                pe = [
                    {
                        "page": page,
                        "excerpt": str(p.get("description") or "")[:120],
                        "source_type": "text",
                        "matched_terms": [],
                        "section_id": None,
                    }
                ]
        if pe:
            excerpt = pe[0].get("excerpt") or ""
        compact_points.append(
            {
                "code": p.get("code"),
                "level": p.get("level"),
                "confidence": p.get("confidence"),
                "evidence_page": page,
                "description": str(p.get("description") or "")[:80],
                "evidence": pe,
                "excerpt": excerpt,
            }
        )
    low_conf = [p["code"] for p in compact_points if p.get("confidence") == "low"]
    quota = int(state.get("search_quota") or 0)
    used = int(state.get("search_used") or 0)
    remain = max(0, quota - used)
    if low_conf and remain > 0:
        hint = (
            f"以下风险点证据不足（confidence=low）：{low_conf}；"
            f"可 search_legal_evidence 补检（剩余配额 {remain}/{quota}），勿批量空搜"
        )
    elif low_conf:
        hint = (
            f"以下风险点证据不足（confidence=low）：{low_conf}；"
            "search 配额已用尽，请继续其他 skill 或 submit_legal_report"
        )
    else:
        hint = "证据充分，可继续下一个 skill"
    if not output.success:
        hint = f"skill 执行降级（{output.degraded_reason}）：{output.error}"
    return {
        "ok": output.success,
        "skill": skill_name,
        "exists": data.get("exists"),
        "confidence": data.get("confidence"),
        "n_risk_points": len(points),
        "risk_point_count": len(points),
        "risk_points": compact_points,
        "features": {
            k: v for k, v in (data.get("features") or {}).items() if v not in (None, [], {})
        },
        "negative_findings_n": len(data.get("negative_findings") or []),
        "evidence_pages": sorted(
            {e.get("page") for e in skill_evidence if e.get("page") is not None}
        ),
        # stream/mapper 用 compact 原文片段
        "evidence": compact_evidence,
        "search_quota": quota,
        "search_used": used,
        "error": output.error,
        "hint": hint,
    }


async def _tool_search_legal_evidence(
    args: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query 必填"}
    quota = int(state.get("search_quota") or 0)
    used = int(state.get("search_used") or 0)
    if used >= quota:
        return {
            "ok": False,
            "error": (
                f"search_legal_evidence 配额已用尽（used={used}, quota={quota}）。"
                "请直接 run_rule_checks 或 submit_legal_report。"
            ),
            "hint": "下一动作优先 submit_legal_report（或尚未做则 run_rule_checks）",
            "search_quota": quota,
            "search_used": used,
        }
    intent = (args.get("intent") or "business_context").strip()
    top_k = int(args.get("top_k") or 6)
    parse_json = state.get("parse_json")
    if not parse_json:
        return {"ok": False, "error": "缺少 full_parse.json，无法执行章节化补证据检索"}
    result = await retrieve_section_evidence(
        doc_id=state.get("doc_id") or "",
        intent=intent,
        query=query,
        parse_json=parse_json,
        section_hint=args.get("section_hint"),
        top_k=top_k,
        prefer_source_type="mixed",
    )
    hits = [h for h in (result.get("hits") or []) if h.get("matched_terms")]
    state["search_used"] = used + 1
    state.setdefault("evidence_log", []).extend(hits)
    state.setdefault("extra_hits", []).extend(hits)
    state.setdefault("queries_used", []).append(
        {
            "tool": "search_legal_evidence",
            "intent": intent,
            "query": query,
            "section_hint": args.get("section_hint"),
            "hits": len(hits),
            "pages": sorted({h.get("page") for h in hits if h.get("page") is not None}),
        }
    )
    remaining = max(0, quota - state["search_used"])
    return {
        "ok": True,
        "intent": intent,
        "query": query,
        "n": len(hits),
        "route": result.get("route") or [],
        "hits": _compact_hits(hits),
        "search_quota": quota,
        "search_used": state["search_used"],
        "hint": (
            (
                "0 命中：招股书为繁体，请改用繁體检索词；"
                if not hits
                else "完整证据已入 state；"
            )
            + (
                "配额已用尽，下一动作必须 run_rule_checks 或 submit_legal_report"
                if remaining == 0
                else f"还可补检 {remaining} 次，优先精选后尽快 submit"
            )
        ),
    }


async def search_legal_evidence_standalone(
    *,
    doc_id: str,
    parse_json: Path | str,
    query: str,
    intent: str = "business_context",
    section_hint: str | list[str] | None = None,
    top_k: int = 6,
    prefer_pages: list[int] | None = None,
) -> dict[str, Any]:
    """独立补证据入口：供总控辩论阶段（无 ReAct state）调用。"""
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
    hits = [
        h
        for h in (result.get("hits") or [])
        if h.get("matched_terms") or (prefer_pages and h.get("page") in set(int(p) for p in prefer_pages))
    ]
    return {
        "ok": True,
        "doc_id": doc_id,
        "intent": intent,
        "query": query,
        "n": len(hits),
        "route": result.get("route") or [],
        "hits": hits,
    }


async def _tool_run_rule_checks(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    bundle = state.get("bundle")
    if not bundle:
        return {"ok": False, "error": "请先调用 retrieve_legal"}
    gates = state.get("gates") or {}
    features = extract_legal_features(
        bundle,
        gates=gates,
        extra_hits=state.get("extra_hits"),
        parse_json=state.get("parse_json"),
    )
    features = enrich_rule_features_from_skills(features, state.get("skill_results"))
    scored = score_legal(features, gates=gates)
    state["rule_features"] = features
    state["rule_pack"] = scored

    # 覆盖缺口：规则命中主题 vs skill 风险点主题
    themes_cfg = ((load_score_rules().get("legal") or {}).get("themes")) or {}
    skill_themes: set[str] = set()
    for data in (state.get("skill_results") or {}).values():
        for p in data.get("risk_points") or []:
            t = _theme_of(str(p.get("code") or ""), themes_cfg)
            if t:
                skill_themes.add(t)
    coverage_hints: list[str] = []
    for b in scored.get("score_breakdown") or []:
        code = str(b.get("code") or "")
        t = _theme_of(code, themes_cfg)
        if t and t not in skill_themes and t not in {"concentration", "pipeline", "valuation"}:
            coverage_hints.append(
                f"规则命中 {code}（主题 {t}）但对应 skill 未给出风险点，建议复查/补证据"
            )
    used = int(state.get("search_used") or 0)
    n_skills = len(state.get("skill_results") or {})
    if coverage_hints:
        state["search_quota"] = max(
            int(state.get("search_quota") or 0),
            _SEARCH_QUOTA_WITH_GAPS,
        )
        state["ready_to_submit"] = False
        state["prefer_llm_submit"] = False
        remain = max(0, int(state["search_quota"]) - used)
        hint = (
            f"存在覆盖缺口（{len(coverage_hints)}）：search 配额已升至 "
            f"{state['search_quota']}（剩余 {remain}）；精选补检后必须 submit_legal_report"
        )
    else:
        # 无缺口：锁死剩余配额；skill 齐全时 prefer_llm_submit，由 react_loop 再叫一轮 submit
        state["search_quota"] = used
        if n_skills >= 5:
            state["ready_to_submit"] = True
            state["prefer_llm_submit"] = True
            hint = (
                "无覆盖缺口且 5 个 skill 已完成。"
                "下一动作必须 submit_legal_report（优先写 summary/reasoning；"
                "risk_points 可空由系统填充）；禁止再 search。"
            )
        else:
            state["ready_to_submit"] = False
            hint = "无覆盖缺口。下一动作必须 submit_legal_report，禁止再 search。"
    return {
        "ok": True,
        "rules_score": scored.get("risk_score"),
        "rules_level": scored.get("risk_level"),
        "flags": scored.get("flags"),
        "breakdown": [
            {"code": b.get("code"), "delta": b.get("delta"), "rule_ref": b.get("rule_ref")}
            for b in scored.get("score_breakdown") or []
        ],
        "coverage_hints": coverage_hints,
        "search_quota": state.get("search_quota"),
        "search_used": used,
        "ready_to_submit": bool(state.get("ready_to_submit")),
        "prefer_llm_submit": bool(state.get("prefer_llm_submit")),
        "n_skills": n_skills,
        "hint": hint,
    }


# ---------- submit：合并、托底、校验、辩论素材包 ----------


def _theme_of(code: str, themes_cfg: dict[str, list[str]]) -> str | None:
    c = (code or "").upper()
    for theme, prefixes in (themes_cfg or {}).items():
        for prefix in prefixes or []:
            if c.startswith(str(prefix).upper()):
                return theme
    return None


def _normalize_level(level: Any) -> str:
    lv = str(level or "medium").lower()
    return lv if lv in _LEVEL_ORDER else "medium"


def _collect_skill_points(state: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, data in (state.get("skill_results") or {}).items():
        for p in data.get("risk_points") or []:
            item = dict(p)
            item.setdefault("skill", name)
            out.append(item)
    return out


def _merge_risk_points(
    submitted: list[dict[str, Any]],
    skill_points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """skill 结果为证据权威；submit 可补充描述/新点。按 code 去重取更高 level。"""
    by_code: dict[str, dict[str, Any]] = {}
    for p in skill_points:
        code = str(p.get("code") or "").upper()
        if code:
            by_code[code] = dict(p)
    for p in submitted or []:
        if not isinstance(p, dict):
            continue
        code = str(p.get("code") or "").upper()
        if not code:
            continue
        prev = by_code.get(code)
        if prev is None:
            by_code[code] = dict(p)
            continue
        merged = dict(prev)
        if p.get("description"):
            merged["description"] = p["description"]
        if p.get("legal_basis"):
            merged["legal_basis"] = p["legal_basis"]
        if _LEVEL_ORDER[_normalize_level(p.get("level"))] > _LEVEL_ORDER[
            _normalize_level(prev.get("level"))
        ]:
            merged["level"] = _normalize_level(p.get("level"))
        by_code[code] = merged
    return list(by_code.values())


def _saturating_aggregate(deltas: list[float]) -> float:
    """多主题饱和聚合：100 * (1 - Π(1 - d_i/100))，自然压住多主题中等关注。"""
    remain = 1.0
    for d in deltas:
        try:
            x = max(0.0, min(100.0, float(d)))
        except (TypeError, ValueError):
            continue
        if x <= 0:
            continue
        remain *= 1.0 - x / 100.0
    # 饱和积会产生长浮点（如 52.251641...），统一保留 1 位小数
    return round(max(0.0, min(100.0, 100.0 * (1.0 - remain))), 1)


def _merge_legal_rules_floor(
    points: list[dict[str, Any]],
    rules_pack: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    """参考分 = 分型过滤 + 披露隔离 + 主题 max + 饱和聚合，再托底实质规则分。

    - boilerplate / benign_negative / disclosure_only：不计分（点仍在 risk_points）
    - structural：delta × structural_weight 后再主题 max
    - 规则 *_DISCLOSURE：仅当该主题尚无实质项时计入
    - 聚合默认 saturating；托底基准为非披露规则 delta 之和（非完整 rules_score）
    """
    legal_cfg = (load_score_rules().get("legal")) or {}
    themes_cfg = legal_cfg.get("themes") or {}
    llm_point_deltas = legal_cfg.get("llm_point_deltas") or {"high": 18, "medium": 8, "low": 3}
    llm_code_deltas = legal_cfg.get("llm_code_deltas") or {}
    try:
        structural_weight = float(legal_cfg.get("structural_weight") or 0.6)
    except (TypeError, ValueError):
        structural_weight = 0.6
    structural_weight = max(0.0, min(1.0, structural_weight))
    try:
        disclosure_weight = float(legal_cfg.get("disclosure_weight") or 0.5)
    except (TypeError, ValueError):
        disclosure_weight = 0.5
    disclosure_weight = max(0.0, min(1.0, disclosure_weight))
    aggregate = str(legal_cfg.get("score_aggregate") or "saturating").lower()

    groups: dict[str, dict[str, Any]] = {}
    skip_kinds = frozenset({"boilerplate", "benign_negative", "disclosure_only"})

    def _put(item: dict[str, Any], *, source: str) -> None:
        code = str(item.get("code") or "").upper()
        if not code:
            return
        theme = _theme_of(code, themes_cfg) or f"code:{code}"
        try:
            delta = float(item.get("delta") or 0)
        except (TypeError, ValueError):
            delta = 0.0
        if delta <= 0:
            return
        row = {**item, "code": code, "delta": delta, "source": source, "theme": theme}
        prev = groups.get(theme)
        if prev is None or delta > float(prev.get("delta") or 0):
            if prev is not None and prev.get("source") == "rules" and source == "llm":
                row["note"] = ((row.get("note") or "") + "（覆盖规则同主题项）").strip()
            groups[theme] = row

    rule_rows = [b for b in (rules_pack.get("score_breakdown") or []) if isinstance(b, dict)]
    disclosure_rows: list[dict[str, Any]] = []
    rules_substantive_score = 0.0
    for b in rule_rows:
        code = str(b.get("code") or "").upper()
        try:
            delta = float(b.get("delta") or 0)
        except (TypeError, ValueError):
            delta = 0.0
        if is_disclosure_rule_code(code):
            disclosure_rows.append(b)
            continue
        rules_substantive_score += max(0.0, delta)
        _put(
            {
                "code": code,
                "delta": delta,
                "rule_ref": b.get("rule_ref"),
                "note": b.get("note"),
                "evidence": b.get("evidence") or [],
                "point_kind": "issuer_specific",
            },
            source="rules",
        )

    for p in points:
        if not isinstance(p, dict):
            continue
        kind = classify_legal_point_kind(p)
        if kind in skip_kinds:
            continue
        code = str(p.get("code") or "").upper()
        if not code:
            continue
        delta = llm_code_deltas.get(code)
        if delta is None:
            delta = llm_point_deltas.get(_normalize_level(p.get("level")), 3)
        delta = float(delta)
        if kind == "structural":
            delta = round(delta * structural_weight, 1)
        if p.get("confidence") == "low":
            delta = round(delta / 2, 1)
        _put(
            {
                "code": code,
                "delta": delta,
                "rule_ref": f"llm§{p.get('skill') or 'legal'}",
                "note": str(p.get("description") or "")[:120],
                "metric_value": p.get("metric_value"),
                "evidence_page": p.get("evidence_page"),
                "point_kind": kind,
            },
            source="llm",
        )

    # 披露基线：仅填补尚无实质项的主题，并按 disclosure_weight 折减
    for b in disclosure_rows:
        code = str(b.get("code") or "").upper()
        theme = _theme_of(code, themes_cfg) or f"code:{code}"
        if theme in groups:
            continue
        try:
            raw_delta = float(b.get("delta") or 0)
        except (TypeError, ValueError):
            raw_delta = 0.0
        _put(
            {
                "code": code,
                "delta": round(raw_delta * disclosure_weight, 1),
                "rule_ref": b.get("rule_ref"),
                "note": b.get("note"),
                "evidence": b.get("evidence") or [],
                "point_kind": "disclosure_only",
            },
            source="rules",
        )

    breakdown = sorted(groups.values(), key=lambda x: -float(x.get("delta") or 0))
    deltas = [float(b.get("delta") or 0) for b in breakdown]
    if aggregate == "sum":
        saturated = round(max(0.0, min(100.0, sum(deltas))), 1)
    else:
        saturated = _saturating_aggregate(deltas)

    total = saturated
    rules_score = float(rules_pack.get("risk_score") or 0)
    if total < rules_substantive_score:
        warnings.append(f"rules_substantive_floor_forced:{rules_substantive_score}")
        total = rules_substantive_score
    total = round(max(0.0, min(100.0, total)), 1)
    return {
        "score_breakdown": breakdown,
        "risk_score": total,
        "risk_level": score_to_level(total),
        "rules_floor": {
            "rules_score": rules_score,
            "rules_substantive_score": rules_substantive_score,
            "saturated_score": saturated,
            "final_score": total,
            "score_aggregate": aggregate if aggregate == "sum" else "saturating",
            "flags": rules_pack.get("flags") or {},
        },
    }


def _point_to_evidence_refs(
    point: dict[str, Any],
    state: dict[str, Any],
) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    page = point.get("evidence_page")
    excerpt = str(point.get("evidence_excerpt") or "").strip()
    if page is not None or excerpt:
        refs.append(
            EvidenceRef(
                page=int(page) if page is not None else None,
                excerpt=excerpt[:200],
                source_type="text",
                field_code=str(point.get("code") or "") or None,
                confidence={"high": 1.0, "medium": 0.7, "low": 0.3}.get(
                    str(point.get("confidence") or "low"), 0.5
                ),
            )
        )
    # 同 skill 的其他证据页作为旁证（最多2条）
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


def build_legal_debate_dossier(
    state: dict[str, Any],
    report: dict[str, Any],
) -> DebateDossier:
    claims: list[DebateClaim] = []
    skill_results = state.get("skill_results") or {}
    for p in report.get("risk_points") or []:
        skill = p.get("skill")
        data = skill_results.get(skill) or {}
        claims.append(
            DebateClaim(
                agent="legal",
                skill=skill,
                code=str(p.get("code") or ""),
                level=_normalize_level(p.get("level")),
                confidence=str(p.get("confidence") or "low"),
                statement=str(p.get("description") or ""),
                legal_basis=p.get("legal_basis"),
                metric_value=p.get("metric_value"),
                reasoning=str(data.get("reasoning") or ""),
                evidence_refs=_point_to_evidence_refs(p, state),
                retrieval_queries=[
                    q
                    for q in (state.get("queries_used") or [])
                    if q.get("skill") == skill
                ][:4],
            )
        )
    return DebateDossier(
        agent="legal",
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
        retrieval_queries=list(state.get("queries_used") or []),
        run_log=state.get("run_log_paths") or {},
    )


async def _tool_submit_legal_report(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []

    # 未跑规则核对时自动补跑（托底不可缺席）
    if not state.get("rule_pack"):
        auto = await _tool_run_rule_checks({}, state)
        if auto.get("ok"):
            warnings.append("rule_checks_auto_run")
        else:
            state["rule_pack"] = {"risk_score": 0, "score_breakdown": [], "flags": {}}
            warnings.append(f"rule_checks_unavailable:{auto.get('error')}")

    skill_points = _collect_skill_points(state)
    submitted = [p for p in (args.get("risk_points") or []) if isinstance(p, dict)]
    # 模型 submit 空/残缺时用 skill_results 填充，避免再要求重写全部风险点
    if not submitted and skill_points:
        submitted = [dict(p) for p in skill_points]
        warnings.append("skill_results_filled_empty_submit")
    known_pages = _known_pages(state)
    skill_codes = {str(p.get("code") or "").upper() for p in skill_points}

    # 证据校验（反思闭环）：无 skill 背书且页码不可核实的提交项
    gaps: list[str] = []
    for p in submitted:
        code = str(p.get("code") or "").upper()
        page = p.get("evidence_page")
        try:
            page = int(page) if page is not None else None
        except (TypeError, ValueError):
            page = None
        if code in skill_codes:
            continue
        if page is None or page not in known_pages:
            gaps.append(code or "(无code)")
    rejects = int(state.get("submit_rejects") or 0)
    if gaps and rejects < 1:
        state["submit_rejects"] = rejects + 1
        return {
            "ok": False,
            "finished": False,
            "error": (
                f"以下风险点缺少可核实证据页码：{gaps}。"
                "请先 search_legal_evidence 补证据（或从风险点中移除），再重新 submit。"
            ),
            "known_pages_sample": sorted(known_pages)[:20],
        }
    if gaps:
        warnings.append(f"unverified_points_accepted:{gaps}")
        for p in submitted:
            if str(p.get("code") or "").upper() in gaps:
                p["confidence"] = "low"
                if _normalize_level(p.get("level")) == "high":
                    p["level"] = "medium"
                p["evidence_note"] = "二次提交仍无可核实证据，已降级"

    points = _merge_risk_points(submitted, skill_points)
    rules_pack = state.get("rule_pack") or {}
    floor = _merge_legal_rules_floor(points, rules_pack, warnings)

    # 规则侧独有 risk_points（如集中度/管线）并入，保持证据
    point_codes = {str(p.get("code") or "").upper() for p in points}
    for rp in rules_pack.get("risk_points") or []:
        if str(rp.get("code") or "").upper() not in point_codes:
            points.append(
                {
                    "code": rp.get("code"),
                    "level": _normalize_level(rp.get("level")),
                    "description": rp.get("description"),
                    "legal_basis": None,
                    "metric_value": rp.get("value"),
                    "evidence_page": (
                        (rp.get("evidence") or [{}])[0].get("page")
                        if rp.get("evidence")
                        else None
                    ),
                    "evidence_excerpt": (
                        (rp.get("evidence") or [{}])[0].get("excerpt")
                        if rp.get("evidence")
                        else ""
                    ),
                    "confidence": "high" if len(rp.get("evidence") or []) >= 2 else "medium",
                    "skill": "rule_engine",
                    "rule_ref": rp.get("rule_ref"),
                }
            )

    negatives = list(args.get("negative_findings") or [])
    if not negatives:
        for data in (state.get("skill_results") or {}).values():
            for n in data.get("negative_findings") or []:
                negatives.append(n if isinstance(n, dict) else {"description": str(n)})
        if negatives:
            warnings.append("skill_results_filled_negatives")

    summary = str(args.get("summary") or "").strip()
    reasoning = str(args.get("reasoning") or "").strip()
    # prefer_llm_submit 路径：空 summary/reasoning 先拒一次，逼模型写终裁叙述
    summary_rejects = int(state.get("summary_rejects") or 0)
    if (not summary or not reasoning) and summary_rejects < 1:
        state["summary_rejects"] = summary_rejects + 1
        state["ready_to_submit"] = True
        state["prefer_llm_submit"] = True
        state["_llm_submit_attempted"] = False
        state["_force_submit_turn"] = True
        return {
            "ok": False,
            "finished": False,
            "error": (
                "submit_legal_report 必须填写非空 summary 与 reasoning（繁體中文终裁）。"
                "risk_points 可留空由系统填充。请立即重新 submit，禁止空 arguments。"
            ),
        }
    if not summary:
        # 托底：从高风险点拼一句，避免「服務端交卷」占位
        highs = [
            str(p.get("description") or p.get("code") or "").strip()
            for p in points
            if _normalize_level(p.get("level")) == "high"
        ]
        highs = [h for h in highs if h][:3]
        if highs:
            summary = "；".join(highs)
            warnings.append("summary_from_high_risk_points")
        else:
            summary = (
                f"法務規則托底交卷：已完成 {len(state.get('skill_results') or {})} 個 skill，"
                f"彙總 {len(points)} 個風險點"
            )
            warnings.append("summary_auto_filled")
    if not reasoning:
        reasoning = summary

    report = {
        "risk_score": floor["risk_score"],
        "risk_level": floor["risk_level"],
        "score_breakdown": floor["score_breakdown"],
        "risk_points": points,
        "negative_findings": negatives,
        "reasoning": reasoning,
        "summary": summary,
        "scoring_mode": "react+rules_floor",
        "rules_floor": floor["rules_floor"],
        "submit_warnings": warnings,
        "model_think": state.get("last_reasoning"),
    }

    # 辩论素材包落盘
    try:
        dossier = build_legal_debate_dossier(state, report)
        debate_dir = state.get("debate_dir") or DEFAULT_DEBATE_DIR
        dossier_path = save_dossier(dossier, debate_dir)
        report["debate_dossier_path"] = str(dossier_path)
        state["debate_dossier"] = dossier.model_dump()
        state["debate_dossier_path"] = str(dossier_path)
    except Exception as exc:
        logger.warning("build/save debate dossier failed: %s", exc)
        warnings.append(f"dossier_failed:{exc}")

    state["final_report"] = report
    state["finished"] = True
    return {
        "ok": True,
        "finished": True,
        "risk_score": report["risk_score"],
        "risk_level": report["risk_level"],
        "n_risk_points": len(points),
        "warnings": warnings,
        "summary": report["summary"],
        "debate_dossier_path": report.get("debate_dossier_path"),
    }


def build_legal_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    handlers = {
        "retrieve_legal": _tool_retrieve_legal,
        "run_legal_skill": _tool_run_legal_skill,
        "search_legal_evidence": _tool_search_legal_evidence,
        "run_rule_checks": _tool_run_rule_checks,
        "submit_legal_report": _tool_submit_legal_report,
    }
    by_name = {s["function"]["name"]: s for s in LEGAL_TOOL_SCHEMAS}
    for name, handler in handlers.items():
        reg.register(by_name[name], handler)
    return reg
