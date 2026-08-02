"""抓取外部环境数据：美联储有效联邦基金利率 DFF、美元指数 DXY。

- DFF：FRED 免 Key 直连 CSV
  https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF （日频）
- DXY（优先级）：
  1) AKShare 东财 `index_global_hist_em(symbol="美元指数")`
  2) yfinance `DX-Y.NYB`
  3) FRED 贸易加权广义美元指数 DTWEXBGS（ICE DXY 不可达时的收益代理；水平不可与 ICE 混比）

输出：data/external/macro/fed_dff.csv、data/external/macro/dxy.csv
美债 DGS10 按研究报告裁剪不采（与 DFF 高度相关）。
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import requests

from config import MACRO_DIR, FETCH_START, FETCH_END, ensure_dirs, write_sidecar

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF&cosd={start}&coed={end}"
FRED_DTWEXBGS = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?"
    "id=DTWEXBGS&cosd={start}&coed={end}"
)


def fetch_dff():
    url = FRED_CSV.format(start=FETCH_START, end=FETCH_END)
    last_err = None
    for timeout in (60, 120, 180):
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            break
        except Exception as e:
            last_err = e
            print(f"FRED DFF timeout/err ({timeout}s): {e}")
    else:
        # 外网失败时：在已有 CSV 上按日历 ffill 延展到 FETCH_END
        out = MACRO_DIR / "fed_dff.csv"
        if not out.exists():
            raise SystemExit(f"FRED DFF 失败且无本地缓存: {last_err}")
        df = pd.read_csv(out)
        df["date"] = pd.to_datetime(df["date"])
        full = pd.date_range(df["date"].min(), FETCH_END, freq="D")
        s = df.set_index("date")["dff"].reindex(full).ffill()
        df = s.rename("dff").rename_axis("date").reset_index()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        df = df[(df["date"] >= FETCH_START) & (df["date"] <= FETCH_END)]
        df.to_csv(out, index=False)
        meta = write_sidecar(
            out,
            source=url,
            note="FRED fetch failed; extended existing series by calendar ffill to FETCH_END",
        )
        print(f"fed_dff (ffill fallback) rows={meta['rows']} "
              f"range={meta['date_min']}..{meta['date_max']}")
        return

    df = pd.read_csv(io.StringIO(r.text))
    # 列名为 observation_date/DFF（旧版为 DATE/DFF）
    df.columns = ["date", "dff"]
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["dff"] = pd.to_numeric(df["dff"], errors="coerce")
    df = df.dropna(subset=["dff"]).sort_values("date")
    out = MACRO_DIR / "fed_dff.csv"
    df.to_csv(out, index=False)
    meta = write_sidecar(out, source=url,
                         note="Effective Federal Funds Rate (percent, daily), FRED no-key CSV")
    print(f"fed_dff rows={meta['rows']} range={meta['date_min']}..{meta['date_max']}")


def dxy_em():
    import akshare as ak
    df = ak.index_global_hist_em(symbol="美元指数")
    df = df.rename(columns={"日期": "date", "今开": "open", "最新价": "close",
                            "最高": "high", "最低": "low"})
    return df, "akshare.index_global_hist_em(美元指数)"


def dxy_yahoo():
    import yfinance as yf
    end = (pd.Timestamp(FETCH_END) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = yf.download("DX-Y.NYB", start=FETCH_START, end=end,
                     progress=False, auto_adjust=False)
    if df is None or len(df) == 0:
        raise RuntimeError("yfinance returned empty frame (rate limit?)")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index().rename(columns={"Date": "date", "Open": "open",
                                          "High": "high", "Low": "low", "Close": "close"})
    return df, "yfinance(DX-Y.NYB)"


def dxy_fred_broad():
    """ICE DXY 不可达时：用 FRED 贸易加权广义美元指数作收益代理。"""
    url = FRED_DTWEXBGS.format(start=FETCH_START, end=FETCH_END)
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "close"]
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    return df, url


def fetch_dxy():
    last_err = None
    for fn in (dxy_em, dxy_yahoo, dxy_fred_broad):
        try:
            df, source = fn()
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            keep = [c for c in ("date", "open", "high", "low", "close") if c in df.columns]
            df = df[keep]
            df = df[(df["date"] >= FETCH_START) & (df["date"] <= FETCH_END)]
            df = df.dropna(subset=["close"]).drop_duplicates("date").sort_values("date")
            if len(df) < 200:
                print(f"{source} 只有 {len(df)} 行，试下一源")
                continue
            note = "US Dollar Index daily"
            if fn is dxy_fred_broad:
                note = ("FRED DTWEXBGS Trade Weighted U.S. Dollar Index: Broad, Goods; "
                        "return proxy when ICE DXY unreachable — do not mix levels with ICE DXY")
            out = MACRO_DIR / "dxy.csv"
            df.to_csv(out, index=False)
            meta = write_sidecar(out, source=source, note=note)
            print(f"dxy rows={meta['rows']} range={meta['date_min']}..{meta['date_max']} "
                  f"via {fn.__name__}")
            return
        except Exception as e:
            last_err = e
            print(f"{fn.__name__} 失败: {type(e).__name__}: {e}")
    raise SystemExit(f"美元指数全部源失败: {last_err}")


def main():
    ensure_dirs()
    fetch_dff()
    fetch_dxy()


if __name__ == "__main__":
    main()
