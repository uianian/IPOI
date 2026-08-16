"""CF 跨页续页：投资/融资半表不得被误判为损益表。"""
from __future__ import annotations

from src.retrieval.evidence_expand import infer_statement_kind


def test_cf_continuation_with_invest_finance() -> None:
    html = """
    <table>
      <tr><td>投資活動所用現金淨額</td><td>(10)</td></tr>
      <tr><td>融資活動所得現金淨額</td><td>20</td></tr>
      <tr><td>現金及現金等價物增加</td><td>5</td></tr>
    </table>
    """
    assert infer_statement_kind(html, "") == "cash_flow"
    # 续页偶发「收益」字样，不能抢先判成损益表
    html2 = html.replace("現金及現金等價物增加", "利息收益")
    assert infer_statement_kind(html2, "綜合現金流量表") == "cash_flow"


def test_cf_must_have_spaced_invest_finance() -> None:
    from pathlib import Path

    import yaml
    from src.retrieval.evidence_expand import must_have_groups_ok

    cfg = yaml.safe_load(
        Path(__file__).resolve().parents[1]
        .joinpath("configs/agent_retrieval_profiles.yaml")
        .read_text(encoding="utf-8")
    )
    groups = None
    for q in cfg["finance"]["queries"]:
        if q.get("field_code") == "TBL_CF":
            groups = q["must_have_groups"]
            break
    assert groups
    html = """
    <table>
      <tr><td>經營活動所用現金淨額</td><td>(49,206)</td></tr>
      <tr><td>投資活動 (所用) 所得現金淨額</td><td>(21,476)</td></tr>
      <tr><td>融資活動所得 (所用)</td><td></td></tr>
      <tr><td>現金淨額</td><td>393,609</td></tr>
    </table>
    """
    assert must_have_groups_ok(html, groups)


def test_cf_operating_used_cash() -> None:
    html = """
    <table>
      <tr><td>經營活動所用現金淨額</td><td>(100)</td></tr>
      <tr><td>投資活動所用現金淨額</td><td>(10)</td></tr>
      <tr><td>融資活動所得現金淨額</td><td>80</td></tr>
    </table>
    """
    assert infer_statement_kind(html, "綜合現金流量表") == "cash_flow"
