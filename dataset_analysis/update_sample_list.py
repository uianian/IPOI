#!/usr/bin/env python3
"""从已有 ipo_catalog 快速重算抽样清单与报告（跳过 PDF 全量体检）。"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_dataset_analysis import (
    OUTPUT_DIR,
    PROJECT_ROOT,
    resolve_company_names,
    stratified_sample,
    summarize_pdf_health,
    summarize_structured,
    to_relative_path,
    write_markdown_report,
)

CATALOG = OUTPUT_DIR / "ipo_catalog_with_metrics.csv"
HEALTH = OUTPUT_DIR / "pdf_health_check.csv"

SAMPLE_EXPORT_COLS = [
    "stock_code", "windcode", "windcode_rule", "company_name", "company_display",
    "list_date", "list_year", "performance_class", "is_unprofitable_proxy",
    "day1_return", "day5_return", "page_count", "likely_scanned",
    "pdf_filename", "pdf_path_relative", "sample_reason",
]


def fix_company_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "company_name_raw" not in df.columns:
        df["company_name_raw"] = df["company_name"]

    def apply_fix(row):
        clean, raw = resolve_company_names(str(row["stock_code"]).zfill(5), row["company_name_raw"])
        return pd.Series({"company_name": clean, "company_display": clean, "company_name_raw": raw})

    fixed = df.apply(apply_fix, axis=1)
    df["company_name"] = fixed["company_name"]
    df["company_display"] = fixed["company_display"]
    df["company_name_raw"] = fixed["company_name_raw"]
    if "pdf_path" in df.columns:
        df["pdf_path_relative"] = df["pdf_path"].map(to_relative_path)
    return df


def main():
    df = pd.read_csv(CATALOG, dtype={"stock_code": str})
    df["stock_code"] = df["stock_code"].str.zfill(5)
    df = fix_company_names(df)
    df.to_csv(CATALOG, index=False, encoding="utf-8-sig")

    health_df = pd.read_csv(HEALTH)
    sample_df = stratified_sample(df)
    struct_summary = summarize_structured(df)
    health_summary = summarize_pdf_health(health_df)

    sample_export = sample_df[[c for c in SAMPLE_EXPORT_COLS if c in sample_df.columns]]
    sample_export.to_csv(OUTPUT_DIR / "sample_list.csv", index=False, encoding="utf-8-sig")
    report = write_markdown_report(struct_summary, health_summary, sample_df, df)
    (OUTPUT_DIR / "dataset_analysis_report.md").write_text(report, encoding="utf-8")

    print("样本数:", len(sample_df))
    print("\n2025 样本公司名:")
    sub = sample_df[sample_df["list_year"] == 2025][["stock_code", "company_name", "company_display"]]
    print(sub.drop_duplicates().to_string(index=False))


if __name__ == "__main__":
    main()
