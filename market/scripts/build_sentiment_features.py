"""汇总最终交付：ipo_sentiment_features.csv —— 565 家 IPO 每家一行。

特征口径（对照《市场情绪agent实现背景材料》）：
- 指数收益 R_n = P0/Pn - 1（交易日收盘）
- 行业收益：优先万得恒生综合行业指数（HSICS）；无则 EDE 概念篮子
- 宏观 HSI/DXY：优先万得清洗结果（ingest_wind_exports.py）
- 美债：us10y_*（万得）
- IPO 热度取上市日前一自然日；缺失一律 NaN，不填 0
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from config import (DERIVED_DIR, MACRO_DIR, NEWS_DIR, WIND_DIR, HS_FLOW_L1,
                    HS_SECTOR_INDEX, ensure_dirs, write_sidecar)


def load_series(path, date_col="date", value_col="close"):
    if not Path(path).exists():
        return None
    df = pd.read_csv(path)
    df[date_col] = pd.to_datetime(df[date_col])
    return df.sort_values(date_col).reset_index(drop=True)


class TradingSeries:
    def __init__(self, df, value_col):
        self.dates = df["date"].to_numpy()
        self.values = df[value_col].to_numpy(dtype=float)

    def pos_at(self, d):
        p = np.searchsorted(self.dates, np.datetime64(pd.Timestamp(d)), side="right") - 1
        return int(p)

    def value_at(self, d):
        p = self.pos_at(d)
        return self.values[p] if p >= 0 else np.nan

    def ret_n(self, d, n):
        p0 = self.pos_at(d)
        pn = p0 - n
        if p0 < 0 or pn < 0:
            return np.nan
        a, b = self.values[p0], self.values[pn]
        if not (np.isfinite(a) and np.isfinite(b)) or b == 0:
            return np.nan
        return a / b - 1.0

    def window(self, d, n, end_offset=0):
        p0 = self.pos_at(d) + end_offset
        if p0 < 0 or p0 - n + 1 < 0:
            return None
        return self.values[p0 - n + 1: p0 + 1]

    def vol_n(self, d, n):
        w = self.window(d, n + 1)
        if w is None:
            return np.nan
        rets = np.diff(w) / w[:-1]
        return float(np.std(rets, ddof=1))

    def mean_n(self, d, n):
        w = self.window(d, n)
        return float(np.nanmean(w)) if w is not None else np.nan

    def sum_n(self, d, n, end_offset=0):
        w = self.window(d, n, end_offset)
        return float(np.nansum(w)) if w is not None else np.nan


def main():
    ensure_dirs()
    ev = pd.read_csv(DERIVED_DIR / "ipo_events.csv", parse_dates=["listing_date"],
                     dtype={"stock_code": str})
    ev["stock_code"] = ev["stock_code"].astype(str).str.zfill(5)
    imap = pd.read_csv(DERIVED_DIR / "ipo_industry_map.csv", dtype={"stock_code": str})
    imap["stock_code"] = imap["stock_code"].astype(str).str.zfill(5)
    ev = ev.drop(columns=[c for c in ("industry",) if c in ev.columns], errors="ignore")
    ev = ev.merge(
        imap[["stock_code", "industry", "hsics_l1_name", "hsics_index_code",
              "hsics_index_name", "industry_source"]],
        on="stock_code", how="left")

    hsi = TradingSeries(load_series(MACRO_DIR / "hsi.csv"), "close")
    hstech = TradingSeries(load_series(MACRO_DIR / "hstech.csv"), "close")
    vhsi_df = load_series(MACRO_DIR / "vhsi.csv")
    vhsi = TradingSeries(vhsi_df, "close") if vhsi_df is not None else None
    dxy = TradingSeries(load_series(MACRO_DIR / "dxy.csv"), "close")
    dff = TradingSeries(load_series(MACRO_DIR / "fed_dff.csv"), "dff")
    us10y_df = load_series(MACRO_DIR / "us10y.csv", value_col="us10y")
    us10y = TradingSeries(us10y_df, "us10y") if us10y_df is not None else None

    # HSICS 官方行业指数
    hsics_series = {}
    hsics_path = WIND_DIR / "hsics_index_daily.csv"
    if hsics_path.exists():
        hx = pd.read_csv(hsics_path, parse_dates=["date"])
        for code, g in hx.groupby("index_code"):
            g = g.dropna(subset=["close"]).sort_values("date")
            if len(g) >= 60:
                hsics_series[code] = TradingSeries(g.reset_index(drop=True), "close")
        print(f"loaded HSICS indices: {len(hsics_series)}")

    # 旧免费板块（仅作补充；有 HSICS 时优先 HSICS）
    hs_sector_series = {}
    for fname in set(HS_SECTOR_INDEX.values()):
        path = MACRO_DIR / f"{fname}.csv"
        df = load_series(path)
        if df is not None:
            hs_sector_series[fname] = TradingSeries(df, "close")

    # 板块净流入
    flow_series = {}
    flow_path = WIND_DIR / "hs_sector_net_inflow_daily.csv"
    flow_valid_from = pd.Timestamp("2022-01-24")
    if flow_path.exists():
        fl = pd.read_csv(flow_path, parse_dates=["date"])
        for sec, g in fl.groupby("hs_sector"):
            g = g.sort_values("date").reset_index(drop=True)
            flow_series[sec] = TradingSeries(g, "net_inflow")
        print(f"loaded sector flow: {len(flow_series)} boards")

    turn = TradingSeries(
        load_series(DERIVED_DIR / "market_turnover_daily.csv"),
        "total_amount_thousand_hkd")
    sb_df = load_series(MACRO_DIR / "southbound.csv")
    southbound = TradingSeries(sb_df, "当日成交净买额") if (
        sb_df is not None and "当日成交净买额" in sb_df.columns) else None

    baskets = pd.read_csv(DERIVED_DIR / "industry_basket_daily.csv", parse_dates=["date"])
    ind_series = {}
    for ind, g in baskets.groupby("industry"):
        g = g.sort_values("date").reset_index(drop=True)
        g["cum"] = (1 + g["eq_return"].fillna(0)).cumprod()
        ind_series[ind] = {
            "level": TradingSeries(g, "cum"),
            "amount": TradingSeries(g, "total_amount"),
            "newhigh": TradingSeries(g, "newhigh_ratio"),
        }

    heat = pd.read_csv(DERIVED_DIR / "ipo_market_heat_daily.csv",
                       parse_dates=["date"]).set_index("date")
    ind_heat = pd.read_csv(DERIVED_DIR / "ipo_industry_heat_daily.csv",
                           parse_dates=["date"])
    ind_heat = ind_heat.set_index(["date", "industry"]).sort_index()

    news_log_path = NEWS_DIR / "news_fetch_log.csv"
    news_log = (pd.read_csv(news_log_path, dtype={"stock_code": str})
                .set_index("stock_code")
                if news_log_path.exists() else None)

    wind_ipo_path = WIND_DIR / "ipo_listing_stats.csv"
    wind_ipo = (pd.read_csv(wind_ipo_path, dtype={"stock_code": str})
                .set_index("stock_code") if wind_ipo_path.exists() else None)

    rows = []
    for _, r in ev.iterrows():
        d = r["listing_date"]
        d_prev = d - pd.Timedelta(days=1)
        f = {
            "stock_code": r["stock_code"], "windcode": r["windcode"],
            "company": r["company_display"],
            "listing_date": d.strftime("%Y-%m-%d"),
            # 所有特征只能使用上市日前可得数据；TradingSeries 会自动回退到
            # d_prev 当日或更早的最近观测日。
            "as_of_date": d_prev.strftime("%Y-%m-%d"),
            "market_observation_date": d_prev.strftime("%Y-%m-%d"),
            "industry": r.get("industry"),
            "hsics_l1_name": r.get("hsics_l1_name"),
            "industry_source": r.get("industry_source"),
            "hsi_ret_5d": hsi.ret_n(d_prev, 5), "hsi_ret_20d": hsi.ret_n(d_prev, 20),
            "hsi_ret_60d": hsi.ret_n(d_prev, 60),
            "hstech_ret_5d": hstech.ret_n(d_prev, 5), "hstech_ret_20d": hstech.ret_n(d_prev, 20),
            "hstech_ret_60d": hstech.ret_n(d_prev, 60),
            "hsi_vol_20d": hsi.vol_n(d_prev, 20),
            "vhsi_avg_5d": vhsi.mean_n(d_prev, 5) if vhsi else np.nan,
            "mkt_turnover_avg_20d": turn.mean_n(d_prev, 20),
            "dff_level": dff.value_at(d_prev),
            "dff_chg_30cd": (
                dff.value_at(d_prev) - dff.value_at(d_prev - pd.Timedelta(days=30))
            ),
            "dxy_ret_20d": dxy.ret_n(d_prev, 20),
            "us10y_level": us10y.value_at(d_prev) if us10y else np.nan,
            "us10y_chg_20d": (
                (us10y.value_at(d_prev) - us10y.value_at(d_prev - pd.Timedelta(days=20)))
                if us10y else np.nan),
        }
        w40 = turn.window(d_prev, 40)
        f["mkt_turnover_chg_20d"] = (
            float(np.nanmean(w40[20:]) / np.nanmean(w40[:20]) - 1)
            if w40 is not None else np.nan)
        if southbound:
            f["southbound_net_20d"] = southbound.sum_n(d_prev, 20)
            w = southbound.window(d_prev, 40)
            f["southbound_net_prev20d"] = float(np.nansum(w[:20])) if w is not None else np.nan
        else:
            f["southbound_net_20d"] = f["southbound_net_prev20d"] = np.nan

        # --- 行业收益：HSICS 优先 ---
        hsics_code = r.get("hsics_index_code")
        hsics_ts = hsics_series.get(hsics_code) if pd.notna(hsics_code) else None
        f["hsics_index_code"] = hsics_code if pd.notna(hsics_code) else None
        f["hsics_index_name"] = r.get("hsics_index_name")
        used_hsics = False
        if hsics_ts is not None:
            f["ind_ret_5d"] = hsics_ts.ret_n(d_prev, 5)
            f["ind_ret_20d"] = hsics_ts.ret_n(d_prev, 20)
            f["ind_ret_60d"] = hsics_ts.ret_n(d_prev, 60)
            f["ind_excess_20d"] = (
                f["ind_ret_20d"] - f["hsi_ret_20d"]
                if not (pd.isna(f["ind_ret_20d"]) or pd.isna(f["hsi_ret_20d"])) else np.nan)
            used_hsics = not pd.isna(f["ind_ret_20d"])
            f["industry_return_source"] = "hsics" if used_hsics else None
        # 概念篮子：金额/创新高；若无 HSICS 收益则用篮子收益
        s = ind_series.get(r.get("industry"))
        if s:
            wa = s["amount"].window(d_prev, 40)
            f["ind_amount_chg_20d"] = (
                float(np.nanmean(wa[20:]) / np.nanmean(wa[:20]) - 1)
                if wa is not None else np.nan)
            f["ind_newhigh_ratio"] = s["newhigh"].value_at(d_prev)
            if not used_hsics:
                f["ind_ret_5d"] = s["level"].ret_n(d_prev, 5)
                f["ind_ret_20d"] = s["level"].ret_n(d_prev, 20)
                f["ind_ret_60d"] = s["level"].ret_n(d_prev, 60)
                f["ind_excess_20d"] = (
                    f["ind_ret_20d"] - f["hsi_ret_20d"]
                    if not (pd.isna(f["ind_ret_20d"]) or pd.isna(f["hsi_ret_20d"]))
                    else np.nan)
                f["industry_return_source"] = (
                    "concept_basket" if not pd.isna(f.get("ind_ret_20d")) else None)
        else:
            if not used_hsics:
                for k in ("ind_ret_5d", "ind_ret_20d", "ind_ret_60d", "ind_excess_20d"):
                    f[k] = np.nan
                f["industry_return_source"] = None
            f["ind_amount_chg_20d"] = f.get("ind_amount_chg_20d", np.nan)
            f["ind_newhigh_ratio"] = f.get("ind_newhigh_ratio", np.nan)

        # hs_sector_*：与 HSICS 对齐（官方行业）；无则回退旧免费板块
        if hsics_ts is not None and used_hsics:
            f["hs_sector_index"] = hsics_code
            f["hs_sector_ret_5d"] = f["ind_ret_5d"]
            f["hs_sector_ret_20d"] = f["ind_ret_20d"]
            f["hs_sector_ret_60d"] = f["ind_ret_60d"]
            f["hs_sector_excess_20d"] = f["ind_excess_20d"]
        else:
            hs_key = HS_SECTOR_INDEX.get(r.get("industry"))
            hs_ts = hs_sector_series.get(hs_key) if hs_key else None
            f["hs_sector_index"] = hs_key
            if hs_ts is not None:
                f["hs_sector_ret_5d"] = hs_ts.ret_n(d_prev, 5)
                f["hs_sector_ret_20d"] = hs_ts.ret_n(d_prev, 20)
                f["hs_sector_ret_60d"] = hs_ts.ret_n(d_prev, 60)
                f["hs_sector_excess_20d"] = (
                    f["hs_sector_ret_20d"] - f["hsi_ret_20d"]
                    if not (pd.isna(f["hs_sector_ret_20d"]) or pd.isna(f["hsi_ret_20d"]))
                    else np.nan)
            else:
                f["hs_sector_ret_5d"] = f["hs_sector_ret_20d"] = f["hs_sector_ret_60d"] = \
                    f["hs_sector_excess_20d"] = np.nan

        # 板块净流入（20 交易日合计）；2022 前视为缺失
        l1 = r.get("hsics_l1_name")
        flow_key = None
        if pd.notna(l1):
            for k, v in HS_FLOW_L1.items():
                if v == l1 or k == l1:
                    flow_key = k
                    break
            if flow_key is None:
                flow_key = str(l1)
        fts = flow_series.get(flow_key) if flow_key else None
        if fts is not None and pd.Timestamp(d_prev) >= flow_valid_from:
            s20 = fts.sum_n(d_prev, 20)
            f["ind_net_inflow_20d"] = s20 if (s20 is not None and s20 != 0) else np.nan
        else:
            f["ind_net_inflow_20d"] = np.nan

        def _asof_heat_row(idx_date):
            idx_date = pd.Timestamp(idx_date).normalize()
            if idx_date in heat.index:
                return heat.loc[idx_date]
            earlier = heat.index[heat.index <= idx_date]
            return heat.loc[earlier.max()] if len(earlier) else None

        try:
            ih = ind_heat.loc[(d_prev.normalize(), r["industry"])]
        except Exception:
            ih = None
            try:
                sub = ind_heat.xs(r["industry"], level="industry", drop_level=False)
                earlier = sub.index.get_level_values("date")
                earlier = earlier[earlier <= d_prev.normalize()]
                if len(earlier):
                    ih = ind_heat.loc[(earlier.max(), r["industry"])]
            except Exception:
                ih = None
        if ih is not None:
            f["ind_ipo_count_365d"] = ih["ipo_count_365d"]
            f["ind_avg_day1_return_365d"] = ih["avg_day1_return_365d"]
            f["ind_break_rate_365d"] = ih["break_rate_365d"]
        else:
            f["ind_ipo_count_365d"] = f["ind_avg_day1_return_365d"] = \
                f["ind_break_rate_365d"] = np.nan

        h = _asof_heat_row(d_prev)
        for c in ("ipo_count_30d", "ipo_count_90d", "avg_day1_return_60d",
                  "avg_day5_return_60d", "avg_day20_return_60d",
                  "break_rate_60d", "avg_mdd20_60d"):
            f[c] = h[c] if h is not None else np.nan
        f["subscription_multiple"] = np.nan

        code5 = str(r["stock_code"]).zfill(5)
        if news_log is not None and code5 in news_log.index:
            f["news_rows"] = news_log.loc[code5, "rows"]
            f["news_earliest"] = news_log.loc[code5, "earliest"]
        else:
            f["news_rows"] = np.nan
            f["news_earliest"] = None

        if wind_ipo is not None and code5 in wind_ipo.index:
            f["issue_price"] = wind_ipo.loc[code5, "issue_price"]
        else:
            f["issue_price"] = np.nan

        for c in ("day1_return", "day5_return", "day20_return", "day60_return",
                  "is_break", "mdd20"):
            f[f"outcome_{c}"] = r[c]
        rows.append(f)

    out_df = pd.DataFrame(rows)
    out = DERIVED_DIR / "ipo_sentiment_features.csv"
    out_df.to_csv(out, index=False, encoding="utf-8-sig")
    meta = write_sidecar(
        out,
        source="Wind(HSICS/DXY/HSI/US10Y) + macro + derived + news log",
        note="ind_ret prefers HSICS composite index; DXY=USDX.FX; us10y from Wind; "
             "all features cut off at listing_date-1 calendar day; "
             "NaN never filled with 0; outcome_* validation only")
    print(f"rows={meta['rows']} cols={len(meta['columns'])}")
    print("industry_return_source:\n", out_df["industry_return_source"].value_counts(dropna=False))
    print("ind_ret_20d non-null", out_df["ind_ret_20d"].notna().sum())
    print("hs_sector_ret_20d non-null", out_df["hs_sector_ret_20d"].notna().sum())
    print("us10y non-null", out_df["us10y_level"].notna().sum())
    print("ind_net_inflow_20d non-null", out_df["ind_net_inflow_20d"].notna().sum())


if __name__ == "__main__":
    main()
