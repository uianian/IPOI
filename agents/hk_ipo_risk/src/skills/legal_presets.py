from __future__ import annotations

"""法务 5 Skill（GPT 七维合并）——可执行实现。

Skill = 检索策略 + 抽取 Prompt + 阈值判定 + 输出 schema 的可移植业务包；
Tool（见 legal_toolbox.py）是原子能力。Skill 内部编排检索与 LLM，
通过 `run_legal_skill` 工具暴露给 ReAct 循环。

可移植性：`LegalSkill.meta()` 返回可序列化元数据（名称/版本/描述/检索策略/
Prompt/风险码/阈值），后续可直接导出为独立 SKILL.md。
"""

import logging
from typing import Any

from src.config import load_legal_schema
from src.llm.prompts import (
    LEGAL_DIMENSION_PROMPTS,
    LEGAL_EXTRACTION_SYSTEM,
    LEGAL_SKILL_EXTRACTION_PROMPTS,
    LEGAL_SUBMIT_SCHEMA,
    LEGAL_SYSTEM,
)
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.extract_legal import (
    harvest_connected_transactions_from_parse,
    parse_related_party_ratio_signals,
    resolve_related_party_ratio,
)
from src.skills.legal_point_kind import classify_legal_point_kind
from src.tools.retrieval_tool import iter_all_text_hits, retrieve_section_evidence

logger = logging.getLogger(__name__)

LEGAL_SKILL_NAMES = [
    "legal_governance",
    "legal_shareholder_rights",
    "legal_related_party",
    "legal_contracts_and_ip",
    "legal_regulatory_litigation",
]

LEGAL_SKILL_META = {
    "legal_governance": {
        "description": "股权结构与治理风险（控股股东/实控人/一致行动/AB股/董事）",
        "gpt_map": "Skill1 Corporate Governance",
    },
    "legal_shareholder_rights": {
        "description": "对赌/赎回与上市前权利清理（doc§3.1+§3.6）",
        "gpt_map": "Skill2 Shareholder Right / 增强 3.1",
    },
    "legal_related_party": {
        "description": "关联交易公允性与依赖（doc§3.2）",
        "gpt_map": "Skill3 Related Party / 增强 3.2",
    },
    "legal_contracts_and_ip": {
        "description": "重大合同 + 知识产权（合并 GPT Skill4+7）",
        "gpt_map": "Skill4 Contract + Skill7 IP",
    },
    "legal_regulatory_litigation": {
        "description": "监管合规 + 诉讼仲裁（合并 GPT Skill5+6）",
        "gpt_map": "Skill5 Regulatory + Skill6 Litigation",
    },
}

_MAX_EVIDENCE_HITS = 8
_MAX_BLOB_CHARS = 6000
_LEVELS = {"high", "medium", "low"}


def _dedupe_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, str]] = set()
    out: list[dict[str, Any]] = []
    for h in hits:
        excerpt = h.get("excerpt") or h.get("content") or ""
        key = (h.get("page"), excerpt[:80])
        if key in seen or not excerpt.strip():
            continue
        seen.add(key)
        item = dict(h)
        item.setdefault("excerpt", excerpt)
        out.append(item)
    return out


def _hit_pages(hits: list[dict[str, Any]]) -> set[int]:
    pages: set[int] = set()
    for h in hits:
        p = h.get("page") or h.get("page_number")
        try:
            if p is not None:
                pages.add(int(p))
        except (TypeError, ValueError):
            continue
    return pages


def _to_evidence_dict(h: dict[str, Any], field_code: str) -> dict[str, Any]:
    excerpt = (h.get("excerpt") or h.get("content") or "").replace("\n", " ").strip()
    return {
        "page": h.get("page") or h.get("page_number"),
        "excerpt": excerpt[:200],
        "source_type": "table" if (h.get("category") or "").lower() == "table" else "text",
        "field_code": field_code,
        "confidence": float(h.get("score") or 0.5),
    }


class LegalSkill(BaseSkill):
    """可执行法务 Skill：定向检索 → LLM 结构化抽取 → 阈值判定 → 置信度。"""

    def __init__(self, skill_name: str) -> None:
        if skill_name not in LEGAL_SKILL_META:
            raise KeyError(f"unknown legal skill: {skill_name}")
        meta = LEGAL_SKILL_META[skill_name]
        schema = (load_legal_schema().get("skills") or {}).get(skill_name) or {}
        self.skill_name = skill_name
        self.version = "1.0.0"
        self.description = meta["description"]
        self.gpt_map = meta["gpt_map"]
        self.prompt_template = LEGAL_SKILL_EXTRACTION_PROMPTS[skill_name]
        self.keywords: list[str] = list(schema.get("keywords") or [])
        self.intents: list[str] = list(schema.get("intents") or [])
        self.section_hints: list[str] = list(schema.get("section_hints") or [])
        self.queries: list[str] = list(schema.get("queries") or [])
        self.biotech_extra_queries: list[str] = list(schema.get("biotech_extra_queries") or [])
        self.risk_codes: list[str] = list(schema.get("risk_codes") or [])
        self.maps_to: list[str] = list(schema.get("maps_to") or [])

    def meta(self) -> dict[str, Any]:
        """可序列化元数据（用于日志、辩论素材包、导出 SKILL.md）。"""
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
            "prompt_preview": self.prompt_template[:200],
        }

    # ---------- 证据收集 ----------

    async def _collect_evidence(
        self, state: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """候选证据 = 证据包关键词命中 ∪ extra grep 命中 ∪ 定向章节检索命中。"""
        hits: list[dict[str, Any]] = []
        bundle = state.get("bundle") or {}
        for h in iter_all_text_hits(bundle):
            text = h.get("excerpt") or h.get("content") or ""
            if any(k in text for k in self.keywords):
                hits.append(h)
        for h in state.get("extra_hits") or []:
            text = h.get("excerpt") or h.get("content") or ""
            if any(k in text for k in self.keywords):
                hits.append(h)

        queries_used: list[dict[str, Any]] = []
        parse_json = state.get("parse_json")
        queries = list(self.queries)
        gates = state.get("gates") or {}
        if gates.get("is_biotech_18a"):
            queries.extend(self.biotech_extra_queries)
        if parse_json:
            intent = self.intents[0] if self.intents else "business_context"
            for query in queries:
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
                matched = [h for h in (result.get("hits") or []) if h.get("matched_terms")]
                hits.extend(matched)
                queries_used.append(
                    {
                        "tool": "retrieve_section_evidence",
                        "intent": intent,
                        "query": query,
                        "section_hint": self.section_hints,
                        "hits": len(matched),
                        "pages": sorted(_hit_pages(matched)),
                    }
                )
        deduped = _dedupe_hits(hits)
        # 关连交易：专章 harvest 补离线召回缺口（表格/百分比率页）
        if self.skill_name == "legal_related_party":
            chapter = harvest_connected_transactions_from_parse(parse_json)
            if chapter:
                deduped = _dedupe_hits(list(deduped) + chapter)
                queries_used.append(
                    {
                        "tool": "harvest_connected_transactions",
                        "intent": "related_party",
                        "query": "關連交易专章",
                        "section_hint": ["connected_transactions"],
                        "hits": len(chapter),
                        "pages": sorted(_hit_pages(chapter)),
                    }
                )
            deduped.sort(
                key=lambda h: (
                    0 if h.get("section_id") == "connected_transactions" else 1,
                    0 if "table" in str(h.get("category") or "") else 1,
                    -float(h.get("score") or 0),
                )
            )
            return deduped[:16], queries_used
        deduped.sort(key=lambda h: -float(h.get("score") or 0))
        return deduped[:_MAX_EVIDENCE_HITS], queries_used

    # ---------- LLM 抽取 ----------

    async def _llm_extract(
        self, llm: Any, hits: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], str | None, str]:
        """返回 (parsed_data, reasoning, raw_content)；JSON 截断/解析失败时 data 为空。"""
        blob_parts: list[str] = []
        used = 0
        for h in hits:
            excerpt = (h.get("excerpt") or h.get("content") or "").strip()
            part = f"[p{h.get('page')}] {excerpt[:600]}"
            if used + len(part) > _MAX_BLOB_CHARS:
                break
            blob_parts.append(part)
            used += len(part)
        prompt = self.prompt_template.format(evidence_text="\n\n".join(blob_parts))
        # 抽取是结构化输出任务：关闭 reasoning 省预算，避免 JSON 被 max_tokens 截断
        resp = await llm.chat_json(
            [
                {"role": "system", "content": LEGAL_EXTRACTION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            enable_reasoning=False,
            max_tokens=2400,
        )
        data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
        content = str(resp.get("content") or "")
        if not data and content.strip():
            logger.warning(
                "%s LLM 返回非空但 JSON 解析失败（疑似截断），content[:200]=%s",
                self.skill_name,
                content[:200],
            )
        return data or {}, resp.get("reasoning"), content

    # ---------- 校验 / 阈值 / 置信度 ----------

    def _validate_points(
        self,
        points: list[dict[str, Any]],
        hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """反臆造：evidence_page 必须来自候选证据页；否则降级 low 并标记未核实。"""
        valid_pages = _hit_pages(hits)
        supporting_pages = len(valid_pages)
        out: list[dict[str, Any]] = []
        for p in points:
            if not isinstance(p, dict) or not p.get("code"):
                continue
            point = dict(p)
            level = str(point.get("level") or "low").lower()
            point["level"] = level if level in _LEVELS else "low"
            page = point.get("evidence_page")
            try:
                page = int(page) if page is not None else None
            except (TypeError, ValueError):
                page = None
            verified = page is not None and page in valid_pages
            if page is not None and not verified:
                point["evidence_page"] = None
                point["level"] = "low"
                point["evidence_note"] = "页码未在候选证据中核实，已降级"
                verified = False
            # doc§5.2 置信度：≥2 独立证据页且可定位 → high；1 个可定位 → medium；否则 low
            if verified and supporting_pages >= 2:
                point["confidence"] = "high"
            elif verified:
                point["confidence"] = "medium"
            else:
                point["confidence"] = "low"
                if point["level"] == "high":
                    point["level"] = "medium"
                    point["evidence_note"] = (
                        (point.get("evidence_note") or "") + "；无可核实证据，high 降级 medium"
                    ).strip("；")
            point["skill"] = self.skill_name
            # 服务端启发式可收紧模型 point_kind，防止套话抬分
            point["point_kind"] = classify_legal_point_kind(point)
            out.append(point)
        return out

    def _threshold_checks(
        self,
        features: dict[str, Any],
        points: list[dict[str, Any]],
        hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """确定性阈值兜底：features 已越线但 LLM 未给出对应风险点时自动补。"""
        have = {str(p.get("code") or "").upper() for p in points}
        top_hit = hits[0] if hits else None

        def _add(code: str, level: str, description: str, metric_value: Any) -> None:
            if code in have or any(code.startswith(c.split("_")[0]) and code == c for c in have):
                return
            point = {
                "code": code,
                "level": level,
                "description": description + "（阈值判定自动补充）",
                "legal_basis": None,
                "metric_value": metric_value,
                "evidence_page": (top_hit or {}).get("page"),
                "evidence_excerpt": ((top_hit or {}).get("excerpt") or "")[:200],
                "confidence": "medium" if top_hit else "low",
                "skill": self.skill_name,
                "rule_auto": True,
            }
            point["point_kind"] = classify_legal_point_kind(point)
            points.append(point)
            have.add(code)

        def _num(v: Any) -> float | None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        if self.skill_name == "legal_governance":
            pct = _num(features.get("control_pct"))
            if pct is not None and pct > 50:
                _add(
                    "GOVERNANCE_CONTROL_GT_50",
                    "medium",
                    f"單一股東/一致行動集團控制 {pct:.1f}% (>50%)，存在治理風險",
                    pct,
                )
        elif self.skill_name == "legal_shareholder_rights":
            months = _num(features.get("remaining_months"))
            if features.get("exists_redemption") and months is not None and months < 12:
                _add(
                    "REDEMPTION_HIGH",
                    "high",
                    f"贖回/對賭觸發期限剩餘約 {months:.0f} 個月 (<12個月)",
                    months,
                )
            if features.get("rights_cleared_pre_ipo") is False:
                _add(
                    "RIGHTS_CLEANUP_INCOMPLETE",
                    "high",
                    "上市前投資者特殊權利未完整解除，存在股權清理風險",
                    None,
                )
        elif self.skill_name == "legal_related_party":
            ratio = _num(features.get("max_ratio_pct"))
            if ratio is not None and ratio > 30:
                _add(
                    "RELATED_PARTY_HIGH",
                    "high",
                    f"關連交易佔同類交易比例約 {ratio:.1f}% (>30%)",
                    ratio,
                )
        elif self.skill_name == "legal_contracts_and_ip":
            if features.get("core_tech_self_owned") is False:
                _add(
                    "IP_NOT_SELF_OWNED",
                    "high",
                    "核心技術非發行人自主擁有",
                    None,
                )
        elif self.skill_name == "legal_regulatory_litigation":
            if features.get("major_litigation") is True:
                _add(
                    "LITIGATION_MAJOR",
                    "high",
                    "存在重大訴訟（涉案金額重大）",
                    None,
                )
        return points

    # ---------- 主入口 ----------

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        state: dict[str, Any] = skill_input.params.get("state") or {}
        llm = skill_input.params.get("llm")
        hits, queries_used = await self._collect_evidence(state)

        if not hits:
            return SkillOutput(
                success=True,
                degraded=True,
                degraded_reason="no_evidence",
                data={
                    "skill": self.skill_name,
                    "exists": False,
                    "features": {},
                    "risk_points": [],
                    "negative_findings": [
                        {
                            "code": f"{self.skill_name.upper()}_NO_HIT",
                            "description": "已檢索本專項關鍵詞與章節，未發現相關披露",
                        }
                    ],
                    "reasoning": "候选证据为空：关键词与定向章节检索均无命中。",
                    "evidence": [],
                    "queries_used": queries_used,
                    "confidence": "low",
                },
            )

        if llm is None or not getattr(llm, "available", False):
            return SkillOutput(
                success=False,
                degraded=True,
                degraded_reason="llm_unavailable",
                error=f"{self.skill_name} 需要 LLM 做非结构化抽取，当前不可用",
                data={
                    "skill": self.skill_name,
                    "evidence": [
                        _to_evidence_dict(h, self.skill_name) for h in hits[:5]
                    ],
                    "queries_used": queries_used,
                },
            )

        try:
            extracted, llm_reasoning, raw_content = await self._llm_extract(llm, hits)
        except Exception as exc:
            logger.warning("%s LLM extract failed: %s", self.skill_name, exc)
            return SkillOutput(
                success=False,
                degraded=True,
                degraded_reason="llm_failed",
                error=str(exc),
                data={
                    "skill": self.skill_name,
                    "evidence": [
                        _to_evidence_dict(h, self.skill_name) for h in hits[:5]
                    ],
                    "queries_used": queries_used,
                },
            )
        if not extracted and raw_content.strip():
            # JSON 解析失败（常见于输出截断）：显式降级，让 ReAct 侧可反思重试
            return SkillOutput(
                success=False,
                degraded=True,
                degraded_reason="json_parse_failed",
                error=f"{self.skill_name} LLM 输出无法解析为 JSON（疑似截断），可重试本 skill",
                data={
                    "skill": self.skill_name,
                    "raw_content_excerpt": raw_content[:300],
                    "evidence": [
                        _to_evidence_dict(h, self.skill_name) for h in hits[:5]
                    ],
                    "queries_used": queries_used,
                },
            )

        features = extracted.get("features") if isinstance(extracted.get("features"), dict) else {}
        if self.skill_name == "legal_related_party":
            features = dict(features)
            texts = [
                str(h.get("excerpt") or h.get("content") or "")
                for h in hits
            ]
            if features.get("waiver"):
                texts.append(str(features.get("waiver")))
            ratio_info = resolve_related_party_ratio(texts)
            if features.get("max_ratio_pct") is None and ratio_info.get("ratio_pct") is not None:
                features["max_ratio_pct"] = ratio_info["ratio_pct"]
                features["ratio_source"] = ratio_info.get("ratio_source")
            elif features.get("max_ratio_pct") is None and features.get("waiver"):
                sig = parse_related_party_ratio_signals(str(features.get("waiver")))
                cand = (sig["waiver_pcts"] or sig["listing_rule_pcts"] or [])
                if cand:
                    features["max_ratio_pct"] = max(cand)
                    features["ratio_source"] = "waiver_text"
            if ratio_info.get("listing_rule_pcts"):
                features.setdefault(
                    "listing_rule_pct_max", max(ratio_info["listing_rule_pcts"])
                )
        raw_points = extracted.get("risk_points") if isinstance(extracted.get("risk_points"), list) else []
        points = self._validate_points(raw_points, hits)
        points = self._threshold_checks(features, points, hits)
        confidences = [p.get("confidence") for p in points]
        overall_conf = (
            "high"
            if confidences and all(c == "high" for c in confidences)
            else ("low" if not points or any(c == "low" for c in confidences) else "medium")
        )
        return SkillOutput(
            success=True,
            data={
                "skill": self.skill_name,
                "exists": bool(points) or bool(features),
                "features": features,
                "risk_points": points,
                "negative_findings": (
                    extracted.get("negative_findings")
                    if isinstance(extracted.get("negative_findings"), list)
                    else []
                ),
                "reasoning": str(extracted.get("reasoning") or ""),
                "llm_reasoning_excerpt": (llm_reasoning or "")[:400] or None,
                "evidence": [_to_evidence_dict(h, self.skill_name) for h in hits],
                "queries_used": queries_used,
                "confidence": overall_conf,
            },
        )


def build_legal_skills() -> dict[str, LegalSkill]:
    return {n: LegalSkill(n) for n in LEGAL_SKILL_NAMES}


# ---------- 旧 stub 接口（兼容保留） ----------


class LegalSkillStub(BaseSkill):
    """预设骨架（已由 LegalSkill 取代，仅兼容保留）。"""

    def __init__(self, skill_name: str) -> None:
        meta = LEGAL_SKILL_META[skill_name]
        self.skill_name = skill_name
        self.version = "0.1.0-stub"
        self.description = meta["description"]
        self.gpt_map = meta["gpt_map"]
        self.prompt_template = LEGAL_DIMENSION_PROMPTS[skill_name]

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=False,
            degraded=True,
            degraded_reason="stub",
            error=f"{self.skill_name} stub 已废弃，请使用 LegalSkill（build_legal_skills）。",
            data={
                "skill": self.skill_name,
                "gpt_map": self.gpt_map,
                "prompt_preview": self.prompt_template[:200],
                "legal_system": LEGAL_SYSTEM[:120],
                "submit_schema_hint": LEGAL_SUBMIT_SCHEMA[:160],
                "params": skill_input.params,
            },
        )


def build_legal_skill_stubs() -> list[LegalSkillStub]:
    return [LegalSkillStub(n) for n in LEGAL_SKILL_NAMES]


def register_legal_skill_stubs(registry: object) -> None:
    for skill in build_legal_skill_stubs():
        registry.register(skill)  # type: ignore[attr-defined]
