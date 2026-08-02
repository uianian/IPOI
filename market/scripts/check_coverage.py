"""数据体检：逐文件打印覆盖范围、行数、关键缺口，形成一页体检报告。

用法：.venv/bin/python scripts/check_coverage.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from config import MACRO_DIR, NEWS_DIR, DERIVED_DIR, DATA_DIR

EXPECT = {
    # file: (min_rows, date_col, required_start, note)
    MACRO_DIR / "hsi.csv": (1400, "date", "2020-01-03", "宏观主指标，必需"),
    MACRO_DIR / "hstech.csv": (1200, "date", "2020-09-01", "2020-07-27 才发布"),
    MACRO_DIR / "vhsi.csv": (900, "date", None, "可选；缺口用 HSI 波动率替代"),
    MACRO_DIR / "southbound.csv": (1300, "date", "2020-01-15", "可选但推荐"),
    MACRO_DIR / "fed_dff.csv": (2000, "date", "2020-01-03", "FRED 日频"),
    MACRO_DIR / "dxy.csv": (1400, "date", "2020-01-03", "美元指数"),
    MACRO_DIR / "hsmbi.csv": (1000, "date", "2020-01-03", "恒生内地银行官方板块"),
    MACRO_DIR / "hsmogi.csv": (1000, "date", "2020-01-03", "恒生内地油气官方板块"),
    MACRO_DIR / "hsmpi.csv": (1000, "date", "2020-01-03", "恒生内地地产官方板块"),
    DERIVED_DIR / "market_turnover_daily.csv": (1400, "date", "2020-01-03", "EOD 汇总"),
    DERIVED_DIR / "industry_universe.csv": (2500, None, None, "EDE 行业标签"),
    DERIVED_DIR / "ipo_industry_map.csv": (565, None, None, "565 家行业映射"),
    DERIVED_DIR / "industry_basket_daily.csv": (10000, "date", "2020-01-03", "行业篮子"),
    DERIVED_DIR / "ipo_events.csv": (565, None, None, "IPO 事件表"),
    DERIVED_DIR / "ipo_market_heat_daily.csv": (2100, "date", "2020-01-01", "市场热度"),
    DERIVED_DIR / "ipo_industry_heat_daily.csv": (15000, "date", "2020-01-01", "行业热度"),
    DERIVED_DIR / "ipo_sentiment_features.csv": (565, None, None, "最终宽表"),
    DATA_DIR / "external" / "ipo" / "subscription_multiples.csv": (100, None, None, "认购倍数（致富+新股渔夫）"),
}


def main():
    problems = []
    print(f"{'file':52s} {'rows':>7s}  {'range':29s} status")
    print("-" * 110)
    for path, (min_rows, date_col, req_start, note) in EXPECT.items():
        rel = path.relative_to(path.parents[2])
        if not path.exists():
            print(f"{str(rel):52s} {'-':>7s}  {'-':29s} MISSING  ({note})")
            problems.append(f"MISSING: {rel}")
            continue
        df = pd.read_csv(path)
        rng = "-"
        status = "ok"
        if date_col and date_col in df.columns:
            dmin, dmax = str(df[date_col].min())[:10], str(df[date_col].max())[:10]
            rng = f"{dmin}..{dmax}"
            if req_start and dmin > req_start:
                status = f"LATE START (need <= {req_start})"
                problems.append(f"{rel}: starts {dmin}, expected <= {req_start}")
        if len(df) < min_rows:
            status = f"TOO FEW ROWS (<{min_rows})"
            problems.append(f"{rel}: {len(df)} rows < {min_rows}")
        print(f"{str(rel):52s} {len(df):>7d}  {rng:29s} {status}  ({note})")

    # 新闻覆盖
    log_path = NEWS_DIR / "news_fetch_log.csv"
    if log_path.exists():
        log = pd.read_csv(log_path)
        ok = (log["status"] == "ok").sum()
        earliest = pd.to_datetime(log["earliest"], errors="coerce").min()
        print(f"\nnews: {ok}/{len(log)} companies with news; "
              f"earliest={earliest}  <-- 历史深度不足 2020 属预期，回测用招股书文本代理")
    else:
        print("\nnews: log 不存在（fetch_news.py 未跑完或未运行）")

    # 特征宽表非空率
    feat_path = DERIVED_DIR / "ipo_sentiment_features.csv"
    if feat_path.exists():
        f = pd.read_csv(feat_path)
        nn = f.notna().mean().sort_values()
        print("\nfeature non-null ratio (lowest 10):")
        print(nn.head(10).to_string())

    print("\n" + ("ALL CHECKS PASSED" if not problems else
                  f"{len(problems)} PROBLEM(S):\n- " + "\n- ".join(problems)))


if __name__ == "__main__":
    main()
