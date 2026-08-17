from __future__ import annotations

import re


def normalize_stock_code(ticker: str | None) -> str:
    """Wind `03378.HK` / `3378` → 五位数字代码 `03378`。无法识别则返回去空白原文。"""
    t = (ticker or "").strip().upper().replace(" ", "")
    t = t.replace(".HK", "")
    if not t:
        return ""
    if t.isdigit():
        return t.zfill(5)
    m = re.match(r"^(\d{1,5})", t)
    return m.group(1).zfill(5) if m else t


def resolve_stock_code(
    *,
    ticker: str | None = None,
    stock_code: str | None = None,
    parse_meta: dict | None = None,
) -> str:
    meta = parse_meta or {}
    raw = (
        ticker
        or stock_code
        or meta.get("stockCode")
        or meta.get("ticker")
        or ""
    )
    return normalize_stock_code(str(raw) if raw is not None else "")
