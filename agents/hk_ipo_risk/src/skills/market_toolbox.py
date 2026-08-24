from __future__ import annotations

from typing import Any

from src.skills.market_presets import MARKET_SKILL_PRESETS
from src.tools.schemas import MARKET_TOOL_SCHEMAS, ToolRegistry


def _known_market_evidence_ids(context: dict[str, Any]) -> set[str]:
    """Union narrative ledger IDs with historical-calibration indicator IDs."""
    known = {
        str(item.evidence_id)
        for item in context["sentiment_analysis"].evidence_ledger
        if getattr(item, "evidence_id", None)
    }
    prelisting = context.get("prelisting_risk")
    known.update(str(value) for value in (getattr(prelisting, "evidence_ids", None) or []) if value)
    for module in (getattr(prelisting, "module_scores", None) or {}).values():
        for indicator in getattr(module, "indicators", None) or []:
            evidence_id = getattr(indicator, "evidence_id", None)
            if evidence_id:
                known.add(str(evidence_id))
    return known


def build_market_tool_registry(agent: Any) -> ToolRegistry:
    """Build the market ReAct tools around the audited pipeline state.

    The first implementation deliberately does not expose retrieve_market: the
    wide table remains the source of truth and market retrieval is disabled.
    """
    registry = ToolRegistry()
    schemas = {(item.get("function") or {}).get("name"): item for item in MARKET_TOOL_SCHEMAS}

    def emit(name: str, status: str, output: dict[str, Any] | None = None) -> None:
        agent._emit({
            "event": "tool",
            "agent": "market",
            "name": name,
            "status": status,
            "output": output or {},
        })

    async def lookup_market_row(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        emit("lookup_market_row", "running")
        context = await agent._prepare_react_context(state)
        snapshot = context["snapshot"]
        result = {
            "ok": True,
            "stock_code": snapshot.stock_code,
            "company": snapshot.company,
            "listing_date": snapshot.listing_date.isoformat(),
            "as_of_date": snapshot.as_of_date.isoformat(),
            "cutoff_verified": snapshot.cutoff_verified,
            "available_fields": sorted(snapshot.features),
            "missing_fields": snapshot.missing_fields,
        }
        emit("lookup_market_row", "ok", {"stock_code": snapshot.stock_code, "cutoff_verified": snapshot.cutoff_verified})
        return result

    async def run_market_skill(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        emit("run_market_skill", "running", {"skill": args.get("skill")})
        context = await agent._prepare_react_context(state)
        skill = str(args.get("skill") or "")
        if skill not in MARKET_SKILL_PRESETS:
            return {"ok": False, "error": f"unknown_market_skill:{skill}"}
        module_name = MARKET_SKILL_PRESETS[skill]["module"]
        module = context["prelisting_risk"].module_scores.get(module_name)
        ledger = [
            item.model_dump(mode="json")
            for item in context["sentiment_analysis"].evidence_ledger
            if item.module == module_name
        ]
        result = {
            "ok": True,
            "skill": skill,
            "module": module_name,
            "result": module.model_dump(mode="json") if module else None,
            "evidence": ledger,
        }
        state.setdefault("market_skill_results", {})[skill] = result
        emit("run_market_skill", "ok", {"skill": skill, "module": module_name, "evidence_n": len(ledger)})
        return result

    async def search_market_evidence(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        emit("search_market_evidence", "running")
        context = await agent._prepare_react_context(state)
        result = {
            "ok": True,
            "public_opinion": context["opinion"].model_dump(mode="json"),
            "firecrawl": context["firecrawl_status"],
            "news_status": context["news_status"],
        }
        emit("search_market_evidence", "ok", {
            "opinion_available": context["opinion"].available,
            "accepted_articles": context["firecrawl_status"].get("accepted_articles", 0),
        })
        return result

    async def run_market_rule_checks(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        emit("run_market_rule_checks", "running")
        context = await agent._prepare_react_context(state)
        risk = context["prelisting_risk"]
        state["rules_floor"] = risk.score
        result = {
            "ok": True,
            "rules_floor": round(risk.score, 1),
            "risk_level": risk.risk_level,
            "score_version": risk.score_version,
            "module_scores": {name: item.model_dump(mode="json") for name, item in risk.module_scores.items()},
        }
        emit("run_market_rule_checks", "ok", {"rules_floor": round(risk.score, 1), "score_version": risk.score_version})
        return result

    async def score_market_with_llm(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        emit("score_market_with_llm", "running")
        context = await agent._prepare_react_context(state)
        known = _known_market_evidence_ids(context)
        supplied = list(args.get("evidence_ids") or [])
        unknown = sorted(set(supplied) - known)
        reason = str(args.get("score_reason") or "")
        missing_in_reason = sorted(evidence_id for evidence_id in supplied if evidence_id not in reason)
        if unknown or not supplied or missing_in_reason:
            return {
                "ok": False,
                "error": "llm_score_requires_known_evidence_ids_in_reason",
                "unknown": unknown,
                "missing_in_reason": missing_in_reason,
            }
        state["react_llm_assessment"] = {
            "risk_score": agent._bounded_score(args.get("risk_score"), default=0),
            "confidence": max(0.0, min(1.0, float(args.get("confidence") or 0))),
            "score_reason": reason,
            "evidence_ids": supplied,
            "dimension_scores": args.get("dimension_scores") or {},
            "validation_status": "accepted_grounded_score",
        }
        emit("score_market_with_llm", "ok", {"risk_score": state["react_llm_assessment"]["risk_score"], "evidence_ids": supplied})
        return {"ok": True, **state["react_llm_assessment"]}

    async def submit_market_report(args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        emit("submit_market_report", "running")
        if "rules_floor" not in state:
            return {"ok": False, "error": "run_market_rule_checks_required_before_submit"}
        if not state.get("react_llm_assessment"):
            return {"ok": False, "error": "score_market_with_llm_required_before_submit"}
        state["react_submission"] = {
            "summary": str(args.get("summary") or ""),
            "module_assessments": args.get("module_assessments") or {},
            "risk_points": args.get("risk_points") or [],
            "llm_assessment": state["react_llm_assessment"],
        }
        state["final_report"] = state["react_submission"]
        state["finished"] = True
        emit("submit_market_report", "ok", {"submitted": True})
        return {"ok": True, "submitted": True}

    handlers = {
        "lookup_market_row": lookup_market_row,
        "run_market_skill": run_market_skill,
        "search_market_evidence": search_market_evidence,
        "run_market_rule_checks": run_market_rule_checks,
        "score_market_with_llm": score_market_with_llm,
        "submit_market_report": submit_market_report,
    }
    for name, handler in handlers.items():
        registry.register(schemas[name], handler)
    return registry

