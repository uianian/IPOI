"""概念行业篮子日频聚合（行业热度模块的零外采实现）。

对 industry_universe.csv 中每个粗行业（排除"其他"）：
- eq_return       等权日收益（成分复权收盘价环比均值）
- total_amount    篮子日成交额之和（千港元）
- newhigh_ratio   当日复权收盘价 = 近60交易日最高 的成分占比
- n_members       当日有行情的成分数

输入：dataset/hkshareeodprices.csv、data/derived/industry_universe.csv
输出：data/derived/industry_basket_daily.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from config import EOD_CSV, DERIVED_DIR, INDUSTRY_FALLBACK, ensure_dirs, write_sidecar


def main():
    ensure_dirs()
    uni = pd.read_csv(DERIVED_DIR / "industry_universe.csv")
    uni = uni[uni["industry"] != INDUSTRY_FALLBACK]
    code2ind = dict(zip(uni["wind_norm"], uni["industry"]))
    print(f"industries={uni['industry'].nunique()}, member stocks={len(code2ind)}")

    usecols = ["S_INFO_WINDCODE", "TRADE_DT", "S_DQ_ADJCLOSE", "S_DQ_AMOUNT"]
    parts = []
    for chunk in pd.read_csv(EOD_CSV, usecols=usecols, chunksize=800_000):
        sub = chunk[chunk["S_INFO_WINDCODE"].isin(code2ind)]
        if len(sub):
            parts.append(sub)
    eod = pd.concat(parts, ignore_index=True)
    del parts
    eod = eod.sort_values(["S_INFO_WINDCODE", "TRADE_DT"])
    print(f"EOD rows in baskets: {len(eod)}")

    g = eod.groupby("S_INFO_WINDCODE", sort=False)
    eod["ret"] = g["S_DQ_ADJCLOSE"].pct_change()
    # 近60交易日滚动最高（含当日）；不足60日按已有窗口算
    eod["roll_max60"] = g["S_DQ_ADJCLOSE"].transform(
        lambda s: s.rolling(60, min_periods=20).max())
    eod["is_newhigh"] = (eod["S_DQ_ADJCLOSE"] >= eod["roll_max60"]) & eod["roll_max60"].notna()
    eod["industry"] = eod["S_INFO_WINDCODE"].map(code2ind)

    agg = eod.groupby(["TRADE_DT", "industry"]).agg(
        n_members=("S_INFO_WINDCODE", "nunique"),
        eq_return=("ret", "mean"),
        total_amount=("S_DQ_AMOUNT", "sum"),
        newhigh_ratio=("is_newhigh", "mean"),
    ).reset_index()
    agg["date"] = pd.to_datetime(agg["TRADE_DT"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    agg = agg[["date", "industry", "n_members", "eq_return",
               "total_amount", "newhigh_ratio"]].sort_values(["date", "industry"])

    out = DERIVED_DIR / "industry_basket_daily.csv"
    agg.to_csv(out, index=False, encoding="utf-8-sig")
    meta = write_sidecar(out, source=f"{EOD_CSV} + industry_universe.csv",
                         note="equal-weighted concept-basket daily aggregates; "
                              "newhigh = adjclose at 60-trading-day rolling max "
                              "(min_periods=20); amount unit = thousand HKD")
    print(f"rows={meta['rows']} range={meta['date_min']}..{meta['date_max']}")
    print(agg.groupby("industry")["n_members"].median().to_string())


if __name__ == "__main__":
    main()
