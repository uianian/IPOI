"""全量 + 抽样市场情绪特征完整度分析。

输出：
- data/derived/ipo_sentiment_completeness.csv          全量逐家
- data/derived/sample_sentiment_completeness.csv       抽样逐家
- data/derived/sample_sentiment_completeness_report.md 抽样报告
- data/derived/sample_feasible_companies.csv           抽样最大可行
- data/derived/sample_feasible_recommended.csv         抽样推荐优先
并打印全量档位汇总（供更新 README）。
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from config import DERIVED_DIR, DATASET_DIR, IPO_END, FETCH_END, ensure_dirs

HSTECH_CUT = pd.Timestamp("2020-09-01")

MACRO_CORE = [
    "hsi_ret_5d", "hsi_ret_20d", "hsi_ret_60d", "hsi_vol_20d",
    "mkt_turnover_avg_20d", "mkt_turnover_chg_20d",
    "southbound_net_20d", "southbound_net_prev20d",
    "dff_level", "dff_chg_30cd", "dxy_ret_20d",
]
IND_BASKET = [
    "ind_ret_5d", "ind_ret_20d", "ind_ret_60d", "ind_excess_20d",
    "ind_amount_chg_20d", "ind_newhigh_ratio",
]
IPO_HEAT = [
    "ipo_count_30d", "ipo_count_90d", "avg_day1_return_60d", "avg_day5_return_60d",
    "avg_day20_return_60d", "break_rate_60d", "avg_mdd20_60d",
]
OUTCOME_NUM = [
    "outcome_day1_return", "outcome_day5_return", "outcome_day20_return",
    "outcome_day60_return", "outcome_mdd20",
]


def nonempty(s: pd.Series) -> pd.Series:
    if s.dtype == object:
        return s.notna() & (s.astype(str).str.strip() != "") & (s.astype(str) != "nan")
    return s.notna()


def classify_row(r: pd.Series):
    hard, soft = [], []
    for c in MACRO_CORE:
        if pd.isna(r[c]):
            hard.append(f"macro:{c}")
    ld = r["listing_date"]
    if ld >= HSTECH_CUT:
        for c in ("hstech_ret_5d", "hstech_ret_20d"):
            if pd.isna(r[c]):
                hard.append(f"HSTECH:{c}")
        if pd.isna(r["hstech_ret_60d"]):
            soft.append("恒生科技60:hstech_ret_60d")
    else:
        soft.append("HSTECH:上市早于指数窗口")
    if pd.isna(r["vhsi_avg_5d"]):
        soft.append("VHSI")
    if r["industry"] != "其他":
        for c in IND_BASKET:
            if pd.isna(r[c]):
                hard.append(f"ind_basket:{c}")
    else:
        soft.append("行业=其他")
    if not nonempty(pd.Series([r.get("hs_sector_index")])).iloc[0]:
        soft.append("无官方板块")
    else:
        miss_hs = [c for c in (
            "hs_sector_ret_5d", "hs_sector_ret_20d", "hs_sector_ret_60d",
            "hs_sector_excess_20d") if pd.isna(r[c])]
        if miss_hs:
            soft.append("官方板块缺:" + ",".join(miss_hs))
    for c in IPO_HEAT:
        if pd.isna(r[c]):
            hard.append(f"ipo_heat:{c}")
    if pd.isna(r["subscription_multiple"]):
        hard.append("认购倍数")
    if pd.isna(r.get("international_placing_multiple")):
        soft.append("国配倍数")
    news_ok = nonempty(pd.Series([r.get("news_earliest")])).iloc[0] and (
        pd.notna(r.get("news_rows")) and r.get("news_rows", 0) not in (0,))
    if not news_ok:
        soft.append("新闻不可用/空")
    else:
        soft.append("新闻仅近期不可回测")
    if not all(pd.notna(r[c]) for c in OUTCOME_NUM):
        hard.append("outcome验证")

    if hard:
        tier = "核心缺口"
    else:
        has_vhsi = pd.notna(r["vhsi_avg_5d"])
        has_ind = r["industry"] != "其他" and all(pd.notna(r[c]) for c in IND_BASKET)
        has_news = news_ok
        tier = "严格完整" if (has_vhsi and has_ind and has_news) else "MVP可行"

    score = 100
    score -= 6 * len(hard) + 2 * len([s for s in soft if s != "新闻仅近期不可回测"])
    if r["industry"] != "其他":
        score += 5
    return tier, ";".join(hard), ";".join(soft), score


def analyze(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["listing_date"] = pd.to_datetime(df["listing_date"])
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(5)
    rows = []
    for _, r in df.iterrows():
        tier, hard, soft, score = classify_row(r)
        rows.append({
            "stock_code": r["stock_code"],
            "company": r["company"],
            "listing_date": r["listing_date"].strftime("%Y-%m-%d"),
            "listing_year": int(r["listing_date"].year),
            "industry": r["industry"],
            "tier": tier,
            "score": score,
            "missing_hard": hard or "无缺口",
            "missing_soft": soft or "—",
            "has_hstech": pd.notna(r["hstech_ret_5d"]) and pd.notna(r["hstech_ret_20d"]),
            "has_vhsi": pd.notna(r["vhsi_avg_5d"]),
            "has_ind_basket": r["industry"] != "其他" and all(
                pd.notna(r[c]) for c in IND_BASKET),
            "has_hs_sector": nonempty(pd.Series([r.get("hs_sector_index")])).iloc[0],
            "has_ipo_heat": all(pd.notna(r[c]) for c in IPO_HEAT),
            "has_subscription": pd.notna(r["subscription_multiple"]),
            "has_outcome": all(pd.notna(r[c]) for c in OUTCOME_NUM),
        })
    return pd.DataFrame(rows)


def write_sample_report(sample: pd.DataFrame, out_md: Path):
    n = len(sample)
    vc = sample["tier"].value_counts()
    feasible = sample[sample["tier"] != "核心缺口"]
    recommended = sample[
        (sample["tier"] == "严格完整")
        | ((sample["tier"] == "MVP可行") & (sample["industry"] != "其他"))
    ].sort_values(["tier", "score"], ascending=[True, False])
    # 严格完整 first in sort: 核心缺口 < MVP < 严格? string sort is wrong
    recommended = sample[
        (sample["tier"] == "严格完整")
        | ((sample["tier"] == "MVP可行") & (sample["industry"] != "其他"))
    ].assign(_ord=lambda x: x["tier"].map({"严格完整": 0, "MVP可行": 1})).sort_values(
        ["_ord", "score"], ascending=[True, False]).drop(columns="_ord")

    by_year = (sample.assign(y=sample["listing_year"])
               .groupby("y")["tier"].value_counts().unstack(fill_value=0))
    for c in ("严格完整", "MVP可行", "核心缺口"):
        if c not in by_year.columns:
            by_year[c] = 0
    by_year["可行合计"] = by_year["严格完整"] + by_year["MVP可行"]

    lines = [
        "# 抽样公司市场情绪数据完整度核验报告",
        "",
        f"> 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"> 对照：`dataset/samples/sample_manifest.csv` × `derived/ipo_sentiment_features.csv`",
        f"> 日历上界：IPO_END={IPO_END}，FETCH_END={FETCH_END}",
        "",
        "## 背景说明",
        "",
        "招股书 PDF 归档年多为 2020–2025，但部分 **2025 年末招股书对应 2026 年初实际上市日**",
        "（EDE/EOD）。热度日表与外采须覆盖到最大 listing_date，否则「上市日前一日」查找失败。",
        "",
        "## 口径",
        "",
        "- **硬缺口**：宏观核心缺任一；上市≥2020-09 仍缺 HSTECH 5/20；已映射行业缺篮子；",
        "  IPO 热度缺；缺认购倍数；缺 outcome 验证",
        "- **软缺口**：VHSI、HSTECH60、官方板块、行业=其他、国配、新闻不可回测等",
        "- **严格完整**：无硬缺口 + VHSI + 行业篮子 + 新闻指针",
        "- **MVP可行**：无硬缺口",
        "",
        "## 总览",
        "",
        f"- 抽样家数：**{n}**",
        f"- **严格完整：{vc.get('严格完整', 0)}** 家",
        f"- **MVP可行：{vc.get('MVP可行', 0)}** 家",
        f"- **核心缺口：{vc.get('核心缺口', 0)}** 家",
        f"- **最大可行合计：{len(feasible)}/{n}（{100*len(feasible)/n:.1f}%）**",
        f"- **推荐优先清单（严格完整，或 MVP 且行业已映射）：{len(recommended)} 家**",
        "",
        "### 按上市年",
        "",
        "| 年份 | 严格完整 | MVP可行 | 核心缺口 | 可行合计 |",
        "|------|----------|---------|----------|----------|",
    ]
    for y, row in by_year.sort_index().iterrows():
        lines.append(
            f"| {y} | {int(row['严格完整'])} | {int(row['MVP可行'])} | "
            f"{int(row['核心缺口'])} | {int(row['可行合计'])} |"
        )
    lines += ["", "## 推荐优先清单", "",
              f"共 **{len(recommended)}** 家：严格完整，或 MVP 可行且行业概念篮子可用。",
              "",
              "| 代码 | 公司 | 上市年 | 档位 | score | 行业 | 软缺口摘要 |",
              "|------|------|--------|------|-------|------|------------|"]
    for _, r in recommended.iterrows():
        soft = r["missing_soft"]
        soft = soft.replace("新闻仅近期不可回测", "").replace("国配倍数", "").strip(" ;")
        soft = soft if soft else "—"
        lines.append(
            f"| {r['stock_code']} | {r['company']} | {r['listing_year']} | "
            f"{r['tier']} | {r['score']} | {r['industry']} | {soft} |"
        )

    core = sample[sample["tier"] == "核心缺口"].sort_values("score")
    lines += ["", "## 核心缺口清单", "",
              f"共 **{len(core)}** 家。",
              "",
              "| 代码 | 公司 | 上市日 | 行业 | 硬缺口 |",
              "|------|------|--------|------|--------|"]
    for _, r in core.iterrows():
        lines.append(
            f"| {r['stock_code']} | {r['company']} | {r['listing_date']} | "
            f"{r['industry']} | {r['missing_hard']} |"
        )

    lines += [
        "", "## 逐家明细", "",
        "完整字段见同目录 CSV：",
        "- [`sample_sentiment_completeness.csv`](sample_sentiment_completeness.csv)",
        "- [`sample_feasible_companies.csv`](sample_feasible_companies.csv)",
        "- [`sample_feasible_recommended.csv`](sample_feasible_recommended.csv)",
        "",
        "| 代码 | 公司 | 年 | 档位 | score | 行业 | 热度 | 认购 | 行业篮 | VHSI | outcome | 硬/软缺口 |",
        "|------|------|----|------|-------|------|------|------|--------|------|---------|-----------|",
    ]
    for _, r in sample.sort_values(["tier", "score"], ascending=[True, False]).iterrows():
        yn = lambda b: "Y" if b else "N"
        gap = r["missing_hard"] if r["missing_hard"] != "无缺口" else r["missing_soft"]
        lines.append(
            f"| {r['stock_code']} | {r['company']} | {r['listing_year']} | {r['tier']} | "
            f"{r['score']} | {r['industry']} | {yn(r['has_ipo_heat'])} | "
            f"{yn(r['has_subscription'])} | {yn(r['has_ind_basket'])} | "
            f"{yn(r['has_vhsi'])} | {yn(r['has_outcome'])} | {gap} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ensure_dirs()
    feat = pd.read_csv(DERIVED_DIR / "ipo_sentiment_features.csv", dtype={"stock_code": str})
    full = analyze(feat)
    full["stock_code"] = full["stock_code"].astype(str).str.zfill(5)
    full.to_csv(DERIVED_DIR / "ipo_sentiment_completeness.csv",
                index=False, encoding="utf-8-sig")

    manifest = pd.read_csv(DATASET_DIR / "samples" / "sample_manifest.csv",
                           dtype=str)
    # 兼容不同列名
    code_col = next(c for c in manifest.columns
                    if "code" in c.lower() or c in ("股票代码", "stock_code"))
    codes = (manifest[code_col].astype(str).str.replace(r"\D", "", regex=True)
             .str.zfill(5))
    sample = full[full["stock_code"].isin(set(codes))].copy()
    sample["stock_code"] = sample["stock_code"].astype(str).str.zfill(5)
    sample.to_csv(DERIVED_DIR / "sample_sentiment_completeness.csv",
                  index=False, encoding="utf-8-sig")
    feasible = sample[sample["tier"] != "核心缺口"]
    feasible.to_csv(DERIVED_DIR / "sample_feasible_companies.csv",
                    index=False, encoding="utf-8-sig")
    recommended = sample[
        (sample["tier"] == "严格完整")
        | ((sample["tier"] == "MVP可行") & (sample["industry"] != "其他"))
    ]
    recommended.to_csv(DERIVED_DIR / "sample_feasible_recommended.csv",
                       index=False, encoding="utf-8-sig")
    write_sample_report(sample, DERIVED_DIR / "sample_sentiment_completeness_report.md")

    print("=== FULL universe ===")
    print(full["tier"].value_counts().to_string())
    print("feasible", (full["tier"] != "核心缺口").sum(), "/", len(full))
    print("by year:")
    print(pd.crosstab(full["listing_year"], full["tier"], margins=True).to_string())
    y26 = full[full["listing_year"] >= 2026]
    print("\n2026+ rows:", len(y26))
    print(y26[["stock_code", "company", "listing_date", "tier",
               "has_ipo_heat", "missing_hard"]].to_string(index=False))
    print("\n=== SAMPLE ===")
    print(sample["tier"].value_counts().to_string())
    print("feasible", (sample["tier"] != "核心缺口").sum(), "/", len(sample))


if __name__ == "__main__":
    main()
