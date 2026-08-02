"""从赛题 EOD 行情构建全市场日成交额汇总（市场流动性代理，报告 M3）。

输入：dataset/hkshareeodprices.csv（约 411 万行，chunked 读取）
输出：data/derived/market_turnover_daily.csv
列：date, total_amount_thousand_hkd, total_volume, n_stocks_traded

单位说明：S_DQ_AMOUNT 按 Wind 惯例为「千港元」（腾讯 2024-01-02 约 6.96e6 千港元
≈ 70 亿港元，与实际吻合）。下游只用相对变化，不做绝对值比较。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from config import EOD_CSV, DERIVED_DIR, ensure_dirs, write_sidecar


def main():
    ensure_dirs()
    parts = []
    usecols = ["TRADE_DT", "S_DQ_AMOUNT", "S_DQ_VOLUME"]
    for chunk in pd.read_csv(EOD_CSV, usecols=usecols, chunksize=800_000):
        g = chunk.groupby("TRADE_DT").agg(
            total_amount_thousand_hkd=("S_DQ_AMOUNT", "sum"),
            total_volume=("S_DQ_VOLUME", "sum"),
            n_stocks_traded=("S_DQ_AMOUNT", lambda s: int((s.fillna(0) > 0).sum())),
        )
        parts.append(g)
    df = pd.concat(parts).groupby(level=0).sum().reset_index()
    df["date"] = pd.to_datetime(df["TRADE_DT"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    df = df[["date", "total_amount_thousand_hkd", "total_volume", "n_stocks_traded"]]
    df = df.sort_values("date")
    out = DERIVED_DIR / "market_turnover_daily.csv"
    df.to_csv(out, index=False)
    meta = write_sidecar(out, source=str(EOD_CSV),
                         note="daily sum over all HK stocks in contest EOD table; "
                              "amount unit = thousand HKD (Wind convention)")
    print(f"rows={meta['rows']} range={meta['date_min']}..{meta['date_max']}")


if __name__ == "__main__":
    main()
