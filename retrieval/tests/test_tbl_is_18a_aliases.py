"""18A 损益表别名：合併損益及其他綜合收益表 + 税前虧損/研究及開發成本门控。"""
from __future__ import annotations

from pathlib import Path

import yaml

from src.retrieval.agent_simulator import _title_hint_bonus
from src.retrieval.evidence_expand import (
    infer_statement_kind,
    must_have_groups_ok,
    matched_row_labels,
)


def _tbl_is_query() -> dict:
    cfg = yaml.safe_load(
        Path(__file__).resolve().parents[1]
        .joinpath("configs/agent_retrieval_profiles.yaml")
        .read_text(encoding="utf-8")
    )
    for q in cfg["finance"]["queries"]:
        if q.get("field_code") == "TBL_IS":
            return q
    raise AssertionError("TBL_IS missing in profile")


def test_weisen_title_and_must_have_groups() -> None:
    q = _tbl_is_query()
    title = "合併損益及其他綜合收益表"
    assert _title_hint_bonus(title, q["title_hints"]) > 0

    # 维昇 p539 形态：无产品收入/毛利，有其他收入+税前虧損+研究及開發成本
    html = """
    <table>
      <tr><td>其他收入</td><td>5,764</td><td>11,356</td></tr>
      <tr><td>研究及開發成本</td><td>(179,546)</td><td>(57,690)</td></tr>
      <tr><td>管理費用</td><td>(177,449)</td><td>(79,944)</td></tr>
      <tr><td>税前虧損</td><td>(288,967)</td><td>(249,570)</td></tr>
      <tr><td>年內／期內虧損</td><td>(288,967)</td><td>(249,570)</td></tr>
    </table>
    """
    assert must_have_groups_ok(html, q["must_have_groups"])
    matched = matched_row_labels(html, q["row_labels"])
    assert "税前虧損" in matched or "年內／期內虧損" in matched
    assert "研究及開發成本" in matched or "其他收入" in matched
    assert infer_statement_kind(html, title) == "income_statement"


def test_full_loss_statement_title() -> None:
    q = _tbl_is_query()
    assert _title_hint_bonus("綜合全面虧損表", q["title_hints"]) > 0
    html = """
    <table>
      <tr><td>其他收入</td><td>10</td></tr>
      <tr><td>除所得稅前虧損</td><td>(100)</td></tr>
      <tr><td>年內虧損</td><td>(100)</td></tr>
    </table>
    """
    assert must_have_groups_ok(html, q["must_have_groups"])
    assert infer_statement_kind(html, "綜合全面虧損表") == "income_statement"


def test_old_full_is_still_passes() -> None:
    q = _tbl_is_query()
    html = """
    <table>
      <tr><td>收入</td><td>100</td></tr>
      <tr><td>銷售成本</td><td>(40)</td></tr>
      <tr><td>毛利</td><td>60</td></tr>
      <tr><td>年內虧損</td><td>(10)</td></tr>
    </table>
    """
    assert must_have_groups_ok(html, q["must_have_groups"])
    assert _title_hint_bonus("綜合損益表", q["title_hints"]) > 0
