"""Build D5,D10,...,D60 realized IPO performance checkpoints.

Primary risk anchor: issue price (below_issue_price).
Secondary-market return base: first trading day's open.
Every checkpoint uses only prices observed through that trading day.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from config import DATASET_DIR, DERIVED_DIR, EOD_CSV, MACRO_DIR, WIND_DIR, ensure_dirs, write_sidecar

CATALOG = Path(__file__).resolve().parents[2] / "dataset_analysis" / "output" / "ipo_catalog_with_metrics.csv"
INDUSTRY_MAP = DERIVED_DIR / "ipo_industry_map.csv"
OUT = DERIVED_DIR / "ipo_postlisting_checkpoints.csv"
CHECKPOINTS = list(range(5, 61, 5))


def _series_return(frame, start_date, end_date, *, code=None):
    data = frame
    if code is not None:
        data = data[data["index_code"] == code]
    data = data[(data["date"] >= start_date) & (data["date"] <= end_date)].sort_values("date")
    if data.empty:
        return np.nan
    start = data.iloc[0]
    end = data.iloc[-1]
    base = start.get("open")
    if pd.isna(base) or float(base) == 0:
        base = start.get("close")
    return float(end["close"] / base - 1.0) if pd.notna(base) and pd.notna(end["close"]) else np.nan


def main():
    ensure_dirs()
    if not EOD_CSV.is_file():
        raise FileNotFoundError(
            f"missing full daily EOD file: {EOD_CSV}; run this builder on the server/full repository"
        )
    catalog = pd.read_csv(CATALOG, dtype={"stock_code": str})
    catalog["stock_code"] = catalog["stock_code"].astype(str).str.zfill(5)
    catalog["listing_date"] = pd.to_datetime(
        catalog["first_trade_date"].fillna(catalog["list_date"]), errors="coerce"
    )
    imap = pd.read_csv(INDUSTRY_MAP, dtype={"stock_code": str})
    imap["stock_code"] = imap["stock_code"].astype(str).str.zfill(5)
    catalog = catalog.merge(
        imap[["stock_code", "hsics_index_code"]], on="stock_code", how="left"
    )
    codes = set(catalog["windcode"].dropna().astype(str))

    header = pd.read_csv(EOD_CSV, nrows=0).columns
    required = ["S_INFO_WINDCODE", "TRADE_DT", "S_DQ_OPEN", "S_DQ_CLOSE"]
    missing = [column for column in required if column not in header]
    if missing:
        raise ValueError(f"EOD file missing required columns: {missing}")
    optional = [column for column in ("S_DQ_ADJCLOSE", "S_DQ_AMOUNT") if column in header]
    parts = []
    for chunk in pd.read_csv(EOD_CSV, usecols=required + optional, chunksize=800_000):
        selected = chunk[chunk["S_INFO_WINDCODE"].isin(codes)]
        if len(selected):
            parts.append(selected)
    if not parts:
        raise ValueError("no IPO securities matched the EOD file")
    eod = pd.concat(parts, ignore_index=True)
    eod["date"] = pd.to_datetime(eod["TRADE_DT"].astype(str), format="%Y%m%d")
    eod = eod.sort_values(["S_INFO_WINDCODE", "date"])

    hsi = pd.read_csv(MACRO_DIR / "hsi.csv")
    hsi["date"] = pd.to_datetime(hsi["date"])
    industry_path = WIND_DIR / "hsics_index_daily.csv"
    industry = pd.read_csv(industry_path) if industry_path.is_file() else pd.DataFrame()
    if not industry.empty:
        industry["date"] = pd.to_datetime(industry["date"])

    meta = catalog.set_index("windcode").to_dict("index")
    rows = []
    for windcode, group in eod.groupby("S_INFO_WINDCODE", sort=False):
        issuer = meta.get(windcode)
        if not issuer:
            continue
        listing_date = issuer.get("listing_date")
        if pd.isna(listing_date):
            continue
        path = group[group["date"] >= listing_date].head(60).copy()
        if path.empty or pd.isna(path.iloc[0]["S_DQ_OPEN"]):
            continue
        first_open = float(path.iloc[0]["S_DQ_OPEN"])
        if first_open <= 0:
            continue
        issue_price = pd.to_numeric(issuer.get("list_price"), errors="coerce")
        for checkpoint in CHECKPOINTS:
            if len(path) < checkpoint:
                continue
            observed = path.iloc[:checkpoint]
            last = observed.iloc[-1]
            close = float(last["S_DQ_CLOSE"])
            cumulative = close / first_open - 1.0
            price_path = np.concatenate(([first_open], observed["S_DQ_CLOSE"].to_numpy(dtype=float)))
            running_max = np.maximum.accumulate(price_path)
            max_drawdown = float(np.min(price_path / running_max - 1.0))
            returns = np.diff(price_path) / price_path[:-1]
            realized_vol = float(np.std(returns, ddof=1)) if len(returns) >= 2 else np.nan
            turnover_change = np.nan
            if "S_DQ_AMOUNT" in observed and observed["S_DQ_AMOUNT"].notna().any():
                first5 = observed["S_DQ_AMOUNT"].head(5).mean()
                last5 = observed["S_DQ_AMOUNT"].tail(5).mean()
                if pd.notna(first5) and first5 != 0 and pd.notna(last5):
                    turnover_change = float(last5 / first5 - 1.0)
            hsi_return = _series_return(hsi, observed.iloc[0]["date"], last["date"])
            industry_return = np.nan
            index_code = issuer.get("hsics_index_code")
            if index_code and not industry.empty:
                industry_return = _series_return(
                    industry,
                    observed.iloc[0]["date"],
                    last["date"],
                    code=index_code,
                )
            rows.append(
                {
                    "stock_code": issuer["stock_code"],
                    "windcode": windcode,
                    "company": issuer.get("company_display") or issuer.get("company_name"),
                    "listing_date": listing_date.strftime("%Y-%m-%d"),
                    "checkpoint": f"D{checkpoint}",
                    "trading_day": checkpoint,
                    "observation_date": last["date"].strftime("%Y-%m-%d"),
                    "first_trading_day_open": first_open,
                    "checkpoint_close": close,
                    "issue_price": issue_price,
                    "below_issue_price": bool(close < issue_price) if pd.notna(issue_price) else None,
                    "cumulative_return_from_open": cumulative,
                    "issue_price_return": close / issue_price - 1.0 if pd.notna(issue_price) and issue_price > 0 else np.nan,
                    "hsi_return": hsi_return,
                    "excess_hsi_return": cumulative - hsi_return if pd.notna(hsi_return) else np.nan,
                    "industry_return": industry_return,
                    "excess_industry_return": cumulative - industry_return if pd.notna(industry_return) else np.nan,
                    "max_drawdown_from_open": max_drawdown,
                    "realized_volatility": realized_vol,
                    "turnover_change": turnover_change,
                    "price_source": str(EOD_CSV.relative_to(Path(__file__).resolve().parents[2])),
                }
            )
    output = pd.DataFrame(rows).sort_values(["listing_date", "stock_code", "trading_day"])
    output.to_csv(OUT, index=False, encoding="utf-8-sig")
    write_sidecar(
        OUT,
        source=f"{EOD_CSV} + hsi.csv + hsics_index_daily.csv",
        note=(
            "D5..D60 every five trading days; primary anchor=issue price; "
            "secondary return base=first trading day open; point-in-time through checkpoint close"
        ),
    )
    print(f"rows={len(output)} stocks={output['stock_code'].nunique()} out={OUT}")


if __name__ == "__main__":
    main()

