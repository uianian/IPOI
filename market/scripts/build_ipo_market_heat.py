"""IPO 市场热度（模块3）+ 行业 IPO 热度（模块2.3）。

事件表：565 家招股书 IPO，上市日口径 = EDE 上市日 > EOD 首日 > PDF 文件名日期。
收益基准 = 首日开盘价（发行价缺失，见研究报告）。

输出：
- data/derived/ipo_events.csv            每家 IPO 一行：上市日、行业、day1/5/20
  收益、是否破发、上市后20交易日最大回撤
- data/derived/ipo_market_heat_daily.csv IPO_START..IPO_END 每日一行：
  近30/90日 IPO 数、近60日平均首日/5日/20日收益、破发率、平均最大回撤
- data/derived/ipo_industry_heat_daily.csv 每日×行业：近365日 IPO 数、
  平均首日收益、破发率

窗口均为自然日（原文档口径），回看窗口含当日。
日历上界见 config.IPO_END（须覆盖 2025 年末招股书对应的 2026 上市日）。
"""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

# 空窗口的 nanmean 按设计返回 NaN，无需告警
warnings.filterwarnings("ignore", message="Mean of empty slice")

from config import (EOD_CSV, IPO_CATALOG_CSV, PROSPECTUS_CSV, DERIVED_DIR,
                    IPO_START, IPO_END, ensure_dirs, write_sidecar)


def _prospectus_names():
    """PDF 文件名中的公司名，用于覆盖 catalog 里的「待补全_*」。"""
    if not Path(PROSPECTUS_CSV).exists():
        return {}
    p = pd.read_csv(PROSPECTUS_CSV)
    p["stock_code"] = p["股票代码"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(5)
    # 同一代码多份 PDF 时取最后一条（通常为最终发售稿）
    return (p.drop_duplicates("stock_code", keep="last")
            .set_index("stock_code")["公司名称"].to_dict())


def build_events():
    cat = pd.read_csv(IPO_CATALOG_CSV, dtype={"stock_code": str})
    cat["stock_code"] = cat["stock_code"].astype(str).str.zfill(5)
    imap = pd.read_csv(DERIVED_DIR / "ipo_industry_map.csv", dtype={"stock_code": str})
    imap["stock_code"] = imap["stock_code"].astype(str).str.zfill(5)
    ev = cat.merge(imap[["windcode", "ede_list_date", "industry"]],
                   on="windcode", how="left")
    for c in ("ede_list_date", "first_trade_date", "list_date"):
        ev[c] = pd.to_datetime(ev[c], errors="coerce")
    # EDE 与 EOD 首日差超 30 天视为错配（老股再发行/代码复用，如保誠 2378），
    # 此时以 EOD 首日为准
    diff = (ev["ede_list_date"] - ev["first_trade_date"]).dt.days.abs()
    ede_ok = ev["ede_list_date"].where(diff.isna() | (diff <= 30))
    ev["listing_date"] = (ede_ok
                          .fillna(ev["first_trade_date"])
                          .fillna(ev["list_date"]))
    # 招股书年≠上市年：2025 年末 PDF → 2026 实际上市，属正常，勿裁掉
    names = _prospectus_names()
    mask = ev["company_display"].astype(str).str.startswith("待补全_")
    ev.loc[mask, "company_display"] = (
        ev.loc[mask, "stock_code"].map(names).fillna(ev.loc[mask, "company_display"]))
    ev["is_break"] = ev["day1_return"] < 0
    return ev


def add_mdd20(ev):
    """上市后前 20 个交易日内（复权收盘）最大回撤，负值。"""
    codes = set(ev["windcode"])
    usecols = ["S_INFO_WINDCODE", "TRADE_DT", "S_DQ_ADJCLOSE"]
    parts = []
    for chunk in pd.read_csv(EOD_CSV, usecols=usecols, chunksize=800_000):
        sub = chunk[chunk["S_INFO_WINDCODE"].isin(codes)]
        if len(sub):
            parts.append(sub)
    eod = pd.concat(parts, ignore_index=True).sort_values(
        ["S_INFO_WINDCODE", "TRADE_DT"])

    first_trade = ev.set_index("windcode")["first_trade_date"]
    mdd = {}
    for code, g in eod.groupby("S_INFO_WINDCODE", sort=False):
        ft = first_trade.get(code)
        if pd.isna(ft):
            continue
        ft_int = int(ft.strftime("%Y%m%d"))
        prices = g.loc[g["TRADE_DT"] >= ft_int, "S_DQ_ADJCLOSE"].head(20).to_numpy()
        prices = prices[~np.isnan(prices)]
        if len(prices) < 5:
            continue  # 交易日不足，记缺失而不是0
        running_max = np.maximum.accumulate(prices)
        mdd[code] = float(np.min(prices / running_max - 1.0))
    ev["mdd20"] = ev["windcode"].map(mdd)
    return ev


def rolling_daily(ev):
    dates = pd.date_range(IPO_START, IPO_END, freq="D")
    ld = ev["listing_date"].to_numpy()
    d1 = ev["day1_return"].to_numpy(dtype=float)
    d5 = ev["day5_return"].to_numpy(dtype=float)
    d20 = ev["day20_return"].to_numpy(dtype=float)
    brk = ev["is_break"].to_numpy(dtype=float)
    mdd = ev["mdd20"].to_numpy(dtype=float)

    rows = []
    for d in dates:
        d64 = np.datetime64(d)
        in30 = (ld > d64 - np.timedelta64(30, "D")) & (ld <= d64)
        in90 = (ld > d64 - np.timedelta64(90, "D")) & (ld <= d64)
        in60 = (ld > d64 - np.timedelta64(60, "D")) & (ld <= d64)
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "ipo_count_30d": int(in30.sum()),
            "ipo_count_90d": int(in90.sum()),
            "avg_day1_return_60d": np.nanmean(d1[in60]) if in60.any() else np.nan,
            "avg_day5_return_60d": np.nanmean(d5[in60]) if in60.any() else np.nan,
            "avg_day20_return_60d": np.nanmean(d20[in60]) if in60.any() else np.nan,
            "break_rate_60d": np.nanmean(brk[in60]) if in60.any() else np.nan,
            "avg_mdd20_60d": np.nanmean(mdd[in60]) if in60.any() else np.nan,
        })
    return pd.DataFrame(rows)


def rolling_industry(ev):
    dates = pd.date_range(IPO_START, IPO_END, freq="D")
    rows = []
    for ind, g in ev.groupby("industry"):
        ld = g["listing_date"].to_numpy()
        d1 = g["day1_return"].to_numpy(dtype=float)
        brk = g["is_break"].to_numpy(dtype=float)
        for d in dates:
            d64 = np.datetime64(d)
            in365 = (ld > d64 - np.timedelta64(365, "D")) & (ld <= d64)
            n = int(in365.sum())
            rows.append({
                "date": d.strftime("%Y-%m-%d"),
                "industry": ind,
                "ipo_count_365d": n,
                "avg_day1_return_365d": np.nanmean(d1[in365]) if n else np.nan,
                "break_rate_365d": np.nanmean(brk[in365]) if n else np.nan,
            })
    return pd.DataFrame(rows).sort_values(["date", "industry"])


def main():
    ensure_dirs()
    ev = build_events()
    print(f"events={len(ev)}, listing_date range="
          f"{ev['listing_date'].min().date()}..{ev['listing_date'].max().date()}")
    ev = add_mdd20(ev)
    print(f"mdd20 available: {ev['mdd20'].notna().sum()}/{len(ev)}")

    keep = ["stock_code", "windcode", "company_display", "listing_date", "industry",
            "day1_return", "day5_return", "day20_return", "day60_return",
            "is_break", "mdd20", "listboard", "performance_class"]
    out_ev = DERIVED_DIR / "ipo_events.csv"
    ev[keep].to_csv(out_ev, index=False, encoding="utf-8-sig")
    write_sidecar(out_ev, source=f"{IPO_CATALOG_CSV} + EDE + EOD",
                  note="565 prospectus IPOs; returns based on day0 open (no issue price); "
                       "mdd20 = max drawdown of adjclose over first 20 trading days")

    heat = rolling_daily(ev)
    out_h = DERIVED_DIR / "ipo_market_heat_daily.csv"
    heat.to_csv(out_h, index=False)
    meta = write_sidecar(out_h, source="ipo_events.csv",
                         note="calendar-day rolling windows (30/90 counts, 60d averages); "
                              "NaN when no IPO in window — do not fill 0")
    print(f"market heat rows={meta['rows']}")

    ih = rolling_industry(ev)
    out_i = DERIVED_DIR / "ipo_industry_heat_daily.csv"
    ih.to_csv(out_i, index=False, encoding="utf-8-sig")
    meta = write_sidecar(out_i, source="ipo_events.csv",
                         note="per-industry 365d rolling IPO count / day1 return / break rate")
    print(f"industry heat rows={meta['rows']}")


if __name__ == "__main__":
    main()
