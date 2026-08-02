"""把认购倍数合并进 ipo_sentiment_features.csv。

优先级：
1. 致富/新股渔夫 subscription_multiples.csv → subscription_multiple（整体超额）
2. 万得 ipo_listing_stats.csv：
   - public_offer_multiple（网上）→ 填补 subscription_multiple 缺口；并写入 public_offer_multiple
   - international_placing_multiple（网下）→ international_placing_multiple
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import numpy as np

from config import DERIVED_DIR, DATA_DIR, WIND_DIR, write_sidecar

SUB_CSV = DATA_DIR / "external" / "ipo" / "subscription_multiples.csv"
WIND_IPO = WIND_DIR / "ipo_listing_stats.csv"
FEAT_CSV = DERIVED_DIR / "ipo_sentiment_features.csv"


def main():
    feat = pd.read_csv(FEAT_CSV, dtype={"stock_code": str})
    feat["stock_code"] = feat["stock_code"].astype(str).str.zfill(5)

    for c in ("subscription_multiple", "international_placing_multiple",
              "public_offer_multiple", "subscription_source"):
        if c in feat.columns:
            feat = feat.drop(columns=[c])

    feat["subscription_multiple"] = np.nan
    feat["international_placing_multiple"] = np.nan
    feat["public_offer_multiple"] = np.nan
    feat["subscription_source"] = pd.NA

    if SUB_CSV.exists():
        sub = pd.read_csv(SUB_CSV, dtype={"stock_code": str})
        sub["stock_code"] = sub["stock_code"].astype(str).str.zfill(5)
        keep = sub[["stock_code", "public_subscription_multiple",
                    "international_placing_multiple", "source"]].drop_duplicates(
                        "stock_code", keep="last")
        m = feat[["stock_code"]].merge(keep, on="stock_code", how="left")
        feat["subscription_multiple"] = m["public_subscription_multiple"].values
        # chiefgroup 国配若有
        feat["international_placing_multiple"] = m["international_placing_multiple"].values
        feat["subscription_source"] = m["source"].values
        print(f"chief/yufu subscription: {feat['subscription_multiple'].notna().sum()}")
    else:
        print(f"WARN missing {SUB_CSV}")

    if WIND_IPO.exists():
        w = pd.read_csv(WIND_IPO, dtype={"stock_code": str})
        w["stock_code"] = w["stock_code"].astype(str).str.zfill(5)
        w = w.drop_duplicates("stock_code", keep="last").set_index("stock_code")
        pub = feat["stock_code"].map(w["public_offer_multiple"] if "public_offer_multiple" in w.columns else {})
        intl = feat["stock_code"].map(
            w["international_placing_multiple"] if "international_placing_multiple" in w.columns else {})
        feat["public_offer_multiple"] = pub.values
        # 国配：万得网下优先补全
        feat["international_placing_multiple"] = feat["international_placing_multiple"].fillna(intl)
        # 超额认购缺口：用网上倍数填补
        fill_mask = feat["subscription_multiple"].isna() & pub.notna()
        feat.loc[fill_mask, "subscription_multiple"] = pub[fill_mask].values
        feat.loc[fill_mask, "subscription_source"] = "wind_public_offer"
        # 已有致富主源的，source 保持；若仅有万得国配
        only_wind = feat["subscription_source"].isna() & (
            feat["public_offer_multiple"].notna() | feat["international_placing_multiple"].notna())
        feat.loc[only_wind, "subscription_source"] = "wind"
        print(f"after Wind: subscription={feat['subscription_multiple'].notna().sum()} "
              f"public={feat['public_offer_multiple'].notna().sum()} "
              f"intl={feat['international_placing_multiple'].notna().sum()}")
    else:
        print(f"WARN missing {WIND_IPO}; run ingest_wind_exports.py")

    cols = list(feat.columns)
    for c in ("subscription_multiple", "public_offer_multiple",
              "international_placing_multiple", "subscription_source"):
        if c in cols:
            cols.remove(c)
    insert_at = next((i for i, c in enumerate(cols) if c.startswith("outcome_")), len(cols))
    for j, c in enumerate(["subscription_multiple", "public_offer_multiple",
                           "international_placing_multiple", "subscription_source"]):
        cols.insert(insert_at + j, c)
    feat = feat[cols]
    feat.to_csv(FEAT_CSV, index=False, encoding="utf-8-sig")
    hit = feat["subscription_multiple"].notna().sum()
    write_sidecar(FEAT_CSV,
                  source="features + subscription_multiples + wind/ipo_listing_stats",
                  note=f"subscription_multiple {hit}/{len(feat)}; "
                       f"public_offer={feat['public_offer_multiple'].notna().sum()}; "
                       f"intl={feat['international_placing_multiple'].notna().sum()}")
    print(f"done subscription_multiple {hit}/{len(feat)} ({hit/len(feat):.1%})")


if __name__ == "__main__":
    main()
