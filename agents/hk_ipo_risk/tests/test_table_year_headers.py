"""Year header / row alignment tests for finance table extraction."""
from __future__ import annotations

from src.skills.table_utils import (
    extract_year_headers,
    find_row_values,
    html_table_to_rows,
)


def test_extract_year_headers_two_column_track_record() -> None:
    """02297-style: two full years on one header row (must not return [])."""
    rows = [
        ["", "附註", "截至12月31日止年度2020年人民幣千元", "2021年人民幣千元"],
        ["經營所得／(所用)現金", "32(a)", "2,237", "(74,643)"],
    ]
    years = extract_year_headers(rows)
    assert years[:2] == ["2020", "2021"]
    vals = find_row_values(
        rows,
        ["經營所得／(所用)現金", "經營活動所得／(所用)現金淨額"],
        years,
        field="CFO",
    )
    assert vals.get("2020") == 2237.0
    assert vals.get("2021") == -74643.0


def test_extract_year_headers_split_unit_row() -> None:
    """Year row then 人民幣千元 unit row — cross-row / same-row still works."""
    rows = [
        ["", "2022年", "2023年", "2024年"],
        ["", "人民幣千元", "人民幣千元", "人民幣千元"],
        ["非流動資產", "", "", ""],
        ["現金及現金等價物", "90,762", "186,830", "137,208"],
    ]
    years = extract_year_headers(rows)
    assert years == ["2022", "2023", "2024"]
    vals = find_row_values(rows, ["現金及現金等價物", "银行结余及现金"], years, field="CASH_EQ")
    assert vals == {"2022": 90762.0, "2023": 186830.0, "2024": 137208.0}


def test_extract_year_headers_from_html_two_years() -> None:
    html = (
        "<table><tr><td></td><td>附註</td>"
        "<td>截至12月31日止年度2020年人民幣千元</td>"
        "<td>2021年人民幣千元</td></tr>"
        "<tr><td>經營活動所得／(所用)現金淨額</td><td>11</td>"
        "<td>2,271</td><td>(72,832)</td></tr></table>"
    )
    rows = html_table_to_rows(html)
    years = extract_year_headers(rows)
    assert years[:2] == ["2020", "2021"]
    vals = find_row_values(
        rows,
        ["經營活動所得／(所用)現金淨額", "經營活動所用現金淨額"],
        years,
        field="CFO",
    )
    assert vals.get("2020") == 2271.0
    assert vals.get("2021") == -72832.0


def test_title_hint_contains_kaisai_variants() -> None:
    """Smoke: retrieval title bonus matches long IS aliases (stem / contains)."""
    import re
    from pathlib import Path
    import textwrap

    path = (
        Path(__file__).resolve().parents[3]
        / "retrieval"
        / "src"
        / "retrieval"
        / "agent_simulator.py"
    )
    src = path.read_text(encoding="utf-8")
    start = src.index("def _title_hint_bonus(")
    # take until next top-level def
    rest = src[start:]
    end = rest.find("\ndef ", 1)
    block = rest if end < 0 else rest[:end]
    ns: dict = {"re": re}
    exec(block, ns)
    bonus = ns["_title_hint_bonus"]

    hints = [
        "綜合損益表",
        "綜合全面收益表",
        "綜合損益及其他全面開支表",
    ]
    assert bonus("綜合損益及其他全面開支表", hints) > 0
    assert bonus("綜合全面收益表", hints) > 0
    # stem: 綜合損益表 should boost 綜合損益及其他全面收益表
    assert bonus("綜合損益及其他全面收益表", hints) > 0
