from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from src.agents.react_loop import run_react_loop
from src.llm.prompts import LEGAL_REACT_SYSTEM, LEGAL_REACT_USER
from src.models.evidence import AgentResult
from src.skills.extract_legal import extract_legal_features, maybe_llm_enrich
from src.skills.legal_toolbox import build_legal_tool_registry
from src.skills.score_legal import score_legal
from src.tools.parse_grep import grep_parse_json, merge_hits
from src.tools.retrieval_tool import (
    iter_field_hits,
    retrieve_agent,
    retrieve_section_evidence,
)

logger = logging.getLogger(__name__)

_LEGAL_NO_TOOL_NUDGE = (
    "请通过 function/tool 调用继续：retrieve_legal → run_legal_skill×5 → "
    "（search 全程≤2，有 coverage_hints 可至 3）→ run_rule_checks → submit_legal_report。"
    "rule_checks 后无缺口时必须调用 submit_legal_report 写 summary/reasoning；"
    "risk_points 可精炼或留空；禁止再 search，也不要只输出自然语言。"
)

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


def _default_gates(issuer_type: str) -> dict[str, Any]:
    it = issuer_type.lower()
    is_biotech = it in {"biotech", "18a", "18c"}
    return {
        "issuer_type": issuer_type,
        "is_biotech_18a": is_biotech,
        "skip_3_5": not is_biotech,
        "skip_3_5_reason": None if is_biotech else "non-biotech",
    }


class LegalAgent:
    """默认规则流水线（service 兼容）；react=True 时走完整 ReAct（多轮选工具→submit）。"""

    def __init__(
        self,
        llm: Any | None = None,
        *,
        on_progress: ProgressCallback | None = None,
        react: bool = False,
        run_logger: Any | None = None,
        max_turns: int = 10,
        debate_dir: Path | str | None = None,
        reasoning_effort: str | None = "high",
    ) -> None:
        self._llm = llm
        self._on_progress = on_progress
        self._react = react
        self._run_logger = run_logger
        self._max_turns = max_turns
        self._debate_dir = debate_dir
        self._reasoning_effort = reasoning_effort or "high"

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
        doc_name: str | None = None,
        pdf_name: str | None = None,
        client_project_id: str | None = None,
        task_id: str | None = None,
        analysis_id: str | None = None,
    ) -> AgentResult:
        if self._react and self._llm is not None and getattr(self._llm, "available", False):
            return await self._run_react(
                doc_id,
                issuer_type=issuer_type,
                gates=gates,
                retrieval_json=retrieval_json,
                parse_json=parse_json,
                top_k=top_k,
                doc_name=doc_name,
                pdf_name=pdf_name,
                client_project_id=client_project_id,
                task_id=task_id,
                analysis_id=analysis_id,
            )
        return await self._run_pipeline(
            doc_id,
            issuer_type=issuer_type,
            gates=gates,
            retrieval_json=retrieval_json,
            parse_json=parse_json,
            top_k=top_k,
        )

    # ---------- ReAct 模式：推理-行动-观察-反思 ----------

    async def _run_react(
        self,
        doc_id: str,
        *,
        issuer_type: str,
        gates: dict[str, Any] | None,
        retrieval_json: Path | str | None,
        parse_json: Path | str | None,
        top_k: int | None,
        doc_name: str | None,
        pdf_name: str | None,
        client_project_id: str | None = None,
        task_id: str | None = None,
        analysis_id: str | None = None,
    ) -> AgentResult:
        t0 = time.time()
        log = self._run_logger
        tools = build_legal_tool_registry()
        state: dict[str, Any] = {
            "doc_id": doc_id,
            "issuer_type": issuer_type,
            "retrieval_json": retrieval_json,
            "parse_json": parse_json,
            "top_k": top_k,
            "doc_name": doc_name,
            "pdf_name": pdf_name,
            "client_project_id": client_project_id,
            "task_id": task_id or doc_id,
            "analysis_id": analysis_id,
            "gates": gates or _default_gates(issuer_type),
            "_llm": self._llm,
            "finished": False,
        }
        if self._debate_dir:
            state["debate_dir"] = self._debate_dir
        if log:
            state["run_log_paths"] = log.paths
        user = LEGAL_REACT_USER.format(
            doc_id=doc_id,
            issuer_type=issuer_type,
            doc_name=doc_name or doc_id,
        )
        try:
            loop_out = await run_react_loop(
                llm=self._llm,
                tools=tools,
                system_prompt=LEGAL_REACT_SYSTEM,
                user_prompt=user,
                state=state,
                run_logger=log,
                max_turns=self._max_turns,
                submit_tool_name="submit_legal_report",
                no_tool_nudge=_LEGAL_NO_TOOL_NUDGE,
                translate_think=True,
                reasoning_effort=self._reasoning_effort,
            )
        except Exception as e:
            logger.warning("Legal ReAct loop failed, fallback pipeline: %s", e)
            if log:
                log.step("react_loop", kind="agent", status="error", error=str(e))
            return await self._run_pipeline(
                doc_id,
                issuer_type=issuer_type,
                gates=gates,
                retrieval_json=retrieval_json,
                parse_json=parse_json,
                top_k=top_k,
            )

        if not loop_out.get("ok") or not state.get("final_report"):
            # 轮次耗尽但仍有 skill 结果时，自动 submit 保留 ReAct 成果，避免整段回退规则
            auto = await self._auto_submit_if_ready(state, tools, reason=str(loop_out.get("error")))
            if not auto:
                logger.warning("Legal ReAct 未 submit，fallback pipeline: %s", loop_out.get("error"))
                if log:
                    log.step(
                        "react_loop",
                        kind="agent",
                        status="error",
                        error=str(loop_out.get("error")),
                    )
                return await self._run_pipeline(
                    doc_id,
                    issuer_type=issuer_type,
                    gates=gates,
                    retrieval_json=retrieval_json,
                    parse_json=parse_json,
                    top_k=top_k,
                )
            loop_out = {**loop_out, "ok": True, "auto_submit": True}

        return self._compose_react_result(
            doc_id=doc_id,
            issuer_type=issuer_type,
            state=state,
            loop_out=loop_out,
            t0=t0,
            log=log,
        )

    async def _auto_submit_if_ready(
        self,
        state: dict[str, Any],
        tools: Any,
        *,
        reason: str | None,
    ) -> bool:
        """max_turns 耗尽但已跑过 skill 时，用已有风险点强制 submit。"""
        skill_results = state.get("skill_results") or {}
        if len(skill_results) < 2:
            return False
        points: list[dict[str, Any]] = []
        negatives: list[dict[str, Any]] = []
        for name, data in skill_results.items():
            for p in data.get("risk_points") or []:
                item = dict(p)
                item.setdefault("skill", name)
                points.append(item)
            for n in data.get("negative_findings") or []:
                negatives.append(n if isinstance(n, dict) else {"description": str(n)})
        summary = (
            f"法務 ReAct 自動收束（{reason or 'max_turns'}）："
            f"已完成 {len(skill_results)} 個 skill，彙總 {len(points)} 個風險點"
        )
        obs = await tools.execute(
            "submit_legal_report",
            {
                "risk_points": points,
                "negative_findings": negatives,
                "reasoning": summary,
                "summary": summary,
            },
            state,
        )
        if not obs.get("ok") or not state.get("final_report"):
            logger.warning("auto submit failed: %s", obs.get("error"))
            return False
        warnings = list((state["final_report"].get("submit_warnings") or []))
        warnings.append(f"auto_submit:{reason or 'max_turns'}")
        state["final_report"]["submit_warnings"] = warnings
        logger.info("Legal ReAct auto-submit after incomplete loop: %s", reason)
        return True

    def _compose_react_result(
        self,
        *,
        doc_id: str,
        issuer_type: str,
        state: dict[str, Any],
        loop_out: dict[str, Any],
        t0: float,
        log: Any,
    ) -> AgentResult:
        report = state["final_report"]
        skill_results = state.get("skill_results") or {}
        rule_features = state.get("rule_features") or {}
        risk_score = round(float(report.get("risk_score") or 0), 1)
        risk_level = str(report.get("risk_level") or "very_low")
        summary = report.get("summary") or (
            f"法務 ReAct 完成 {len(skill_results)} 個 skill；風險分 {risk_score:.1f} ({risk_level})"
        )
        log_paths = log.paths if log else {}

        snippets: list[dict[str, Any]] = []
        for name, data in skill_results.items():
            for e in data.get("evidence") or []:
                snippets.append(
                    {
                        "section": name,
                        "page": e.get("page"),
                        "excerpt": e.get("excerpt"),
                        "source_type": e.get("source_type"),
                    }
                )
        for sec in ("3.1", "3.2", "3.3", "3.5"):
            for e in (rule_features.get(sec) or {}).get("evidence") or []:
                snippets.append(
                    {
                        "section": f"rule_{sec}",
                        "page": e.get("page"),
                        "excerpt": e.get("excerpt"),
                        "source_type": e.get("source_type"),
                    }
                )

        features: dict[str, Any] = {
            "scoring_mode": "react+rules_floor",
            "rules_floor": report.get("rules_floor"),
            "skill_results": {
                name: {
                    "exists": data.get("exists"),
                    "confidence": data.get("confidence"),
                    "features": data.get("features"),
                    "risk_points": data.get("risk_points"),
                    "negative_findings": data.get("negative_findings"),
                    "reasoning": data.get("reasoning"),
                    "degraded": data.get("degraded"),
                    "degraded_reason": data.get("degraded_reason"),
                }
                for name, data in skill_results.items()
            },
            "rule_features": rule_features,
            "negative_findings": report.get("negative_findings") or [],
            "submit_warnings": report.get("submit_warnings") or [],
            "model_think_excerpt": (report.get("model_think") or "")[:500] or None,
            "react_turns": loop_out.get("n_turns"),
            "auto_submit": bool(loop_out.get("auto_submit")),
            "debate_dossier_path": report.get("debate_dossier_path"),
            "debate_dossier": state.get("debate_dossier"),
            "run_log": log_paths,
        }
        # 顶层挂 3.1–3.6，供报告/API 与规则链路径一致读取
        for sec in ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6"):
            if sec in rule_features and isinstance(rule_features.get(sec), dict):
                features[sec] = rule_features[sec]
        if log:
            log.result(
                {
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "scoring_mode": "react+rules_floor",
                    "summary": summary,
                    "n_turns": loop_out.get("n_turns"),
                    "auto_submit": bool(loop_out.get("auto_submit")),
                    "debate_dossier_path": report.get("debate_dossier_path"),
                }
            )
            log.close(final_summary=summary)

        return AgentResult(
            agent="legal",
            doc_id=doc_id,
            risk_score=risk_score,
            risk_level=risk_level,
            score_breakdown=[
                {
                    "code": b.get("code"),
                    "delta": b.get("delta"),
                    "rule_ref": b.get("rule_ref") or "llm",
                    "note": b.get("note"),
                    "metric_value": b.get("metric_value"),
                    "evidence_page": b.get("evidence_page"),
                    "evidence": b.get("evidence") or [],
                }
                for b in report.get("score_breakdown") or []
            ],
            risk_points=[
                {
                    "code": p.get("code"),
                    "level": p.get("level") or "medium",
                    "rule_ref": p.get("rule_ref") or f"llm§{p.get('skill') or 'legal'}",
                    "value": p.get("metric_value"),
                    "description": p.get("description") or "",
                    "evidence": (
                        [
                            {
                                "page": p.get("evidence_page"),
                                "excerpt": (p.get("evidence_excerpt") or "")[:200],
                                "source_type": "text",
                                "field_code": p.get("code"),
                            }
                        ]
                        if p.get("evidence_page") is not None or p.get("evidence_excerpt")
                        else []
                    ),
                }
                for p in report.get("risk_points") or []
            ],
            features=features,
            gates={
                "skip_3_5": (state.get("gates") or {}).get("skip_3_5"),
                "skip_3_5_reason": (state.get("gates") or {}).get("skip_3_5_reason"),
                "issuer_type": issuer_type,
            },
            evidence_summary={
                "snippets": snippets,
                "queries_used": state.get("queries_used") or [],
                "known_pages": sorted(
                    {s.get("page") for s in snippets if s.get("page") is not None}
                ),
                "debate_dossier_path": report.get("debate_dossier_path"),
                "run_log": log_paths,
            },
            trace={
                "tool_calls": loop_out.get("turns") or [],
                "elapsed_sec": round(time.time() - t0, 3),
                "scoring_mode": "react+rules_floor",
                "structured_reasoning": report.get("reasoning"),
                "n_turns": loop_out.get("n_turns"),
                "auto_submit": bool(loop_out.get("auto_submit")),
                "run_log": log_paths,
            },
            summary=summary,
        )

    # ---------- 规则流水线（原路径，service/前端默认） ----------

    async def _run_pipeline(
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
        gates = gates or _default_gates(issuer_type)

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
        features = extract_legal_features(
            bundle,
            gates=gates,
            extra_hits=extra_hits,
            parse_json=parse_json,
        )
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
            risk_score=round(float(scored["risk_score"]), 1),
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
