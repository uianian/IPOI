"""抓取南向资金（港股通）日频历史。

数据源优先级：
1. AKShare `stock_hsgt_hist_em(symbol="南向资金")` —— 东财沪深港通历史，
   返回：日期、当日成交净买额、买入/卖出成交额、历史累计净买额、
   当日资金流入、持股市值、相关指数收盘/涨跌幅（字段以实际返回为准）
2. AKShare `stock_hsgt_south_net_flow_in_em(symbol="全部")` —— 南向净流入备用

输出：data/external/macro/southbound.csv
南向属"可选但推荐"（报告 M4）：全部失败时脚本报错退出，但下游允许缺失。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from config import MACRO_DIR, FETCH_START, FETCH_END, ensure_dirs, write_sidecar


def try_hist_em():
    import akshare as ak
    df = ak.stock_hsgt_hist_em(symbol="南向资金")
    df = df.rename(columns={"日期": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df, "akshare.stock_hsgt_hist_em(南向资金)"


def try_net_flow():
    import akshare as ak
    df = ak.stock_hsgt_south_net_flow_in_em(symbol="全部")
    # 返回列一般为 date/value（亿元）
    df.columns = ["date", "south_net_flow"] + list(df.columns[2:])
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df, "akshare.stock_hsgt_south_net_flow_in_em(全部)"


def main():
    ensure_dirs()
    last_err = None
    for fn in (try_hist_em, try_net_flow):
        try:
            df, source = fn()
            df = df[(df["date"] >= FETCH_START) & (df["date"] <= FETCH_END)]
            df = df.drop_duplicates("date").sort_values("date")
            if len(df) < 200:
                print(f"{source} 只有 {len(df)} 行，视为不完整，试下一源")
                continue
            out = MACRO_DIR / "southbound.csv"
            df.to_csv(out, index=False)
            meta = write_sidecar(out, source=source,
                                 note="southbound (HK Stock Connect) daily flows; "
                                      "amounts in 亿元 per Eastmoney convention")
            print(f"southbound rows={meta['rows']} range={meta['date_min']}..{meta['date_max']}")
            print("columns:", meta["columns"])
            return
        except Exception as e:
            last_err = e
            print(f"{fn.__name__} 失败: {type(e).__name__}: {e}")
    raise SystemExit(f"南向资金全部源失败: {last_err}（下游按可选数据处理，可稍后重试）")


if __name__ == "__main__":
    main()
