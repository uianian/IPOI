"""三专家并行后总控应收到真实 market；对照分按 yaml 权重合成。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.graph.parallel import merge_results, run_finance_legal_market_parallel
from src.models.evidence import AgentResult
from src.models.master import CompositeJudgment, MasterResult
from src.skills.master_cards import reference_fundamental, reference_formula_label


def test_reference_fundamental_swapped_weights_without_market():
    # legal 0.55 * 60 + finance 0.45 * 80 = 33 + 36 = 69
    assert reference_fundamental(80, 60) == 69.0
    assert "market" not in reference_formula_label(has_market=False)


def test_reference_fundamental_includes_market():
    # 69 * 0.65 + 40 * 0.35 = 44.85 + 14 = 58.85
    assert reference_fundamental(80, 60, 40) == 58.85
    assert "market" in reference_formula_label(has_market=True)


def test_merge_results_skips_demo_market_score():
    finance = AgentResult(agent="finance", doc_id="d", risk_score=80, risk_level="high")
    legal = AgentResult(agent="legal", doc_id="d", risk_score=60, risk_level="medium")
    demo = AgentResult(
        agent="market",
        doc_id="d",
        risk_score=50,
        risk_level="medium",
        features={"demo": True},
    )
    out = asyncio.run(merge_results(finance, legal, market=demo, skip_master=True))
    assert out["reference_fundamental_score"] == 69.0
    assert out["market"]["risk_score"] == 50


def test_run_finance_legal_market_parallel_passes_real_market_to_master():
    finance = AgentResult(agent="finance", doc_id="doc-1", risk_score=80, risk_level="high", summary="f")
    legal = AgentResult(agent="legal", doc_id="doc-1", risk_score=60, risk_level="medium", summary="l")
    market = AgentResult(agent="market", doc_id="doc-1", risk_score=40, risk_level="low", summary="m")
    captured: dict = {}

    async def fake_experts(doc_id, **kwargs):
        return finance, legal, object(), object()

    async def fake_market_run(self, doc_id, **kwargs):
        self._last_result = market
        return market

    async def fake_master_run(self, **kwargs):
        captured["market"] = kwargs.get("market")
        captured["market_agent"] = self._market_agent
        return MasterResult(
            doc_id=kwargs["doc_id"],
            judgment=CompositeJudgment(overall_score=70, level="high", risk_level_http="HIGH"),
        )

    async def _go():
        with (
            patch("src.graph.parallel._run_finance_legal_experts", new=fake_experts),
            patch("src.graph.parallel.MarketAgent.run", new=fake_market_run),
            patch("src.graph.parallel.MasterAgent.run", new=fake_master_run),
        ):
            return await run_finance_legal_market_parallel(
                "doc-1",
                stock_code="02451",
                market_settings={"llm": {"enabled": False, "max_turns": 1}, "cutoff": {}, "data": {}},
                firecrawl_settings={"enabled": False},
                sina_settings={"enabled": False},
            )

    out = asyncio.run(_go())
    assert out["market"]["agent"] == "market"
    assert out["market"]["risk_score"] == 40
    assert captured["market"] is not None
    assert captured["market"].agent == "market"
    assert captured["market"].risk_score == 40
    assert captured["market_agent"] is not None
    assert out["reference_fundamental_score"] == 58.85
    assert "market*" in (out.get("note") or "")
    assert out.get("market_error") is None
