"""可移植财务 Skill：4 个业务包（检索策略 + 规则/LLM 抽取 + schema）。

Tool 层经 `run_finance_skill` 调用；`meta()` 可序列化便于导出 SKILL.md。
profitability / cash_flow / solvency 以确定性规则+metrics 为主；
business_context 做章节检索 + 可选 LLM 定性。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from src.llm.prompts import FINANCE_SKILL_EXTRACTION_PROMPTS, FINANCE_EXTRACTION_SYSTEM
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.evidence_utils import dedupe_hits, hit_pages, normalize_query_record
from src.skills.score_finance import score_finance
from src.tools.retrieval_tool import retrieve_section_evidence

logger = logging.getLogger(__name__)

_PKG = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _PKG / "configs" / "finance_schema.yaml"

FINANCE_SKILL_META: dict[str, dict[str, str]] = {
    "finance_profitability": {
        "description": "盈亏与毛利质量（连续亏损/单年亏损/毛利率恶化）",
        "gpt_map": "Profitability + Growth Quality",
    },
    "finance_cash_flow": {
        "description": "CFO、现金跑道与烧钱加速",
        "gpt_map": "Cash Flow",
    },
    "finance_solvency": {
        "description": "资产负债表与 CV_PREF 表内负债压力",
        "gpt_map": "Solvency",
    },
    "finance_business_context": {
        "description": "非主表业务上下文（加盟/供应链/融资依赖）",
        "gpt_map": "Business Model",
    },
}

FINANCE_SKILL_NAMES = list(FINANCE_SKILL_META.keys())

_SKILL_CODES: dict[str, set[str]] = {
    "finance_profitability": {
        "CONTINUOUS_LOSS",
        "SINGLE_YEAR_LOSS",
        "GP_MARGIN_DROP",
    },
    "finance_cash_flow": {
        "CFO_NEGATIVE",
        "CASH_RUNWAY_LT_12",
        "CASH_RUNWAY_12_24",
        "BURN_YOY_UP_30",
    },
    "finance_solvency": {"CV_PREF_LIABILITY"},
    "finance_business_context": set(),  # 定性点，无硬规则码
}

_CODE_DESC: dict[str, str] = {
    "CONTINUOUS_LOSS": "業績記錄期連續虧損",
    "SINGLE_YEAR_LOSS": "最近完整年度虧損",
    "GP_MARGIN_DROP": "毛利率降幅超過 5 個百分點",
    "CFO_NEGATIVE": "經營活動現金流持續為負",
    "CASH_RUNWAY_LT_12": "未盈利且現金跑道不足 12 個月",
    "CASH_RUNWAY_12_24": "未盈利且現金跑道 12–24 個月",
    "BURN_YOY_UP_30": "未盈利且燒錢同比上升超過 30%",
    "CV_PREF_LIABILITY": "表內可轉換可贖回優先股/贖回負債壓力顯著",
}

_MAX_EVIDENCE_HITS = 12
_MAX_BLOB_CHARS = 6000


def _series_brief(metrics: dict[str, Any], code: str, *, limit: int = 4) -> str:
    series = metrics.get(code) if isinstance(metrics.get(code), dict) else None
    if not series:
        return "無"
    parts: list[str] = []
    for y, v in list(series.items())[:limit]:
        try:
            parts.append(f"{y}={float(v):,.1f}")
        except (TypeError, ValueError):
            parts.append(f"{y}={v}")
    return "；".join(parts)


def _yoy_change_brief(metrics: dict[str, Any], code: str) -> str | None:
    series = metrics.get(code) if isinstance(metrics.get(code), dict) else None
    if not series:
        return None
    years = sorted([y for y in series if str(y).isdigit()], key=lambda x: int(x))
    if len(years) < 2:
        return None
    y0, y1 = years[0], years[-1]
    try:
        v0, v1 = float(series[y0]), float(series[y1])
    except (TypeError, ValueError):
        return None
    if v0 == 0:
        return f"{y0}→{y1}: {v0:,.1f}→{v1:,.1f}"
    pct = (v1 - v0) / abs(v0) * 100
    return f"{y0}→{y1}: {v0:,.1f}→{v1:,.1f}（變化 {pct:+.1f}%）"


def _build_rule_skill_reasoning(
    skill_name: str,
    state: dict[str, Any],
    risk_points: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
) -> str:
    """规则类 skill：用 metrics/cash_burn 写可读结论，避免只写「命中 N 项」。"""
    metrics = state.get("metrics") or {}
    gates = state.get("gates") or {}
    cash = state.get("cash_burn") or {}
    codes = [str(p.get("code") or "") for p in risk_points if isinstance(p, dict)]
    parts: list[str] = []

    if skill_name == "finance_profitability":
        net = _series_brief(metrics, "NET_LOSS")
        gp = _series_brief(metrics, "GP_MARGIN")
        yoy = _yoy_change_brief(metrics, "NET_LOSS")
        parts.append(
            f"盈虧：NET_LOSS/利潤序列 {net}；未盈利={gates.get('is_unprofitable')}，"
            f"連續虧損={gates.get('continuous_net_loss')}，最近完整年度虧損={gates.get('latest_full_year_loss')}。"
        )
        if yoy:
            parts.append(f"年度對比：{yoy}。")
        if gp != "無":
            parts.append(f"毛利率：{gp}。")
    elif skill_name == "finance_cash_flow":
        cfo = _series_brief(metrics, "CFO")
        yoy = _yoy_change_brief(metrics, "CFO")
        runway = cash.get("CASH_RUNWAY_MONTHS")
        burn = cash.get("BURN_RATE_MONTHLY")
        burn_yoy = cash.get("burn_yoy_pct") or cash.get("BURN_YOY_PCT")
        parts.append(f"CFO 序列：{cfo}。")
        if yoy:
            parts.append(f"CFO 對比：{yoy}。")
        if runway is not None:
            parts.append(f"現金跑道約 {runway} 個月。")
        if burn is not None:
            parts.append(f"月均燒錢約 {burn}。")
        if burn_yoy is not None:
            parts.append(f"燒錢同比約 {burn_yoy}%。")
        elif cash.get("burn_yoy_up_gt_30"):
            parts.append("燒錢同比上升超過 30%。")
    elif skill_name == "finance_solvency":
        assets = _series_brief(metrics, "NET_ASSETS")
        liab = _series_brief(metrics, "TOTAL_LIAB")
        cv = metrics.get("CV_PREF")
        cv_txt = _series_brief(metrics, "CV_PREF") if isinstance(cv, dict) else (
            f"{cv}" if cv is not None else "無"
        )
        parts.append(f"淨資產：{assets}；總負債：{liab}；CV_PREF/贖回負債：{cv_txt}。")
    else:
        parts.append(f"{skill_name}: 規則命中 {len(risk_points)} 項")

    if codes:
        parts.append("觸發：" + "、".join(codes[:6]) + "。")
    else:
        parts.append("本維未觸發硬規則扣分。")
    if negatives:
        neg_codes = [str(n.get("code") or "") for n in negatives if isinstance(n, dict)]
        parts.append("陰性：" + "、".join(c for c in neg_codes if c)[:6] + "。")
    return " ".join(p for p in parts if p)


def _enrich_rule_point_metrics(
    point: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """为规则风险点补 metric_value（跑道月数、CV_PREF 等）。"""
    if point.get("metric_value") is not None:
        return point
    code = str(point.get("code") or "").upper()
    cash = state.get("cash_burn") or {}
    metrics = state.get("metrics") or {}
    if code in {"CASH_RUNWAY_LT_12", "CASH_RUNWAY_12_24"} and cash.get("CASH_RUNWAY_MONTHS") is not None:
        point["metric_value"] = cash.get("CASH_RUNWAY_MONTHS")
    elif code == "BURN_YOY_UP_30":
        point["metric_value"] = (
            cash.get("burn_yoy_pct")
            or cash.get("BURN_YOY_PCT")
            or cash.get("burn_yoy_up_gt_30")
        )
    elif code == "CV_PREF_LIABILITY":
        cv = metrics.get("CV_PREF")
        if isinstance(cv, dict) and cv:
            # 取最近一期
            keys = list(cv.keys())
            point["metric_value"] = cv.get(keys[-1])
        elif cv is not None:
            point["metric_value"] = cv
    elif code in {"CONTINUOUS_LOSS", "SINGLE_YEAR_LOSS"}:
        point["metric_value"] = True
    elif code == "CFO_NEGATIVE":
        point["metric_value"] = True
    return point


def load_finance_schema() -> dict[str, Any]:
    if not _SCHEMA_PATH.is_file():
        return {}
    with _SCHEMA_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _evidence_page_from_point(p: dict[str, Any]) -> int | None:
    page = p.get("evidence_page")
    if page is not None:
        try:
            return int(page)
        except (TypeError, ValueError):
            pass
    for e in p.get("evidence") or []:
        if isinstance(e, dict) and e.get("page") is not None:
            try:
                return int(e["page"])
            except (TypeError, ValueError):
                continue
    return None


def _point_from_rule(rp: dict[str, Any], skill: str) -> dict[str, Any]:
    code = str(rp.get("code") or "").upper()
    evid = rp.get("evidence") or []
    page = _evidence_page_from_point(rp)
    excerpt = ""
    if evid and isinstance(evid[0], dict):
        excerpt = str(evid[0].get("excerpt") or "")[:200]
    level = str(rp.get("level") or "medium").lower()
    if level not in {"high", "medium", "low"}:
        level = "medium"
    return {
        "code": code,
        "level": level,
        "description": _CODE_DESC.get(code) or rp.get("description") or f"觸發 {code}",
        "metric_value": rp.get("value") if rp.get("value") is not None else rp.get("metric_value"),
        "evidence_page": page,
        "evidence_excerpt": excerpt,
        "evidence": evid,
        "confidence": "high" if page is not None else "medium",
        "skill": skill,
        "rule_ref": rp.get("rule_ref"),
        "rule_auto": True,
    }


class FinanceSkill(BaseSkill):
    """可执行财务 Skill。"""

    def __init__(self, skill_name: str) -> None:
        if skill_name not in FINANCE_SKILL_META:
            raise KeyError(f"unknown finance skill: {skill_name}")
        meta = FINANCE_SKILL_META[skill_name]
        schema = (load_finance_schema().get("skills") or {}).get(skill_name) or {}
        self.skill_name = skill_name
        self.version = "1.0.0"
        self.description = meta["description"]
        self.gpt_map = meta["gpt_map"]
        self.prompt_template = FINANCE_SKILL_EXTRACTION_PROMPTS.get(skill_name) or ""
        self.keywords: list[str] = list(schema.get("keywords") or [])
        self.intents: list[str] = list(schema.get("intents") or [])
        self.section_hints: list[str] = list(schema.get("section_hints") or [])
        self.queries: list[str] = list(schema.get("queries") or [])
        self.biotech_extra_queries: list[str] = list(schema.get("biotech_extra_queries") or [])
        self.risk_codes: list[str] = list(schema.get("risk_codes") or list(_SKILL_CODES.get(skill_name) or []))
        self.maps_to: list[str] = list(schema.get("maps_to") or [])

    def meta(self) -> dict[str, Any]:
        return {
            "skill": self.skill_name,
            "version": self.version,
            "description": self.description,
            "gpt_map": self.gpt_map,
            "maps_to_doc_sections": self.maps_to,
            "keywords": self.keywords,
            "intents": self.intents,
            "section_hints": self.section_hints,
            "queries": self.queries,
            "risk_codes": self.risk_codes,
            "prompt_preview": (self.prompt_template or "")[:200],
        }

    def _ensure_rule_pack(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("rule_pack") and isinstance(state["rule_pack"], dict):
            return state["rule_pack"]
        metrics = state.get("metrics") or {}
        gates = state.get("gates") or {}
        cash_burn = state.get("cash_burn") or {"skipped": True}
        extracted = state.get("extracted") or {"evidence": {}, "table_meta": {}}
        pack = score_finance(metrics, gates, cash_burn, extracted)
        state["rule_pack"] = pack
        return pack

    async def _collect_context_evidence(
        self, state: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        hits: list[dict[str, Any]] = []
        queries_used: list[dict[str, Any]] = []
        parse_json = state.get("parse_json")
        if not parse_json:
            return [], []
        gates = state.get("gates") or {}
        queries = list(self.queries)
        if gates.get("is_biotech_18a") or (state.get("issuer_type") or "").lower() in {
            "18a",
            "18c",
            "biotech",
        }:
            queries.extend(self.biotech_extra_queries)
        # general 才跑加盟类 query；biotech 只用融资依赖
        it = (state.get("issuer_type") or "general").lower()
        if it in {"18a", "18c", "biotech"} and self.skill_name == "finance_business_context":
            queries = [
                q
                for q in queries
                if "加盟" not in q and "franchise" not in q.lower()
            ] or list(self.biotech_extra_queries) or [
                "融資 資金需求 營運資金 所得款項用途"
            ]
        intent = self.intents[0] if self.intents else "business_context"
        for query in queries[:3]:
            try:
                result = await retrieve_section_evidence(
                    doc_id=state.get("doc_id") or "",
                    intent=intent,
                    query=query,
                    parse_json=parse_json,
                    section_hint=self.section_hints or None,
                    top_k=6,
                    prefer_source_type="mixed",
                )
            except Exception as exc:
                logger.warning("%s section retrieval failed: %s", self.skill_name, exc)
                continue
            matched = [h for h in (result.get("hits") or []) if isinstance(h, dict)]
            hits.extend(matched)
            queries_used.append(
                normalize_query_record(
                    tool="retrieve_section_evidence",
                    intent=intent,
                    query=query,
                    section_hint=self.section_hints,
                    hits=len(matched),
                    pages=hit_pages(matched),
                    skill=self.skill_name,
                )
            )
        deduped = dedupe_hits(hits)
        deduped.sort(key=lambda h: -float(h.get("score") or 0))
        return deduped[:_MAX_EVIDENCE_HITS], queries_used

    async def _llm_extract_context(
        self, llm: Any, hits: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self.prompt_template or llm is None:
            return [], None
        blob_parts: list[str] = []
        used = 0
        for h in hits:
            excerpt = (h.get("excerpt") or h.get("content") or "").strip()
            part = f"[p{h.get('page')}] {excerpt[:600]}"
            if used + len(part) > _MAX_BLOB_CHARS:
                break
            blob_parts.append(part)
            used += len(part)
        if not blob_parts:
            return [], None
        prompt = self.prompt_template.format(evidence_text="\n\n".join(blob_parts))
        try:
            resp = await llm.chat_json(
                [
                    {"role": "system", "content": FINANCE_EXTRACTION_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                enable_reasoning=False,
                max_tokens=1800,
            )
        except Exception as exc:
            logger.warning("%s LLM extract failed: %s", self.skill_name, exc)
            return [], None
        data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
        points = [p for p in (data.get("risk_points") or []) if isinstance(p, dict)]
        valid_pages = hit_pages(hits)
        out: list[dict[str, Any]] = []
        for p in points:
            code = str(p.get("code") or "").upper() or "OTHER_CONTEXT"
            page = p.get("evidence_page")
            try:
                page = int(page) if page is not None else None
            except (TypeError, ValueError):
                page = None
            verified = page is not None and page in valid_pages
            level = str(p.get("level") or "low").lower()
            if level not in {"high", "medium", "low"}:
                level = "low"
            if not verified and level == "high":
                level = "medium"
            out.append(
                {
                    "code": code,
                    "level": level,
                    "description": str(p.get("description") or ""),
                    "metric_value": p.get("metric_value"),
                    "evidence_page": page if verified else None,
                    "evidence_excerpt": str(p.get("evidence_excerpt") or "")[:200],
                    "confidence": "high" if verified and len(valid_pages) >= 2 else (
                        "medium" if verified else "low"
                    ),
                    "skill": self.skill_name,
                }
            )
        return out, resp.get("reasoning")

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        state = skill_input.params.get("state") or {}
        if not isinstance(state, dict):
            return SkillOutput(success=False, error="missing state", data={})

        # 前置：需要 metrics/gates
        if not state.get("metrics") or not state.get("gates"):
            return SkillOutput(
                success=False,
                error="请先 retrieve_finance → extract_metrics → derive_gates",
                data={"skill": self.skill_name},
            )

        queries_used: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        risk_points: list[dict[str, Any]] = []
        negatives: list[dict[str, Any]] = []
        reasoning = ""

        if self.skill_name != "finance_business_context":
            pack = self._ensure_rule_pack(state)
            codes = _SKILL_CODES.get(self.skill_name) or set(self.risk_codes)
            for rp in pack.get("risk_points") or []:
                code = str(rp.get("code") or "").upper()
                if code in codes:
                    risk_points.append(
                        _enrich_rule_point_metrics(_point_from_rule(rp, self.skill_name), state)
                    )
            # 阴性发现按 skill 粗分
            for n in pack.get("negative_findings") or []:
                if not isinstance(n, dict):
                    continue
                nc = str(n.get("code") or "").upper()
                if self.skill_name == "finance_profitability" and nc in {
                    "PROFITABLE",
                    "GP_MARGIN_STABLE",
                }:
                    negatives.append(n)
                elif self.skill_name == "finance_cash_flow" and nc in {
                    "CFO_POSITIVE",
                    "SKIP_CASH_BURN",
                }:
                    negatives.append(n)
            # 表证据摘要
            table_meta = (state.get("extracted") or {}).get("table_meta") or {}
            for code, info in table_meta.items():
                if not isinstance(info, dict):
                    continue
                if self.skill_name == "finance_profitability" and code.startswith("TBL_IS"):
                    evidence.append(info)
                elif self.skill_name == "finance_cash_flow" and code.startswith("TBL_CF"):
                    evidence.append(info)
                elif self.skill_name == "finance_solvency" and "BS" in code:
                    evidence.append(info)
            reasoning = _build_rule_skill_reasoning(
                self.skill_name, state, risk_points, negatives
            )
        else:
            hits, queries_used = await self._collect_context_evidence(state)
            evidence = hits
            state.setdefault("section_evidence_hits", []).extend(hits)
            llm = state.get("_llm")
            if llm is not None and getattr(llm, "available", False) and hits:
                llm_points, llm_reason = await self._llm_extract_context(llm, hits)
                risk_points.extend(llm_points)
                reasoning = llm_reason or f"business_context: 召回 {len(hits)} 條，抽取 {len(llm_points)} 點"
            else:
                reasoning = (
                    f"business_context: 召回 {len(hits)} 條"
                    + ("（無 LLM，僅保留證據供 submit）" if hits else "（無命中）")
                )
                if not hits:
                    negatives.append(
                        {
                            "code": "NO_CONTEXT_HITS",
                            "description": "業務上下文章節未召回額外證據（或已跳過）",
                            "skill": self.skill_name,
                        }
                    )

        data = {
            "skill": self.skill_name,
            "risk_points": risk_points,
            "negative_findings": negatives,
            "evidence": [
                {
                    "page": e.get("page"),
                    "excerpt": str(e.get("excerpt") or "")[:200],
                    "source_type": e.get("source_type") or e.get("category"),
                    "field_code": e.get("field_code") or e.get("code"),
                    "confidence": e.get("score") or e.get("confidence"),
                }
                for e in evidence
                if isinstance(e, dict)
            ][:12],
            "queries_used": queries_used,
            "confidence": "high" if risk_points else ("medium" if evidence else "low"),
            "reasoning": reasoning,
            "meta": self.meta(),
        }
        return SkillOutput(success=True, data=data)


def build_finance_skills() -> dict[str, FinanceSkill]:
    return {name: FinanceSkill(name) for name in FINANCE_SKILL_NAMES}
