"""抓取宏观指数日线：恒生指数 HSI、恒生科技 HSTECH、恒指波幅 VHSI。

数据源优先级：
1. AKShare 新浪 `stock_hk_index_daily_sina`（国内直连，历史长）
2. AKShare 东财 `stock_hk_index_daily_em`
3. yfinance（^HSI / HSTECH.HK；VHSI 在 Yahoo 无稳定代码，失败即记录缺失）

输出：data/external/macro/{hsi,hstech,vhsi}.csv
统一列：date, open, high, low, close, volume, source
VHSI 拉不到时不报错——报告已论证可用 HSI 20日波动率替代。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from config import MACRO_DIR, FETCH_START, FETCH_END, ensure_dirs, write_sidecar

TARGETS = {
    # name: (sina_symbol, em_symbol, yahoo_symbol)
    "hsi": ("HSI", "HSI", "^HSI"),
    "hstech": ("HSTECH", "HSTECH", "HSTECH.HK"),
    "vhsi": ("VHSI", "VHSI", None),
}

# sidecar 备注：明确各指数的已知覆盖限制，供下游正确处理 NaN
NOTES = {
    "hsi": "daily OHLC; full coverage from FETCH_START",
    "hstech": ("HSTECH index launched 2020-07-27; no data before launch. "
               "IPO features prior to launch must be NaN (use HSI instead)."),
    "vhsi": ("Sina coverage starts ~2021-03; for earlier dates use HSI 20d "
             "rolling std as volatility proxy (see research report)."),
}

COLMAP = {
    "日期": "date", "date": "date", "Date": "date",
    "开盘": "open", "open": "open", "Open": "open", "今开": "open",
    "最高": "high", "high": "high", "High": "high",
    "最低": "low", "low": "low", "Low": "low",
    "收盘": "close", "close": "close", "Close": "close", "最新价": "close",
    "成交量": "volume", "volume": "volume", "Volume": "volume",
}


def normalize(df, source):
    df = df.rename(columns={c: COLMAP[c] for c in df.columns if c in COLMAP})
    keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
    out = df[keep].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out = out[(out["date"] >= FETCH_START) & (out["date"] <= FETCH_END)]
    out = out.dropna(subset=["close"]).drop_duplicates("date").sort_values("date")
    out["source"] = source
    return out


def try_sina(symbol):
    import akshare as ak
    df = ak.stock_hk_index_daily_sina(symbol=symbol)
    return normalize(df, f"akshare.stock_hk_index_daily_sina({symbol})")


def try_em(symbol):
    import akshare as ak
    df = ak.stock_hk_index_daily_em(symbol=symbol)
    return normalize(df, f"akshare.stock_hk_index_daily_em({symbol})")


def try_yahoo(symbol):
    import yfinance as yf
    df = yf.download(symbol, start=FETCH_START, end="2026-01-01",
                     progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    return normalize(df, f"yfinance({symbol})")


def fetch_one(name, sina_sym, em_sym, yahoo_sym):
    attempts = []
    if sina_sym:
        attempts.append(("sina", lambda: try_sina(sina_sym)))
    if em_sym:
        attempts.append(("em", lambda: try_em(em_sym)))
    if yahoo_sym:
        attempts.append(("yahoo", lambda: try_yahoo(yahoo_sym)))
    for label, fn in attempts:
        try:
            df = fn()
            if len(df) >= 100:  # 起码要有几个月的数据才算成功
                return df, None
            print(f"  [{name}] {label} 只返回 {len(df)} 行，视为不完整，试下一源")
        except Exception as e:
            print(f"  [{name}] {label} 失败: {type(e).__name__}: {e}")
    return None, "all sources failed or incomplete"


def main():
    ensure_dirs()
    results = {}
    for name, (sina_sym, em_sym, yahoo_sym) in TARGETS.items():
        print(f"== fetching {name} ==")
        df, err = fetch_one(name, sina_sym, em_sym, yahoo_sym)
        if df is None:
            print(f"  [{name}] 全部源失败：{err}（VHSI 可用 HSI 波动率替代，见报告）")
            results[name] = None
            continue
        out = MACRO_DIR / f"{name}.csv"
        df.to_csv(out, index=False)
        meta = write_sidecar(out, source=df["source"].iloc[0], note=NOTES.get(name, ""))
        print(f"  [{name}] rows={meta['rows']} range={meta['date_min']}..{meta['date_max']}")
        results[name] = meta
    # 覆盖校验：
    # - HSI 必须覆盖 2020-01 起点（宏观主指标）
    # - HSTECH 2020-07-27 才发布，只要求覆盖发布后首月
    # - VHSI 可选（缺口用 HSI 20日波动率替代）
    m = results.get("hsi")
    assert m is not None and m["date_min"] <= "2020-01-03", \
        f"hsi 覆盖不足（{m and m['date_min']}），宏观模块必需，需换源"
    m = results.get("hstech")
    assert m is not None and m["date_min"] <= "2020-09-01", \
        f"hstech 覆盖不足（{m and m['date_min']}），应从指数发布日 2020-07-27 附近开始"
    if results.get("vhsi") is None:
        print("  [vhsi] 缺失：下游一律用 HSI 20日波动率")
    print("done")


if __name__ == "__main__":
    main()
