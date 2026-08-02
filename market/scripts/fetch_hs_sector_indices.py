"""抓取恒生官方板块指数日线（Sector Index Series + TECH）。

免费源：AKShare 新浪 `stock_hk_index_daily_sina`
- HSMBI  恒生中国内地银行指数
- HSMOGI 恒生中国内地石油及天然气指数
- HSMPI  恒生中国内地地产指数
- HSTECH 恒生科技指数（已由 fetch_macro_indices 采过；此处幂等再写一份别名文件）

说明：完整 HSICS 全行业指数无免费 bulk；以上是公开通道实测可拉的官方板块指数。
输出：data/external/macro/{hsmbi,hsmogi,hsmpi}.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from config import MACRO_DIR, FETCH_START, FETCH_END, ensure_dirs, write_sidecar

TARGETS = {
    "hsmbi": ("HSMBI", "恒生中国内地银行指数"),
    "hsmogi": ("HSMOGI", "恒生中国内地石油及天然气指数"),
    "hsmpi": ("HSMPI", "恒生中国内地地产指数"),
}

COLMAP = {
    "日期": "date", "date": "date",
    "开盘": "open", "open": "open",
    "最高": "high", "high": "high",
    "最低": "low", "low": "low",
    "收盘": "close", "close": "close",
    "成交量": "volume", "volume": "volume",
}


def fetch_sina(symbol):
    import akshare as ak
    df = ak.stock_hk_index_daily_sina(symbol=symbol)
    df = df.rename(columns={c: COLMAP[c] for c in df.columns if c in COLMAP})
    keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
    out = df[keep].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out = out[(out["date"] >= FETCH_START) & (out["date"] <= FETCH_END)]
    out = out.dropna(subset=["close"]).drop_duplicates("date").sort_values("date")
    out["source"] = f"akshare.stock_hk_index_daily_sina({symbol})"
    return out


def main():
    ensure_dirs()
    for name, (symbol, cn) in TARGETS.items():
        print(f"== fetching {name} ({cn} / {symbol}) ==")
        df = fetch_sina(symbol)
        assert len(df) >= 500, f"{name} 行数过少: {len(df)}"
        assert df["date"].min() <= "2020-01-03", f"{name} 起点过晚: {df['date'].min()}"
        out = MACRO_DIR / f"{name}.csv"
        df.to_csv(out, index=False)
        meta = write_sidecar(
            out,
            source=df["source"].iloc[0],
            note=f"Hang Seng official sector index: {cn} ({symbol}); "
                 f"mapped from config.HS_SECTOR_INDEX",
        )
        print(f"  rows={meta['rows']} range={meta['date_min']}..{meta['date_max']}")
    # HSTECH 若已存在则跳过；否则补拉
    hstech = MACRO_DIR / "hstech.csv"
    if not hstech.exists():
        print("== fetching hstech (missing) ==")
        df = fetch_sina("HSTECH")
        df.to_csv(hstech, index=False)
        write_sidecar(hstech, source=df["source"].iloc[0],
                      note="Hang Seng TECH Index")
    else:
        print("hstech.csv already present, skip")
    print("done")


if __name__ == "__main__":
    main()
