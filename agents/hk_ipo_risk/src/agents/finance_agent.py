from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from src.agents.react_loop import run_react_loop
from src.llm.prompts import FINANCE_REACT_SYSTEM, FINANCE_REACT_USER
from src.models.evidence import AgentResult
from src.skills.analyze_finance import _normalize_risk_points, analyze_finance_llm
from src.skills.extract_financials import extract_financials_from_retrieval
from src.skills.finance_toolbox import build_finance_tool_registry
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
        max_turns: int = 8,
    ) -> None:
        self._llm = llm
        self._run_logger = run_logger
        self._rules_only = rules_only
        self._pipeline = pipeline
        self._max_turns = max_turns

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
    ) -> AgentResult:
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
            )
        return await self._run_react(
            doc_id,
            issuer_type=issuer_type,
            retrieval_json=retrieval_json,
            parse_json=parse_json,
            top_k=top_k,
            doc_name=doc_name,
            pdf_name=pdf_name,
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
            "finished": False,
        }
        user = FINANCE_REACT_USER.format(
            doc_id=doc_id,
            issuer_type=issuer_type,
            doc_name=doc_name or doc_id,
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
            )

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
        features = {
            "scoring_mode": scoring_mode,
            "rules_floor": report.get("rules_floor"),
            "negative_findings": report.get("negative_findings") or [],
            "bs_reconcile": extracted.get("bs_reconcile") or {},
            "dimensions": report.get("dimensions") or [],
            "llm_analysis": report.get("llm_analysis"),
            "model_think_excerpt": (report.get("model_think") or "")[:500] or None,
            "think_status": report.get("think_status"),
            "submit_warnings": report.get("submit_warnings") or [],
            "react_turns": loop_out.get("n_turns"),
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
            log.close(final_summary=summary)

        return AgentResult(
            agent="finance",
            doc_id=doc_id,
            risk_score=risk_score,
            risk_level=risk_level,
            score_breakdown=report.get("score_breakdown") or [],
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
                "run_log": log_paths,
            },
            trace={
                "tool_calls": loop_out.get("turns") or [],
                "elapsed_sec": round(time.time() - t0, 3),
                "scoring_mode": scoring_mode,
                "structured_reasoning": report.get("reasoning"),
                "n_turns": loop_out.get("n_turns"),
                "run_log": log_paths,
            },
            summary=summary,
        )

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
            llm_pack = {
                "scoring_mode": "rules",
                "risk_score": scored["risk_score"],
                "risk_level": scored["risk_level"],
                "score_breakdown": scored.get("score_breakdown") or [],
                "risk_points": scored.get("risk_points") or [],
                "negative_findings": scored.get("negative_findings") or [],
                "dimensions": [],
                "reasoning": "规则/流水线兜底",
                "summary": "",
                "think_status": "n/a",
            }
            tool_calls.append({"tool": "score_finance_rules_fallback", "risk_score": scored["risk_score"]})

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
        summary = llm_pack.get("summary") or (
            f"财务指标{len(metrics)}项；风险分 {risk_score:.1f} ({risk_level}) [{scoring_mode}]"
        )
        log_paths = log.paths if log else {}
        if log:
            log.result({"risk_score": risk_score, "scoring_mode": scoring_mode, "summary": summary})
            log.close(final_summary=summary)

        return AgentResult(
            agent="finance",
            doc_id=doc_id,
            risk_score=risk_score,
            risk_level=risk_level,
            score_breakdown=llm_pack.get("score_breakdown") or [],
            risk_points=llm_pack.get("risk_points") or [],
            metrics={**metrics, "cash_burn": cash_burn},
            features={
                "scoring_mode": scoring_mode,
                "negative_findings": nf,
                "bs_reconcile": extracted.get("bs_reconcile") or {},
                "dimensions": llm_pack.get("dimensions") or [],
                "llm_analysis": llm_pack.get("llm_analysis"),
                "model_think_excerpt": (llm_pack.get("model_think") or "")[:500] or None,
                "think_status": llm_pack.get("think_status"),
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
