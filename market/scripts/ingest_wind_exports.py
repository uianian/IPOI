"""清洗马宝灵万得导出（dataset/wind/）→ market/data/external/{wind,macro}/。

替换/增强：
- ICE 美元指数 USDX.FX → 覆盖原 FRED DTWEXBGS 代理（写入 macro/dxy.csv）
- 美国 10Y 国债收益率 → macro/us10y.csv
- 恒生指数日行情 → macro/hsi.csv（权威替换 AKShare）
- HSICS 证券行业 + 综合行业指数日线
- IPO 首日/发行价/网上·网下认购倍数
- 港股 HS 板块净流入（约 2022 起有值）

原始文件只读不改；可重复运行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from config import (
    WIND_RAW_DIR, WIND_DIR, MACRO_DIR, FETCH_START, FETCH_END,
    ensure_dirs, write_sidecar,
)


def _stock_code5(x) -> str | None:
    s = re.sub(r"\D", "", str(x).upper().replace(".HK", ""))
    return s.zfill(5) if s else None


def _to_date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.normalize()


def _num(s: pd.Series) -> pd.Series:
    if s.dtype == object:
        s = s.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False)
    return pd.to_numeric(s, errors="coerce")


def ingest_us10y():
    p = WIND_RAW_DIR / "美国10年期国债收益率20160801-20260801.csv"
    df = pd.read_csv(p, encoding="gbk")
    df = df.rename(columns={df.columns[0]: "date", df.columns[1]: "us10y"})
    df = df[df["date"].astype(str).str.match(r"^\d{4}")]
    df["date"] = _to_date_series(df["date"]).dt.strftime("%Y-%m-%d")
    df["us10y"] = _num(df["us10y"])
    df = df.dropna(subset=["date", "us10y"]).drop_duplicates("date").sort_values("date")
    df = df[(df["date"] >= FETCH_START) & (df["date"] <= FETCH_END)]
    out = MACRO_DIR / "us10y.csv"
    df.to_csv(out, index=False)
    write_sidecar(out, source=str(p), note="US 10Y Treasury yield (%), Wind G0000891")
    print(f"us10y {len(df)} {df.date.min()}..{df.date.max()}")
    return df


def ingest_dxy():
    p = WIND_RAW_DIR / "美元指数十年日行情.xlsx"
    raw = pd.read_excel(p, engine="openpyxl", header=None)
    # row0 titles, row1 ticker, data from row2
    rows = []
    for i in range(2, len(raw)):
        d = raw.iloc[i, 0]
        o, c = raw.iloc[i, 1], raw.iloc[i, 2]
        if pd.isna(d):
            continue
        rows.append({"date": pd.Timestamp(d).normalize(), "open": o, "close": c})
    df = pd.DataFrame(rows)
    df["open"] = _num(df["open"])
    df["close"] = _num(df["close"])
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["close"]).drop_duplicates("date").sort_values("date")
    df = df[(df["date"] >= FETCH_START) & (df["date"] <= FETCH_END)]
    # backup old proxy if present
    old = MACRO_DIR / "dxy.csv"
    if old.exists():
        bak = MACRO_DIR / "dxy_fred_dtwexbgs_backup.csv"
        if not bak.exists():
            old.replace(bak)
            print(f"backed up previous dxy → {bak.name}")
    out = MACRO_DIR / "dxy.csv"
    df.to_csv(out, index=False)
    write_sidecar(out, source=str(p),
                  note="ICE US Dollar Index USDX.FX from Wind — replaces FRED DTWEXBGS proxy")
    # also copy under wind/
    df.to_csv(WIND_DIR / "dxy.csv", index=False)
    print(f"dxy(Wind USDX) {len(df)} {df.date.min()}..{df.date.max()}")
    return df


def ingest_hsi():
    p = WIND_RAW_DIR / "恒生指数十年日行情20160801-20260801.xlsx"
    raw = pd.read_excel(p, engine="openpyxl", header=None)
    rows = []
    for i in range(2, len(raw)):
        d = raw.iloc[i, 0]
        if pd.isna(d):
            continue
        rows.append({
            "date": pd.Timestamp(d).normalize().strftime("%Y-%m-%d"),
            "open": _num(pd.Series([raw.iloc[i, 1]])).iloc[0],
            "close": _num(pd.Series([raw.iloc[i, 2]])).iloc[0],
            "source": "wind.HSI.HI",
        })
    df = pd.DataFrame(rows).dropna(subset=["close"]).drop_duplicates("date").sort_values("date")
    df = df[(df["date"] >= FETCH_START) & (df["date"] <= FETCH_END)]
    old = MACRO_DIR / "hsi.csv"
    if old.exists():
        bak = MACRO_DIR / "hsi_akshare_backup.csv"
        if not bak.exists():
            # copy not replace path for backup
            pd.read_csv(old).to_csv(bak, index=False)
            print(f"backed up previous hsi → {bak.name}")
    out = MACRO_DIR / "hsi.csv"
    df.to_csv(out, index=False)
    write_sidecar(out, source=str(p), note="HSI.HI daily OHLC from Wind — replaces AKShare sina")
    df.to_csv(WIND_DIR / "hsi.csv", index=False)
    print(f"hsi(Wind) {len(df)} {df.date.min()}..{df.date.max()}")
    return df


def _parse_wide_index_csv(path: Path, value_name: str, encoding: str) -> pd.DataFrame:
    raw = pd.read_csv(path, encoding=encoding, header=None)
    hdr = raw.iloc[1, 1:]
    cols_meta = []
    for j, h in hdr.items():
        if pd.isna(h):
            continue
        parts = str(h).replace("\r", "").split("\n")
        name = parts[0].strip()
        code = parts[-1].strip() if len(parts) > 1 else name
        cols_meta.append((j, name, code))
    rows = []
    for i in range(2, len(raw)):
        d = raw.iloc[i, 0]
        if pd.isna(d) or str(d).startswith("数据来源"):
            continue
        ds = pd.Timestamp(d).strftime("%Y-%m-%d") if not isinstance(d, str) else str(
            pd.to_datetime(d, errors="coerce").date())
        if ds == "NaT":
            continue
        for j, name, code in cols_meta:
            v = _num(pd.Series([raw.iloc[i, j]])).iloc[0]
            if pd.isna(v) or v == 0:
                # 0 对部分主题指数表示未发布，记 NaN
                if v == 0:
                    continue
            rows.append({"date": ds, "index_code": code, "index_name": name, value_name: v})
    return pd.DataFrame(rows)


def ingest_hsics_indices():
    close = _parse_wide_index_csv(
        WIND_RAW_DIR / "恒生行业分类指数十年收盘价.csv", "close", "utf-8-sig")
    open_ = _parse_wide_index_csv(
        WIND_RAW_DIR / "恒生行业分类指数十年开盘价.csv", "open", "gbk")
    df = close.merge(open_, on=["date", "index_code", "index_name"], how="outer")
    df = df.sort_values(["index_code", "date"])
    df = df[(df["date"] >= FETCH_START) & (df["date"] <= FETCH_END)]
    out = WIND_DIR / "hsics_index_daily.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    write_sidecar(out, source="dataset/wind/恒生行业分类指数十年开盘价|收盘价.csv",
                  note="long-form HSICS / HS theme index daily; 0-close rows dropped as unpublished")
    print(f"hsics_index_daily {len(df)} codes={df.index_code.nunique()} "
          f"{df.date.min()}..{df.date.max()}")
    # also split composite 12 into macro-like files for convenience
    for code in df.loc[df.index_name.str.contains("恒生综合行业指数", na=False), "index_code"].unique():
        sub = df[df.index_code == code][["date", "open", "close"]].drop_duplicates("date")
        safe = code.replace(".", "_").lower()
        sub.to_csv(WIND_DIR / f"index_{safe}.csv", index=False)
    return df


def ingest_hsics_security():
    p = WIND_RAW_DIR / "恒生行业分类.xlsx"
    df = pd.read_excel(p, engine="calamine")
    df = df.dropna(subset=["证券代码"])
    df = df[~df["证券代码"].astype(str).str.contains("数据来源")]
    rename = {}
    for c in df.columns:
        if c == "证券代码":
            rename[c] = "windcode"
        elif c == "证券简称":
            rename[c] = "name"
        elif "全部明细" in c:
            rename[c] = "hsics_path"
        elif "一级行业" in c:
            rename[c] = "hsics_l1_code"
        elif "二级行业" in c:
            rename[c] = "hsics_l2_code"
        elif "三级行业" in c:
            rename[c] = "hsics_l3_code"
        elif "综合行业指数名称" in c:
            rename[c] = "hsics_composite_index_name"
    df = df.rename(columns=rename)
    df["stock_code"] = df["windcode"].map(_stock_code5)
    df["windcode"] = df["windcode"].astype(str).str.upper()

    def l1_name(path):
        if pd.isna(path):
            return None
        # e.g. 医疗保健业(HS)-药品及生物科技(HS)-药品(HS)
        return str(path).split("(HS)")[0].strip()

    df["hsics_l1_name"] = df["hsics_path"].map(l1_name)
    out = WIND_DIR / "hsics_security_industry.csv"
    keep = ["stock_code", "windcode", "name", "hsics_l1_name", "hsics_l1_code",
            "hsics_l2_code", "hsics_l3_code", "hsics_path", "hsics_composite_index_name"]
    df[keep].to_csv(out, index=False, encoding="utf-8-sig")
    write_sidecar(out, source=str(p), note="HSICS classification per HK security from Wind")
    print(f"hsics_security {len(df)} with L1 {df.hsics_l1_name.notna().sum()}")
    return df


def ingest_ipo_listing():
    p = WIND_RAW_DIR / "股票上市首日表现.xlsx"
    df = pd.read_excel(p, engine="calamine")
    df = df.dropna(subset=["证券代码"])
    df = df[~df["证券代码"].astype(str).str.contains("数据来源")]
    colmap = {
        "证券代码": "windcode",
        "证券简称": "name",
        "Wind代码": "windcode2",
        "网上发行有效认购倍数": "public_offer_multiple",
        "网下发行有效申购倍数": "international_placing_multiple",
        "公开发售申购人数": "public_offer_subscribers",
        "申购一手中签率\n[单位] %": "one_lot_odds_pct",
    }
    # fuzzy for multiline headers
    for c in list(df.columns):
        if "首发价格" in c:
            colmap[c] = "issue_price"
        elif "首发上市日期" in c or c == "首发上市日期":
            colmap[c] = "ipo_list_date"
        elif "上市首日开盘价" in c:
            colmap[c] = "day1_open"
        elif "上市首日收盘价" in c:
            colmap[c] = "day1_close"
        elif "上市首日涨跌幅" in c:
            colmap[c] = "day1_pct_wind"
        elif c not in colmap and "网上发行有效认购倍数" in str(c):
            colmap[c] = "public_offer_multiple"
        elif c not in colmap and "网下发行有效申购倍数" in str(c):
            colmap[c] = "international_placing_multiple"
    df = df.rename(columns=colmap)
    if "windcode" not in df.columns and "windcode2" in df.columns:
        df["windcode"] = df["windcode2"]
    df["stock_code"] = df["windcode"].map(_stock_code5)
    for c in ("issue_price", "public_offer_multiple", "international_placing_multiple",
              "day1_open", "day1_close", "day1_pct_wind", "one_lot_odds_pct"):
        if c in df.columns:
            df[c] = _num(df[c])
    if "ipo_list_date" in df.columns:
        df["ipo_list_date"] = _to_date_series(df["ipo_list_date"]).dt.strftime("%Y-%m-%d")
    keep = [c for c in ("stock_code", "windcode", "name", "issue_price", "ipo_list_date",
                        "day1_open", "day1_close", "day1_pct_wind",
                        "public_offer_multiple", "international_placing_multiple",
                        "public_offer_subscribers", "one_lot_odds_pct") if c in df.columns]
    out_df = df[keep].drop_duplicates("stock_code", keep="last")
    out = WIND_DIR / "ipo_listing_stats.csv"
    out_df.to_csv(out, index=False, encoding="utf-8-sig")
    write_sidecar(out, source=str(p),
                  note="Wind IPO issue price + online/offline subscription multiples")
    print(f"ipo_listing_stats {len(out_df)} issue_price "
          f"{out_df.issue_price.notna().sum()} public_mult "
          f"{out_df.public_offer_multiple.notna().sum()}")
    return out_df


def ingest_sector_flow():
    p = WIND_RAW_DIR / "港股板块净流入（港交所分类、2021年及之前无数据）.xlsx"
    raw = pd.read_excel(p, engine="openpyxl", header=None)
    # row1: sector headers for cols 1..13 = 合计净流入; 14..26 = 算术平均 — 只用合计
    hdr = raw.iloc[1, 1:14]
    sectors = []
    for j, h in hdr.items():
        if pd.isna(h):
            continue
        name = str(h).replace("\r", "").split("\n")[0]
        name = re.sub(r"^\(HS\)", "", name).strip()
        sectors.append((j, name))
    rows = []
    for i in range(2, len(raw)):
        d = raw.iloc[i, 0]
        if pd.isna(d):
            continue
        ds = pd.Timestamp(d).normalize().strftime("%Y-%m-%d")
        for j, name in sectors:
            v = _num(pd.Series([raw.iloc[i, j]])).iloc[0]
            rows.append({"date": ds, "hs_sector": name, "net_inflow": v})
    df = pd.DataFrame(rows)
    df = df[(df["date"] >= FETCH_START) & (df["date"] <= FETCH_END)]
    # 标注有效期：全 0 的早期日期对 Agent 应按缺失处理
    out = WIND_DIR / "hs_sector_net_inflow_daily.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    nz = df[df.net_inflow.fillna(0) != 0]
    write_sidecar(out, source=str(p),
                  note=f"HS board net inflow (HKEX); nonzero from ~{nz.date.min() if len(nz) else 'n/a'}; "
                       f"pre-2022 mostly 0 — treat as missing in features")
    print(f"sector_flow {len(df)} nonzero_rows={len(nz)} "
          f"nonzero_from={nz.date.min() if len(nz) else None}")
    return df


def main():
    ensure_dirs()
    WIND_DIR.mkdir(parents=True, exist_ok=True)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    if not WIND_RAW_DIR.exists():
        raise SystemExit(f"missing {WIND_RAW_DIR}")
    ingest_us10y()
    ingest_dxy()
    ingest_hsi()
    ingest_hsics_indices()
    ingest_hsics_security()
    ingest_ipo_listing()
    ingest_sector_flow()
    print("done →", WIND_DIR, "and", MACRO_DIR)


if __name__ == "__main__":
    main()
