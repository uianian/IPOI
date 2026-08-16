"""P0 别名：中文年份、溢利(虧損) 行、所用現金淨額。"""
from __future__ import annotations

from src.skills.extract_financials import extract_financials_from_retrieval
from src.skills.finance_toolbox import (
    _align_narrative_to_level,
)
from src.skills.gates import detect_profitability
from src.skills.table_utils import (
    _row_label_score,
    extract_year_headers,
    html_table_to_rows,
)


def test_chinese_year_headers() -> None:
    html = """
    <table>
      <tr><td></td><td>截至十二月三十一日止年度</td><td>截至六月三十日止六個月</td></tr>
      <tr><td>二零一八年人民幣千元</td><td>二零一九年人民幣千元</td>
          <td>二零一九年人民幣千元（未經審核）</td><td>二零二零年人民幣千元</td></tr>
      <tr><td>年內虧損</td><td>(100)</td><td>(200)</td><td>(80)</td><td>(90)</td></tr>
    </table>
    """
    years = extract_year_headers(html_table_to_rows(html))
    assert years[:2] == ["2018", "2019"]


def test_net_loss_profit_loss_parentheses_row() -> None:
    assert _row_label_score("年／期內溢利 (虧損) 及全面收益 (開支) 總額", ["年內溢利"], field="NET_LOSS") >= 50
    assert _row_label_score("除所得稅前虧損", ["除税前虧損"], field="NET_LOSS") >= 50
    assert _row_label_score("貴公司權益持有人應佔年內虧損及全面虧損總額", ["年內虧損"], field="NET_LOSS") >= 50
    assert _row_label_score("每股虧損", ["年內虧損"], field="NET_LOSS") == 0


def test_cfo_cash_used_net_row() -> None:
    assert _row_label_score("經營活動所用現金淨額", ["經營活動所得現金淨額"], field="CFO") >= 50
    assert _row_label_score("經營活動所產生（所用）現金淨額", ["經營活動所得現金淨額"], field="CFO") >= 50


def test_text_table_stacked_years_and_cf_inflow() -> None:
    html_lines = "\n".join(
        [
            "截至12月31日止年度",
            "附註",
            "2023年 人民幣千元",
            "2024年 人民幣千元",
            "收入 5 1,786,540 1,941,257",
            "所得稅前虧損 (202,249) (1,014,546)",
            "本公司擁有人應佔年內 全面虧損總額 (378,753) (1,088,399)",
        "每股基本及攤薄虧損 (44.7) (131.3)",
        ]
    )
    years = extract_year_headers(html_table_to_rows(html_lines))
    assert years[:2] == ["2023", "2024"]
    cf = """
經營活動現金流入淨額 816,335 285,781
投資活動現金流出淨額 (78,550) (211,151)
年末現金及現金等價物 1,130,889 1,208,906
"""
    out = extract_financials_from_retrieval(
        {
            "evidence_by_table": {
                "TBL_IS": [{"page": 586, "excerpt": html_lines}],
                "TBL_CF": [{"page": 590, "excerpt": "2023年 2024年\n" + cf}],
            },
            "evidence_by_field": {},
            "evidence": [],
        }
    )
    assert (out["metrics"].get("NET_LOSS") or {}).get("2023") == -378753.0
    assert (out["metrics"].get("CFO") or {}).get("2023") == 816335.0


def test_extract_xianrui_style_is() -> None:
    html = """
    <table>
      <tr><td></td><td>截至12月31日止年度</td><td>截至3月31日止三個月</td></tr>
      <tr><td>2019年</td><td>2020年</td><td>2020年</td><td>2021年</td></tr>
      <tr><td>收益</td><td>124,910</td><td>193,975</td><td>19,624</td><td>53,320</td></tr>
      <tr><td>除税前溢利 (虧損)</td><td>26,708</td><td>(31,447)</td><td>(3,697)</td><td>(38,094)</td></tr>
      <tr><td>年／期內溢利 (虧損) 及全面收益 (開支) 總額</td>
          <td>23,105</td><td>(44,292)</td><td>(3,130)</td><td>(40,016)</td></tr>
    </table>
    """
    out = extract_financials_from_retrieval(
        {"evidence_by_table": {"TBL_IS": [{"page": 469, "excerpt": html}]}, "evidence_by_field": {}, "evidence": []}
    )
    net = out["metrics"].get("NET_LOSS") or {}
    assert net.get("2019") == 23105.0
    assert net.get("2020") == -44292.0
    assert detect_profitability(out["metrics"])["profitability_known"] is True


def test_align_paren_score_and_rules_template() -> None:
    report = {
        "risk_score": 40.0,
        "risk_level": "medium",
        "summary": "18A/生物科技規則打分 0.0（very_low）。未觸發規則扣分項。",
        "reasoning": "綜合風險等級為中等（40分）。中級（40分）。",
    }
    warnings: list[str] = []
    _align_narrative_to_level(report, warnings)
    assert "規則打分40（中等）" in report["summary"] or "40" in report["summary"]
    assert "0.0" not in report["summary"]

    report2 = {
        "risk_score": 55.0,
        "risk_level": "medium",
        "summary": "綜合財務風險中級（40分）。",
        "reasoning": "",
    }
    _align_narrative_to_level(report2, [])
    assert "40" not in report2["summary"]
    assert "55" in report2["summary"]

    report3 = {
        "risk_score": 45.0,
        "risk_level": "medium",
        "summary": "財務風險定為低（45分）。",
        "reasoning": "",
    }
    _align_narrative_to_level(report3, [])
    assert "定為低" not in report3["summary"]
    assert "中等" in report3["summary"]
    assert "45" in report3["summary"]


def test_extract_bs_asset_total_value_and_deficit() -> None:
    html = """
    <table>
      <tr><td></td><td>2018年</td><td>2019年</td></tr>
      <tr><td>資產總值</td><td>423,597</td><td>553,376</td></tr>
      <tr><td>負債總額</td><td>171,920</td><td>183,712</td></tr>
      <tr><td>權益總額</td><td>251,677</td><td>369,664</td></tr>
    </table>
    """
    out = extract_financials_from_retrieval(
        {"evidence_by_table": {"TBL_BS": [{"page": 397, "excerpt": html}]}, "evidence_by_field": {}, "evidence": []}
    )
    assert (out["metrics"].get("TOTAL_ASSETS") or {}).get("2018") == 423597.0
    assert (out["metrics"].get("TOTAL_LIAB") or {}).get("2018") == 171920.0
    assert (out["metrics"].get("NET_ASSETS") or {}).get("2018") == 251677.0

    text = """
2023年 2024年
資產總值 1,499,909 2,090,222
虧絀總額 (1,123,913) (2,021,899)
負債總值 2,623,822 4,112,121
"""
    out2 = extract_financials_from_retrieval(
        {"evidence_by_table": {"TBL_BS": [{"page": 587, "excerpt": text}]}, "evidence_by_field": {}, "evidence": []}
    )
    assert (out2["metrics"].get("TOTAL_ASSETS") or {}).get("2023") == 1499909.0
    assert (out2["metrics"].get("NET_ASSETS") or {}).get("2023") == -1123913.0
    assert (out2["metrics"].get("TOTAL_LIAB") or {}).get("2023") == 2623822.0

