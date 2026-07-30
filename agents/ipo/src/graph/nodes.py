from __future__ import annotations

import logging
from typing import Any

from src.graph.state import AgentState
from src.agents.legal.agent import LegalAgent
from src.agents.finance.agent import FinanceAgent
from src.agents.sentiment.agent import SentimentAgent

logger = logging.getLogger(__name__)


async def task_decomposition_node(state: AgentState) -> dict[str, Any]:
    doc_id = state.get("doc_id", "")
    logger.info(f"[TaskDecomposition] Decomposing task for doc_id={doc_id}")

    sub_tasks = [
        {"agent": "legal", "doc_id": doc_id},
        {"agent": "finance", "doc_id": doc_id},
        {"agent": "sentiment", "doc_id": doc_id},
    ]

    return {"sub_tasks": sub_tasks}


async def legal_analysis_node(state: AgentState, legal_agent: LegalAgent) -> dict[str, Any]:
    doc_id = state.get("doc_id", "")
    logger.info(f"[LegalAnalysis] Starting for doc_id={doc_id}")

    params = {
        "industry": state.get("industry", ""),
    }

    try:
        result = await legal_agent.analyze(doc_id, params)
        return {"legal_result": result}
    except Exception as e:
        logger.error(f"Legal analysis failed: {e}")
        return {"legal_result": {"doc_id": doc_id, "summary": f"法务分析失败: {e}"}}


async def finance_analysis_node(state: AgentState, finance_agent: FinanceAgent) -> dict[str, Any]:
    doc_id = state.get("doc_id", "")
    logger.info(f"[FinanceAnalysis] Starting for doc_id={doc_id}")

    params = {
        "industry": state.get("industry", ""),
    }

    try:
        result = await finance_agent.analyze(doc_id, params)
        return {"finance_result": result}
    except Exception as e:
        logger.error(f"Finance analysis failed: {e}")
        return {"finance_result": {"doc_id": doc_id, "summary": f"财务分析失败: {e}"}}


async def sentiment_analysis_node(state: AgentState, sentiment_agent: SentimentAgent) -> dict[str, Any]:
    doc_id = state.get("doc_id", "")
    logger.info(f"[SentimentAnalysis] Starting for doc_id={doc_id}")

    params = {
        "stock_code": state.get("stock_code", ""),
        "industry": state.get("industry", ""),
    }

    try:
        result = await sentiment_agent.analyze(doc_id, params)
        return {"sentiment_result": result}
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        return {"sentiment_result": {"doc_id": doc_id, "summary": f"情绪分析失败: {e}"}}


async def conflict_detection_node(state: AgentState, debate_protocol: Any) -> dict[str, Any]:
    legal_result = state.get("legal_result", {})
    finance_result = state.get("finance_result", {})
    sentiment_result = state.get("sentiment_result", {})

    logger.info("[ConflictDetection] Checking for conflicts")

    try:
        conflicts = await debate_protocol.detect_conflicts(legal_result, finance_result, sentiment_result)
        conflicts_data = [c.model_dump() for c in conflicts]
        return {"conflicts": conflicts_data}
    except Exception as e:
        logger.error(f"Conflict detection failed: {e}")
        return {"conflicts": []}


async def debate_round_node(state: AgentState, debate_protocol: Any) -> dict[str, Any]:
    conflicts = state.get("conflicts", [])
    legal_result = state.get("legal_result", {})
    finance_result = state.get("finance_result", {})
    sentiment_result = state.get("sentiment_result", {})

    logger.info(f"[DebateRound] Processing {len(conflicts)} conflicts")

    agent_results = {
        "legal": legal_result,
        "finance": finance_result,
        "sentiment": sentiment_result,
    }

    debate_results_data = state.get("debate_results", [])

    for conflict_data in conflicts:
        from src.models.conflict import ConflictItem
        conflict = ConflictItem(**conflict_data)

        try:
            debate_result = await debate_protocol.run_debate(conflict, agent_results)
            debate_results_data.append(debate_result.model_dump())
        except Exception as e:
            logger.error(f"Debate failed for conflict {conflict.conflict_id}: {e}")

    return {"debate_results": debate_results_data}


async def cross_modal_fusion_node(state: AgentState, fusion_engine: Any) -> dict[str, Any]:
    legal_result = state.get("legal_result", {})
    finance_result = state.get("finance_result", {})
    sentiment_result = state.get("sentiment_result", {})

    logger.info("[CrossModalFusion] Fusing results")

    try:
        fused = fusion_engine.fuse_and_rate(legal_result, finance_result, sentiment_result)
        return {"fused_result": fused.model_dump()}
    except Exception as e:
        logger.error(f"Cross-modal fusion failed: {e}")
        return {"fused_result": {"overall_score": 0, "overall_level": "medium", "error": str(e)}}


async def report_generation_node(state: AgentState) -> dict[str, Any]:
    import uuid
    from datetime import datetime

    doc_id = state.get("doc_id", "")
    company_name = state.get("company_name", "")
    fused_result = state.get("fused_result", {})
    conflicts = state.get("conflicts", [])
    debate_results = state.get("debate_results", [])

    logger.info(f"[ReportGeneration] Generating report for doc_id={doc_id}")

    report = {
        "report_id": str(uuid.uuid4()),
        "doc_id": doc_id,
        "company_name": company_name,
        "generated_at": datetime.now().isoformat(),
        "risk_assessment": fused_result,
        "high_risk_factors": fused_result.get("factor_details", []),
        "conflicts": conflicts,
        "debate_results": debate_results,
        "summary": (
            f"综合风险评分: {fused_result.get('overall_score', 'N/A')}，"
            f"风险等级: {fused_result.get('overall_level', 'N/A')}，"
            f"冲突数: {len(conflicts)}，辩论轮次: {len(debate_results)}"
        ),
    }

    return {"final_report": report}


def _generate_summary(fused: dict, conflicts: list, debates: list) -> str:
    score = fused.get("overall_score", "N/A")
    level = fused.get("overall_level", "N/A")
    return f"综合风险评分: {score}，风险等级: {level}，冲突数: {len(conflicts)}，辩论轮次: {len(debates)}"