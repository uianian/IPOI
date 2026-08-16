from __future__ import annotations

"""市场情绪 Agent demo toolbox。周杰合入时替换本文件即可，总控契约不变。"""

from pathlib import Path
from typing import Any

from src.models.debate import DebateClaim, DebateDossier, save_dossier


async def search_market_evidence_standalone(
    *,
    doc_id: str,
    query: str = "",
    intent: str = "market_sentiment",
    **_: Any,
) -> dict[str, Any]:
    """Demo：禁止伪造页码/认购倍数，固定空 hits。"""
    return {
        "ok": True,
        "doc_id": doc_id,
        "intent": intent,
        "query": query,
        "n": 0,
        "hits": [],
        "demo": True,
        "error": None,
        "note": "market_demo_stub_empty_hits",
    }


def submit_market_demo_dossier(
    *,
    doc_id: str,
    debate_dir: Path | str | None,
    doc_name: str | None = None,
    summary: str = "",
) -> str | None:
    if not debate_dir:
        return None
    dossier = DebateDossier(
        agent="market",
        doc_id=doc_id,
        doc_name=doc_name,
        risk_score=50.0,
        risk_level="medium",
        summary=summary or "市場情緒 Agent demo stub，未接入寬表。",
        reasoning="demo_stub",
        claims=[
            DebateClaim(
                agent="market",
                code="MARKET_DEMO",
                level="medium",
                confidence="low",
                statement="市場情緒尚未接入真实行情，本輪不提供認購/破發證據。",
                reasoning="demo_stub",
            )
        ],
        negative_findings=[{"code": "MARKET_DEMO", "note": "empty_wide_table"}],
    )
    path = save_dossier(dossier, debate_dir)
    return str(path)
