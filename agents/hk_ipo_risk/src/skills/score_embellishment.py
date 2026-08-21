from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.config import load_master_rules
from src.llm.master_prompts import MASTER_EMBELLISHMENT_SYSTEM
from src.models.master import (
    EmbellishmentCoverage,
    EmbellishmentHighRiskExcerpt,
    EmbellishmentHit,
    EmbellishmentResult,
)
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.llm_json import llm_json
from src.skills.master_cards import first_pages_text
from src.tools.retrieval_tool import _load_section_map_module

TARGET_SECTIONS = (
    "summary",
    "risk_factors",
    "industry_overview",
    "business",
    "financial_information",
)
DIMENSIONS = (
    "marketing_language",
    "ranking_manipulation",
    "concept_packaging",
    "obscurity",
    "key_info_postponed",
)
DIMENSION_NAMES = {
    "marketing_language": "过度营销语言",
    "ranking_manipulation": "行业排名操纵",
    "concept_packaging": "概念包装",
    "obscurity": "表述晦涩",
    "key_info_postponed": "关键信息后置",
}
NEGATIVE_EMBELLISHMENT_FINDINGS = (
    "不構成粉飾", "不构成粉饰", "未構成粉飾", "未构成粉饰", "未淡化風險", "未淡化风险",
    "有充分支撐", "有充分支撑", "已充分披露", "已妥善整改", "不屬於粉飾", "不属于粉饰",
)

RISK_TACTICS = {
    "risk_minimization",
    "vague_qualification",
    "quantification_omission",
    "boilerplate_dilution",
    "key_fact_burial",
    "contradictory_framing",
}
DEFAULT_MARKETING_TERMS = (
    "領先", "领先", "第一", "最大", "唯一", "最佳", "卓越", "革命性", "革命性",
    "顛覆", "颠覆", "首屈一指", "世界級", "世界级", "領軍", "领军",
)
DEFAULT_CONCEPT_TERMS = (
    "人工智能", "AI賦能", "AI赋能", "科技賦能", "科技赋能", "智能化", "數字化生態",
    "数字化生态", "平台化", "生態圈", "生态圈", "新零售", "顛覆性", "颠覆性",
)
STRONG_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("risk_minimization", r"(?:影響|影响)(?:相對|相对)?有限|並無重大|并无重大|不會造成重大|不会造成重大|並不重大|并不重大|無實質影響|无实质影响|風險可控|风险可控"),
    ("vague_qualification", r"在一定程度上|於適當時候|于适当时候|可能不時|可能不时|若干(?:重大)?事項|若干(?:重大)?事项"),
    ("key_fact_burial", r"(?:然而|惟|但是|但|儘管|尽管).{0,180}(?:虧損|亏损|負債|负债|贖回|赎回|違規|违规|訴訟|诉讼|中止|終止|终止|重大不利)"),
)
QUANT_RISK_TERMS = (
    "虧損", "亏损", "現金流", "现金流", "流動性", "流动性", "贖回", "赎回",
    "負債", "负债", "客戶集中", "客户集中", "供應商集中", "供应商集中",
    "關連交易", "关联交易", "訴訟", "诉讼", "處罰", "处罚",
)
RANKING_RE = re.compile(
    r"(?:排名|排行|位列|位居|名列|市場份額|市场份额).{0,100}(?:第[一二三四五六七八九十\d]+|首位|領先|领先)"
    r"|(?:第[一二三四五六七八九十\d]+|最大|領先|领先).{0,100}(?:市場|市场|行業|行业|品牌|供應商|供应商)",
    re.I | re.S,
)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|億|亿|萬|万|年|月|日|港元|人民幣|人民币)")
MANDATORY_FRONT_TERMS = (
    "全球發售", "全球发售", "重要提示", "預期時間表", "预期时间表", "申請程序", "申请程序",
    "聯交所", "联交所", "證券及期貨", "证券及期货", "概不表示", "概不保證", "概不保证",
)
SUBSTANTIVE_FRONT_TERMS = (
    "主要業務", "主要业务", "商業模式", "商业模式", "核心產品", "核心产品", "收入來源",
    "收入来源", "客戶", "客户", "供應商", "供应商", "風險因素", "风险因素",
)


def buzzword_hits(text: str, words: list[str]) -> list[str]:
    found: list[str] = []
    folded = str(text or "").casefold()
    for word in words:
        value = str(word or "").strip()
        if value and value.casefold() in folded and value not in found:
            found.append(value)
    return found


def _load_pages(parse_json: Path | str | None) -> list[dict[str, Any]]:
    if not parse_json:
        return []
    path = Path(parse_json)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("pages") or data.get("content") or []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _page_number(page: dict[str, Any], fallback: int) -> int:
    try:
        value = int(page.get("page") or page.get("page_number") or fallback)
    except (TypeError, ValueError):
        value = fallback
    return max(1, value)


def _element_texts(page: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for element in page.get("elements") or page.get("items") or []:
        if not isinstance(element, dict):
            continue
        category = str(element.get("category") or "text")
        if category not in {"text", "title", "header", "table", "table_caption", "table_footnote"}:
            continue
        value = str(element.get("text") or element.get("content") or element.get("html") or "")
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            values.append(value)
    if not values:
        value = re.sub(r"\s+", " ", str(page.get("text") or page.get("content") or "")).strip()
        if value:
            values.append(value)
    return values


def _section_lookup(parse_json: Path | str, pages: list[dict[str, Any]]) -> tuple[dict[int, str], dict[str, tuple[int, int]]]:
    try:
        section_map = _load_section_map_module().build_section_map_from_parse(parse_json)
    except Exception:
        return {}, {}
    page_to_section = {int(page): str(section) for page, section in section_map.page_to_section.items()}
    spans = {
        str(span.canonical_section): (int(span.start_page), int(span.end_page))
        for span in section_map.section_spans
    }
    return page_to_section, spans


def _normal_key(text: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", str(text or "").casefold())[:180]


def _candidate(
    *,
    page: int,
    section: str,
    text: str,
    dimension: str,
    tactic: str,
    rule: str,
    priority: int,
    concept_family: str = "",
) -> dict[str, Any]:
    excerpt = text[:360]
    return {
        "candidate_id": "",
        "page": page,
        "section": section,
        "dimension_hint": dimension,
        "tactic_hint": tactic,
        "rule": rule,
        "priority": priority,
        "concept_family": concept_family,
        "excerpt": excerpt,
        "context": text[:700],
    }


def _scan_candidates(
    pages: list[dict[str, Any]],
    *,
    page_to_section: dict[int, str],
    first_pages: int,
    marketing_terms: list[str],
    concept_terms: list[str],
) -> tuple[list[dict[str, Any]], list[int], list[int]]:
    candidates: list[dict[str, Any]] = []
    analyzed_pages: list[int] = []
    risk_pages: list[int] = []
    first_blob: list[str] = []
    seen: set[tuple[str, str]] = set()
    risk_paragraphs: dict[str, list[tuple[int, str]]] = {}

    for fallback, page_data in enumerate(pages, start=1):
        page = _page_number(page_data, fallback)
        analyzed_pages.append(page)
        section = page_to_section.get(page) or ("front_matter" if page <= first_pages else "other")
        texts = _element_texts(page_data)
        if page <= first_pages:
            first_blob.extend(texts)
        if section == "risk_factors":
            risk_pages.append(page)
        for text in texts:
            if section == "risk_factors" and len(_normal_key(text)) >= 120:
                risk_paragraphs.setdefault(_normal_key(text)[:120], []).append((page, text))
            found: list[dict[str, Any]] = []
            terms = [term for term in marketing_terms if term.casefold() in text.casefold()]
            if terms:
                found.append(_candidate(page=page, section=section, text=text, dimension="marketing_language", tactic="unsupported_superlative", rule="marketing", priority=3 if section == "risk_factors" else 2))
            if RANKING_RE.search(text):
                found.append(_candidate(page=page, section=section, text=text, dimension="ranking_manipulation", tactic="niche_ranking", rule="ranking", priority=4))
            concepts = [term for term in concept_terms if term.casefold() in text.casefold()]
            if concepts:
                found.append(_candidate(page=page, section=section, text=text, dimension="concept_packaging", tactic="unsupported_concept", rule="concept", priority=3, concept_family=concepts[0]))
            if section == "risk_factors":
                for tactic, pattern in STRONG_RISK_PATTERNS:
                    if re.search(pattern, text, re.I | re.S):
                        found.append(_candidate(page=page, section=section, text=text, dimension="obscurity", tactic=tactic, rule="obscurity", priority=6))
                if any(term in text for term in QUANT_RISK_TERMS) and "重大不利" in text and not NUMBER_RE.search(text):
                    found.append(_candidate(page=page, section=section, text=text, dimension="obscurity", tactic="quantification_omission", rule="obscurity", priority=5))
            # 同一原文只能有一个主计分类别，优先风险弱化，其次排名、概念、营销。
            # 这样“排名第一”不会同时按 ranking 与 marketing 重复加分。
            if found:
                rule_priority = {"obscurity": 4, "ranking": 3, "concept": 2, "marketing": 1}
                found = [max(found, key=lambda item: (rule_priority.get(str(item["rule"]), 0), int(item["priority"])))]
            for item in found:
                key = ("excerpt", _normal_key(item["excerpt"]))
                if not key[1] or key in seen:
                    continue
                seen.add(key)
                candidates.append(item)

    for occurrences in risk_paragraphs.values():
        if len(occurrences) < 3:
            continue
        page, text = occurrences[0]
        item = _candidate(
            page=page,
            section="risk_factors",
            text=text,
            dimension="obscurity",
            tactic="boilerplate_dilution",
            rule="obscurity",
            priority=6,
        )
        key = ("excerpt", _normal_key(item["excerpt"]))
        if key[1] and key not in seen:
            seen.add(key)
            candidates.append(item)

    front_text = " ".join(first_blob)
    has_promo = any(term.casefold() in front_text.casefold() for term in marketing_terms)
    has_substance = any(term in front_text for term in SUBSTANTIVE_FRONT_TERMS)
    mandatory_density = sum(front_text.count(term) for term in MANDATORY_FRONT_TERMS)
    if has_promo and not has_substance and mandatory_density < 8 and first_blob:
        candidates.append(
            _candidate(
                page=1,
                section="front_matter",
                text=" ".join(first_blob)[:700],
                dimension="key_info_postponed",
                tactic="promotional_front_loading",
                rule="key_info_postponed",
                priority=5,
            )
        )

    candidates.sort(key=lambda item: (-int(item["priority"]), int(item["page"]), item["rule"], item["excerpt"]))
    for index, item in enumerate(candidates, start=1):
        item["candidate_id"] = f"emb-{index:04d}"
    return candidates, sorted(set(analyzed_pages)), sorted(set(risk_pages))


def _expert_digest(finance_cards: Any, legal_cards: Any) -> dict[str, Any]:
    def trim(cards: Any) -> dict[str, Any]:
        if not isinstance(cards, dict):
            return {}
        claims: list[dict[str, Any]] = []
        for claim in cards.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            evidence = []
            for ref in claim.get("evidence") or []:
                if isinstance(ref, dict):
                    evidence.append({"page": ref.get("page"), "excerpt": str(ref.get("excerpt") or "")[:220]})
            claims.append({
                "claim_id": claim.get("claim_id"),
                "statement": str(claim.get("statement") or claim.get("claim") or claim.get("summary") or "")[:260],
                "evidence": evidence[:2],
            })
        return {"summary": str(cards.get("summary") or "")[:400], "claims": claims[:8]}
    return {"finance": trim(finance_cards), "legal": trim(legal_cards)}


def _assessment_prompt(candidates: list[dict[str, Any]], expert_digest: dict[str, Any]) -> str:
    public_candidates = [
        {
            key: item.get(key)
            for key in ("candidate_id", "page", "section", "dimension_hint", "tactic_hint", "rule", "excerpt", "context")
        }
        for item in candidates
    ]
    return (
        "【候选原文】\n"
        + json.dumps(public_candidates, ensure_ascii=False)
        + "\n\n【财务/法务交叉核验证据】\n"
        + json.dumps(expert_digest, ensure_ascii=False)
        + "\n\n逐条判断。只能引用 candidate_id，不得另造原文或页码。普通法定风险措辞不能单独定为粉饰。"
    )


def _as_choice(value: Any, allowed: set[str], default: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in allowed else default


def _score_assessments(
    candidates: list[dict[str, Any]], assessments: list[dict[str, Any]]
) -> tuple[int, dict[str, Any], list[EmbellishmentHit], list[EmbellishmentHighRiskExcerpt]]:
    by_id = {str(item["candidate_id"]): item for item in candidates}
    accepted: list[tuple[dict[str, Any], dict[str, Any], int]] = []
    concept_families: set[str] = set()
    seen_candidates: set[str] = set()

    for raw in assessments:
        if not isinstance(raw, dict):
            continue
        candidate_id = str(raw.get("candidate_id") or "")
        candidate = by_id.get(candidate_id)
        if candidate is None or candidate_id in seen_candidates:
            continue
        seen_candidates.add(candidate_id)
        severity = _as_choice(raw.get("severity"), {"high", "medium", "low"}, "low")
        confidence = _as_choice(raw.get("confidence"), {"high", "medium", "low"}, "low")
        support = _as_choice(
            raw.get("support_status"),
            {"supported", "weakly_supported", "unsupported", "contradictory", "unknown"},
            "unknown",
        )
        reason = str(raw.get("reason") or "")
        # 结构字段与自然语言理由冲突时，以明确的“不构成粉饰”结论为准，禁止误加分。
        if any(marker in reason for marker in NEGATIVE_EMBELLISHMENT_FINDINGS):
            severity = "low"
            support = "supported"
        if support == "supported" or confidence != "high" or severity not in {"high", "medium"}:
            contribution = 0
        elif candidate["rule"] == "marketing":
            contribution = 1
        elif candidate["rule"] == "ranking":
            contribution = 2
        elif candidate["rule"] == "concept":
            family = str(candidate.get("concept_family") or candidate_id)
            contribution = 0 if family in concept_families or len(concept_families) >= 2 else 1
            if contribution:
                concept_families.add(family)
        elif candidate["rule"] == "key_info_postponed":
            contribution = 2
        else:
            try:
                contribution = int(raw.get("score_contribution") or 1)
            except (TypeError, ValueError):
                contribution = 1
            contribution = max(1, min(3, contribution))
        normalized = dict(raw)
        normalized.update({"severity": severity, "confidence": confidence, "support_status": support})
        accepted.append((candidate, normalized, contribution))

    dimension_scores = {dimension: 0 for dimension in DIMENSIONS}
    evidence_ids = {dimension: [] for dimension in DIMENSIONS}
    hits: list[EmbellishmentHit] = []
    high: list[EmbellishmentHighRiskExcerpt] = []
    for candidate, assessment, contribution in accepted:
        # 候选规则决定主维度；LLM 只能研判语境，不能把风险弱化任意改成概念包装。
        dimension = str(candidate["dimension_hint"])
        dimension_scores[dimension] += contribution
        if contribution:
            evidence_ids[dimension].append(candidate["candidate_id"])
        if contribution:
            hits.append(EmbellishmentHit(page=candidate["page"], excerpt=candidate["excerpt"], dimension=dimension, note=str(assessment.get("reason") or "")))
        if candidate["rule"] != "key_info_postponed" and assessment["severity"] == "high" and assessment["confidence"] == "high" and (contribution > 0 or assessment["support_status"] == "contradictory"):
            cross = assessment.get("cross_evidence") if isinstance(assessment.get("cross_evidence"), list) else []
            high.append(
                EmbellishmentHighRiskExcerpt(
                    candidate_id=candidate["candidate_id"],
                    dimension=dimension,
                    tactic=str(assessment.get("tactic") or candidate["tactic_hint"]),
                    section=str(candidate["section"]),
                    page=int(candidate["page"]),
                    excerpt=str(candidate["excerpt"]),
                    context=str(candidate["context"]),
                    reason=str(assessment.get("reason") or ""),
                    support_status=assessment["support_status"],
                    score_contribution=contribution,
                    severity="high",
                    confidence="high",
                    cross_evidence=[item for item in cross if isinstance(item, dict)][:4],
                )
            )
    total = min(10, sum(dimension_scores.values()))
    dimensions = {
        dimension: {
            "name": DIMENSION_NAMES[dimension],
            "score": min(10, dimension_scores[dimension]),
            "finding": f"识别到 {len(evidence_ids[dimension])} 条有效计分证据",
            "evidence_ids": evidence_ids[dimension],
        }
        for dimension in DIMENSIONS
    }
    high.sort(key=lambda item: (0 if item.section == "risk_factors" else 1, -item.score_contribution, item.page or 10**9, item.candidate_id))
    return total, dimensions, hits, high


class ScoreEmbellishmentSkill(BaseSkill):
    skill_name = "master_score_embellishment"
    version = "0.2.0"
    description = "全书规则扫描并重点研判风险因素，按第四章可复核计分"

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        params = skill_input.params
        rules = load_master_rules()
        config = rules.get("embellishment") or {}
        first_page_count = int(config.get("first_pages") or 5)
        parse_json = params.get("parse_json")
        pages = _load_pages(parse_json)
        if not pages:
            result = EmbellishmentResult(
                status="not_available",
                reason="招股书解析文本不可用，无法评估文本粉饰度。",
                limitations=["full_parse.json 缺失、格式错误或不含可读页面。"],
            )
            return SkillOutput(
                success=True,
                data={"embellishment": result.model_dump(), "prompt_user": "", "llm_ok": False},
                degraded=True,
                degraded_reason="embellishment_parse_unavailable",
            )

        page_to_section, spans = _section_lookup(parse_json, pages)
        marketing_terms = list(dict.fromkeys([*(config.get("buzzwords") or []), *DEFAULT_MARKETING_TERMS]))
        concept_terms = list(dict.fromkeys([*(config.get("concept_words") or []), *DEFAULT_CONCEPT_TERMS]))
        candidates, analyzed_pages, risk_pages = _scan_candidates(
            pages,
            page_to_section=page_to_section,
            first_pages=first_page_count,
            marketing_terms=marketing_terms,
            concept_terms=concept_terms,
        )
        candidate_count = len(candidates)
        max_candidates = int(config.get("max_candidates") or 0)
        selected = candidates if max_candidates <= 0 else candidates[:max_candidates]
        limitations: list[str] = []
        if candidate_count > len(selected):
            limitations.append(f"规则扫描命中 {candidate_count} 条候选，仅对优先级最高的 {len(selected)} 条完成模型复核。")
        missing_sections = [section for section in TARGET_SECTIONS if section not in spans]
        if "risk_factors" in missing_sections:
            limitations.append("未可靠定位风险因素章节，无法确认该章节完整覆盖。")
        other_missing = [section for section in missing_sections if section != "risk_factors"]
        if other_missing:
            limitations.append("未可靠定位重点章节：" + "、".join(other_missing) + "。")

        llm = params.get("llm")
        batch_size = max(1, int(config.get("batch_size") or 12))
        debate_config = rules.get("debate") or {}
        max_tokens = int(debate_config.get("embellishment_max_tokens") or 4096)
        reasoning_max_tokens = int(debate_config.get("embellishment_reasoning_max_tokens") or 512)
        digest = _expert_digest(params.get("finance_cards"), params.get("legal_cards"))
        assessments: list[dict[str, Any]] = []
        prompt_parts: list[str] = []
        outputs: list[dict[str, Any]] = []
        for start in range(0, len(selected), batch_size):
            batch = selected[start : start + batch_size]
            user = _assessment_prompt(batch, digest)
            prompt_parts.append(user)
            out = await llm_json(
                llm,
                [
                    {"role": "system", "content": MASTER_EMBELLISHMENT_SYSTEM},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                reasoning_max_tokens=reasoning_max_tokens,
                required_keys=("assessments",),
            )
            outputs.append(out)
            data = out.get("data") or {}
            assessments.extend(item for item in (data.get("assessments") or []) if isinstance(item, dict))

        llm_ok = bool(selected) and bool(outputs) and all(out.get("ok") for out in outputs)
        if not selected:
            llm_ok = True
        evaluated_ids = {str(item.get("candidate_id") or "") for item in assessments}
        evaluated_count = len(evaluated_ids & {str(item["candidate_id"]) for item in selected})
        if selected and evaluated_count < len(selected):
            limitations.append(f"模型仅返回 {evaluated_count}/{len(selected)} 条有效候选判断。")

        score, dimensions, hits, high = _score_assessments(selected, assessments)
        complete = llm_ok and evaluated_count == len(selected) and candidate_count == len(selected) and not missing_sections
        status = "complete" if complete else "partial"
        if not selected and not missing_sections:
            status = "complete"
        level = "high" if score >= 7 else "medium" if score >= 4 else "low"
        if status == "complete":
            reason = f"完成全书规则扫描及重点章节复核，文本粉饰度 {score}/10（{level}）。"
        else:
            reason = f"文本粉饰度暂计 {score}/10（{level}），但分析覆盖或模型复核不完整，结论仅供参考。"
        hints = buzzword_hits(" ".join(item["excerpt"] for item in candidates), marketing_terms)
        coverage = EmbellishmentCoverage(
            first_pages=[page for page in analyzed_pages if page <= first_page_count],
            sections=[section for section in TARGET_SECTIONS if section in spans],
            pages_analyzed=analyzed_pages,
            risk_factor_pages=risk_pages,
            candidate_count=candidate_count,
            evaluated_candidate_count=evaluated_count,
            verified_excerpt_count=len(high),
        )
        result = EmbellishmentResult(
            score=score,
            level=level,
            status=status,
            reason=reason,
            hits=hits,
            dimensions=dimensions,
            buzzword_hints=hints,
            coverage=coverage,
            high_risk_excerpts=high,
            limitations=limitations,
        )
        logger_ = params.get("run_logger")
        if logger_ is not None:
            logger_.master_step(
                event="embellishment",
                utterance=result.reason,
                duration_ms=sum(int(out.get("duration_ms") or 0) for out in outputs),
                reasoning="\n".join(str(out.get("reasoning") or "") for out in outputs)[:4000],
                usage={"batches": [out.get("usage") for out in outputs]},
                extra={
                    "score": score,
                    "level": level,
                    "status": status,
                    "candidate_count": candidate_count,
                    "risk_factor_pages": risk_pages,
                    "verified_excerpt_count": len(high),
                },
                model=next((out.get("model") for out in outputs if out.get("model")), None),
            )
        return SkillOutput(
            success=True,
            data={
                "embellishment": result.model_dump(),
                "prompt_user": "\n\n--- batch ---\n\n".join(prompt_parts),
                "llm_ok": llm_ok,
                "front_pages_text": first_pages_text(parse_json, n_pages=first_page_count, page_char_cap=int(config.get("page_char_cap") or 1200)),
            },
            degraded=status != "complete",
            degraded_reason="; ".join(limitations) or (None if status == "complete" else "embellishment_partial"),
        )
