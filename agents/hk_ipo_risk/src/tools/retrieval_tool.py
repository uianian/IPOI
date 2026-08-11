from __future__ import annotations

import json
import logging
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

IPOI_ROOT = Path(__file__).resolve().parents[4]
RETRIEVAL_ROOT = IPOI_ROOT / "retrieval"

INTENT_SECTION_ROUTES: dict[str, list[str]] = {
    "business_model": ["business", "risk_factors", "summary"],
    "business_context": ["business", "risk_factors", "summary"],
    "franchise": ["business", "risk_factors", "summary"],
    "supply_chain": ["business", "risk_factors", "summary"],
    "financing_dependency": [
        "history_and_corporate_structure",
        "financial_information",
        "risk_factors",
    ],
    "related_party": ["connected_transactions", "business", "financial_information"],
    "redemption": ["history_and_corporate_structure", "risk_factors"],
    "concentration": ["business", "risk_factors", "financial_information"],
    "regulatory": ["regulatory_overview", "business", "risk_factors"],
    "litigation": ["business", "risk_factors"],
    "ip": ["business", "regulatory_overview", "risk_factors"],
}

INTENT_QUERY_TERMS: dict[str, list[str]] = {
    "business_model": ["商業模式", "商业模式", "收入模式", "盈利模式"],
    "business_context": ["商業模式", "商业模式", "收入模式", "依賴", "依赖"],
    "franchise": ["加盟", "加盟商", "特許經營", "特许经营", "加盟協議", "加盟协议"],
    "supply_chain": ["供應鏈", "供应链", "採購", "采购", "供應商", "供应商"],
    "financing_dependency": [
        "融資", "融资", "Pre-IPO", "資金需求", "资金需求",
        "營運資金", "营运资金", "研發開支", "研发开支", "所得款項用途", "所得款项用途",
    ],
    "related_party": ["關連交易", "关联交易", "持續關連", "持续关连", "關聯方"],
    "redemption": ["贖回", "赎回", "對賭", "对赌", "優先股", "优先股", "回購"],
    "concentration": ["前五大客戶", "前五大客户", "前五大供應商", "前五大供应商"],
    "regulatory": ["監管", "监管", "合規", "合规", "牌照", "批准"],
    "litigation": ["訴訟", "诉讼", "仲裁", "法律程序", "處罰", "处罚"],
    "ip": ["知識產權", "知识产权", "商標", "商标", "專利", "专利"],
}


def _load_section_map_module() -> Any:
    """Load retrieval/section_map.py without colliding with hk_ipo_risk's src package."""
    module_name = "_ipoi_retrieval_section_map"
    if module_name in sys.modules:
        return sys.modules[module_name]
    path = RETRIEVAL_ROOT / "src" / "retrieval" / "section_map.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load section map module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_full_parse_pages(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"full_parse.json top-level must be a list: {path}")
    return data


def _split_section_hints(section_hint: str | list[str] | None) -> list[str]:
    """拆分 section_hint：支持 'business/industry/financing' 或逗号分隔，避免整串当一个 id。"""
    if section_hint is None:
        return []
    if isinstance(section_hint, list):
        raw_parts = [str(x) for x in section_hint]
    else:
        raw_parts = [str(section_hint)]
    out: list[str] = []
    for part in raw_parts:
        for token in re.split(r"[/,\s;；|]+", part):
            t = token.strip()
            if t:
                out.append(t)
    return list(dict.fromkeys(out))


def resolve_sections(
    *,
    intent: str,
    section_map: Any,
    section_hint: str | list[str] | None = None,
) -> list[dict[str, Any]]:
    hints = _split_section_hints(section_hint)
    fallback = INTENT_SECTION_ROUTES.get(intent) or [
        "business",
        "risk_factors",
        "summary",
    ]
    requested = hints or list(fallback)

    def _resolve(ids: list[str]) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for section_id in ids:
            span = section_map.span_for(str(section_id))
            if span is None:
                continue
            resolved.append(
                {
                    "section_id": span.canonical_section,
                    "section_title": span.display_title,
                    "start_page": span.start_page,
                    "end_page": span.end_page,
                    "confidence": span.confidence,
                }
            )
        return resolved

    resolved = _resolve(requested)
    # hint 全无效时回退 intent 默认路由（修 business/industry/financing 整串废路由）
    if not resolved and hints:
        resolved = _resolve(list(fallback))
    return resolved


def _query_terms(query: str, intent: str) -> list[str]:
    terms = [
        token
        for token in re.split(r"[\s,，、;；/]+", query or "")
        if len(token.strip()) >= 2
    ]
    terms.extend(INTENT_QUERY_TERMS.get(intent) or [])
    return list(dict.fromkeys(term.strip() for term in terms if term.strip()))


def _tokenize_for_bm25(text: str) -> list[str]:
    try:
        import jieba  # type: ignore[import-not-found]

        return [token.strip() for token in jieba.lcut(text) if token.strip()]
    except Exception:
        return list(text)


def _direct_section_search(
    pages: list[dict[str, Any]],
    *,
    sections: list[dict[str, Any]],
    query: str,
    intent: str,
    top_k: int,
    prefer_source_type: str,
) -> list[dict[str, Any]]:
    terms = _query_terms(query, intent)
    rows: list[tuple[int, int, dict[str, Any], dict[str, Any], str, str]] = []
    corpus: list[str] = []
    candidates: list[dict[str, Any]] = []
    section_by_page: dict[int, dict[str, Any]] = {}
    for section in sections:
        for page in range(int(section["start_page"]), int(section["end_page"]) + 1):
            section_by_page[page] = section
    for page_data in pages:
        page = int(page_data.get("page") or 0)
        section = section_by_page.get(page)
        if section is None:
            continue
        for elem_index, element in enumerate(page_data.get("elements") or []):
            category = str(element.get("category") or "text")
            if category not in {"text", "title", "table", "table_footnote", "table_caption"}:
                continue
            text = str(element.get("text") or "").strip()
            if not text:
                continue
            rows.append((page, elem_index, element, section, category, text))
            corpus.append(text)

    bm25_scores = [0.0] * len(rows)
    try:
        from rank_bm25 import BM25Okapi  # type: ignore[import-not-found]

        bm25 = BM25Okapi([_tokenize_for_bm25(text) for text in corpus])
        bm25_scores = [
            float(value)
            for value in bm25.get_scores(
                _tokenize_for_bm25(" ".join(terms) or query)
            )
        ]
    except Exception:
        pass

    for row_index, (page, elem_index, element, section, category, text) in enumerate(rows):
        matched = [term for term in terms if term.lower() in text.lower()]
        bm25_score = bm25_scores[row_index] if row_index < len(bm25_scores) else 0.0
        if not matched and bm25_score <= 0:
            continue
        score = float(len(matched))
        score += min(max(bm25_score, 0.0), 10.0) * 0.12
        score += min(len(text), 2000) / 10000.0
        if category == "title":
            score += 0.35
        if prefer_source_type == "table" and category == "table":
            score += 0.4
        elif prefer_source_type == "text" and category == "text":
            score += 0.25
        elif prefer_source_type == "mixed" and category in {"text", "table"}:
            score += 0.15
        candidates.append(
            {
                "page": page,
                "excerpt": text[:1200],
                "section_id": section["section_id"],
                "section_title": section["section_title"],
                "source_type": "table" if category == "table" else "text",
                "category": category,
                "bbox": element.get("bbox") or [],
                "score": round(score, 4),
                "match_sources": [
                    "section",
                    *(["grep"] if matched else []),
                    *(["bm25"] if bm25_score > 0 else []),
                ],
                "matched_terms": matched,
                "element_index": elem_index,
            }
        )
    candidates.sort(key=lambda item: (-float(item["score"]), int(item["page"])))
    return diversify_section_hits(candidates, top_k=top_k)


def _norm_excerpt_prefix(text: str, n: int = 80) -> str:
    t = re.sub(r"\s+", "", str(text or ""))
    return t[:n]


def diversify_section_hits(
    candidates: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """页级去重 + excerpt 前缀去重 + 章节多样性，再裁到 top_k。"""
    if not candidates:
        return []
    ordered = sorted(
        candidates,
        key=lambda item: (-float(item.get("score") or 0), int(item.get("page") or 0)),
    )
    page_best: dict[tuple[Any, str], dict[str, Any]] = {}
    for c in ordered:
        try:
            page = int(c.get("page"))
        except (TypeError, ValueError):
            page = c.get("page")
        key = (page, str(c.get("source_type") or "text"))
        if key not in page_best:
            page_best[key] = c
    uniq = sorted(
        page_best.values(),
        key=lambda item: (-float(item.get("score") or 0), int(item.get("page") or 0)),
    )
    # excerpt 前缀二次去重
    prefix_seen: set[str] = set()
    after_prefix: list[dict[str, Any]] = []
    for c in uniq:
        pref = _norm_excerpt_prefix(c.get("excerpt") or "")
        if pref and pref in prefix_seen:
            continue
        if pref:
            prefix_seen.add(pref)
        after_prefix.append(c)
    # 章节多样性：先各章节取最高分，再按分数补齐
    by_section: dict[str, list[dict[str, Any]]] = {}
    for c in after_prefix:
        sid = str(c.get("section_id") or "_")
        by_section.setdefault(sid, []).append(c)
    hits: list[dict[str, Any]] = []
    used: set[int] = set()
    for sid, rows in by_section.items():
        best = rows[0]
        hits.append(best)
        used.add(id(best))
        if len(hits) >= top_k:
            return hits[:top_k]
    for c in after_prefix:
        if id(c) in used:
            continue
        hits.append(c)
        if len(hits) >= top_k:
            break
    return hits[:top_k]


async def retrieve_section_evidence(
    *,
    doc_id: str,
    intent: str,
    query: str,
    parse_json: Path | str,
    section_hint: str | list[str] | None = None,
    top_k: int = 5,
    prefer_source_type: str = "mixed",
) -> dict[str, Any]:
    """Section-first retrieval over full_parse.json; no full-document LLM context."""
    pages = _load_full_parse_pages(parse_json)
    section_module = _load_section_map_module()
    section_map = section_module.build_section_map(pages)
    sections = resolve_sections(
        intent=intent,
        section_map=section_map,
        section_hint=section_hint,
    )
    hits = _direct_section_search(
        pages,
        sections=sections,
        query=query,
        intent=intent,
        top_k=max(1, min(int(top_k), 20)),
        prefer_source_type=prefer_source_type,
    )
    return {
        "ok": True,
        "doc_id": doc_id,
        "intent": intent,
        "query": query,
        "source": f"section_parse:{parse_json}",
        "route": sections,
        "section_map_version": section_map.version,
        "n": len(hits),
        "hits": hits,
    }


def load_retrieval_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"retrieval json must be object: {p}")
    return data


def normalize_agent_bundle(data: dict[str, Any], agent: str) -> dict[str, Any]:
    """Accept either a single-agent result or {finance, legal} wrapper."""
    if agent in data and isinstance(data[agent], dict) and (
        "evidence_by_field" in data[agent] or "evidence_by_table" in data[agent] or "evidence" in data[agent]
    ):
        return data[agent]
    if data.get("agent") == agent or (
        "evidence_by_field" in data or "evidence_by_table" in data or "per_query" in data
    ):
        return data
    raise KeyError(f"Cannot find agent={agent} payload in retrieval json keys={list(data.keys())}")


async def retrieve_agent(
    agent: str,
    doc_id: str,
    *,
    issuer_type: str = "general",
    top_k: int | None = None,
    offline_json: Path | str | None = None,
) -> dict[str, Any]:
    """优先离线 JSON；否则调用 retrieval.AgentRetrievalSimulator（不修改其代码）。"""
    if offline_json:
        raw = load_retrieval_json(offline_json)
        bundle = normalize_agent_bundle(raw, agent)
        bundle.setdefault("doc_id", doc_id)
        bundle.setdefault("issuer_type", issuer_type)
        bundle["_source"] = f"offline:{offline_json}"
        return bundle

    if not RETRIEVAL_ROOT.is_dir():
        raise FileNotFoundError(f"retrieval root not found: {RETRIEVAL_ROOT}")

    # 在隔离路径下导入 retrieval 包
    retrieval_src = str(RETRIEVAL_ROOT)
    if retrieval_src not in sys.path:
        sys.path.insert(0, retrieval_src)

    from src.llm.client import VLLMClient  # type: ignore
    from src.retrieval.agent_simulator import AgentRetrievalSimulator  # type: ignore
    from src.retrieval.store import DocumentIndexStore  # type: ignore

    client = VLLMClient()
    await client.init()
    try:
        store = DocumentIndexStore(client)
        if not store.exists(doc_id):
            raise FileNotFoundError(
                f"Index not found for doc_id={doc_id} under {store.index_root}. "
                "Provide --retrieval-*-json offline file or build index first."
            )
        sim = AgentRetrievalSimulator(store)
        result = await sim.run_agent(
            agent,
            doc_id,
            top_k=top_k,
            issuer_type=issuer_type,
        )
        result["_source"] = "live_retrieval"
        return result
    finally:
        await client.close()


def iter_field_hits(bundle: dict[str, Any], field_code: str) -> list[dict[str, Any]]:
    by_table = bundle.get("evidence_by_table") or {}
    by_field = bundle.get("evidence_by_field") or {}
    hits = by_table.get(field_code) or by_field.get(field_code) or []
    return list(hits)


def iter_all_text_hits(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten field/table hits for legal keyword scan."""
    seen: set[tuple[Any, str]] = set()
    out: list[dict[str, Any]] = []
    for store_name in ("evidence_by_field", "evidence_by_table"):
        store = bundle.get(store_name) or {}
        for fc, hits in store.items():
            for h in hits or []:
                key = (h.get("page"), (h.get("excerpt") or "")[:80])
                if key in seen:
                    continue
                seen.add(key)
                item = dict(h)
                item.setdefault("field_code", fc)
                out.append(item)
    # legacy flat evidence list
    for h in bundle.get("evidence") or []:
        key = (h.get("page"), (h.get("excerpt") or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(h))
    # per_query hits (older legal format)
    for q in bundle.get("per_query") or []:
        for h in q.get("hits") or []:
            key = (h.get("page"), (h.get("excerpt") or h.get("content") or "")[:80])
            if key in seen:
                continue
            seen.add(key)
            item = dict(h)
            if "excerpt" not in item and "content" in item:
                item["excerpt"] = item["content"]
            item.setdefault("field_code", q.get("name") or q.get("field_code"))
            out.append(item)
    return out
