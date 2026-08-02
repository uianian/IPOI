"""批量抓取 565 家 IPO 公司的东财个股新闻（舆情模块原始语料）。

已知限制（探针实测）：`ak.stock_news_em` 每个关键词只返回最近约 10~100 条，
历史深度只有最近数周——**盖不住 2020-2025 回测期**。按项目决策仍然落盘，
每家的实际最早/最新日期写入 news_fetch_log.csv；回测期舆情建议用招股书
文本代理（见研究报告模块4）。

策略：先按 5 位股票代码查询；0 条则回退公司名（跳过"待补全_"占位名）。
断点续抓：已有 {code}.csv 的公司直接跳过。
输出：data/external/news/{code}.csv、data/external/news/news_fetch_log.csv
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from config import IPO_CATALOG_CSV, NEWS_DIR, ensure_dirs

SLEEP_SEC = 0.4


def fetch_one(ak, code5, name):
    """返回 (df, query_used)；两种查询都失败/为空时返回 (空df, None)。"""
    queries = [code5]
    if name and not str(name).startswith("待补全"):
        queries.append(str(name).replace("－", "-"))
    for q in queries:
        try:
            df = ak.stock_news_em(symbol=q)
            if df is not None and len(df):
                df.insert(0, "query", q)
                return df, q
        except Exception as e:
            print(f"  {code5} query={q!r} 失败: {type(e).__name__}: {e}")
        time.sleep(SLEEP_SEC)
    return pd.DataFrame(), None


def main():
    ensure_dirs()
    import akshare as ak

    cat = pd.read_csv(IPO_CATALOG_CSV, dtype={"stock_code": str})
    log_path = NEWS_DIR / "news_fetch_log.csv"
    logs = []
    done = skipped = empty = 0

    for i, row in cat.iterrows():
        code5 = str(row["stock_code"]).zfill(5)
        out = NEWS_DIR / f"{code5}.csv"
        if out.exists():
            skipped += 1
            continue
        df, q = fetch_one(ak, code5, row.get("company_display"))
        if len(df):
            df.to_csv(out, index=False, encoding="utf-8-sig")
            dates = pd.to_datetime(df["发布时间"], errors="coerce")
            logs.append({"stock_code": code5, "query": q, "rows": len(df),
                         "earliest": str(dates.min()), "latest": str(dates.max()),
                         "status": "ok"})
            done += 1
        else:
            logs.append({"stock_code": code5, "query": None, "rows": 0,
                         "earliest": None, "latest": None, "status": "empty"})
            empty += 1
        if (done + empty) % 25 == 0:
            print(f"progress: fetched={done} empty={empty} skipped={skipped}")
            # 阶段性落盘日志，抓挂了也不丢进度
            pd.DataFrame(logs).to_csv(log_path, index=False, encoding="utf-8-sig")
        time.sleep(SLEEP_SEC)

    # 合并旧日志（断点续抓场景）
    new_log = pd.DataFrame(logs)
    if log_path.exists() and skipped:
        old = pd.read_csv(log_path, dtype={"stock_code": str})
        new_log = pd.concat([old[~old["stock_code"].isin(new_log.get("stock_code", []))],
                             new_log], ignore_index=True)
    new_log = new_log.drop_duplicates("stock_code", keep="last").sort_values("stock_code")
    new_log.to_csv(log_path, index=False, encoding="utf-8-sig")
    print(f"FINISHED fetched={done} empty={empty} skipped={skipped}")
    if len(new_log):
        earliest = pd.to_datetime(new_log["earliest"], errors="coerce").min()
        print(f"earliest news across all companies: {earliest} "
              f"(coverage vs 2020-2025 backtest window is expected to be poor; "
              f"use prospectus-text sentiment proxy for backtest)")


if __name__ == "__main__":
    main()
