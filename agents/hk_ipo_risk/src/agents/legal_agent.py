from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from src.models.evidence import AgentResult
from src.skills.extract_legal import extract_legal_features, maybe_llm_enrich
from src.skills.score_legal import score_legal
from src.tools.parse_grep import grep_parse_json, merge_hits
from src.tools.retrieval_tool import (
    iter_field_hits,
    retrieve_agent,
    retrieve_section_evidence,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict[str, Any]], None]

_LEGAL_GREP_KEYWORDS = [
    "關連交易", "关联交易", "持續關連", "持续关连", "關連交易豁免",
    "贖回", "赎回", "對賭", "对赌", "優先股", "优先股",
    "可轉換可贖回", "可转换可赎回", "股東協議", "股东协议", "特別權利",
    "前五大客戶", "前五大客户", "五大客戶", "最大客戶",
    "前五大供應商", "供應商A", "供應商", "供应商", "佔總採購", "佔總收入",
]

_LEGAL_SECTION_QUERIES = {
    "redemption": "贖回 赎回 對賭 对赌 優先股 优先股 特別權利 特别权利",
    "related_party": "關連交易 关联交易 持續關連交易 持续关联交易 關連人士",
    "concentration": "前五大客戶 前五大客户 最大客戶 前五大供應商 最大供應商",
}


class LegalAgent:
    """检索 → 3.1/3.2/3.3 抽取 → 打分(0-100)；3.5 受 biotech 门控。"""

    def __init__(
        self,
        llm: Any | None = None,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._llm = llm
        self._on_progress = on_progress

    def _emit(self, event: dict[str, Any]) -> None:
        if self._on_progress is None:
            return
        try:
            self._on_progress(event)
        except Exception:
            logger.exception("legal on_progress failed")

    async def run(
        self,
        doc_id: str,
        *,
        issuer_type: str = "general",
        gates: dict[str, Any] | None = None,
        retrieval_json: Path | str | None = None,
        parse_json: Path | str | None = None,
        top_k: int | None = None,
    ) -> AgentResult:
        t0 = time.time()
        tool_calls: list[dict[str, Any]] = []
        gates = gates or {
            "issuer_type": issuer_type,
            "is_biotech_18a": issuer_type.lower() in {"biotech", "18a", "18c"},
            "skip_3_5": issuer_type.lower() not in {"biotech", "18a", "18c"},
            "skip_3_5_reason": None if issuer_type.lower() in {"biotech", "18a", "18c"} else "non-biotech",
        }

        self._emit(
            {
                "event": "step",
                "agent": "legal",
                "name": "retrieve_legal",
                "kind": "tool",
                "status": "running",
                "input_summary": {"doc_id": doc_id, "issuer_type": issuer_type},
            }
        )
        bundle = await retrieve_agent(
            "legal",
            doc_id,
            issuer_type=issuer_type,
            top_k=top_k,
            offline_json=retrieval_json,
        )
        has_field_index = bool(bundle.get("evidence_by_field"))
        retrieve_out = {
            "tool": "retrieve_legal",
            "source": bundle.get("_source"),
            "fields": list((bundle.get("evidence_by_field") or {}).keys())[:20],
            "per_query": len(bundle.get("per_query") or []),
            "has_evidence_by_field": has_field_index,
            "hint": (
                None
                if has_field_index
                else "旧格式/字段索引为空：依赖 parse_grep；建议 --use-live-retrieval 重跑 legal profile"
            ),
        }
        tool_calls.append(retrieve_out)
        self._emit(
            {
                "event": "step",
                "agent": "legal",
                "name": "retrieve_legal",
                "kind": "tool",
                "status": "ok",
                "output": retrieve_out,
            }
        )

        extra_hits: list[dict[str, Any]] = []
        if parse_json:
            self._emit(
                {
                    "event": "step",
                    "agent": "legal",
                    "name": "parse_grep",
                    "kind": "tool",
                    "status": "running",
                    "input_summary": {"path": str(parse_json)},
                }
            )
            grep_hits = grep_parse_json(parse_json, _LEGAL_GREP_KEYWORDS, top_k=40)
            extra_hits = merge_hits(grep_hits, top_k=40)
            grep_out = {
                "tool": "parse_grep",
                "path": str(parse_json),
                "hits": len(extra_hits),
                "pages": [h.get("page") for h in extra_hits[:10]],
            }
            tool_calls.append(grep_out)
            self._emit(
                {
                    "event": "step",
                    "agent": "legal",
                    "name": "parse_grep",
                    "kind": "tool",
                    "status": "ok",
                    "output": grep_out,
                    "evidence_hits": [
                        {
                            "page": h.get("page"),
                            "excerpt": (h.get("excerpt") or h.get("content") or "")[:200],
                            "source_type": h.get("source_type") or "text",
                            "category": h.get("category"),
                            "field_code": h.get("field_code"),
                        }
                        for h in extra_hits[:8]
                    ],
                }
            )

            section_hits_by_intent: dict[str, list[dict[str, Any]]] = {}
            section_routes: dict[str, list[dict[str, Any]]] = {}
            self._emit(
                {
                    "event": "step",
                    "agent": "legal",
                    "name": "retrieve_section_evidence",
                    "kind": "tool",
                    "status": "running",
                }
            )
            for intent, query in _LEGAL_SECTION_QUERIES.items():
                section_result = await retrieve_section_evidence(
                    doc_id=doc_id,
                    intent=intent,
                    query=query,
                    parse_json=parse_json,
                    top_k=8,
                    prefer_source_type="mixed",
                )
                # Legal feature extraction is precision-sensitive. Keep
                # section-constrained Grep hits; BM25-only candidates remain
                # visible in the retrieval result but do not trigger rules.
                section_hits_by_intent[intent] = [
                    hit
                    for hit in (section_result.get("hits") or [])
                    if hit.get("matched_terms")
                ]
                section_routes[intent] = section_result.get("route") or []
            extra_hits = merge_hits(
                extra_hits,
                *section_hits_by_intent.values(),
                top_k=60,
            )
            section_out = {
                "tool": "retrieve_section_evidence",
                "intents": {
                    intent: {
                        "hits": len(hits),
                        "pages": [hit.get("page") for hit in hits],
                        "route": section_routes.get(intent) or [],
                    }
                    for intent, hits in section_hits_by_intent.items()
                },
            }
            tool_calls.append(section_out)
            evidence_hits = []
            for intent, hits in section_hits_by_intent.items():
                for hit in hits[:4]:
                    evidence_hits.append(
                        {
                            "page": hit.get("page"),
                            "excerpt": (hit.get("excerpt") or hit.get("content") or "")[:200],
                            "source_type": hit.get("source_type") or "text",
                            "category": hit.get("category"),
                            "field_code": hit.get("field_code"),
                            "section_id": intent,
                        }
                    )
            self._emit(
                {
                    "event": "step",
                    "agent": "legal",
                    "name": "retrieve_section_evidence",
                    "kind": "tool",
                    "status": "ok",
                    "output": section_out,
                    "evidence_hits": evidence_hits[:12],
                }
            )

        self._emit(
            {
                "event": "step",
                "agent": "legal",
                "name": "extract_legal",
                "kind": "tool",
                "status": "running",
            }
        )
        features = extract_legal_features(bundle, gates=gates, extra_hits=extra_hits)
        extract_out = {
            "tool": "extract_legal",
            "sections": {
                k: {
                    "exists": (features.get(k) or {}).get("exists"),
                    "skipped": (features.get(k) or {}).get("skipped"),
                    "evidence_n": len((features.get(k) or {}).get("evidence") or []),
                    "search_log": (features.get(k) or {}).get("search_log"),
                    "top1_supplier_pct": (features.get(k) or {}).get("top1_supplier_pct"),
                    "top5_supplier_pct": (features.get(k) or {}).get("top5_supplier_pct"),
                }
                for k in ("3.1", "3.2", "3.3", "3.5")
            },
        }
        tool_calls.append(extract_out)
        feature_evidence = []
        for sec in ("3.1", "3.2", "3.3", "3.5"):
            for e in (features.get(sec) or {}).get("evidence") or []:
                feature_evidence.append(
                    {
                        "page": e.get("page"),
                        "excerpt": (e.get("excerpt") or "")[:200],
                        "source_type": e.get("source_type") or "unknown",
                        "field_code": e.get("field_code"),
                        "section_id": sec,
                        "confidence": e.get("confidence"),
                    }
                )
        self._emit(
            {
                "event": "step",
                "agent": "legal",
                "name": "extract_legal",
                "kind": "tool",
                "status": "ok",
                "output": extract_out,
                "evidence_hits": feature_evidence[:16],
            }
        )

        if self._llm is not None:
            self._emit(
                {
                    "event": "step",
                    "agent": "legal",
                    "name": "llm_enrich_legal",
                    "kind": "tool",
                    "status": "running",
                }
            )
            for sec, fc in (("3.1", "REDEMPTION_CLAUSE"), ("3.2", "RELATED_PARTY"), ("3.3", "CONCENTRATION")):
                hits = iter_field_hits(bundle, fc)
                if not hits:
                    for e in (features.get(sec) or {}).get("evidence") or []:
                        hits.append({"page": e.get("page"), "excerpt": e.get("excerpt"), "content": e.get("excerpt")})
                if not hits and extra_hits:
                    hits = extra_hits[:6]
                features[sec] = await maybe_llm_enrich(self._llm, sec, features[sec], hits)
            tool_calls.append({"tool": "llm_enrich_legal", "used": True})
            self._emit(
                {
                    "event": "step",
                    "agent": "legal",
                    "name": "llm_enrich_legal",
                    "kind": "tool",
                    "status": "ok",
                    "output": {"used": True},
                }
            )

        self._emit(
            {
                "event": "step",
                "agent": "legal",
                "name": "score_legal",
                "kind": "tool",
                "status": "running",
            }
        )
        scored = score_legal(features, gates=gates)
        score_out = {
            "tool": "score_legal",
            "risk_score": scored["risk_score"],
            "breakdown_n": len(scored.get("score_breakdown") or []),
        }
        tool_calls.append(score_out)
        self._emit(
            {
                "event": "step",
                "agent": "legal",
                "name": "score_legal",
                "kind": "tool",
                "status": "ok",
                "output": score_out,
                "risk_points": scored.get("risk_points") or [],
                "summary": (
                    f"法務 3.1/3.2/3.3 抽取完成；"
                    f"3.5={'跳過' if gates.get('skip_3_5') else '啓用'}；"
                    f"風險分 {scored['risk_score']:.1f} ({scored['risk_level']})"
                ),
            }
        )

        summary = (
            f"法務 3.1/3.2/3.3 抽取完成；"
            f"3.5={'跳過' if gates.get('skip_3_5') else '啓用'}；"
            f"風險分 {scored['risk_score']:.1f} ({scored['risk_level']})"
        )

        return AgentResult(
            agent="legal",
            doc_id=doc_id,
            risk_score=float(scored["risk_score"]),
            risk_level=str(scored["risk_level"]),
            score_breakdown=scored.get("score_breakdown") or [],
            risk_points=scored.get("risk_points") or [],
            features=features,
            gates={
                "skip_3_5": gates.get("skip_3_5"),
                "skip_3_5_reason": gates.get("skip_3_5_reason"),
                "issuer_type": gates.get("issuer_type") or issuer_type,
            },
            evidence_summary={
                "3.1_pages": [e.get("page") for e in (features.get("3.1") or {}).get("evidence") or []],
                "3.2_pages": [e.get("page") for e in (features.get("3.2") or {}).get("evidence") or []],
                "3.3_pages": [e.get("page") for e in (features.get("3.3") or {}).get("evidence") or []],
                "3.1_search_log": (features.get("3.1") or {}).get("search_log"),
                "snippets": [
                    {
                        "section": sec,
                        "page": e.get("page"),
                        "excerpt": e.get("excerpt"),
                        "source_type": e.get("source_type"),
                    }
                    for sec in ("3.1", "3.2", "3.3")
                    for e in (features.get(sec) or {}).get("evidence") or []
                ],
            },
            trace={"tool_calls": tool_calls, "elapsed_sec": round(time.time() - t0, 3)},
            summary=summary,
        )
