from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from src.agents.react_loop import run_react_loop
from src.llm.prompts import (
    FINANCE_ISSUER_GUIDANCE,
    FINANCE_REACT_SYSTEM,
    FINANCE_REACT_USER,
)
from src.models.evidence import AgentResult
from src.skills.analyze_finance import (
    _normalize_breakdown,
    _normalize_risk_points,
    analyze_finance_llm,
)
from src.skills.extract_financials import extract_financials_from_retrieval
from src.skills.finance_toolbox import (
    _apply_18a_data_insufficient_guard,
    _compose_finance_submit_payload,
    build_finance_tool_registry,
)
from src.skills.gates import compute_cash_burn, resolve_issuer_gates
from src.skills.score_finance import score_finance
from src.tools.retrieval_tool import retrieve_agent

logger = logging.getLogger(__name__)


class FinanceAgent:
    """默认 ReAct（多轮选工具→submit）；pipeline=旧一次 LLM；rules_only=规则兜底。"""

    def __init__(
        self,
        llm: Any | None = None,
        *,
        run_logger: Any | None = None,
        rules_only: bool = False,
        pipeline: bool = False,
        max_turns: int = 10,
        debate_dir: Path | str | None = None,
        reasoning_effort: str | None = "low",
        close_logger: bool = True,
    ) -> None:
        self._llm = llm
        self._run_logger = run_logger
        self._rules_only = rules_only
        self._pipeline = pipeline
        self._max_turns = max_turns
        self._debate_dir = debate_dir
        self._reasoning_effort = reasoning_effort or "low"
        self._close_logger = close_logger
        self._doc_id = ""
        self._parse_json: Path | str | None = None

    async def run(
        self,
        doc_id: str,
        *,
        issuer_type: str = "general",
        retrieval_json: Path | str | None = None,
        parse_json: Path | str | None = None,
        top_k: int | None = None,
        doc_name: str | None = None,
        pdf_name: str | None = None,
        client_project_id: str | None = None,
        task_id: str | None = None,
        analysis_id: str | None = None,
    ) -> AgentResult:
        self._doc_id = doc_id
        self._parse_json = parse_json
        if self._rules_only or self._pipeline or not (
            self._llm is not None and getattr(self._llm, "available", False)
        ):
            return await self._run_pipeline(
                doc_id,
                issuer_type=issuer_type,
                retrieval_json=retrieval_json,
                parse_json=parse_json,
                top_k=top_k,
                doc_name=doc_name,
                pdf_name=pdf_name,
                force_rules=self._rules_only or not (
                    self._llm is not None and getattr(self._llm, "available", False)
                ),
                client_project_id=client_project_id,
                task_id=task_id,
                analysis_id=analysis_id,
            )
        return await self._run_react(
            doc_id,
            issuer_type=issuer_type,
            retrieval_json=retrieval_json,
            parse_json=parse_json,
            top_k=top_k,
            doc_name=doc_name,
            pdf_name=pdf_name,
            client_project_id=client_project_id,
            task_id=task_id,
            analysis_id=analysis_id,
        )

    async def _run_react(
        self,
        doc_id: str,
        *,
        issuer_type: str,
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
        tools = build_finance_tool_registry()
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
            "finished": False,
            "skill_results": {},
            "queries_used": [],
            "search_quota": 2,
            "search_used": 0,
            "_llm": self._llm,
        }
        if self._debate_dir:
            state["debate_dir"] = self._debate_dir
        it = (issuer_type or "general").lower()
        guidance = FINANCE_ISSUER_GUIDANCE.get(it) or FINANCE_ISSUER_GUIDANCE["general"]
        user = FINANCE_REACT_USER.format(
            doc_id=doc_id,
            issuer_type=issuer_type,
            doc_name=doc_name or doc_id,
            issuer_guidance=guidance,
        )
        try:
            loop_out = await run_react_loop(
                llm=self._llm,
                tools=tools,
                system_prompt=FINANCE_REACT_SYSTEM,
                user_prompt=user,
                state=state,
                run_logger=log,
                max_turns=self._max_turns,
                reasoning_effort=self._reasoning_effort,
            )
        except Exception as e:
            logger.warning("ReAct loop failed, fallback pipeline: %s", e)
            if log:
                log.step("react_loop", kind="agent", status="error", error=str(e))
            return await self._run_pipeline(
                doc_id,
                issuer_type=issuer_type,
                retrieval_json=retrieval_json,
                parse_json=parse_json,
                top_k=top_k,
                doc_name=doc_name,
                pdf_name=pdf_name,
                force_rules=False,
            )

        if not loop_out.get("ok") or not state.get("final_report"):
            auto_ok = await self._auto_submit_if_ready(
                state, tools, reason=str(loop_out.get("error"))
            )
            if not auto_ok:
                logger.warning("ReAct未submit，fallback pipeline: %s", loop_out.get("error"))
                return await self._run_pipeline(
                    doc_id,
                    issuer_type=issuer_type,
                    retrieval_json=retrieval_json,
                    parse_json=parse_json,
                    top_k=top_k,
                    doc_name=doc_name,
                    pdf_name=pdf_name,
                    force_rules=False,
                    client_project_id=client_project_id,
                    task_id=task_id,
                    analysis_id=analysis_id,
                )
            loop_out = {**loop_out, "ok": True, "auto_submit": True}

        report = state["final_report"]
        metrics = state.get("metrics") or {}
        gates = state.get("gates") or {}
        cash_burn = state.get("cash_burn") or {"skipped": True, "reason": "not_computed"}
        extracted = state.get("extracted") or {}
        table_meta = extracted.get("table_meta") or {}
        snippets = [
            {
                "field_code": code,
                "page": info.get("page"),
                "source_type": info.get("source_type") or info.get("category"),
                "excerpt": info.get("excerpt") or "",
            }
            for code, info in table_meta.items()
        ]
        risk_score = float(report.get("risk_score") or 0)
        risk_level = str(report.get("risk_level") or "very_low")
        summary = report.get("summary") or f"ReAct 财务风险分 {risk_score:.1f} ({risk_level})"
        scoring_mode = str(report.get("scoring_mode") or "react+rules_floor")
        log_paths = log.paths if log else {}
        turn_think = []
        for t in loop_out.get("turns") or []:
            if not isinstance(t, dict):
                continue
            if t.get("think_status") or t.get("status"):
                turn_think.append(
                    {
                        "turn": t.get("turn"),
                        "tool": t.get("tool"),
                        "think_status": t.get("think_status") or t.get("status"),
                    }
                )
        features = {
            "scoring_mode": scoring_mode,
            "rules_floor": report.get("rules_floor"),
            "negative_findings": report.get("negative_findings") or [],
            "bs_reconcile": extracted.get("bs_reconcile") or {},
            "dimensions": report.get("dimensions") or [],
            "llm_analysis": report.get("llm_analysis"),
            "model_think_excerpt": (report.get("model_think") or "")[:500] or None,
            "think_status": report.get("think_status"),
            "turn_think_status": turn_think,
            "submit_warnings": report.get("submit_warnings") or [],
            "submit_recovered": bool(report.get("submit_recovered")),
            "submit_composed_from_skills": bool(report.get("submit_composed_from_skills")),
            "react_turns": loop_out.get("n_turns"),
            "cash_burn": cash_burn,
            "risk_points": report.get("risk_points") or [],
            "skill_results": {
                k: {
                    "risk_point_count": len((v or {}).get("risk_points") or []),
                    "confidence": (v or {}).get("confidence"),
                    "reasoning": ((v or {}).get("reasoning") or "")[:400] or None,
                    "risk_points": [
                        {
                            "code": p.get("code"),
                            "level": p.get("level"),
                            "description": (p.get("description") or "")[:160],
                            "evidence_page": p.get("evidence_page"),
                        }
                        for p in ((v or {}).get("risk_points") or [])[:6]
                        if isinstance(p, dict)
                    ],
                }
                for k, v in (state.get("skill_results") or {}).items()
            },
            "debate_dossier_path": report.get("debate_dossier_path")
            or state.get("debate_dossier_path"),
            "run_log": log_paths,
        }
        if log:
            log.result({
                "risk_score": risk_score,
                "risk_level": risk_level,
                "scoring_mode": scoring_mode,
                "summary": summary,
                "n_turns": loop_out.get("n_turns"),
            })
            if self._close_logger:
                log.close(final_summary=summary)

        guard_warnings: list[str] = []
        _apply_18a_data_insufficient_guard(report, state, guard_warnings)
        if guard_warnings:
            features.setdefault("submit_warnings", [])
            if isinstance(features["submit_warnings"], list):
                features["submit_warnings"] = list(features["submit_warnings"]) + guard_warnings
            risk_score = float(report.get("risk_score") or risk_score)
            risk_level = str(report.get("risk_level") or risk_level)
            summary = report.get("summary") or summary

        return AgentResult(
            agent="finance",
            doc_id=doc_id,
            risk_score=risk_score,
            risk_level=risk_level,
            score_breakdown=_normalize_breakdown(
                report.get("score_breakdown") or [], extracted
            ),
            risk_points=_normalize_risk_points(list(report.get("risk_points") or [])),
            metrics={**metrics, "cash_burn": cash_burn},
            features=features,
            gates=gates,
            evidence_summary={
                "table_meta": table_meta,
                "evidence_keys": list((extracted.get("evidence") or {}).keys()),
                "snippets": snippets,
                "section_evidence_hits": state.get("section_evidence_hits") or [],
                "section_routes": state.get("section_routes") or [],
                "queries_used": state.get("queries_used") or [],
                "run_log": log_paths,
            },
            trace={
                "tool_calls": loop_out.get("turns") or [],
                "elapsed_sec": round(time.time() - t0, 3),
                "scoring_mode": scoring_mode,
                "structured_reasoning": report.get("reasoning"),
                "n_turns": loop_out.get("n_turns"),
                "debate_dossier_path": features.get("debate_dossier_path"),
                "run_log": log_paths,
            },
            summary=summary,
        )

    async def _auto_submit_if_ready(
        self,
        state: dict[str, Any],
        tools: Any,
        *,
        reason: str | None,
    ) -> bool:
        """max_turns 耗尽但已有 metrics/skill 时强制 submit，保留 ReAct 成果。"""
        if not state.get("metrics") or not state.get("gates"):
            return False
        skill_results = state.get("skill_results") or {}
        pack = state.get("rule_pack") or {}
        payload = _compose_finance_submit_payload(state, pack)
        # 结构化摘要：按 skill 列 top 风险，避免空模板
        lines = [
            f"財務 ReAct 自動收束（{reason or 'max_turns'}）："
            f"已完成 {len(skill_results)}/{4} skill；"
            f"規則參考分 {pack.get('risk_score')}（{pack.get('risk_level')}）。"
        ]
        for name, data in skill_results.items():
            pts = [p for p in (data.get("risk_points") or []) if isinstance(p, dict)]
            top = sorted(
                pts,
                key=lambda p: {"high": 0, "medium": 1, "low": 2}.get(
                    str(p.get("level") or "medium"), 3
                ),
            )[:3]
            bits = []
            for p in top:
                code = p.get("code") or "?"
                page = p.get("evidence_page")
                if page is None:
                    ev = p.get("evidence") or []
                    if isinstance(ev, list) and ev and isinstance(ev[0], dict):
                        page = ev[0].get("page")
                bits.append(f"{code}" + (f"@p{page}" if page else ""))
            lines.append(
                f"- {name}：{len(pts)} 點"
                + (f"（{'；'.join(bits)}）" if bits else "")
            )
        cash = state.get("cash_burn") or {}
        if cash.get("CASH_RUNWAY_MONTHS") is None and not cash.get("skipped"):
            lines.append("- 注意：現金跑道未測算（runway=null），已/應計 RUNWAY_UNCERTAIN。")
        summary = "\n".join(lines)
        payload["summary"] = summary
        payload["reasoning"] = f"{summary}\n{payload.get('reasoning') or ''}".strip()
        obs = await tools.execute("submit_finance_report", payload, state)
        return bool(obs.get("ok") and state.get("final_report"))

    async def _run_pipeline(
        self,
        doc_id: str,
        *,
        issuer_type: str = "general",
        retrieval_json: Path | str | None = None,
        parse_json: Path | str | None = None,
        top_k: int | None = None,
        doc_name: str | None = None,
        pdf_name: str | None = None,
        force_rules: bool = False,
        client_project_id: str | None = None,
        task_id: str | None = None,
        analysis_id: str | None = None,
    ) -> AgentResult:
        """旧流水线：retrieve→extract→gates→单次LLM/规则。"""
        t0 = time.time()
        tool_calls: list[dict[str, Any]] = []
        log = self._run_logger

        t1 = time.time()
        bundle = await retrieve_agent(
            "finance",
            doc_id,
            issuer_type=issuer_type,
            top_k=top_k,
            offline_json=retrieval_json,
        )
        retrieve_info = {
            "source": bundle.get("_source"),
            "tables": list((bundle.get("evidence_by_table") or {}).keys()),
            "skipped_fields": len(bundle.get("skipped_fields") or []),
        }
        tool_calls.append({"tool": "retrieve_finance", **retrieve_info})
        if log:
            log.step(
                "retrieve_finance",
                kind="tool",
                input_summary={"doc_id": doc_id, "mode": "pipeline"},
                output=retrieve_info,
                duration_ms=int((time.time() - t1) * 1000),
            )

        t1 = time.time()
        extracted = extract_financials_from_retrieval(bundle)
        metrics = extracted.get("metrics") or {}
        extract_info = {
            "metrics": list(metrics.keys()),
            "years": extracted.get("years"),
            "bs_reconcile": extracted.get("bs_reconcile"),
        }
        tool_calls.append({"tool": "extract_metrics", **extract_info})
        if log:
            log.step("extract_metrics", kind="skill", output=extract_info, duration_ms=int((time.time() - t1) * 1000))

        t1 = time.time()
        gates = resolve_issuer_gates(issuer_type, metrics)
        cash_burn = compute_cash_burn(metrics, gates)
        if log:
            log.step(
                "gates_and_cash_burn",
                kind="helper",
                output={"gates": {k: gates.get(k) for k in ("is_unprofitable", "skip_3_4")}, "cash_burn": cash_burn},
                duration_ms=int((time.time() - t1) * 1000),
            )

        scoring_mode = "rules"
        llm_pack: dict[str, Any] = {}
        use_llm = (
            not force_rules
            and self._llm is not None
            and getattr(self._llm, "available", False)
        )
        if use_llm:
            try:
                llm_pack = await analyze_finance_llm(
                    self._llm,
                    doc_id=doc_id,
                    issuer_type=issuer_type,
                    metrics=metrics,
                    gates=gates,
                    cash_burn=cash_burn,
                    extracted=extracted,
                    run_logger=log,
                )
                scoring_mode = "llm"
                tool_calls.append({"tool": "analyze_finance_llm", "risk_score": llm_pack.get("risk_score")})
            except Exception as e:
                logger.warning("pipeline LLM failed: %s", e)
                use_llm = False

        if scoring_mode != "llm":
            scored = score_finance(metrics, gates, cash_burn, extracted)
            from src.skills.finance_toolbox import _draft_finance_dimensions_metrics

            draft_state = {
                "metrics": metrics,
                "gates": gates,
                "cash_burn": cash_burn,
                "issuer_type": issuer_type,
                "skill_results": {},
            }
            dims = _draft_finance_dimensions_metrics(draft_state)
            llm_pack = {
                "scoring_mode": "rules",
                "risk_score": scored["risk_score"],
                "risk_level": scored["risk_level"],
                "score_breakdown": scored.get("score_breakdown") or [],
                "risk_points": scored.get("risk_points") or [],
                "negative_findings": scored.get("negative_findings") or [],
                "dimensions": dims,
                "reasoning": scored.get("reasoning")
                or scored.get("summary")
                or "规则引擎打分（含 runway/CFO；无证据页仍计分）",
                "summary": scored.get("summary") or "",
                "think_status": "n/a",
                "flags": scored.get("flags") or {},
            }
            tool_calls.append(
                {
                    "tool": "score_finance_rules_fallback",
                    "risk_score": scored["risk_score"],
                    "flags": scored.get("flags"),
                    "n_breakdown": len(scored.get("score_breakdown") or []),
                }
            )

        table_meta = extracted.get("table_meta") or {}
        snippets = [
            {
                "field_code": code,
                "page": info.get("page"),
                "source_type": info.get("source_type") or info.get("category"),
                "excerpt": info.get("excerpt") or "",
            }
            for code, info in table_meta.items()
        ]
        risk_score = float(llm_pack.get("risk_score") or 0)
        risk_level = str(llm_pack.get("risk_level") or "very_low")
        nf = llm_pack.get("negative_findings") or []
        # 禁止模板摘要「财务指标N项 [rules]」
        summary = (llm_pack.get("summary") or "").strip()
        if (not summary) or summary.startswith("财务指标") or "[rules]" in summary:
            from src.skills.score_finance import build_rules_summary

            summary = build_rules_summary(
                risk_score=risk_score,
                risk_level=risk_level,
                flags=llm_pack.get("flags") or {},
                breakdown=list(llm_pack.get("score_breakdown") or []),
                metrics=metrics,
                cash_burn=cash_burn,
                gates=gates,
            )
            llm_pack["summary"] = summary
        guard_warnings: list[str] = []
        _apply_18a_data_insufficient_guard(
            llm_pack,
            {
                "metrics": metrics,
                "gates": gates,
                "issuer_type": issuer_type,
            },
            guard_warnings,
        )
        if guard_warnings:
            risk_score = float(llm_pack.get("risk_score") or risk_score)
            risk_level = str(llm_pack.get("risk_level") or risk_level)
            summary = (llm_pack.get("summary") or summary or "").strip()
            if (not summary) or summary.startswith("财务指标") or "[rules]" in summary:
                from src.skills.score_finance import build_rules_summary

                summary = build_rules_summary(
                    risk_score=risk_score,
                    risk_level=risk_level,
                    flags=llm_pack.get("flags") or {},
                    breakdown=list(llm_pack.get("score_breakdown") or []),
                    metrics=metrics,
                    cash_burn=cash_burn,
                    gates=gates,
                )
                summary = summary + "；data_insufficient 已抬档"
                llm_pack["summary"] = summary
        log_paths = log.paths if log else {}
        if log:
            log.result({"risk_score": risk_score, "scoring_mode": scoring_mode, "summary": summary})
            if self._close_logger:
                log.close(final_summary=summary)

        return AgentResult(
            agent="finance",
            doc_id=doc_id,
            risk_score=risk_score,
            risk_level=risk_level,
            score_breakdown=_normalize_breakdown(
                llm_pack.get("score_breakdown") or [], extracted
            ),
            risk_points=_normalize_risk_points(list(llm_pack.get("risk_points") or [])),
            metrics={**metrics, "cash_burn": cash_burn},
            features={
                "scoring_mode": scoring_mode,
                "negative_findings": nf,
                "bs_reconcile": extracted.get("bs_reconcile") or {},
                "dimensions": llm_pack.get("dimensions") or [],
                "llm_analysis": llm_pack.get("llm_analysis"),
                "model_think_excerpt": (llm_pack.get("model_think") or "")[:500] or None,
                "think_status": llm_pack.get("think_status"),
                "submit_warnings": guard_warnings,
                "run_log": log_paths,
            },
            gates=gates,
            evidence_summary={
                "table_meta": table_meta,
                "evidence_keys": list((extracted.get("evidence") or {}).keys()),
                "snippets": snippets,
                "run_log": log_paths,
            },
            trace={
                "tool_calls": tool_calls,
                "elapsed_sec": round(time.time() - t0, 3),
                "scoring_mode": scoring_mode,
                "structured_reasoning": llm_pack.get("reasoning"),
                "run_log": log_paths,
            },
            summary=summary,
        )

    async def respond_to_controller(
        self,
        question,
        claim_card: dict[str, Any] | None = None,
        *,
        round_no: int = 1,
        doc_id: str | None = None,
        parse_json: Path | str | None = None,
    ):
        from src.skills.debate_reply import expert_respond_to_controller

        return await expert_respond_to_controller(
            agent="finance",
            question=question,
            claim_card=claim_card,
            llm=self._llm,
            doc_id=doc_id or self._doc_id,
            parse_json=parse_json or self._parse_json,
            run_logger=self._run_logger,
            round_no=round_no,
        )
