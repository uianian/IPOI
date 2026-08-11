#!/usr/bin/env python3
"""从 IPO 目录中鉴别生物科技/18A 公司，按年份×上市后表现分层抽样 30 份，并复制 PDF 到 dataset/18a。"""

from __future__ import annotations

import re
import shutil
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CATALOG = PROJECT_ROOT / "dataset_analysis/output/ipo_catalog_with_metrics.csv"
WIND_SLIM = PROJECT_ROOT / "dataset_analysis/output/wind_ede20260715_slim.csv"
DATASET_DIR = PROJECT_ROOT / "dataset"
DEST_DIR = DATASET_DIR / "18a"
OUTPUT_DIR = PROJECT_ROOT / "dataset_analysis/output"

CONCEPT_COL = "所属概念板块 [交易日期] 最新收盘日"
TARGET_N = 30
RANDOM_STATE = 42

# 生科核心概念（用于鉴别「未知」行业）
CORE_BIO_TAGS = ["未盈利生物科技", "生物医疗", "创新药", "抗肿瘤", "CXO", "CAR-T"]
CLEAR_NAME_KW = [
    "生物", "醫藥", "医药", "制药", "製藥", "药业", "藥業", "疫苗",
    "基因", "Biotech", "Pharma", "Therapeutics", "Bioscience", "Medicine",
]
# 仅 industry_coarse 命中、缺乏 Wind/命名支撑时的弱医疗（偏诊所/互联网医疗，非典型 18A 生科）
WEAK_ONLY_EXCLUDE = {
    "固生堂", "思派健康", "健康之路", "美中嘉和", "HYGIEIA GROUP", "佰泽医疗",
}

# 年份配额（合计 30）；表现配额在年内尽量覆盖
YEAR_QUOTA = {2020: 6, 2021: 6, 2022: 4, 2023: 4, 2024: 4, 2025: 6}
PERF_ORDER = ["暴跌", "暴涨", "破发/走弱", "平稳", "无行情"]


def wind_to_code5(w) -> str | None:
    m = re.match(r"^0*(\d+)\.HK$", str(w).strip(), re.I)
    return m.group(1).zfill(5) if m else None


def build_biotech_pool() -> pd.DataFrame:
    catalog = pd.read_csv(CATALOG, dtype={"stock_code": str}, encoding="utf-8-sig")
    catalog["stock_code"] = catalog["stock_code"].astype(str).str.zfill(5)

    wind = pd.read_csv(WIND_SLIM)
    wind["stock_code"] = wind["Wind代码"].map(wind_to_code5)
    wind = wind.dropna(subset=["stock_code"]).drop_duplicates("stock_code")

    df = catalog.merge(
        wind[["stock_code", CONCEPT_COL, "证券简称", "公司中文名称", "公司英文名称", "list_date"]],
        on="stock_code",
        how="left",
        suffixes=("", "_wind"),
    )

    rows = []
    for _, row in df.iterrows():
        concepts = str(row[CONCEPT_COL]) if pd.notna(row[CONCEPT_COL]) else ""
        name_parts = []
        for c in [
            "company_name", "company_display", "company_name_raw",
            "证券简称", "公司中文名称", "公司英文名称",
        ]:
            if c in row.index and pd.notna(row[c]):
                name_parts.append(str(row[c]))
        names = " ".join(name_parts)
        display = str(row.get("证券简称") or row.get("company_display") or row.get("company_name") or "")

        hit_core = [t for t in CORE_BIO_TAGS if t in concepts]
        clear_name = any(k.lower() in names.lower() for k in CLEAR_NAME_KW)
        suffix_b = any(m in names for m in ["－Ｂ", "-B", "－B", "－ＳＢ", "-SB", "－ＷＢ"])
        industry_hit = row.get("industry_coarse") == "生物科技/医药"
        is_18a_tag = "未盈利生物科技" in concepts

        is_biotech = bool(hit_core) or (suffix_b and (clear_name or is_18a_tag)) or (clear_name and industry_hit) or clear_name
        # 弱医疗兜底：仅靠 industry_coarse、无 Wind 核心标签且无 -B/生科命名 → 排除
        if industry_hit and not hit_core and not suffix_b and not clear_name:
            is_biotech = False
        if display in WEAK_ONLY_EXCLUDE and not is_18a_tag and "生物" not in names and "藥" not in names and "药" not in names:
            is_biotech = False
        # HYGIEIA / 固生堂等：industry_coarse 误标
        if not hit_core and not suffix_b and display in WEAK_ONLY_EXCLUDE:
            is_biotech = False

        if not is_biotech:
            continue

        reasons = []
        if is_18a_tag:
            reasons.append("wind:未盈利生物科技")
        other_tags = [t for t in hit_core if t != "未盈利生物科技"]
        if other_tags:
            reasons.append("wind:" + ",".join(other_tags))
        if suffix_b:
            reasons.append("suffix_B/18A命名")
        if clear_name:
            reasons.append("名称关键词")
        if industry_hit:
            reasons.append("industry_coarse")

        rows.append({
            "stock_code": row["stock_code"],
            "windcode": row.get("windcode"),
            "company_display": display,
            "company_name_pdf": row.get("company_display") or row.get("company_name"),
            "company_name_cn": row.get("公司中文名称"),
            "list_date_pdf": row.get("list_date"),
            "list_date_wind": row.get("list_date_wind"),
            "list_year": int(row["list_year"]),
            "performance_class": row.get("performance_class") or "无行情",
            "day1_return": row.get("day1_return"),
            "day5_return": row.get("day5_return"),
            "day20_return": row.get("day20_return"),
            "is_unprofitable_proxy": bool(row.get("is_unprofitable_proxy")),
            "is_18a_unprofit_bio": bool(is_18a_tag or suffix_b),
            "wind_core_tags": ",".join(hit_core),
            "biotech_reason": ";".join(reasons),
            "industry_coarse": row.get("industry_coarse"),
            "page_count": row.get("page_count"),
            "pdf_filename": row.get("pdf_filename"),
            "pdf_path": row.get("pdf_path"),
            "pdf_path_relative": row.get("pdf_path_relative"),
            "folder_year": row.get("folder_year"),
        })

    pool = pd.DataFrame(rows).drop_duplicates("stock_code")
    return pool.sort_values(["list_year", "performance_class", "stock_code"]).reset_index(drop=True)


def _add_sort_keys(df: pd.DataFrame) -> pd.DataFrame:
    """抽样优先级：18A 标签 > 极端表现 > 有 Wind 标签 > 页数适中。"""
    out = df.copy()
    out["_a18"] = (~out["is_18a_unprofit_bio"].astype(bool)).astype(int)
    out["_extreme"] = out["performance_class"].map(
        lambda p: 0 if p in ("暴跌", "暴涨", "破发/走弱") else 1
    )
    out["_wind"] = out["wind_core_tags"].fillna("").eq("").astype(int)
    out["_pages"] = (out["page_count"].fillna(600) - 600).abs()
    return out


def stratified_sample(pool: pd.DataFrame, n: int = TARGET_N) -> pd.DataFrame:
    selected = []
    used = set()
    sort_cols = ["_a18", "_extreme", "_wind", "_pages", "stock_code"]

    # 第一轮：按年份配额，年内按表现轮转覆盖
    for year, quota in YEAR_QUOTA.items():
        year_df = _add_sort_keys(pool[pool["list_year"] == year])
        if year_df.empty:
            continue
        by_perf = {
            p: year_df[year_df["performance_class"] == p].sort_values(sort_cols)
            for p in PERF_ORDER
        }
        picks = []
        while len(picks) < quota:
            progressed = False
            for p in PERF_ORDER:
                sub = by_perf[p]
                avail = sub[~sub["stock_code"].isin(used | {x["stock_code"] for x in picks})]
                if avail.empty:
                    continue
                picks.append(avail.iloc[0].to_dict())
                progressed = True
                if len(picks) >= quota:
                    break
            if not progressed:
                break
        for row in picks:
            row["sample_reason"] = (
                f"年份配额:{year}|表现:{row['performance_class']}|{row['biotech_reason']}"
            )
            selected.append(row)
            used.add(row["stock_code"])

    # 第二轮：补足到 n，优先补稀缺表现
    if len(selected) < n:
        perf_counts = defaultdict(int)
        for r in selected:
            perf_counts[r["performance_class"]] += 1
        rest = _add_sort_keys(pool[~pool["stock_code"].isin(used)])
        rest["_perf_rank"] = rest["performance_class"].map(lambda p: perf_counts.get(p, 0))
        rest = rest.sort_values(["_perf_rank"] + sort_cols)
        for _, row in rest.iterrows():
            if len(selected) >= n:
                break
            d = row.to_dict()
            d["sample_reason"] = (
                f"补足配额|表现:{d['performance_class']}|{d['biotech_reason']}"
            )
            selected.append(d)
            used.add(d["stock_code"])

    sample = pd.DataFrame(selected).head(n)
    # 去掉内部排序列
    drop_cols = [c for c in sample.columns if c.startswith("_")]
    sample = sample.drop(columns=drop_cols, errors="ignore")
    sample["stock_code"] = sample["stock_code"].astype(str).str.zfill(5)
    return sample.reset_index(drop=True)


def copy_pdfs(sample: pd.DataFrame, dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    # 清空旧 PDF（保留清单类文件稍后覆盖）
    for old in dest.glob("*.pdf"):
        old.unlink()

    pdf_index: dict[str, list[Path]] = {}
    for pdf in DATASET_DIR.rglob("*.pdf"):
        if pdf.parent.name in {"18a", "samples", "sample"}:
            continue
        m = re.match(r"^(\d{5})_", pdf.name)
        if m:
            pdf_index.setdefault(m.group(1), []).append(pdf)

    copied, missing = [], []
    manifest = []
    for _, row in sample.iterrows():
        code = row["stock_code"]
        src = None
        preferred = row.get("pdf_filename")
        cands = pdf_index.get(code, [])
        if preferred and cands:
            for p in cands:
                if p.name == preferred:
                    src = p
                    break
        if src is None and cands:
            src = sorted(cands)[0]
        if src is None and pd.notna(row.get("pdf_path")):
            p = Path(str(row["pdf_path"]))
            if p.is_file():
                src = p
        if src is None:
            missing.append(code)
            continue
        dst = dest / src.name
        shutil.copy2(src, dst)
        copied.append(src.name)
        manifest.append({
            **{k: row.get(k) for k in sample.columns},
            "source_pdf_path": str(src),
            "dest_pdf_path": str(dst),
        })

    man_df = pd.DataFrame(manifest)
    man_df.to_csv(dest / "sample_manifest.csv", index=False, encoding="utf-8-sig")
    return {"copied": len(copied), "missing": missing, "manifest_rows": len(man_df)}


def _crosstab_md(df: pd.DataFrame, row: str, col: str) -> str:
    ct = pd.crosstab(df[row], df[col])
    try:
        return ct.to_markdown()
    except Exception:
        header = "| " + row + " | " + " | ".join(map(str, ct.columns)) + " |"
        sep = "|---|" + "|".join(["---"] * len(ct.columns)) + "|"
        body = [
            "| " + str(idx) + " | " + " | ".join(str(v) for v in vals) + " |"
            for idx, vals in zip(ct.index, ct.values)
        ]
        return "\n".join([header, sep] + body)


def write_report(pool: pd.DataFrame, sample: pd.DataFrame) -> str:
    lines = [
        "# 生物科技 / 18A 分层抽样报告",
        "",
        f"> 生成时间：{pd.Timestamp.now().strftime('%Y-%m-%dT%H:%M:%S')}",
        "",
        "## 鉴别规则",
        "",
        "因 `industry_coarse=未知` 占绝大多数，生物科技鉴别采用多信号并集：",
        "1. **万得概念板块**：`未盈利生物科技` / `生物医疗` / `创新药` / `抗肿瘤` / `CXO` / `CAR-T`",
        "2. **18A 命名**：股票简称含 `-B` / `－Ｂ` / `－ＳＢ` 等",
        "3. **名称关键词**：生物 / 医药 / 制药 / Biotech / Pharma 等",
        "4. 排除仅靠粗行业、无 Wind/命名支撑的弱医疗样本（如固生堂、思派健康等）",
        "",
        "## 候选池",
        "",
        f"- 鉴别为生物科技：**{len(pool)}** 家（PDF 目录交集）",
        f"- 其中 18A/未盈利风格（Wind 标签或 -B 后缀）：**{int(pool['is_18a_unprofit_bio'].sum())}** 家",
        "",
        "### 候选池：年份 × 上市后表现",
        "",
        _crosstab_md(pool, "list_year", "performance_class"),
        "",
        "## 抽样结果（目标 30）",
        "",
        f"- 实际抽出：**{len(sample)}** 家",
        f"- PDF 输出目录：`dataset/18a/`",
        "",
        "### 样本：年份 × 表现",
        "",
        _crosstab_md(sample, "list_year", "performance_class"),
        "",
        "### 样本清单",
        "",
        "| 代码 | 简称 | 年份 | 表现 | 18A | Wind核心标签 | 抽样理由 |",
        "|------|------|------|------|-----|--------------|----------|",
    ]
    for _, r in sample.sort_values(["list_year", "performance_class", "stock_code"]).iterrows():
        lines.append(
            f"| {r['stock_code']} | {r['company_display']} | {r['list_year']} | "
            f"{r['performance_class']} | {bool(r['is_18a_unprofit_bio'])} | "
            f"{r.get('wind_core_tags','')} | {r.get('sample_reason','')} |"
        )
    lines += [
        "",
        "## 产出文件",
        "",
        "- `dataset_analysis/output/biotech_pool.csv` — 全量生科候选池",
        "- `dataset_analysis/output/biotech_18a_sample_list.csv` — 30 份抽样清单",
        "- `dataset/18a/*.pdf` — 抽样招股书",
        "- `dataset/18a/sample_manifest.csv` — 复制清单",
        "",
    ]
    text = "\n".join(lines)
    path = OUTPUT_DIR / "biotech_18a_sample_report.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pool = build_biotech_pool()
    pool.to_csv(OUTPUT_DIR / "biotech_pool.csv", index=False, encoding="utf-8-sig")

    sample = stratified_sample(pool, TARGET_N)
    export_cols = [
        "stock_code", "windcode", "company_display", "company_name_cn",
        "list_year", "list_date_pdf", "list_date_wind", "performance_class",
        "day1_return", "day5_return", "day20_return",
        "is_18a_unprofit_bio", "is_unprofitable_proxy", "wind_core_tags",
        "biotech_reason", "page_count", "pdf_filename", "pdf_path_relative",
        "sample_reason",
    ]
    sample[[c for c in export_cols if c in sample.columns]].to_csv(
        OUTPUT_DIR / "biotech_18a_sample_list.csv", index=False, encoding="utf-8-sig"
    )

    copy_stats = copy_pdfs(sample, DEST_DIR)
    report_path = write_report(pool, sample)

    print(f"生物科技候选池: {len(pool)}")
    print("候选池 year×perf:")
    print(pd.crosstab(pool["list_year"], pool["performance_class"]))
    print(f"\n抽样: {len(sample)}")
    print(pd.crosstab(sample["list_year"], sample["performance_class"]))
    print(f"\nPDF 复制: {copy_stats['copied']}/{len(sample)} → {DEST_DIR}")
    if copy_stats["missing"]:
        print("缺失:", copy_stats["missing"])
    print(f"报告: {report_path}")
    print(f"清单: {OUTPUT_DIR / 'biotech_18a_sample_list.csv'}")


if __name__ == "__main__":
    main()
