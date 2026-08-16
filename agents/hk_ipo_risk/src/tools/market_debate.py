from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from src.skills.score_postlisting import PostlistingRiskScorer
from src.tools.market_data import MarketDataLoader, normalize_stock_code


async def search_market_evidence_standalone(
    *,
    stock_code: str,
    query: str,
    features_csv: Path | str,
    news_dir: Path | str,
    limit: int = 10,
) -> dict[str, Any]:
    """Search audited local market/news evidence without ReAct state.

    This first-version debate tool is intentionally local-first and never
    spends Firecrawl credits. A later caller may explicitly run the configured
    collector before invoking it, after which saved bodies are searchable here.
    """
    loader = MarketDataLoader(features_csv, news_dir=news_dir, strict_cutoff=True)
    snapshot = loader.load_snapshot(stock_code)
    terms = [term.lower() for term in str(query).split() if term.strip()]
    candidates = loader.load_news_candidates(snapshot)
    hits: list[dict[str, Any]] = []
    for item in candidates:
        haystack = " ".join(str(value or "") for value in item.values()).lower()
        if not terms or any(term in haystack for term in terms):
            hits.append(item)
        if len(hits) >= max(1, int(limit)):
            break
    feature_hits = {
        key: value
        for key, value in snapshot.features.items()
        if not terms or any(term in key.lower() for term in terms)
    }
    return {
        "available": bool(hits or feature_hits),
        "stock_code": snapshot.stock_code,
        "query": query,
        "as_of_date": snapshot.as_of_date.isoformat(),
        "cutoff_verified": snapshot.cutoff_verified,
        "news_hits": hits,
        "feature_hits": feature_hits,
        "remote_fetch_attempted": False,
    }


class MarketDebateToolbox:
    """Bounded evidence tools for the master-agent debate stage.

    The phase guard is part of the API contract: pre-listing debates cannot
    access realized post-listing prices. Tool results are data, not authority to
    mutate an already persisted score version.
    """

    TOOL_SCHEMAS = [
        {
            "type": "function",
            "function": {
                "name": "get_existing_market_evidence",
                "description": "Read persisted evidence for this IPO and phase.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_market_snapshot",
                "description": "Reload the audited local pre-listing market snapshot.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_postlisting_checkpoint",
                "description": "Read a realized D5..D60 checkpoint; available only in postlisting debate.",
                "parameters": {
                    "type": "object",
                    "properties": {"trading_day": {"type": "integer", "minimum": 5, "maximum": 60, "multipleOf": 5}},
                    "required": ["trading_day"], "additionalProperties": False,
                },
            },
        },
    ]

    def __init__(
        self,
        *,
        doc_id: str,
        stock_code: str,
        phase: Literal["prelisting", "postlisting"],
        features_csv: Path | str,
        news_dir: Path | str,
        checkpoints_csv: Path | str,
        store: Any | None = None,
    ) -> None:
        self.doc_id = doc_id
        self.stock_code = normalize_stock_code(stock_code)
        self.phase = phase
        self.features_csv = Path(features_csv)
        self.news_dir = Path(news_dir)
        self.checkpoints_csv = Path(checkpoints_csv)
        self.store = store

    async def execute(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        if tool_name == "get_existing_market_evidence":
            if self.store is None:
                return {"available": False, "reason": "postgres_store_not_configured"}
            rows = await self.store.query_evidence(
                doc_id=self.doc_id, stock_code=self.stock_code, phase=self.phase
            )
            return {"available": True, "phase": self.phase, "evidence": rows}
        if tool_name == "get_market_snapshot":
            snapshot = MarketDataLoader(
                self.features_csv, news_dir=self.news_dir, strict_cutoff=True
            ).load_snapshot(self.stock_code)
            return {"available": True, "snapshot": snapshot.model_dump(mode="json")}
        if tool_name == "get_postlisting_checkpoint":
            if self.phase != "postlisting":
                return {
                    "available": False,
                    "reason": "temporal_guard_postlisting_evidence_forbidden_in_prelisting_debate",
                }
            day = int(arguments.get("trading_day") or 0)
            if day not in range(5, 61, 5):
                raise ValueError("trading_day must be D5,D10,...,D60")
            results = PostlistingRiskScorer().load_and_score(
                self.stock_code, checkpoints_csv=self.checkpoints_csv, through_day=day
            )
            result = next((item for item in results if item.trading_day == day), None)
            return {
                "available": result is not None,
                "checkpoint": result.model_dump(mode="json") if result else None,
            }
        raise KeyError(f"unknown market debate tool: {tool_name}")

