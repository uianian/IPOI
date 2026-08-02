"""行业映射：优先万得 HSICS（马宝灵导出），EDE 概念规则兜底。

输入：
- data/external/wind/hsics_security_industry.csv（ingest_wind_exports.py）
- dataset_analysis/output/wind_ede20260715_slim.csv
- dataset_analysis/output/ipo_catalog_with_metrics.csv

输出：
- data/derived/industry_universe.csv
- data/derived/ipo_industry_map.csv
  新增：hsics_l1_name, hsics_index_code, hsics_index_name, industry_source
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from config import (
    EDE_SLIM_CSV, IPO_CATALOG_CSV, DERIVED_DIR, WIND_DIR,
    INDUSTRY_RULES, INDUSTRY_FALLBACK,
    HSICS_L1_TO_COARSE, HSICS_L1_TO_INDEX,
    ensure_dirs, write_sidecar,
)

CONCEPT_COL = "所属概念板块 [交易日期] 最新收盘日"


def norm_code(x):
    x = str(x).strip().upper().replace(".HK", "")
    m = re.sub(r"\D", "", x)
    return f"{int(m):04d}.HK" if m else str(x)


def map_industry_concepts(concepts):
    if pd.isna(concepts):
        return INDUSTRY_FALLBACK
    text = str(concepts)
    for name, keys in INDUSTRY_RULES:
        if any(k in text for k in keys):
            return name
    return INDUSTRY_FALLBACK


def main():
    ensure_dirs()
    ede = pd.read_csv(EDE_SLIM_CSV)
    ede["wind_norm"] = ede["Wind代码"].map(norm_code)
    ede["industry_concept"] = ede[CONCEPT_COL].map(map_industry_concepts)

    hsics_path = WIND_DIR / "hsics_security_industry.csv"
    if hsics_path.exists():
        hs = pd.read_csv(hsics_path, dtype={"stock_code": str})
        hs["wind_norm"] = hs["windcode"].map(norm_code)
        hs["industry_hsics"] = hs["hsics_l1_name"].map(
            lambda x: HSICS_L1_TO_COARSE.get(x, INDUSTRY_FALLBACK) if pd.notna(x) else None)
        hs["hsics_index_code"] = hs["hsics_l1_name"].map(
            lambda x: HSICS_L1_TO_INDEX.get(x, (None, None))[0] if pd.notna(x) else None)
        hs["hsics_index_name"] = hs["hsics_l1_name"].map(
            lambda x: HSICS_L1_TO_INDEX.get(x, (None, None))[1] if pd.notna(x) else None)
    else:
        print("WARN: missing hsics_security_industry.csv — run ingest_wind_exports.py")
        hs = pd.DataFrame(columns=["wind_norm", "industry_hsics", "hsics_l1_name",
                                   "hsics_index_code", "hsics_index_name"])

    universe = ede[["wind_norm", "证券简称", "list_date", "上市板",
                    "industry_concept", CONCEPT_COL]].rename(
        columns={"证券简称": "name", "list_date": "ede_list_date",
                 "上市板": "board", CONCEPT_COL: "concepts"})
    universe = universe.merge(
        hs[["wind_norm", "industry_hsics", "hsics_l1_name",
            "hsics_index_code", "hsics_index_name"]].drop_duplicates("wind_norm"),
        on="wind_norm", how="left")
    # 优先 HSICS
    universe["industry"] = universe["industry_hsics"].where(
        universe["industry_hsics"].notna() & (universe["industry_hsics"] != INDUSTRY_FALLBACK),
        universe["industry_concept"])
    universe["industry"] = universe["industry"].fillna(INDUSTRY_FALLBACK)
    universe["industry_source"] = "hsics"
    universe.loc[universe["industry_hsics"].isna()
                 | (universe["industry_hsics"] == INDUSTRY_FALLBACK),
                 "industry_source"] = universe.loc[
        universe["industry_hsics"].isna()
        | (universe["industry_hsics"] == INDUSTRY_FALLBACK),
        "industry"].map(lambda x: "concept" if x != INDUSTRY_FALLBACK else "fallback")
    # refine: if hsics gave non-其他, source=hsics
    universe.loc[universe["industry_hsics"].notna()
                 & (universe["industry_hsics"] != INDUSTRY_FALLBACK),
                 "industry_source"] = "hsics"
    universe.loc[universe["industry_source"] == "hsics", "industry"] = universe.loc[
        universe["industry_source"] == "hsics", "industry_hsics"]

    out_u = DERIVED_DIR / "industry_universe.csv"
    universe.to_csv(out_u, index=False, encoding="utf-8-sig")
    write_sidecar(out_u, source=f"{hsics_path} + {EDE_SLIM_CSV}",
                  note="HSICS L1 preferred; EDE concept rules as fallback")
    print("universe industry:")
    print(universe["industry"].value_counts().to_string())
    print("source:", universe["industry_source"].value_counts().to_string())

    cat = pd.read_csv(IPO_CATALOG_CSV, dtype={"stock_code": str})
    cat["stock_code"] = cat["stock_code"].astype(str).str.zfill(5)
    cat["wind_norm"] = cat["windcode"].map(norm_code)
    m = cat[["stock_code", "windcode", "wind_norm", "company_display",
             "list_date", "first_trade_date"]].merge(
        universe[["wind_norm", "ede_list_date", "industry", "industry_source",
                  "hsics_l1_name", "hsics_index_code", "hsics_index_name", "concepts"]],
        on="wind_norm", how="left")
    m["industry"] = m["industry"].fillna(INDUSTRY_FALLBACK)
    m["industry_source"] = m["industry_source"].fillna("fallback")
    m["needs_manual_label"] = m["industry"] == INDUSTRY_FALLBACK
    out_i = DERIVED_DIR / "ipo_industry_map.csv"
    m.to_csv(out_i, index=False, encoding="utf-8-sig")
    write_sidecar(out_i, source=f"HSICS + EDE + {IPO_CATALOG_CSV}",
                  note="565 IPOs; hsics_index_code used for official industry returns")
    print("\nIPO industry:")
    print(m["industry"].value_counts().to_string())
    print("with hsics_index_code", m["hsics_index_code"].notna().sum())
    print("needs_manual_label", m["needs_manual_label"].sum())


if __name__ == "__main__":
    main()
