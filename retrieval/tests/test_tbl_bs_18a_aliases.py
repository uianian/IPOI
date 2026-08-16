"""18A 资产负债表：資產總值 / 虧絀總額 / 綜合資產負債表。"""
from __future__ import annotations

from pathlib import Path

import yaml

from src.retrieval.agent_simulator import _title_hint_bonus
from src.retrieval.evidence_expand import (
    infer_statement_kind,
    must_have_groups_ok,
    statement_kind_compatible,
)


def _tbl_bs_query() -> dict:
    cfg = yaml.safe_load(
        Path(__file__).resolve().parents[1]
        .joinpath("configs/agent_retrieval_profiles.yaml")
        .read_text(encoding="utf-8")
    )
    for q in cfg["finance"]["queries"]:
        if q.get("field_code") == "TBL_BS":
            return q
    raise AssertionError("TBL_BS missing in profile")


def test_kintor_asset_total_value_html() -> None:
    """開拓：綜合財務狀況表 + 資產總值/負債總額/權益總額。"""
    q = _tbl_bs_query()
    title = "綜合財務狀況表"
    assert _title_hint_bonus(title, q["title_hints"]) > 0
    html = """
    <table>
      <tr><td>非流動資產</td><td>205,254</td></tr>
      <tr><td>流動資產</td><td>218,343</td></tr>
      <tr><td>資產總值</td><td>423,597</td></tr>
      <tr><td>負債總額</td><td>171,920</td></tr>
      <tr><td>權益總額</td><td>251,677</td></tr>
    </table>
    """
    assert must_have_groups_ok(html, q["must_have_groups"])
    kind = infer_statement_kind(html, title)
    assert kind == "balance_sheet"
    assert statement_kind_compatible("balance_sheet", kind)


def test_immunogen_consolidated_bs_text_deficit() -> None:
    """映恩：綜合資產負債表为 text，行名資產總值/虧絀總額/負債總值。"""
    q = _tbl_bs_query()
    title = "綜合資產負債表"
    assert _title_hint_bonus(title, q["title_hints"]) > 0
    text = """
非流動資產總值 166,014 180,387
流動資產總值 1,333,895 1,909,835
資產總值 1,499,909 2,090,222
虧絀總額 (1,123,913) (2,021,899)
流動負債總值 2,561,246 3,871,568
負債總值 2,623,822 4,112,121
虧絀及負債總值 1,499,909 2,090,222
"""
    assert must_have_groups_ok(text, q["must_have_groups"])
    kind = infer_statement_kind(text, title)
    assert kind == "balance_sheet"
    assert statement_kind_compatible("balance_sheet", kind)
    # 无标题时仍能凭 資產總值/虧絀總額 判 BS
    assert infer_statement_kind(text, "") == "balance_sheet"


def test_company_bs_title_bendi() -> None:
    kind = infer_statement_kind(
        "非流動資產\n於附屬公司的投資\n資產總值",
        "本公司資產負債表",
    )
    assert kind == "company_balance_sheet"
    assert not statement_kind_compatible("balance_sheet", kind)
