"""Year-header interim tagging + legal 3.5 pipeline extract."""

from __future__ import annotations

from src.skills.extract_legal import extract_pipeline
from src.skills.table_utils import extract_year_headers


def test_track_record_tail_year_marked_interim() -> None:
    years = extract_year_headers(
        [["千元", "2023", "2024", "2024", "2025"]]
    )
    assert years == ["2023", "2024", "2024_i1", "2025_i1"]


def test_cell_interim_hint() -> None:
    years = extract_year_headers(
        [["", "2023年", "2024年", "截至2024年8月31日止八個月", "截至2025年8月31日止八個月"]]
    )
    assert years[0] == "2023"
    assert years[1] == "2024"
    assert years[2].startswith("2024_i")
    assert years[3].startswith("2025_i")


def test_bs_three_col_mixed_ye_interim() -> None:
    years = extract_year_headers(
        [
            ["附註", "於12月31日", "於8月31日"],
            ["", "2023年", "2024年", "2025年"],
        ]
    )
    assert years == ["2023", "2024", "2025_i1"]


def test_extract_pipeline_from_field_hits() -> None:
    bundle = {
        "evidence_by_field": {
            "PIPELINE_RISK": [
                {
                    "page": 120,
                    "excerpt": "我们的产品管线候选产品全部自主研发，已完成一项常规I期临床研究。",
                    "score": 0.9,
                }
            ]
        }
    }
    feat = extract_pipeline(bundle)
    assert feat["exists"] is True
    assert feat["pipeline_high"] is False
    assert feat["evidence"]
    assert "I期" in (feat.get("stages_mentioned") or [])


def test_extract_pipeline_high_on_clinical_hold() -> None:
    bundle = {
        "evidence_by_field": {
            "PIPELINE_RISK": [
                {
                    "page": 99,
                    "excerpt": "核心产品HX009因安全性问题被临床搁置，暂停临床。",
                    "score": 0.95,
                }
            ]
        }
    }
    feat = extract_pipeline(bundle)
    assert feat["exists"] is True
    assert feat["pipeline_high"] is True
