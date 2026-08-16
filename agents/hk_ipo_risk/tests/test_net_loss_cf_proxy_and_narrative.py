"""维昇类问题：CF 税前虧損回填 NET_LOSS；摘要风险分与最终分对齐。"""
from __future__ import annotations

from src.skills.extract_financials import extract_financials_from_retrieval
from src.skills.finance_toolbox import (
    _align_narrative_to_level,
    _apply_18a_data_insufficient_guard,
)
from src.skills.gates import detect_profitability


def test_net_loss_from_cf_pretax_loss_when_is_missing() -> None:
    html = """
    <table>
      <tr><td></td><td>截至12月31日止年度</td><td>截至9月30日止九個月</td></tr>
      <tr><td>2022年人民幣千元</td><td>2023年人民幣千元</td>
          <td>2023年人民幣千元(未經審計)</td><td>2024年人民幣千元</td></tr>
      <tr><td>經營活動所得現金流量</td><td></td><td></td><td></td><td></td></tr>
      <tr><td>税前虧損</td><td>(288,967)</td><td>(249,570)</td>
          <td>(208,342)</td><td>(129,495)</td></tr>
      <tr><td>經營活動所得現金流量淨額</td><td>(246,549)</td><td>(271,310)</td>
          <td>(155,734)</td><td>(102,406)</td></tr>
    </table>
    """
    bundle = {
        "evidence_by_table": {"TBL_CF": [{"page": 543, "excerpt": html}]},
        "evidence_by_field": {},
        "evidence": [],
    }
    out = extract_financials_from_retrieval(bundle)
    net = out["metrics"].get("NET_LOSS") or {}
    assert net.get("2022") == -288967.0
    assert net.get("2023") == -249570.0
    notes = (out.get("bs_reconcile") or {}).get("extract_notes") or []
    assert any("TBL_CF" in str(n) and "NET_LOSS" in str(n) for n in notes)
    profit = detect_profitability(out["metrics"])
    assert profit["profitability_known"] is True
    assert profit["continuous_net_loss"] is True


def test_align_narrative_rewrites_stale_score_after_floor() -> None:
    report = {
        "risk_score": 25.0,
        "risk_level": "low",
        "summary": "維昇藥業連續虧損；風險分25(低)。",
        "reasoning": "綜上風險分25，屬低-中風險。",
        "score_breakdown": [
            {"code": "CFO_NEGATIVE", "delta": 15},
            {"code": "CASH_RUNWAY_12_24", "delta": 10},
        ],
    }
    state = {
        "issuer_type": "18a",
        "gates": {"issuer_type": "18a", "is_biotech_18a": True},
        "metrics": {},
    }
    warnings: list[str] = []
    _apply_18a_data_insufficient_guard(report, state, warnings)
    assert float(report["risk_score"]) == 40.0
    assert report["risk_level"] == "medium"
    _align_narrative_to_level(report, warnings)
    assert "風險分40（中等）" in report["summary"]
    assert "25" not in report["summary"]
    assert "風險分40（中等）" in report["reasoning"] or "40" in report["reasoning"]
    assert any(w.startswith("narrative_aligned:") for w in warnings)
