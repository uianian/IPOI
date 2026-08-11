"""关连交易专章占比/金额抽取单测。"""

from __future__ import annotations

import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.skills.extract_legal import (  # noqa: E402
    extract_related_party,
    harvest_connected_transactions_from_parse,
    parse_related_party_amount_rows,
    parse_related_party_ratio_signals,
    resolve_related_party_ratio,
)


def test_parse_listing_rule_pct_not_buffer() -> None:
    text = (
        "最高年度上限的最高適用百分比率（利潤比率除外）按年計預期低於5%且最高年度上限低於3,000,000港元，"
        "因此將構成完全豁免持續關連交易。"
        "故在預期採購金額之上預留10%的緩衝。"
    )
    sig = parse_related_party_ratio_signals(text)
    assert 5.0 in sig["listing_rule_pcts"] or 5.0 in sig["waiver_pcts"]
    assert 10.0 not in sig["listing_rule_pcts"]
    assert 10.0 not in sig["share_pcts"]
    assert 10.0 not in sig["waiver_pcts"]
    info = resolve_related_party_ratio([text])
    assert info["ratio_pct"] == 5.0
    assert info["related_party_ratio_gt_30"] is False
    assert info["ratio_source"] in {"listing_rule_pct_ratio", "waiver_threshold"}


def test_parse_share_of_procurement() -> None:
    text = "向關連方採購金額佔本集團總採購額約35.2%。"
    info = resolve_related_party_ratio([text])
    assert info["ratio_pct"] == 35.2
    assert info["ratio_source"] == "share_of_similar_txn"
    assert info["related_party_ratio_gt_30"] is True


def test_parse_amount_total_row() -> None:
    html = """
    <table><tr><td>總計：</td><td>714,000</td><td>39,000</td><td>559,000</td></tr></table>
    """
    rows = parse_related_party_amount_rows(html)
    assert rows
    assert rows[0]["max"] == 714000.0


def test_harvest_hansiaitai_connected_chapter() -> None:
    parse = (
        Path("/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch_old")
        / "03378_15-12-2025_翰思艾泰－Ｂ_全球發售"
        / "full_parse.json"
    )
    if not parse.is_file():
        return
    hits = harvest_connected_transactions_from_parse(parse)
    pages = {h.get("page") for h in hits}
    assert pages & {416, 417, 418, 419, 423, 424}
    texts = [h.get("excerpt") or "" for h in hits]
    info = resolve_related_party_ratio(texts)
    assert info["ratio_pct"] == 5.0
    assert info["ratio_source"] in {"listing_rule_pct_ratio", "waiver_threshold"}


def test_extract_related_party_with_parse_json() -> None:
    parse = (
        Path("/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch_old")
        / "03378_15-12-2025_翰思艾泰－Ｂ_全球發售"
        / "full_parse.json"
    )
    if not parse.is_file():
        return
    feat = extract_related_party(
        {"evidence_by_field": {}},
        extra_hits=[],
        parse_json=parse,
    )
    assert feat.get("exists") is True
    assert feat.get("ratio_pct") == 5.0
    assert feat.get("related_party_ratio_gt_30") is False
    assert feat.get("ratio_source")
    assert (feat.get("theme_filter") or {}).get("chapter_hits", 0) > 0
    # 历史金额表应抽到
    assert feat.get("historical_amount_rows")
