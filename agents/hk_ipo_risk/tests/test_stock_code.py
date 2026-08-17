from __future__ import annotations

import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from service.stock_code import normalize_stock_code, resolve_stock_code


def test_normalize_wind_ticker():
    assert normalize_stock_code("03378.HK") == "03378"
    assert normalize_stock_code("3378.hk") == "03378"
    assert normalize_stock_code("3378") == "03378"
    assert normalize_stock_code(" 02451 ") == "02451"


def test_resolve_prefers_start_body_over_parse_meta():
    assert (
        resolve_stock_code(
            ticker="02451.HK",
            parse_meta={"stockCode": "03378", "ticker": "03378.HK"},
        )
        == "02451"
    )
    assert resolve_stock_code(parse_meta={"ticker": "2097.HK"}) == "02097"
    assert resolve_stock_code(ticker=None, stock_code=None, parse_meta={}) == ""
