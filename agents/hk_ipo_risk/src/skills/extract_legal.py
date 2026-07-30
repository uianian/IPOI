from __future__ import annotations

import logging
import re
from typing import Any

from src.models.evidence import EvidenceRef
from src.tools.retrieval_tool import iter_all_text_hits, iter_field_hits

logger = logging.getLogger(__name__)

_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# 3.1 定向检索词（可转换可赎回优先股 / 股东协议 / 特别权利）
_REDEMPTION_KEYWORDS = [
    "赎回", "贖回", "对赌", "對賭", "回购", "回購", "优先股", "優先股",
    "领售", "領售", "撤资", "撤資", "贖回權", "可換股", "可转换可赎回", "可轉換可贖回",
    "股东协议", "股東協議", "特别权利", "特別權利", "赎回权终止", "特別權利終止",
]
_REDEMPTION_STRONG = [
    "對賭", "对赌", "優先股", "优先股", "贖回權", "赎回权",
    "要求公司贖回", "要求公司赎回", "有權要求", "有权要求",
    "撤資權益", "撤资权益", "領售", "领售", "回購義務", "回购义务",
    "可轉換可贖回", "可转换可赎回", "特別權利", "特别权利",
]
_REDEMPTION_NOISE = ["理財產品", "理财产品", "到期及贖回", "到期及赎回", "購回股份的一般授權"]

# 3.2：优先关连交易正文，排除购回授权噪声
_RELATED_PREFER = ["關連交易", "关联交易", "持續關連", "持续关连", "關連交易豁免", "关联交易豁免", "非豁免關連"]
_RELATED_NOISE = [
    "購回股份的一般授權", "购回股份的一般授权",
    "知會本公司", "知会本公司", "目前有意在購回", "目前有意在购回",
    "承諾向本公司出售股份",
]

_CONC_KEYWORDS = [
    "前五大客户", "五大客戶", "最大客户", "最大客戶",
    "前五大供應商", "前五大供应商", "佔總收入", "占总收入", "佔總採購", "占总采购",
]


def _hit_to_evidence(h: dict[str, Any], field_code: str | None = None) -> EvidenceRef:
    excerpt = h.get("excerpt") or h.get("content") or ""
    excerpt = excerpt.replace("\n", " ").strip()
    if len(excerpt) > 200:
        excerpt = excerpt[:200]
    cat = (h.get("category") or "").lower()
    # text/html 均可作为表格证据喂给 Agent（上游解析形态不强制）
    st = "table" if cat == "table" or "<table" in excerpt.lower() or "%" in excerpt else "text"
    return EvidenceRef(
        page=h.get("page") or h.get("page_number"),
        excerpt=excerpt,
        source_type=st if st in ("table", "text") else "unknown",
        field_code=field_code or h.get("field_code"),
        confidence=float(h.get("score") or 0.5),
    )


def _pages_from_hits(hits: list[dict[str, Any]]) -> list[int]:
    pages: list[int] = []
    for h in hits:
        p = h.get("page") or h.get("page_number")
        if p is not None:
            try:
                pages.append(int(p))
            except (TypeError, ValueError):
                pass
    return sorted(set(pages))


def _collect_hits(
    bundle: dict[str, Any],
    field_codes: list[str],
    keywords: list[str],
    extra_hits: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for fc in field_codes:
        hits.extend(iter_field_hits(bundle, fc))
    for h in iter_all_text_hits(bundle):
        text = h.get("excerpt") or h.get("content") or ""
        if any(k in text for k in keywords):
            hits.append(h)
    for q in bundle.get("per_query") or []:
        name = (q.get("name") or q.get("field_code") or "").lower()
        label = (q.get("label") or q.get("query_label") or "").lower()
        if any(
            x in name or x in label
            for x in [
                "redeem",
                "gamble",
                "related",
                "concentr",
                "pipeline",
                "客户",
                "关联",
                "赎回",
                "对赌",
                "關連",
                "供應商",
                "管线",
                "管線",
                "临床",
            ]
        ):
            for h in q.get("hits") or []:
                if "excerpt" not in h and "content" in h:
                    h = {**h, "excerpt": h["content"]}
                hits.append(h)
    if extra_hits:
        for h in extra_hits:
            text = h.get("excerpt") or h.get("content") or ""
            if any(k in text for k in keywords):
                hits.append(h)
    return hits


def _parse_pct_from_table_blob(text: str) -> list[float]:
    """从供应商/客户表（HTML 或纯文本）抽出比例列数值。"""
    pcts = [float(x) for x in _PCT_RE.findall(text)]
    # HTML 单元格末列常见无 % 号：... <td>426,084</td><td>5.0</td></tr>
    if "供應商" in text or "供应商" in text or "客戶" in text or "客户" in text:
        for m in re.finditer(
            r"<td[^>]*>\s*([\d,]+(?:\.\d+)?)\s*</td>\s*<td[^>]*>\s*(\d+(?:\.\d+)?)\s*</td>\s*</tr>",
            text,
            flags=re.I,
        ):
            v = float(m.group(2))
            if 0 < v <= 100:
                pcts.append(v)
        # 退化：行末独立小数
        if not pcts:
            for m in re.finditer(r"<td[^>]*>\s*(\d+(?:\.\d+)?)\s*</td>\s*</tr>", text, flags=re.I):
                v = float(m.group(1))
                if 0 < v <= 100:
                    pcts.append(v)
    if not pcts and "比例" in text:
        for m in re.finditer(r">\s*(\d+(?:\.\d+)?)\s*<", text):
            v = float(m.group(1))
            if 0 < v <= 100:
                pcts.append(v)
    if not pcts:
        for m in re.finditer(r"(?:比例|%)[^\d]{0,8}(\d+(?:\.\d+)?)", text):
            v = float(m.group(1))
            if 0 < v <= 100:
                pcts.append(v)
    return pcts


def extract_redemption(
    bundle: dict[str, Any],
    extra_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw_hits = _collect_hits(
        bundle,
        ["REDEMPTION_CLAUSE", "gamble_redemption"],
        _REDEMPTION_KEYWORDS,
        extra_hits=extra_hits,
    )
    strong: list[dict[str, Any]] = []
    filtered_noise = 0
    for h in raw_hits:
        text = h.get("excerpt") or h.get("content") or ""
        if any(n in text for n in _REDEMPTION_NOISE) and not any(p in text for p in _REDEMPTION_STRONG):
            filtered_noise += 1
            continue
        if any(p in text for p in _REDEMPTION_STRONG):
            strong.append(h)
    exists = len(strong) > 0
    remaining_months = None
    rate = None
    joined = " ".join((h.get("excerpt") or "")[:300] for h in strong[:5])
    m_rate = re.search(r"年[化利率息]\s*(\d+(?:\.\d+)?)\s*%|年利率\s*(\d+(?:\.\d+)?)\s*%", joined)
    if m_rate:
        rate = float(m_rate.group(1) or m_rate.group(2))
    m_month = re.search(r"(\d+)\s*个?月内|於\s*(\d+)\s*個月", joined)
    if m_month:
        remaining_months = int(m_month.group(1) or m_month.group(2))
    high = exists and remaining_months is not None and remaining_months < 12
    medium = exists and not high
    evidences = [_hit_to_evidence(h, "REDEMPTION_CLAUSE") for h in strong[:5]]
    pages_scanned = _pages_from_hits(raw_hits)
    search_log = {
        "keywords_tried": _REDEMPTION_KEYWORDS,
        "pages_scanned": pages_scanned,
        "raw_hits": len(raw_hits),
        "filtered_noise": filtered_noise,
        "strong_hits": len(strong),
        "note": (
            "已检索无命中强对赌/赎回/优先股模式"
            if not exists
            else "命中对赌/赎回相关披露"
        ),
    }
    return {
        "exists": exists,
        "trigger_condition": None,
        "redemption_price_or_rate": rate,
        "amount": None,
        "remaining_months": remaining_months,
        "redemption_high": high,
        "redemption_medium": medium,
        "evidence": [e.model_dump() for e in evidences],
        "evidence_strength": "high" if len(evidences) >= 2 else ("medium" if evidences else "low"),
        "search_log": search_log,
    }


def extract_related_party(
    bundle: dict[str, Any],
    extra_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    keywords = _RELATED_PREFER + ["关联方", "關連方", "核心關連"]
    hits = _collect_hits(bundle, ["RELATED_PARTY", "related_party"], keywords, extra_hits=extra_hits)
    prefer: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    for h in hits:
        text = h.get("excerpt") or h.get("content") or ""
        if any(n in text for n in _RELATED_NOISE) and not any(p in text for p in _RELATED_PREFER):
            continue
        if any(p in text for p in _RELATED_PREFER):
            prefer.append(h)
        elif any(k in text for k in ["關連", "关联"]):
            weak.append(h)
    strong = prefer or weak
    exists = len(strong) > 0
    ratios: list[float] = []
    for h in strong[:10]:
        text = h.get("excerpt") or ""
        ratios.extend(_parse_pct_from_table_blob(text))
    max_ratio = max(ratios) if ratios else None
    high = max_ratio is not None and max_ratio > 30
    evidences = [_hit_to_evidence(h, "RELATED_PARTY") for h in strong[:5]]
    return {
        "exists": exists,
        "ratio_pct": max_ratio,
        "related_party_ratio_gt_30": high,
        "related_party_rising": False,
        "evidence": [e.model_dump() for e in evidences],
        "evidence_strength": "high" if prefer and len(evidences) >= 2 else (
            "medium" if evidences else "low"
        ),
        "theme_filter": {
            "prefer_hits": len(prefer),
            "weak_hits": len(weak),
            "noise_excluded": True,
        },
    }


def extract_concentration(
    bundle: dict[str, Any],
    extra_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hits = _collect_hits(
        bundle,
        ["CONCENTRATION", "concentration", "customer"],
        _CONC_KEYWORDS + ["供應商", "供应商", "客戶", "客户"],
        extra_hits=extra_hits,
    )
    strong: list[dict[str, Any]] = []
    for h in hits:
        text = h.get("excerpt") or h.get("content") or ""
        if any(k in text for k in _CONC_KEYWORDS) or (
            ("供應商" in text or "供应商" in text or "客戶" in text or "客户" in text)
            and ("%" in text or "比例" in text or "供應商A" in text or "供应商A" in text or re.search(r"\d+\.\d+\s*</td>\s*</tr>", text))
        ):
            strong.append(h)
    # 优先带数据行的片段（含 供應商A / 小数比例），表头排后
    def _richness(h: dict[str, Any]) -> int:
        t = h.get("excerpt") or h.get("content") or ""
        score = 0
        if "供應商A" in t or "供应商A" in t:
            score += 5
        score += len(_parse_pct_from_table_blob(t))
        return score
    strong.sort(key=_richness, reverse=True)
    exists = len(strong) > 0

    top1_customer = None
    top5_customer = None
    top1_supplier = None
    top5_supplier = None
    all_supplier_pcts: list[float] = []
    all_customer_pcts: list[float] = []

    def _nearby_pcts(text: str, labels: list[str]) -> list[float]:
        starts = [text.find(label) for label in labels if text.find(label) >= 0]
        if not starts:
            return []
        segment = text[min(starts): min(starts) + 260]
        # “前五大…分别占…” and “同期，最大供应商…” often share one
        # paragraph. Do not add percentages from different metrics/years.
        for boundary in ["同期", "最大供應商", "最大供应商", "最大客戶", "最大客户"]:
            pos = segment.find(boundary, 2)
            if pos > 0:
                segment = segment[:pos]
                break
        return [float(value) for value in _PCT_RE.findall(segment)]

    for h in strong[:15]:
        text = h.get("excerpt") or h.get("content") or ""
        pcts = _parse_pct_from_table_blob(text)
        is_supplier = any(k in text for k in ["供應商", "供应商", "採購", "采购"])
        is_customer = any(k in text for k in ["客戶", "客户", "收入"])
        if is_supplier:
            all_supplier_pcts.extend(pcts)
        if is_customer:
            all_customer_pcts.extend(pcts)
        if any(k in text for k in ["最大客户", "最大客戶", "单一客户", "單一客戶"]) and pcts:
            nearby = _nearby_pcts(text, ["最大客户", "最大客戶", "单一客户", "單一客戶"])
            top1_customer = top1_customer or (max(nearby) if nearby else pcts[0])
        if any(k in text for k in ["前五大客戶", "前五大客户", "五大客戶", "五大客户"]) and pcts:
            nearby = _nearby_pcts(text, ["前五大客戶", "前五大客户", "五大客戶", "五大客户"])
            top5_customer = top5_customer or max(nearby or pcts)
        if any(k in text for k in ["前五大供應商", "前五大供应商"]) and pcts:
            nearby = _nearby_pcts(text, ["前五大供應商", "前五大供应商"])
            top5_supplier = top5_supplier or max(nearby or pcts)
        if any(k in text for k in ["最大供應商", "最大供应商"]) and pcts:
            nearby = _nearby_pcts(text, ["最大供應商", "最大供应商"])
            top1_supplier = top1_supplier or max(nearby or pcts)

    if all_supplier_pcts and top1_supplier is None:
        # 排名表各行占比：最大=top1，合计可近似 sum（若 sum<=100）
        top1_supplier = max(all_supplier_pcts)
    if all_supplier_pcts and top5_supplier is None:
        s = sum(all_supplier_pcts)
        top5_supplier = round(s, 2) if s <= 100 else top1_supplier
    if all_customer_pcts and top1_customer is None:
        top1_customer = max(all_customer_pcts)
    if all_customer_pcts and top5_customer is None:
        s = sum(all_customer_pcts)
        top5_customer = round(s, 2) if s <= 100 else max(all_customer_pcts)

    high = (
        (top1_customer is not None and top1_customer > 50)
        or (top5_customer is not None and top5_customer > 50)
        or (top1_supplier is not None and top1_supplier > 50)
        or (top5_supplier is not None and top5_supplier > 50)
    )
    evidences = [_hit_to_evidence(h, "CONCENTRATION") for h in strong[:5]]
    return {
        "exists": exists,
        "top1_customer_pct": top1_customer,
        "top5_customer_pct": top5_customer,
        "top1_supplier_pct": top1_supplier,
        "top5_supplier_pct": top5_supplier,
        "concentration_high": high,
        "evidence": [e.model_dump() for e in evidences],
        "evidence_strength": "high" if len(evidences) >= 2 else ("medium" if evidences else "low"),
    }


async def maybe_llm_enrich(
    llm: Any,
    section: str,
    feature: dict[str, Any],
    hits: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM 从候选段抽取金额/占比等；失败则保留规则结果。"""
    if llm is None or not getattr(llm, "available", False):
        return feature
    if not hits:
        # 回退：用已有 evidence 页
        for e in feature.get("evidence") or []:
            hits.append({"page": e.get("page"), "excerpt": e.get("excerpt"), "content": e.get("excerpt")})
    if not hits:
        return feature
    blob = "\n\n".join(
        f"[p{h.get('page')}] {(h.get('excerpt') or h.get('content') or '')[:500]}" for h in hits[:6]
    )
    prompt = (
        f"你是港股招股书法务抽取器。根据下列原文，抽取章节 {section} 的结构化字段，"
        "只输出 JSON。字段示例：ratio_pct, top1_customer_pct, top5_customer_pct, "
        "top1_supplier_pct, exists, evidence_page, evidence_excerpt。"
        "若无法判断则用 null。\n\n"
        f"原文：\n{blob[:6000]}"
    )
    try:
        resp = await llm.chat_json(
            [{"role": "user", "content": prompt}],
            enable_reasoning=False,
        )
        # 兼容 chat_json 新返回 {data, reasoning, ...}
        data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
        if not data:
            return feature
        feature = {**feature, "llm": data}
        # 合并可用数值
        for k in (
            "ratio_pct", "top1_customer_pct", "top5_customer_pct",
            "top1_supplier_pct", "top5_supplier_pct", "exists",
        ):
            if data.get(k) is not None and feature.get(k) in (None, False, []):
                feature[k] = data[k]
        if data.get("ratio_pct") is not None:
            try:
                feature["related_party_ratio_gt_30"] = float(data["ratio_pct"]) > 30
            except (TypeError, ValueError):
                pass
        if any(
            (feature.get(k) or 0) > 50
            for k in ("top1_customer_pct", "top5_customer_pct", "top1_supplier_pct", "top5_supplier_pct")
        ):
            feature["concentration_high"] = True
    except Exception as e:
        logger.warning("LLM enrich %s failed: %s", section, e)
    return feature


_PIPELINE_KEYWORDS = [
    "核心產品",
    "核心产品",
    "臨床試驗",
    "临床试验",
    "臨床擱置",
    "临床搁置",
    "暫停臨床",
    "暂停临床",
    "管線",
    "管线",
    "授權引進",
    "授权引进",
    "license-in",
    "知識產權",
    "知识产权",
    "NDA",
    "BLA",
    "監管批准",
    "监管批准",
]
_PIPELINE_STRONG = [
    "核心產品",
    "核心产品",
    "臨床試驗",
    "临床试验",
    "管線候選",
    "管线候选",
    "產品管線",
    "产品管线",
    "授權引進",
    "授权引进",
    "臨床研究",
    "临床研究",
]
_PIPELINE_HIGH = [
    "臨床擱置",
    "临床搁置",
    "暫停臨床",
    "暂停临床",
    "终止开发",
    "終止開發",
    "临床失败",
    "臨床失敗",
    "研发失败",
    "研發失敗",
]


def extract_pipeline(
    bundle: dict[str, Any],
    extra_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """3.5 核心产品/管线：从 PIPELINE_RISK 检索命中抽取存在性与高危信号。"""
    raw_hits = _collect_hits(
        bundle,
        ["PIPELINE_RISK", "PIPELINE", "pipeline"],
        _PIPELINE_KEYWORDS,
        extra_hits=extra_hits,
    )
    strong: list[dict[str, Any]] = []
    high_hits: list[dict[str, Any]] = []
    for h in raw_hits:
        text = h.get("excerpt") or h.get("content") or ""
        if any(p in text for p in _PIPELINE_HIGH):
            high_hits.append(h)
            strong.append(h)
        elif any(p in text for p in _PIPELINE_STRONG):
            strong.append(h)
    exists = len(strong) > 0
    pipeline_high = len(high_hits) > 0
    evid_src = high_hits[:5] if pipeline_high else strong[:5]
    evidences = [_hit_to_evidence(h, "PIPELINE_RISK") for h in evid_src]
    stages: list[str] = []
    joined = " ".join((h.get("excerpt") or "")[:400] for h in strong[:8])
    for pat, label in (
        (r"III\s*期|三期|第III期", "III期"),
        (r"II\s*期|二期|第II期", "II期"),
        (r"I\s*期|一期|第I期", "I期"),
        (r"NDA|BLA|上市申請|上市申请", "注册申请"),
    ):
        if re.search(pat, joined, flags=re.I):
            stages.append(label)
    return {
        "exists": exists,
        "skipped": False,
        "pipeline_high": pipeline_high,
        "stages_mentioned": stages,
        "evidence": [e.model_dump() for e in evidences],
        "evidence_strength": (
            "high"
            if pipeline_high or len(evidences) >= 2
            else ("medium" if evidences else "low")
        ),
        "search_log": {
            "raw_hits": len(raw_hits),
            "strong_hits": len(strong),
            "high_hits": len(high_hits),
            "pages_scanned": _pages_from_hits(raw_hits),
        },
    }


def extract_legal_features(
    bundle: dict[str, Any],
    *,
    gates: dict[str, Any] | None = None,
    extra_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    gates = gates or {}
    redemption = extract_redemption(bundle, extra_hits=extra_hits)
    related = extract_related_party(bundle, extra_hits=extra_hits)
    concentration = extract_concentration(bundle, extra_hits=extra_hits)
    out: dict[str, Any] = {
        "3.1": redemption,
        "3.2": related,
        "3.3": concentration,
    }
    if gates.get("skip_3_5"):
        out["3.5"] = {"skipped": True, "reason": gates.get("skip_3_5_reason")}
    else:
        out["3.5"] = extract_pipeline(bundle, extra_hits=extra_hits)
    out["3.4"] = {"owner": "finance", "skipped_by_legal": True}
    out["3.6"] = {"valuation_inversion": False, "evidence": []}
    return out
