from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from pathlib import Path
from typing import Any, Callable

from src.config import resolve_firecrawl_settings, resolve_market_agent_settings, resolve_sina_finance_settings
from src.agents.react_loop import run_react_loop
from src.llm.prompts import (
    MARKET_ANALYSIS_SYSTEM,
    MARKET_ANALYSIS_USER,
    MARKET_DEBATE_USER,
    MARKET_OPINION_USER,
    MARKET_REACT_SYSTEM,
    MARKET_REACT_USER,
)
from src.models.evidence import AgentResult, RiskPoint, ScoreBreakdownItem
from src.models.debate import DebateClaim, DebateDossier
from src.models.market import (
    MarketDebateResponse,
    MarketEvidence,
    MarketSentimentAnalysis,
    PublicOpinionAssessment,
)
from src.skills.explain_market import MarketEvidenceBuilder
from src.skills.score_market import MarketRiskScorer
from src.skills.score_market_history import HistoricalMarketRiskScorer
from src.skills.market_toolbox import build_market_tool_registry
from src.tools.firecrawl_news import FirecrawlNewsCollector
from src.tools.market_data import MarketDataLoader
from src.tools.market_debate import MarketDebateToolbox
from src.models.debate import save_dossier
from src.tools.sina_finance_news import SinaFinanceNewsCollector

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[dict[str, Any]], None]


class MarketAgent:
    """Offline-first pre-listing market-risk agent.

    Structured market data produces the authoritative deterministic score. The
    LLM explains that score and, when dated pre-cutoff articles exist, classifies
    public opinion. This keeps historical runs reproducible and debate-ready.
    """

    def __init__(
        self,
        llm: Any | None = None,
        *,
        scorer: MarketRiskScorer | None = None,
        historical_scorer: HistoricalMarketRiskScorer | None = None,
        on_progress: ProgressCallback | None = None,
        strict_cutoff: bool | None = None,
        market_settings: dict[str, Any] | None = None,
        firecrawl_settings: dict[str, Any] | None = None,
        firecrawl_client: Any | None = None,
        sina_settings: dict[str, Any] | None = None,
        sina_client: Any | None = None,
        run_logger: Any | None = None,
        max_turns: int | None = None,
    ) -> None:
        self._scorer = scorer or MarketRiskScorer()
        self._historical_scorer = historical_scorer or HistoricalMarketRiskScorer()
        self._on_progress = on_progress
        self._market_settings = (
            market_settings
            if market_settings is not None
            else resolve_market_agent_settings()
        )
        self._llm = (
            llm
            if bool((self._market_settings.get("llm") or {}).get("enabled", True))
            else None
        )
        configured_cutoff = bool(
            (self._market_settings.get("cutoff") or {}).get(
                "strict_prelisting",
                True,
            )
        )
        self._strict_cutoff = (
            configured_cutoff if strict_cutoff is None else strict_cutoff
        )
        if firecrawl_settings is None:
            firecrawl_ref = self._market_settings.get("firecrawl") or {}
            firecrawl_settings = resolve_firecrawl_settings(
                settings_path=firecrawl_ref.get("settings_path"),
                local_settings_path=firecrawl_ref.get("local_settings_path"),
                enabled=bool(firecrawl_ref.get("enabled", True)),
            )
        self._firecrawl_settings = firecrawl_settings
        self._firecrawl_client = firecrawl_client
        if sina_settings is None:
            sina_ref = self._market_settings.get("sina_finance") or {}
            sina_settings = resolve_sina_finance_settings(
                settings_path=sina_ref.get("settings_path"),
                local_settings_path=sina_ref.get("local_settings_path"),
                enabled=bool(sina_ref.get("enabled", False)),
            )
        self._sina_settings = sina_settings
        self._sina_client = sina_client
        self._run_logger = run_logger
        self._last_result: AgentResult | None = None
        self._doc_id = ""
        configured_turns = int(
            max_turns
            if max_turns is not None
            else (self._market_settings.get("llm") or {}).get("max_turns") or 10
        )
        self._max_turns = max(1, configured_turns)

    def _emit(self, event: dict[str, Any]) -> None:
        if not self._on_progress:
            return
        try:
            self._on_progress(event)
        except Exception:
            logger.exception("market on_progress failed")

    def _emit_step(
        self,
        name: str,
        status: str,
        output: dict[str, Any] | None = None,
    ) -> None:
        """Emit a bounded, UI-facing market stage event.

        Stage output is deliberately bounded to counters, identifiers and
        short evidence excerpts; it must never receive article bodies or
        credentials.
        """
        event: dict[str, Any] = {
            "event": "step",
            "agent": "market",
            "name": name,
            "status": status,
        }
        if output:
            event["output"] = output
        self._emit(event)

    async def run(
        self,
        doc_id: str,
        *,
        stock_code: str,
        features_csv: Path | str | None = None,
        news_dir: Path | str | None = None,
        public_opinion: PublicOpinionAssessment | dict[str, Any] | None = None,
    ) -> AgentResult:
        started = time.time()
        self._doc_id = doc_id
        data_settings = self._market_settings.get("data") or {}
        news_search_settings = self._firecrawl_settings.get("search") or {}
        news_lookback_days = int(news_search_settings.get("lookback_days") or 365)
        news_max_articles = int(news_search_settings.get("max_urls") or 10)
        loader_kwargs: dict[str, Any] = {
            "strict_cutoff": self._strict_cutoff,
            "features_csv": features_csv or data_settings.get("features_csv"),
            "news_dir": news_dir or data_settings.get("news_dir"),
            "news_lookback_days": news_lookback_days,
            "news_max_articles": news_max_articles,
        }
        loader_kwargs = {key: value for key, value in loader_kwargs.items() if value is not None}
        loader = MarketDataLoader(**loader_kwargs)

        self._emit_step("load_market_snapshot", "running")
        snapshot = loader.load_snapshot(stock_code)
        self._emit_step(
            "load_market_snapshot",
            "ok",
            {
                "stock_code": snapshot.stock_code,
                "as_of_date": snapshot.as_of_date.isoformat(),
                "cutoff_verified": snapshot.cutoff_verified,
                "missing_fields": len(snapshot.missing_fields),
            },
        )

        self._emit_step("inspect_public_opinion", "running")
        news_status = loader.inspect_news_availability(snapshot)
        self._emit_step(
            "inspect_public_opinion",
            "ok" if not news_status.get("errors") else "degraded",
            {
                "total_rows": news_status.get("total_rows", 0),
                "in_window_rows": news_status.get("in_window_rows", 0),
                "before_window_rows": news_status.get("before_window_rows", 0),
                "after_cutoff_rows": max(
                    0,
                    int(news_status.get("total_rows") or 0)
                    - int(news_status.get("pre_cutoff_rows") or 0),
                ),
                "max_articles": news_status.get("max_articles"),
                "remaining_capacity": news_status.get("remaining_capacity"),
                "reason": news_status.get("unavailable_reason"),
            },
        )
        sina_status = await self._maybe_fetch_sina_news(
            snapshot,
            news_dir=loader.news_dir,
            local_news_status=news_status,
        )
        if sina_status.get("accepted_articles"):
            news_status = loader.inspect_news_availability(snapshot)
        firecrawl_status = await self._maybe_fetch_firecrawl_news(
            snapshot,
            news_dir=loader.news_dir,
            local_news_status=news_status,
        )
        if firecrawl_status.get("accepted_articles"):
            news_status = loader.inspect_news_availability(snapshot)
        news_status["firecrawl"] = firecrawl_status
        self._emit_step("validate_public_opinion", "running")
        opinion = await self._resolve_public_opinion(
            loader,
            snapshot,
            public_opinion,
            news_status=news_status,
        )
        self._emit_step(
            "validate_public_opinion",
            "ok" if opinion.available else "degraded",
            {
                "available": opinion.available,
                "candidate_count": news_status.get("in_window_rows", 0),
                "date_verified_count": news_status.get("in_window_rows", 0),
                "llm_verified_count": opinion.relevant_articles if opinion.available else 0,
                "used_in_score_count": opinion.relevant_articles if opinion.available else 0,
                "relevant_articles": opinion.relevant_articles,
                "has_risk_score": opinion.risk_score is not None,
                "reason": opinion.unavailable_reason,
            },
        )
        self._emit_step("analyze_market_dimensions", "running")
        score_pack = self._scorer.score(snapshot, opinion)
        prelisting_risk = self._historical_scorer.score(
            snapshot,
            features_csv=loader.features_csv,
            public_opinion=opinion,
            fallback_score_pack=score_pack,
        )
        evidence_builder = MarketEvidenceBuilder()
        sentiment_analysis = evidence_builder.build(
            snapshot,
            score_pack,
            opinion,
            features_file=loader.features_csv,
            news_status=news_status,
        )
        self._emit_step(
            "analyze_market_dimensions",
            "ok",
            {
                "modules": sorted(score_pack.module_scores),
                "public_opinion_used": score_pack.public_opinion_used,
                "coverage_ratio": score_pack.coverage_ratio,
            },
        )
        react_context = {
            "snapshot": snapshot,
            "score_pack": score_pack,
            "opinion": opinion,
            "sentiment_analysis": sentiment_analysis,
            "prelisting_risk": prelisting_risk,
            "news_status": news_status,
            "firecrawl_status": firecrawl_status,
        }
        self._emit_step("validate_llm_assessment", "running")
        llm_pack, react_trace = await self._analyze_with_react(
            doc_id=doc_id,
            context=react_context,
        )
        if not llm_pack:
            llm_pack = await self._analyze_with_llm(
                snapshot,
                score_pack,
                opinion,
                sentiment_analysis,
                prelisting_risk,
            )
            react_trace["fallback"] = "single_call_llm_analysis" if llm_pack else "deterministic_only"
        self._emit_step(
            "validate_llm_assessment",
            "ok" if llm_pack else "degraded",
            {
                "used": bool(llm_pack),
                "fallback": react_trace.get("fallback"),
                "react_turns": react_trace.get("n_turns"),
            },
        )
        llm_assessment = self._validate_llm_risk_assessment(
            llm_pack,
            evidence_ids={item.evidence_id for item in sentiment_analysis.evidence_ledger},
        )
        self._emit_step("score_market_rules", "running")
        scoring = self._reconcile_scores(
            deterministic_score=prelisting_risk.score,
            deterministic_level=prelisting_risk.risk_level,
            llm_assessment=llm_assessment,
        )
        self._emit_step(
            "score_market_rules",
            "ok",
            {
                "deterministic_score": scoring.get("deterministic_score"),
                "llm_score": scoring.get("llm_score"),
                "final_score": scoring.get("final_score"),
                "final_risk_level": scoring.get("final_risk_level"),
                "scoring_mode": scoring.get("scoring_mode"),
                "public_opinion_used": score_pack.public_opinion_used,
            },
        )
        self._emit_step("build_market_report", "running")
        self._apply_llm_sentiment_analysis(sentiment_analysis, llm_pack)
        sentiment_analysis.report_markdown = evidence_builder.render_markdown(
            snapshot,
            score_pack,
            sentiment_analysis,
        )
        sentiment_analysis.report_markdown = self._inject_prelisting_risk(
            sentiment_analysis.report_markdown,
            prelisting_risk,
            scoring,
        )
        summary = (
            f"{sentiment_analysis.overall_summary}；上市首日破发风险分"
            f"{scoring['final_score']:.1f}（{scoring['final_risk_level']}）"
        )

        breakdown = []
        risk_points: list[RiskPoint] = []
        for name, module in prelisting_risk.module_scores.items():
            weight = prelisting_risk.effective_module_weights.get(name, 0.0)
            if module.risk_score is None or weight <= 0:
                continue
            breakdown.append(
                ScoreBreakdownItem(
                    code=f"MARKET_{name.upper()}",
                    delta=round(module.risk_score * weight, 2),
                    rule_ref=f"market/{name}",
                    note=f"historical_module={module.risk_score:.2f}, weight={weight:.4f}, coverage={module.coverage_ratio:.2%}",
                    metric_value=module.risk_score,
                )
            )
            if module.risk_score >= 60:
                risk_points.append(
                    RiskPoint(
                        code=f"MARKET_{name.upper()}_RISK",
                        level="high" if module.risk_score >= 80 else "medium",
                        rule_ref=f"market/{name}",
                        value=module.risk_score,
                        description=f"{name}历史校准风险分 {module.risk_score:.2f}",
                    )
                )

        known_evidence_ids = {item.evidence_id for item in sentiment_analysis.evidence_ledger}
        for item in llm_pack.get("risk_points") or []:
            if not isinstance(item, dict) or not item.get("description"):
                continue
            description = str(item.get("description"))
            if not any(evidence_id in description for evidence_id in known_evidence_ids):
                continue
            risk_points.append(
                RiskPoint(
                    code=str(item.get("code") or "MARKET_LLM_FINDING"),
                    level=str(item.get("level") or "medium") if str(item.get("level") or "medium") in {"high", "medium", "low"} else "medium",
                    rule_ref=str(item.get("rule_ref") or "market/llm-analysis"),
                    value=item.get("value"),
                    description=description,
                )
            )

        evidence = [e.model_dump(mode="json") for e in snapshot.evidence]
        evidence.extend(e.model_dump(mode="json") for e in opinion.evidence)
        dossier = self._build_debate_dossier(
            doc_id=doc_id,
            final_score=scoring["final_score"],
            final_level=scoring["final_risk_level"],
            score_version=prelisting_risk.score_version,
            scoring=scoring,
            sentiment_analysis=sentiment_analysis,
            risk_points=risk_points,
        )
        dossier_path = save_dossier(
            dossier,
            (self._market_settings.get("output") or {}).get("debate_directory")
            or Path(__file__).resolve().parents[2] / ".runtime" / "debate",
        )
        sentiment_analysis.report_markdown = (
            sentiment_analysis.report_markdown.rstrip()
            + "\n\n## DebateDossier\n\n"
            + f"- 证据档案：`{dossier_path}`\n"
            + "- 第一版未启用 market retrieval package；辩论补证使用独立市场证据工具。\n"
        )
        safe_evidence = [
            {
                "title": item.label,
                "url": item.url,
                "published_at": (
                    item.observation_date.isoformat()
                    if item.observation_date is not None
                    else None
                ),
                "excerpt": (item.excerpt or item.claim or item.interpretation)[:500],
                "source_type": "unknown",
                "field_code": item.indicator,
                "section_id": item.module,
            }
            for item in sentiment_analysis.evidence_ledger[:12]
        ]
        safe_risk_points = [
            {
                "code": item.code,
                "level": item.level,
                "value": item.value,
                "description": item.description,
                "evidence": [
                    evidence.model_dump(mode="json")
                    for evidence in item.evidence[:3]
                ],
            }
            for item in risk_points[:12]
        ]
        self._emit_step(
            "build_market_report",
            "ok",
            {
                "summary": summary,
                "evidence_count": len(sentiment_analysis.evidence_ledger),
                "risk_point_count": len(risk_points),
                "report_chars": len(sentiment_analysis.report_markdown or ""),
                "evidence": safe_evidence,
                "risk_points": safe_risk_points,
            },
        )
        result = AgentResult(
            agent="market",
            doc_id=doc_id,
            risk_score=scoring["final_score"],
            risk_level=scoring["final_risk_level"],
            score_breakdown=breakdown,
            risk_points=risk_points,
            metrics=snapshot.features,
            features={
                "stock_code": snapshot.stock_code,
                "company": snapshot.company,
                "listing_date": snapshot.listing_date.isoformat(),
                "as_of_date": snapshot.as_of_date.isoformat(),
                "market_observation_date": (
                    snapshot.market_observation_date.isoformat()
                    if snapshot.market_observation_date
                    else None
                ),
                "effective_weights": score_pack.effective_weights,
                "public_opinion_used": score_pack.public_opinion_used,
                "public_opinion": opinion.model_dump(mode="json"),
                "firecrawl": firecrawl_status,
                "sina_finance": sina_status,
                "coverage_ratio": score_pack.coverage_ratio,
                "quality_flags": snapshot.quality_flags,
                "cutoff_verified": snapshot.cutoff_verified,
                "sentiment_analysis": sentiment_analysis.model_dump(mode="json"),
                "evidence_catalog": [
                    item.model_dump(mode="json")
                    for item in sentiment_analysis.evidence_ledger
                ],
                "prelisting_day1_risk": prelisting_risk.model_dump(mode="json"),
                "deterministic_score": scoring["deterministic_score"],
                "llm_score": scoring["llm_score"],
                "llm_risk_assessment": llm_assessment,
                "score_reconciliation": scoring,
                "sentiment_report_markdown": sentiment_analysis.report_markdown,
                "compatibility_scoring": {
                    "deprecated_as_primary_output": True,
                    "risk_score": score_pack.risk_score,
                    "risk_level": score_pack.risk_level,
                    "inverse_risk_score": score_pack.market_heat_score,
                    "module_scores": {
                        name: module.model_dump(mode="json")
                        for name, module in score_pack.module_scores.items()
                    },
                },
                "scoring_mode": scoring["scoring_mode"],
                "rules_floor": scoring["deterministic_score"],
                "skill_results": {
                    name: module.model_dump(mode="json")
                    for name, module in prelisting_risk.module_scores.items()
                },
                "llm_analysis": llm_pack or None,
                "react_turns": react_trace.get("n_turns"),
                "debate_ready": True,
                "debate_dossier_path": str(dossier_path),
            },
            gates={
                "public_opinion_available": opinion.available,
                "four_module_equal_weight": score_pack.public_opinion_used,
                "strict_prelisting_cutoff": self._strict_cutoff,
                "firecrawl_configured": bool(firecrawl_status.get("configured")),
                "firecrawl_attempted": bool(firecrawl_status.get("attempted")),
                "sina_finance_configured": bool(sina_status.get("configured")),
                "sina_finance_attempted": bool(sina_status.get("attempted")),
            },
            evidence_summary={
                "evidence": evidence,
                "evidence_ledger": [
                    item.model_dump(mode="json")
                    for item in sentiment_analysis.evidence_ledger
                ],
                "historical_risk_evidence": [
                    item.model_dump(mode="json")
                    for module in prelisting_risk.module_scores.values()
                    for item in module.indicators
                ],
                "data_boundary": sentiment_analysis.data_boundary.model_dump(mode="json"),
                "contradictions": sentiment_analysis.contradictions,
                "limitations": sentiment_analysis.limitations,
                "missing_fields": snapshot.missing_fields,
                "data_source": str(loader.features_csv),
                "firecrawl": firecrawl_status,
                "sina_finance": sina_status,
            },
            trace={
                "elapsed_sec": round(time.time() - started, 3),
                "llm_reasoning": llm_pack.get("_reasoning") if llm_pack else None,
                "weight_policy": "25% each with reliable public opinion; otherwise 1/3 for macro/industry/ipo_market",
                "compatibility_note": (
                    "top-level risk_score is the historical prelisting D1 break-risk index; "
                    "the former fixed-threshold score remains under compatibility_scoring"
                ),
                "primary_risk_contract": (
                    "risk_score=max(deterministic historical floor, grounded LLM score); "
                    "risk anchor=issue price; "
                    "secondary market return base=first trading day open"
                ),
                "score_reconciliation": scoring,
                "react": react_trace,
                "debate_dossier_path": str(dossier_path),
                "firecrawl_policy": firecrawl_status.get("fetch_policy"),
                "configuration": {
                    "market_settings_path": self._market_settings.get("settings_path"),
                    "market_local_settings_path": self._market_settings.get("local_settings_path"),
                    "strict_prelisting": self._strict_cutoff,
                },
            },
            summary=summary,
        )
        self._last_result = result
        return result

    async def _prepare_react_context(self, state: dict[str, Any]) -> dict[str, Any]:
        context = state.get("_market_context")
        if not isinstance(context, dict):
            raise RuntimeError("market ReAct context has not been prepared")
        return context

    async def _analyze_with_react(
        self,
        *,
        doc_id: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self._llm_available:
            return {}, {"ok": False, "reason": "llm_unavailable", "n_turns": 0}
        snapshot = context["snapshot"]
        state: dict[str, Any] = {
            "doc_id": doc_id,
            "stock_code": snapshot.stock_code,
            "_market_context": context,
            "finished": False,
            "no_tool_call_hint": (
                "请使用市场工具继续：先lookup_market_row并运行市场skills，随后"
                "run_market_rule_checks、score_market_with_llm，最后submit_market_report。"
            ),
        }
        try:
            loop_out = await run_react_loop(
                llm=self._llm,
                tools=build_market_tool_registry(self),
                system_prompt=MARKET_REACT_SYSTEM,
                user_prompt=MARKET_REACT_USER.format(
                    company=snapshot.company,
                    stock_code=snapshot.stock_code,
                    doc_id=doc_id,
                    as_of_date=snapshot.as_of_date.isoformat(),
                    listing_date=snapshot.listing_date.isoformat(),
                ),
                state=state,
                run_logger=self._run_logger,
                max_turns=self._max_turns,
                submit_tool_name="submit_market_report",
                no_tool_nudge=state["no_tool_call_hint"],
                reasoning_effort="low",
            )
        except Exception as exc:
            logger.warning("market ReAct failed, fallback to single-call analysis: %s", exc)
            return {}, {"ok": False, "reason": f"{type(exc).__name__}:{exc}", "n_turns": 0}
        submission = state.get("react_submission") or {}
        assessment = submission.get("llm_assessment") or {}
        result = {
            **assessment,
            "summary": submission.get("summary"),
            "module_assessments": submission.get("module_assessments") or {},
            "risk_points": submission.get("risk_points") or [],
            "_reasoning": state.get("last_reasoning"),
        } if submission else {}
        trace = {
            "ok": bool(loop_out.get("ok") and submission),
            "n_turns": loop_out.get("n_turns"),
            "tools": [turn.get("tool") for turn in loop_out.get("turns") or [] if turn.get("tool")],
            "error": loop_out.get("error"),
        }
        return result, trace

    async def _maybe_fetch_sina_news(
        self,
        snapshot: Any,
        *,
        news_dir: Path,
        local_news_status: dict[str, Any],
    ) -> dict[str, Any]:
        self._emit_step("collect_sina_news", "running")
        collector = SinaFinanceNewsCollector(self._sina_settings, client=self._sina_client)
        status = collector.public_status()
        status.update({"attempted": False, "accepted_articles": 0})
        if int(local_news_status.get("pre_cutoff_rows") or 0) > 0:
            status["skip_reason"] = "usable_local_prelisting_news_exists"
            self._emit_step("collect_sina_news", "skipped", {"reason": status["skip_reason"]})
            return status
        if not self._sina_settings.get("enabled"):
            status["skip_reason"] = (
                "sina_api_not_configured" if status.get("requested_enabled") else "sina_disabled"
            )
            self._emit_step("collect_sina_news", "skipped", {"reason": status["skip_reason"]})
            return status
        try:
            status = await collector.collect(
                company=snapshot.company,
                stock_code=snapshot.stock_code,
                as_of_date=snapshot.as_of_date,
                news_dir=news_dir,
            )
            self._emit_step(
                "collect_sina_news",
                "ok" if not status.get("errors") else "degraded",
                {
                    "accepted_articles": status.get("accepted_articles", 0),
                    "rejected_missing_date": status.get("rejected_missing_date", 0),
                    "rejected_after_cutoff": status.get("rejected_after_cutoff", 0),
                },
            )
            return status
        except Exception as exc:
            logger.warning("Sina Finance public-opinion collection failed: %s", exc)
            status.update({
                "attempted": True,
                "errors": [f"collector_failed:{type(exc).__name__}:{exc}"],
            })
            self._emit_step("collect_sina_news", "error", {"error": "collector_failed"})
            return status

    async def _maybe_fetch_firecrawl_news(
        self,
        snapshot: Any,
        *,
        news_dir: Path,
        local_news_status: dict[str, Any],
    ) -> dict[str, Any]:
        self._emit_step(
            "firecrawl_public_opinion",
            "running",
            {"stock_code": snapshot.stock_code, "as_of_date": snapshot.as_of_date.isoformat()},
        )
        collector = FirecrawlNewsCollector(
            self._firecrawl_settings,
            client=self._firecrawl_client,
        )
        status = collector.public_status()
        status.update({"attempted": False, "accepted_articles": 0})
        policy = str(self._firecrawl_settings.get("fetch_policy") or "on_missing")
        reusable_raw = collector.has_reusable_raw_cache(
            stock_code=snapshot.stock_code,
            as_of_date=snapshot.as_of_date,
            news_dir=news_dir,
        )
        if policy == "never" and not reusable_raw:
            status["skip_reason"] = "fetch_policy_never"
            self._emit_step("firecrawl_public_opinion", "skipped", {"reason": status["skip_reason"]})
            return status
        in_window_rows = int(
            local_news_status.get("in_window_rows")
            if local_news_status.get("in_window_rows") is not None
            else local_news_status.get("pre_cutoff_rows") or 0
        )
        max_articles = int(
            local_news_status.get("max_articles")
            or (self._firecrawl_settings.get("search") or {}).get("max_urls")
            or 10
        )
        status["local_in_window_rows"] = in_window_rows
        status["max_articles"] = max_articles
        status["remaining_capacity"] = max(0, max_articles - in_window_rows)
        if policy == "on_missing" and in_window_rows > 0:
            status["skip_reason"] = "usable_local_news_in_window"
            self._emit_step("firecrawl_public_opinion", "skipped", {"reason": status["skip_reason"]})
            return status
        if not collector.enabled and not reusable_raw:
            status["skip_reason"] = (
                "firecrawl_api_key_missing"
                if status.get("requested_enabled") and not status.get("configured")
                else "firecrawl_disabled"
            )
            self._emit_step("firecrawl_public_opinion", "skipped", {"reason": status["skip_reason"]})
            return status
        try:
            status = await asyncio.to_thread(
                collector.collect,
                company=snapshot.company,
                stock_code=snapshot.stock_code,
                listing_date=snapshot.listing_date,
                as_of_date=snapshot.as_of_date,
                news_dir=news_dir,
            )
        except Exception as exc:
            logger.warning("Firecrawl public-opinion collection failed: %s", exc)
            status = collector.public_status()
            status.update(
                {
                    "attempted": True,
                    "accepted_articles": 0,
                    "errors": [
                        collector.redact_error(
                            f"collector_failed:{type(exc).__name__}:{exc}"
                        )
                    ],
                }
            )
        self._emit_step(
            "firecrawl_public_opinion",
            "ok" if not status.get("errors") else "degraded",
            {
                "search_requests": status.get("search_requests", 0),
                "search_hits": status.get("search_hits", 0),
                "unique_urls": status.get("unique_urls", 0),
                "scrape_requests": status.get("scrape_requests", 0),
                "accepted_articles": status.get("accepted_articles", 0),
                "rejected_after_cutoff": status.get("rejected_after_cutoff", 0),
                "rejected_missing_date": status.get("rejected_missing_date", 0),
                "rejected_before_window": status.get("rejected_before_window", 0),
                "raw_cache_used": status.get("raw_cache_used", False),
            },
        )
        return status

    async def _resolve_public_opinion(
        self,
        loader: MarketDataLoader,
        snapshot: Any,
        supplied: PublicOpinionAssessment | dict[str, Any] | None,
        *,
        news_status: dict[str, Any],
    ) -> PublicOpinionAssessment:
        if supplied is not None:
            assessment = (
                supplied
                if isinstance(supplied, PublicOpinionAssessment)
                else PublicOpinionAssessment.model_validate(supplied)
            )
            if not assessment.available:
                return assessment
            dated_evidence = [e for e in assessment.evidence if e.observation_date is not None]
            if (
                assessment.risk_score is None
                or assessment.relevant_articles <= 0
                or not dated_evidence
                or any(e.observation_date > snapshot.as_of_date for e in dated_evidence)
            ):
                return PublicOpinionAssessment(
                    available=False,
                    unavailable_reason="supplied_public_opinion_failed_cutoff_or_evidence_validation",
                )
            return assessment
        candidates = loader.load_news_candidates(snapshot)
        if not candidates:
            firecrawl = news_status.get("firecrawl") or {}
            raw_success = int(
                firecrawl.get("raw_successful_articles")
                or firecrawl.get("scraped_urls")
                or 0
            )
            if raw_success and not int(firecrawl.get("accepted_articles") or 0):
                unavailable_reason = (
                    "firecrawl_bodies_saved_but_no_verified_prelisting_publication_date"
                )
            elif firecrawl.get("errors"):
                unavailable_reason = "firecrawl_completed_with_errors_and_no_accepted_articles"
            else:
                unavailable_reason = str(
                    news_status.get("unavailable_reason")
                    or "no_reliable_prelisting_public_opinion"
                )
            return PublicOpinionAssessment(
                available=False,
                unavailable_reason=unavailable_reason,
            )
        if not self._llm_available:
            return PublicOpinionAssessment(
                available=False,
                unavailable_reason="prelisting_candidates_exist_but_relevance_not_verified",
            )

        prompt = MARKET_OPINION_USER.format(
            company=snapshot.company,
            stock_code=snapshot.stock_code,
            as_of_date=snapshot.as_of_date.isoformat(),
            articles=json.dumps(candidates[:30], ensure_ascii=False),
        )
        try:
            response = await self._llm.chat_json(
                [
                    {"role": "system", "content": MARKET_ANALYSIS_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                # 舆情相关性分类是简单结构化 JSON 输出；thinking 模式长 CoT 会
                # 挤爆 max_tokens 预算导致 content 为空、最终 JSON 被截断，
                # 因此本调用关闭 thinking，确保分类结果稳定产出。
                enable_reasoning=False,
                max_tokens=2048,
            )
        except Exception as exc:
            logger.warning("market public-opinion classification failed: %s", exc)
            return PublicOpinionAssessment(
                available=False,
                unavailable_reason="public_opinion_llm_classification_failed",
            )
        data = response.get("data") or {}
        candidates_by_url = {str(item.get("url") or ""): item for item in candidates if item.get("url")}
        candidates_by_title = {str(item.get("title") or ""): item for item in candidates if item.get("title")}
        events: list[dict[str, Any]] = []
        for item in data.get("events") or []:
            if not isinstance(item, dict) or item.get("relevant") is not True:
                continue
            candidate = candidates_by_url.get(str(item.get("url") or ""))
            if candidate is None:
                candidate = candidates_by_title.get(str(item.get("title") or ""))
            if candidate is None:
                continue
            events.append(
                {
                    **candidate,
                    "relevant": True,
                    "direction": item.get("direction"),
                    "rationale": item.get("rationale"),
                }
            )
        if not data.get("has_relevant_opinion") or not events:
            return PublicOpinionAssessment(
                available=False,
                unavailable_reason="no_llm_verified_relevant_prelisting_public_opinion",
            )
        direction = self._bounded_score(data.get("direction_risk_score"), default=50.0)
        attention = self._bounded_score(data.get("attention_risk_score"), default=50.0)
        evidence = [
            MarketEvidence(
                source=str(item.get("source") or "news"),
                field="public_opinion",
                value=item.get("direction"),
                observation_date=self._date_or_none(item.get("published_at")),
                url=item.get("url"),
                note=str(item.get("rationale") or item.get("title") or ""),
            )
            for item in events
        ]
        return PublicOpinionAssessment(
            available=True,
            risk_score=round(direction * 0.8 + attention * 0.2, 2),
            relevant_articles=len(events),
            direction_score=direction,
            attention_score=attention,
            events=events,
            evidence=evidence,
        )

    async def _analyze_with_llm(
        self,
        snapshot: Any,
        score_pack: Any,
        opinion: Any,
        sentiment_analysis: MarketSentimentAnalysis,
        prelisting_risk: Any,
    ) -> dict[str, Any]:
        if not self._llm_available:
            return {}
        prompt = MARKET_ANALYSIS_USER.format(
            snapshot=json.dumps(
                {
                    "stock_code": snapshot.stock_code,
                    "company": snapshot.company,
                    "listing_date": snapshot.listing_date.isoformat(),
                    "as_of_date": snapshot.as_of_date.isoformat(),
                    "industry": snapshot.industry,
                    "features": snapshot.features,
                    "missing_fields": snapshot.missing_fields,
                },
                ensure_ascii=False,
                default=str,
            ),
            score_pack=json.dumps(
                {
                    "prelisting_day1_risk": prelisting_risk.model_dump(mode="json"),
                    "compatibility_scoring": score_pack.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
            public_opinion=json.dumps(opinion.model_dump(mode="json"), ensure_ascii=False),
            evidence_ledger=json.dumps(
                [
                    {
                        "evidence_id": item.evidence_id,
                        "module": item.module,
                        "label": item.label,
                        "display_value": item.display_value,
                        "direction": item.direction,
                        "interpretation": item.interpretation,
                        "quality_flags": item.quality_flags,
                    }
                    for item in sentiment_analysis.evidence_ledger
                ],
                ensure_ascii=False,
            ),
            preliminary_analysis=json.dumps(
                sentiment_analysis.model_dump(
                    mode="json",
                    exclude={"report_markdown", "evidence_ledger"},
                ),
                ensure_ascii=False,
            ),
        )
        try:
            response = await self._llm.chat_json(
                [{"role": "system", "content": MARKET_ANALYSIS_SYSTEM}, {"role": "user", "content": prompt}],
                enable_reasoning=True,
                max_tokens=2048,
                reasoning_max_tokens=256,
            )
            data = response.get("data") or {}
            data["_reasoning"] = response.get("reasoning")
            return data
        except Exception as exc:
            logger.warning("market LLM explanation failed: %s", exc)
            return {}

    @staticmethod
    def _inject_prelisting_risk(
        report: str,
        assessment: Any,
        scoring: dict[str, Any],
    ) -> str:
        modules = "\n".join(
            f"- {name}: {module.risk_score if module.risk_score is not None else '不可用'}"
            f"（有效权重 {module.effective_weight:.1%}，覆盖率 {module.coverage_ratio:.1%}）"
            for name, module in assessment.module_scores.items()
        )
        limitations = "\n".join(f"- {item}" for item in assessment.limitations) or "- 无"
        risk_bullets = (
            f"- **最终首日破发风险分：{scoring['final_score']:.1f}/100"
            f"（{scoring['final_risk_level']}）**\n"
            f"- 确定性历史校准分（rules floor）：{scoring['deterministic_score']:.1f}/100\n"
            f"- LLM 独立风险分：{scoring['llm_score'] if scoring['llm_score'] is not None else '不可用'}\n"
            f"- 合并方法：`{scoring['method']}`；{scoring['decision_reason']}\n"
            "- **主要风险锚点：发行价**（首日收盘价低于发行价）\n"
            "- **二级市场收益基准：上市首日开盘价**\n"
            f"- 评分版本：`{assessment.score_version}`\n"
            f"- 历史数据截止：`{assessment.history_cutoff}`\n"
            f"- 发行价锚点：{assessment.break_anchor_status}"
        )
        calibration = (
            "## 历史校准模块（首日破发风险分解）\n\n"
            f"{modules}\n\n"
            "## 校准限制\n\n"
            f"{limitations}\n"
        )

        data_heading = "## 数据边界\n"
        if data_heading in report:
            report = report.replace(
                data_heading,
                risk_bullets + "\n\n" + data_heading,
                1,
            )
        else:
            report = report.rstrip() + "\n\n" + risk_bullets + "\n"

        evidence_heading = "## 逐指标证据账本\n"
        if evidence_heading in report:
            report = report.replace(
                evidence_heading,
                calibration + "\n" + evidence_heading,
                1,
            )
        else:
            report = report.rstrip() + "\n\n" + calibration + "\n"

        return report

    @classmethod
    def _validate_llm_risk_assessment(
        cls,
        llm_pack: dict[str, Any],
        *,
        evidence_ids: set[str],
    ) -> dict[str, Any] | None:
        if not llm_pack or llm_pack.get("risk_score") is None:
            return None
        reason = str(llm_pack.get("score_reason") or "").strip()
        cited = sorted(evidence_id for evidence_id in evidence_ids if evidence_id in reason)
        if not reason or not cited:
            return None
        try:
            raw_score = float(llm_pack.get("risk_score"))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(raw_score):
            return None
        score = max(0.0, min(100.0, raw_score))
        try:
            confidence = max(0.0, min(1.0, float(llm_pack.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        return {
            "risk_score": round(score, 1),
            "risk_level": cls._risk_level(score),
            "confidence": round(confidence, 3),
            "score_reason": reason,
            "evidence_ids": cited,
            "dimension_scores": llm_pack.get("dimension_scores") or {},
            "validation_status": "accepted_grounded_score",
        }

    @classmethod
    def _reconcile_scores(
        cls,
        *,
        deterministic_score: float,
        deterministic_level: str,
        llm_assessment: dict[str, Any] | None,
    ) -> dict[str, Any]:
        floor = round(cls._bounded_score(deterministic_score, default=0), 1)
        if not llm_assessment:
            return {
                "deterministic_score": floor,
                "llm_score": None,
                "final_score": floor,
                "final_risk_level": cls._risk_level(floor),
                "difference": None,
                "method": "deterministic_fallback",
                "decision_reason": "LLM评分不可用或未通过证据引用校验，使用确定性历史校准分",
                "scoring_mode": "historical_rules_floor",
            }
        llm_score = round(float(llm_assessment["risk_score"]), 1)
        final = max(floor, llm_score)
        return {
            "deterministic_score": floor,
            "llm_score": llm_score,
            "final_score": round(final, 1),
            "final_risk_level": cls._risk_level(final),
            "difference": round(llm_score - floor, 1),
            "llm_evidence_ids": list(llm_assessment.get("evidence_ids") or []),
            "method": "max_llm_and_rules_floor",
            "decision_reason": (
                "LLM识别到更高且有证据支持的风险，采用LLM分"
                if llm_score > floor
                else "确定性历史校准分不低于LLM判断，规则托底生效"
            ),
            "scoring_mode": "market_react+historical_rules_floor",
        }

    @staticmethod
    def _risk_level(score: float) -> str:
        if score < 20:
            return "very_low"
        if score < 40:
            return "low"
        if score < 60:
            return "medium"
        if score < 80:
            return "high"
        return "very_high"

    @staticmethod
    def _build_debate_dossier(
        *,
        doc_id: str,
        final_score: float,
        final_level: str,
        score_version: str,
        scoring: dict[str, Any],
        sentiment_analysis: MarketSentimentAnalysis,
        risk_points: list[RiskPoint],
    ) -> DebateDossier:
        ledger = {item.evidence_id: item.model_dump(mode="json") for item in sentiment_analysis.evidence_ledger}
        claims: list[DebateClaim] = []
        for index, point in enumerate(risk_points, start=1):
            ids = [evidence_id for evidence_id in ledger if evidence_id in point.description]
            if not ids:
                module_hint = point.code.removeprefix("MARKET_").removesuffix("_RISK").lower()
                module_hint = "ipo_market" if module_hint == "ipo_market" else module_hint
                ids = [
                    evidence_id
                    for evidence_id, item in ledger.items()
                    if item.get("module") == module_hint
                ]
            refs = [
                {
                    "excerpt": str(ledger[evidence_id].get("interpretation") or ledger[evidence_id].get("claim") or "")[:500],
                    "source_type": "table",
                    "field_code": str(ledger[evidence_id].get("derived_field") or "") or None,
                    "confidence": 1.0,
                }
                for evidence_id in ids
            ]
            claims.append(DebateClaim(
                claim_id=f"MARKET-CLAIM-{index:03d}",
                agent="market",
                statement=point.description,
                code=point.code,
                level=point.level,
                confidence="high" if ids else "medium",
                evidence_ids=ids,
                evidence_refs=refs,
                retrieval_queries=[{"query": point.description, "intent": "market_evidence"}],
                metadata={"risk_code": point.code, "rule_ref": point.rule_ref},
            ))
        claims.append(DebateClaim(
            claim_id="MARKET-SCORE-001",
            agent="market",
            statement=f"上市首日破发风险最终评分为{final_score:.1f}（{final_level}）",
            code="MARKET_FINAL_SCORE",
            level="high" if final_score >= 60 else ("medium" if final_score >= 40 else "low"),
            confidence="high",
            evidence_ids=list(scoring.get("llm_evidence_ids") or []),
            metadata={"scoring": scoring},
        ))
        return DebateDossier(
            doc_id=doc_id,
            agent="market",
            score_version=score_version,
            risk_score=final_score,
            risk_level=final_level,
            claims=claims,
            summary=f"上市首日破发风险最终评分为{final_score:.1f}（{final_level}）",
            reasoning=str(scoring.get("decision_reason") or ""),
            retrieval_queries=[query for claim in claims for query in claim.retrieval_queries],
            evidence_catalog=ledger,
            scoring=scoring,
            limitations=list(sentiment_analysis.limitations),
        )

    @staticmethod
    def _apply_llm_sentiment_analysis(
        analysis: MarketSentimentAnalysis,
        llm_pack: dict[str, Any],
    ) -> None:
        """Accept LLM prose only when it cites an evidence ID from the ledger."""
        if not llm_pack:
            return
        evidence_ids = {item.evidence_id for item in analysis.evidence_ledger}

        def grounded(text: Any) -> str | None:
            candidate = str(text or "").strip()
            if not candidate:
                return None
            return candidate if any(evidence_id in candidate for evidence_id in evidence_ids) else None

        summary = grounded(llm_pack.get("summary"))
        if summary:
            analysis.overall_summary = summary
        assessments = llm_pack.get("module_assessments") or {}
        if isinstance(assessments, dict):
            for module, text in assessments.items():
                replacement = grounded(text)
                if module in analysis.module_summaries and replacement:
                    analysis.module_summaries[module] = replacement

    async def challenge(
        self,
        original_result: AgentResult | dict[str, Any],
        challenge: str,
        *,
        additional_evidence: list[dict[str, Any]] | None = None,
    ) -> MarketDebateResponse:
        """Debate hook reserved for the future master agent.

        A revised numeric score is advisory until the caller supplies new
        evidence and reruns ``run``; debate text alone never mutates the audited
        deterministic score.
        """
        original = original_result.model_dump(mode="json") if isinstance(original_result, AgentResult) else original_result
        if not self._llm_available:
            return MarketDebateResponse(
                stance="maintain",
                response="当前没有可用 LLM；维持可审计基准结论，需补充新证据后重新评分。",
                evidence_requests=["提供可验证且不晚于 as_of_date 的新增证据"],
                requires_new_evidence=True,
            )
        prompt = MARKET_DEBATE_USER.format(
            original=json.dumps(original, ensure_ascii=False, default=str),
            challenge=challenge,
            additional_evidence=json.dumps(additional_evidence or [], ensure_ascii=False, default=str),
        )
        response = await self._llm.chat_json(
            [{"role": "system", "content": MARKET_ANALYSIS_SYSTEM}, {"role": "user", "content": prompt}],
            enable_reasoning=True,
            max_tokens=1536,
            reasoning_max_tokens=256,
        )
        return MarketDebateResponse.model_validate(response.get("data") or {})

    async def respond_to_controller(
        self,
        question,
        claim_card: dict[str, Any] | None = None,
        *,
        round_no: int = 1,
        doc_id: str | None = None,
        parse_json: Path | str | None = None,
    ):
        from src.models.master import ClaimUpdate

        del claim_card, round_no, parse_json
        if doc_id:
            self._doc_id = doc_id
        original = self._last_result
        if original is None:
            return ClaimUpdate(
                question_id=getattr(question, "question_id", "") or "",
                target_agent="market",
                clue_id=getattr(question, "claim_id", None),
                status="unresolved",
                confidence=0.3,
                reply="市場情緒 Agent 尚無已完成的探查結果，無法回應總控質詢。",
                remaining_uncertainty="等待市場探查完成",
            )
        resp = await self.challenge(original, getattr(question, "question", "") or "")
        stance_status = {
            "maintain": "verified",
            "revise": "partially_accepted",
            "concede": "challenged",
        }
        status = stance_status.get(resp.stance, "unresolved")
        if resp.requires_new_evidence and resp.stance == "maintain":
            status = "unresolved"
        reply = (resp.response or "").strip()
        if resp.revised_summary:
            reply = f"{reply}\n修訂摘要：{resp.revised_summary}".strip()
        return ClaimUpdate(
            question_id=getattr(question, "question_id", "") or "",
            target_agent="market",
            clue_id=getattr(question, "claim_id", None),
            status=status,
            confidence=0.6 if status != "unresolved" else 0.4,
            reply=reply or "維持原市場結論，未提供可驗證的新證據。",
            revision_reason=resp.stance,
            remaining_uncertainty="; ".join(resp.evidence_requests) if resp.evidence_requests else "",
        )

    def build_debate_toolbox(
        self,
        *,
        doc_id: str,
        stock_code: str,
        phase: str,
        store: Any | None = None,
    ) -> MarketDebateToolbox:
        """Expose audited evidence tools to the future master-agent debate loop."""
        if phase not in {"prelisting", "postlisting"}:
            raise ValueError("phase must be prelisting or postlisting")
        data = self._market_settings.get("data") or {}
        return MarketDebateToolbox(
            doc_id=doc_id,
            stock_code=stock_code,
            phase=phase,
            features_csv=data.get("features_csv"),
            news_dir=data.get("news_dir"),
            checkpoints_csv=data.get("postlisting_checkpoints_csv"),
            store=store,
        )

    @property
    def _llm_available(self) -> bool:
        return bool(self._llm is not None and getattr(self._llm, "available", False))

    @staticmethod
    def _date_or_none(value: Any):
        from datetime import datetime

        try:
            return datetime.fromisoformat(str(value)[:10]).date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _bounded_score(value: Any, *, default: float) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = default
        return max(0.0, min(100.0, score))
