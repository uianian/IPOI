#!/usr/bin/env python3
"""构建评测测试集 test_set_v1：年×表现分层、holdout 优先、恒生行业标签、解析复用映射。"""

from __future__ import annotations

import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DATASET_DIR = PROJECT_ROOT / "dataset"
CATALOG = OUTPUT_DIR / "ipo_catalog_with_metrics.csv"
WIND_SLIM = OUTPUT_DIR / "wind_ede20260715_slim.csv"
HS_XLSX = DATASET_DIR / "wind" / "恒生行业分类.xlsx"
SAMPLE_LIST = OUTPUT_DIR / "sample_list.csv"
BIO_LIST = OUTPUT_DIR / "biotech_18a_sample_list.csv"
PARSE_18A = PROJECT_ROOT / "pdf_parsing" / "output" / "18a_batch"
PARSE_SAMPLES = PROJECT_ROOT / "pdf_parsing" / "output" / "samples_batch"
DEST_TEST = DATASET_DIR / "test"

TARGET_N = 48
PER_CELL = 2  # per (year, perf)
YEARS = list(range(2020, 2026))
PERFS = ["平稳", "破发/走弱", "暴跌", "暴涨"]
RANDOM_STATE = 42
BIO_FLOOR = 15
HOLD_OUT_FLOOR = 24
HS_L1_CAP = 0.40
CONCEPT_COL = "所属概念板块 [交易日期] 最新收盘日"
HS_NAME_COL = "所属恒生行业名称\n[行业级别] 全部明细"

STOCK_CODE_RE = re.compile(r"^(\d{5})_")


def wind_to_code5(w) -> Optional[str]:
    m = re.match(r"^0*(\d+)\.HK$", str(w).strip(), re.I)
    return m.group(1).zfill(5) if m else None


def parse_hs_levels(s) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    text = str(s) if pd.notna(s) else ""
    parts = [p.strip() for p in re.findall(r"([^()-]+)\(HS\)", text)]
    l1 = parts[0] if parts else None
    l2 = parts[1] if len(parts) > 1 else None
    l3 = parts[2] if len(parts) > 2 else None
    return l1, l2, l3


def to_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def build_parse_index(batch_dir: Path) -> Dict[str, Path]:
    """stock_code -> directory containing full_parse.json."""
    index: Dict[str, Path] = {}
    if not batch_dir.is_dir():
        return index
    for fp in batch_dir.rglob("full_parse.json"):
        parent = fp.parent
        # skip shard dirs
        if parent.name.startswith("_shard"):
            continue
        m = STOCK_CODE_RE.match(parent.name)
        if not m:
            continue
        code = m.group(1)
        # prefer non-reparse dirs
        if code not in index or "reparse" not in str(parent):
            index[code] = parent
    return index


def build_pdf_index(dataset_root: Path) -> Dict[str, List[Path]]:
    index: Dict[str, List[Path]] = {}
    skip_parents = {"test", "sample", "samples", "18a"}
    for pdf in dataset_root.rglob("*.pdf"):
        # allow searching year folders; skip dest/test and nested sample dumps when indexing source
        if pdf.parent.name in skip_parents and pdf.parent.parent == dataset_root:
            continue
        if pdf.parent.name == "test":
            continue
        m = STOCK_CODE_RE.match(pdf.name)
        if not m:
            continue
        index.setdefault(m.group(1), []).append(pdf)
    return index


def choose_pdf(cands: List[Path], preferred: Optional[str] = None) -> Optional[Path]:
    if not cands:
        return None
    if preferred:
        for p in cands:
            if p.name == preferred:
                return p
    return sorted(cands, key=lambda p: str(p))[0]


def load_universe() -> pd.DataFrame:
    catalog = pd.read_csv(CATALOG, dtype={"stock_code": str}, encoding="utf-8-sig")
    catalog["stock_code"] = catalog["stock_code"].astype(str).str.zfill(5)

    hs = pd.read_excel(HS_XLSX)
    hs["stock_code"] = hs["证券代码"].map(wind_to_code5)
    levels = hs[HS_NAME_COL].map(parse_hs_levels)
    hs["hs_l1"] = levels.map(lambda t: t[0])
    hs["hs_l2"] = levels.map(lambda t: t[1])
    hs["hs_l3"] = levels.map(lambda t: t[2])
    hs = hs.dropna(subset=["stock_code"]).drop_duplicates("stock_code")

    wind = pd.read_csv(WIND_SLIM)
    wind["stock_code"] = wind["Wind代码"].map(wind_to_code5)
    wind = wind.dropna(subset=["stock_code"]).drop_duplicates("stock_code")

    df = catalog.merge(
        hs[["stock_code", "hs_l1", "hs_l2", "hs_l3"]],
        on="stock_code",
        how="left",
    )
    df = df.merge(
        wind[["stock_code", CONCEPT_COL, "证券简称"]],
        on="stock_code",
        how="left",
    )

    def issuer_bucket(row) -> str:
        concepts = str(row[CONCEPT_COL]) if pd.notna(row[CONCEPT_COL]) else ""
        hs_l1 = row.get("hs_l1")
        hs_l2 = row.get("hs_l2")
        if "未盈利生物科技" in concepts:
            return "18a_unprofit"
        if hs_l2 == "药品及生物科技":
            return "biotech_pharma"
        if hs_l1 == "医疗保健业":
            return "healthcare_other"
        if pd.isna(hs_l1):
            return "unknown"
        return "general"

    df["issuer_bucket"] = df.apply(issuer_bucket, axis=1)
    df["is_biotech_quota"] = df["issuer_bucket"].isin(["18a_unprofit", "biotech_pharma"])

    display = []
    for _, r in df.iterrows():
        name = r.get("证券简称") if pd.notna(r.get("证券简称")) else r.get("company_display")
        if pd.isna(name) or not str(name).strip():
            name = r.get("company_name")
        display.append(str(name) if pd.notna(name) else r["stock_code"])
    df["company_display_final"] = display

    # exclude no market
    df = df[df["performance_class"].isin(PERFS)].copy()
    df["list_year"] = df["list_year"].astype(int)
    return df.reset_index(drop=True)


def load_code_sets() -> Tuple[Set[str], Set[str]]:
    samples = pd.read_csv(SAMPLE_LIST, dtype={"stock_code": str}, encoding="utf-8-sig")
    samples["stock_code"] = samples["stock_code"].astype(str).str.zfill(5)
    bio = pd.read_csv(BIO_LIST, dtype={"stock_code": str}, encoding="utf-8-sig")
    bio["stock_code"] = bio["stock_code"].astype(str).str.zfill(5)
    return set(samples["stock_code"]), set(bio["stock_code"])


def stratified_sample(universe: pd.DataFrame, samples_codes: Set[str], bio_codes: Set[str]) -> pd.DataFrame:
    rng = RANDOM_STATE
    used: Set[str] = set()
    selected: List[dict] = []

    def pool_for(year: int, perf: str, prefer: str) -> pd.DataFrame:
        base = universe[
            (universe["list_year"] == year)
            & (universe["performance_class"] == perf)
            & (~universe["stock_code"].isin(used))
        ]
        if prefer == "holdout_samples":
            sub = base[base["stock_code"].isin(samples_codes - bio_codes)]
        elif prefer == "holdout_new":
            sub = base[~base["stock_code"].isin(samples_codes | bio_codes)]
        elif prefer == "dev_18a":
            sub = base[base["stock_code"].isin(bio_codes)]
        elif prefer == "any_samples":
            sub = base[base["stock_code"].isin(samples_codes)]
        else:
            sub = base
        return sub.sample(frac=1.0, random_state=rng) if len(sub) else sub

    def pick_one(year: int, perf: str) -> Optional[dict]:
        # holdout first: samples (not in 18a) -> new -> then 18a as dev_seen
        for prefer, role, source in [
            ("holdout_samples", "holdout", "samples"),
            ("holdout_new", "holdout", "new"),
            ("dev_18a", "dev_seen", "18a"),
            ("any_samples", "holdout", "samples"),  # samples that overlap 18a already handled; remaining samples
            ("all", "holdout", "new"),
        ]:
            if prefer == "all":
                sub = universe[
                    (universe["list_year"] == year)
                    & (universe["performance_class"] == perf)
                    & (~universe["stock_code"].isin(used))
                ]
                sub = sub.sample(frac=1.0, random_state=rng) if len(sub) else sub
            else:
                sub = pool_for(year, perf, prefer)
            if sub.empty:
                continue
            row = sub.iloc[0].to_dict()
            # fix source/role for fallbacks
            code = row["stock_code"]
            if code in bio_codes:
                row["reuse_source"] = "18a"
                row["eval_role"] = "dev_seen"
            elif code in samples_codes:
                row["reuse_source"] = "samples"
                row["eval_role"] = "holdout" if code not in bio_codes else "dev_seen"
            else:
                row["reuse_source"] = "new"
                row["eval_role"] = "holdout"
            row["sample_reason"] = f"年份配额:{year}|表现:{perf}|source:{row['reuse_source']}"
            return row
        return None

    # primary fill
    for year in YEARS:
        for perf in PERFS:
            for _ in range(PER_CELL):
                row = pick_one(year, perf)
                if row is None:
                    continue
                used.add(row["stock_code"])
                selected.append(row)

    # relax fill if short
    if len(selected) < TARGET_N:
        rest = universe[~universe["stock_code"].isin(used)].sample(
            frac=1.0, random_state=rng
        )
        for _, r in rest.iterrows():
            if len(selected) >= TARGET_N:
                break
            d = r.to_dict()
            code = d["stock_code"]
            if code in bio_codes:
                d["reuse_source"] = "18a"
                d["eval_role"] = "dev_seen"
            elif code in samples_codes:
                d["reuse_source"] = "samples"
                d["eval_role"] = "holdout"
            else:
                d["reuse_source"] = "new"
                d["eval_role"] = "holdout"
            d["sample_reason"] = f"quota_relax|表现:{d['performance_class']}|source:{d['reuse_source']}"
            selected.append(d)
            used.add(code)

    sample = pd.DataFrame(selected).head(TARGET_N).copy()

    # --- biotech floor ---
    def bio_count(df: pd.DataFrame) -> int:
        return int(df["is_biotech_quota"].sum())

    def replace_for_bio(sample: pd.DataFrame) -> pd.DataFrame:
        while bio_count(sample) < BIO_FLOOR:
            # candidates: biotech not used, prefer new holdout then 18a
            have = set(sample["stock_code"])
            cand = universe[
                universe["is_biotech_quota"] & ~universe["stock_code"].isin(have)
            ]
            if cand.empty:
                break
            # prefer same perf as a replaceable general row
            replaceable = sample[
                (~sample["is_biotech_quota"]) & (sample["eval_role"] == "holdout")
            ]
            if replaceable.empty:
                replaceable = sample[~sample["is_biotech_quota"]]
            if replaceable.empty:
                break
            # pick cand matching a replaceable cell if possible
            matched = None
            for _, rr in replaceable.iterrows():
                cell = cand[
                    (cand["list_year"] == rr["list_year"])
                    & (cand["performance_class"] == rr["performance_class"])
                ]
                if not cell.empty:
                    matched = (rr["stock_code"], cell.sample(1, random_state=rng).iloc[0])
                    break
            if matched is None:
                # any bio cand, replace any replaceable
                matched = (
                    replaceable.iloc[0]["stock_code"],
                    cand.sample(1, random_state=rng).iloc[0],
                )
            old_code, new_row = matched
            nd = new_row.to_dict()
            code = nd["stock_code"]
            if code in bio_codes:
                nd["reuse_source"] = "18a"
                nd["eval_role"] = "dev_seen"
            elif code in samples_codes:
                nd["reuse_source"] = "samples"
                nd["eval_role"] = "holdout" if code not in bio_codes else "dev_seen"
            else:
                nd["reuse_source"] = "new"
                nd["eval_role"] = "holdout"
            nd["sample_reason"] = f"biotech_floor_replace|{old_code}->{code}"
            sample = sample[sample["stock_code"] != old_code]
            sample = pd.concat([sample, pd.DataFrame([nd])], ignore_index=True)
        return sample

    sample = replace_for_bio(sample)

    # --- HS L1 cap: demote excess healthcare_other / general in dominant L1 ---
    def enforce_l1_cap(sample: pd.DataFrame) -> pd.DataFrame:
        for _ in range(20):
            vc = sample["hs_l1"].fillna("未匹配").value_counts(normalize=True)
            if vc.empty or vc.iloc[0] <= HS_L1_CAP:
                break
            top_l1 = vc.index[0]
            # only trim if top is 医疗保健业 and we have healthcare_other excess
            excess = sample[
                (sample["hs_l1"] == top_l1)
                & (sample["issuer_bucket"] == "healthcare_other")
            ]
            if excess.empty:
                # try general in that L1 (shouldn't for 医疗)
                excess = sample[
                    (sample["hs_l1"] == top_l1)
                    & (~sample["is_biotech_quota"])
                    & (sample["eval_role"] == "holdout")
                ]
            if excess.empty:
                break
            victim = excess.iloc[0]
            have = set(sample["stock_code"])
            repl = universe[
                (~universe["stock_code"].isin(have))
                & (universe["list_year"] == victim["list_year"])
                & (universe["performance_class"] == victim["performance_class"])
                & (universe["hs_l1"].fillna("") != top_l1)
            ]
            if repl.empty:
                repl = universe[
                    (~universe["stock_code"].isin(have))
                    & (universe["hs_l1"].fillna("") != top_l1)
                    & (~universe["is_biotech_quota"])
                ]
            if repl.empty:
                break
            nd = repl.sample(1, random_state=rng).iloc[0].to_dict()
            code = nd["stock_code"]
            if code in bio_codes:
                nd["reuse_source"] = "18a"
                nd["eval_role"] = "dev_seen"
            elif code in samples_codes:
                nd["reuse_source"] = "samples"
                nd["eval_role"] = "holdout"
            else:
                nd["reuse_source"] = "new"
                nd["eval_role"] = "holdout"
            nd["sample_reason"] = f"hs_l1_cap_replace|{victim['stock_code']}->{code}"
            sample = sample[sample["stock_code"] != victim["stock_code"]]
            sample = pd.concat([sample, pd.DataFrame([nd])], ignore_index=True)
            # re-apply bio floor if damaged
            sample = replace_for_bio(sample)
        return sample

    sample = enforce_l1_cap(sample)

    # --- holdout floor: if <24, try swap some 18a-only cells with new/samples same cell ---
    def enforce_holdout(sample: pd.DataFrame) -> pd.DataFrame:
        for _ in range(30):
            n_hold = int((sample["eval_role"] == "holdout").sum())
            if n_hold >= HOLD_OUT_FLOOR:
                break
            victims = sample[sample["eval_role"] == "dev_seen"]
            if victims.empty:
                break
            progressed = False
            for _, v in victims.iterrows():
                have = set(sample["stock_code"])
                repl = universe[
                    (~universe["stock_code"].isin(have))
                    & (universe["list_year"] == v["list_year"])
                    & (universe["performance_class"] == v["performance_class"])
                    & (~universe["stock_code"].isin(bio_codes))
                ]
                if repl.empty:
                    continue
                # prefer keeping biotech quota: if victim is biotech, replacement should be too if possible
                if v["is_biotech_quota"]:
                    bio_repl = repl[repl["is_biotech_quota"]]
                    if not bio_repl.empty:
                        repl = bio_repl
                    else:
                        continue  # don't sacrifice biotech for holdout if no alt
                nd = repl.sample(1, random_state=rng).iloc[0].to_dict()
                code = nd["stock_code"]
                nd["reuse_source"] = "samples" if code in samples_codes else "new"
                nd["eval_role"] = "holdout"
                nd["sample_reason"] = f"holdout_floor_replace|{v['stock_code']}->{code}"
                sample = sample[sample["stock_code"] != v["stock_code"]]
                sample = pd.concat([sample, pd.DataFrame([nd])], ignore_index=True)
                progressed = True
                break
            if not progressed:
                break
        sample = replace_for_bio(sample)
        return sample

    sample = enforce_holdout(sample)

    sample["stock_code"] = sample["stock_code"].astype(str).str.zfill(5)
    sample = sample.drop_duplicates("stock_code").head(TARGET_N).reset_index(drop=True)
    return sample


def attach_parse_and_copy(sample: pd.DataFrame) -> pd.DataFrame:
    parse_18a = build_parse_index(PARSE_18A)
    parse_samp = build_parse_index(PARSE_SAMPLES)
    pdf_index = build_pdf_index(DATASET_DIR)

    if DEST_TEST.exists():
        for old in DEST_TEST.glob("*.pdf"):
            old.unlink()
        for old in DEST_TEST.glob("sample_manifest.csv"):
            old.unlink()
    DEST_TEST.mkdir(parents=True, exist_ok=True)

    rows = []
    for _, r in sample.iterrows():
        code = r["stock_code"]
        preferred = r.get("pdf_filename") if pd.notna(r.get("pdf_filename")) else None
        legacy = r.get("pdf_path") if pd.notna(r.get("pdf_path")) else None
        src = choose_pdf(pdf_index.get(code, []), preferred)
        if src is None and legacy and Path(str(legacy)).is_file():
            src = Path(str(legacy))
        # also check 18a / samples folders
        if src is None:
            for folder in (DATASET_DIR / "18a", DATASET_DIR / "samples"):
                if folder.is_dir():
                    hit = choose_pdf(list(folder.glob(f"{code}_*.pdf")), preferred)
                    if hit:
                        src = hit
                        break

        parse_status = "need_parse"
        parse_dir = ""
        if code in parse_18a and (parse_18a[code] / "full_parse.json").is_file():
            parse_status = "reuse_18a"
            parse_dir = to_rel(parse_18a[code])
        elif code in parse_samp and (parse_samp[code] / "full_parse.json").is_file():
            parse_status = "reuse_samples"
            parse_dir = to_rel(parse_samp[code])
        elif r.get("reuse_source") in ("18a", "samples"):
            parse_status = "missing_parse"

        dest_pdf = ""
        if src is not None:
            dst = DEST_TEST / src.name
            shutil.copy2(src, dst)
            dest_pdf = to_rel(dst)

        rows.append(
            {
                "stock_code": code,
                "windcode": r.get("windcode"),
                "company_display": r.get("company_display_final") or r.get("company_display"),
                "list_year": r.get("list_year"),
                "list_date": r.get("list_date"),
                "performance_class": r.get("performance_class"),
                "day1_return": r.get("day1_return"),
                "day5_return": r.get("day5_return"),
                "hs_l1": r.get("hs_l1"),
                "hs_l2": r.get("hs_l2"),
                "hs_l3": r.get("hs_l3"),
                "issuer_bucket": r.get("issuer_bucket"),
                "is_biotech_quota": r.get("is_biotech_quota"),
                "reuse_source": r.get("reuse_source"),
                "eval_role": r.get("eval_role"),
                "sample_reason": r.get("sample_reason"),
                "page_count": r.get("page_count"),
                "pdf_filename": src.name if src else preferred,
                "pdf_path_relative": dest_pdf,
                "source_pdf_path": str(src) if src else "",
                "parse_status": parse_status,
                "parse_dir": parse_dir,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(DEST_TEST / "sample_manifest.csv", index=False, encoding="utf-8-sig")
    return out


def write_outputs(final: pd.DataFrame, universe: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export = final.copy()
    export.to_csv(OUTPUT_DIR / "test_set_v1.csv", index=False, encoding="utf-8-sig")

    need = final[final["parse_status"].isin(["need_parse", "missing_parse"])].copy()
    need_rows = []
    for _, r in need.iterrows():
        need_rows.append(
            {
                "stock_code": r["stock_code"],
                "company_display": r["company_display"],
                "reuse_source": r["reuse_source"],
                "eval_role": r["eval_role"],
                "parse_status": r["parse_status"],
                "pdf_path": r.get("source_pdf_path") or "",
                "pdf_path_in_test": r.get("pdf_path_relative") or "",
                "suggested_output": "pdf_parsing/output/test_batch",
            }
        )
    to_parse = pd.DataFrame(need_rows)
    to_parse.to_csv(OUTPUT_DIR / "to_parse_list.csv", index=False, encoding="utf-8-sig")

    # parse plan md
    n_reuse = int(final["parse_status"].isin(["reuse_18a", "reuse_samples"]).sum())
    n_need = int((final["parse_status"] == "need_parse").sum())
    n_miss = int((final["parse_status"] == "missing_parse").sum())
    plan_lines = [
        "# test_set_v1 解析计划",
        "",
        f"- 复用已有解析：{n_reuse}",
        f"- 需新解析 need_parse：{n_need}",
        f"- 旧池缺失 missing_parse：{n_miss}",
        "",
        "## 复用映射",
        "",
        "| 代码 | 来源 | parse_status | parse_dir |",
        "|------|------|--------------|-----------|",
    ]
    for _, r in final.sort_values("stock_code").iterrows():
        plan_lines.append(
            f"| {r['stock_code']} | {r['reuse_source']} | {r['parse_status']} | {r.get('parse_dir','')} |"
        )
    plan_lines += [
        "",
        "## 待解析列表",
        "",
        "见 `to_parse_list.csv`。建议命令（确认 GPU 后）：",
        "",
        "```bash",
        "cd pdf_parsing",
        "# 可将 to_parse 的 PDF 链到临时目录后：",
        "# batch_parse_samples.py --samples-dir <tmp> --limit N -o output/test_batch --rotate-mode none ...",
        "```",
        "",
    ]
    (OUTPUT_DIR / "test_set_v1_parse_plan.md").write_text(
        "\n".join(plan_lines), encoding="utf-8"
    )

    # main report
    def crosstab_md(df, a, b):
        ct = pd.crosstab(df[a], df[b])
        header = "| " + a + " | " + " | ".join(map(str, ct.columns)) + " |"
        sep = "|---|" + "|".join(["---"] * len(ct.columns)) + "|"
        body = [
            "| " + str(i) + " | " + " | ".join(str(x) for x in row) + " |"
            for i, row in zip(ct.index, ct.values)
        ]
        return "\n".join([header, sep] + body)

    bio_n = int(final["is_biotech_quota"].sum())
    hold_n = int((final["eval_role"] == "holdout").sum())
    l1_share = final["hs_l1"].fillna("未匹配").value_counts(normalize=True)
    top_l1 = l1_share.index[0] if len(l1_share) else ""
    top_pct = float(l1_share.iloc[0]) if len(l1_share) else 0.0

    lines = [
        "# 测试集 test_set_v1 报告",
        "",
        f"> random_state={RANDOM_STATE}；N={len(final)}",
        "",
        "## 摘要",
        "",
        f"- 家数：**{len(final)}**（目标 {TARGET_N}）",
        f"- holdout：**{hold_n}**（目标 ≥{HOLD_OUT_FLOOR}）",
        f"- dev_seen：**{int((final['eval_role']=='dev_seen').sum())}**",
        f"- 生科配额（18a_unprofit∪biotech_pharma）：**{bio_n}**（目标 ≥{BIO_FLOOR}）",
        f"- 最大恒生一级：`{top_l1}` = **{top_pct*100:.1f}%**（目标 ≤{HS_L1_CAP*100:.0f}%）",
        f"- 解析复用 / 待解析 / 缺失：{n_reuse} / {n_need} / {n_miss}",
        "",
        "## 年份 × 表现",
        "",
        crosstab_md(final, "list_year", "performance_class"),
        "",
        "## 复用来源",
        "",
        final["reuse_source"].value_counts().to_string(),
        "",
        "## eval_role",
        "",
        final["eval_role"].value_counts().to_string(),
        "",
        "## issuer_bucket",
        "",
        final["issuer_bucket"].value_counts().to_string(),
        "",
        "## 恒生一级行业",
        "",
        final["hs_l1"].fillna("未匹配").value_counts().to_string(),
        "",
        "## 相对全库（有行情子集）占比差（示意）",
        "",
    ]
    uni = universe.copy()
    for col, title in [
        ("list_year", "年份"),
        ("performance_class", "表现"),
    ]:
        full_p = uni[col].value_counts(normalize=True)
        samp_p = final[col].value_counts(normalize=True)
        diff = (samp_p - full_p).dropna().round(3)
        lines.append(f"### {title}")
        lines.append("")
        lines.append(diff.to_string())
        lines.append("")

    lines += [
        "## 样本清单",
        "",
        "| 代码 | 简称 | 年 | 表现 | HS一级 | bucket | source | role | parse |",
        "|------|------|----|------|--------|--------|--------|------|-------|",
    ]
    for _, r in final.sort_values(["list_year", "performance_class", "stock_code"]).iterrows():
        lines.append(
            f"| {r['stock_code']} | {r['company_display']} | {r['list_year']} | "
            f"{r['performance_class']} | {r.get('hs_l1','')} | {r['issuer_bucket']} | "
            f"{r['reuse_source']} | {r['eval_role']} | {r['parse_status']} |"
        )
    lines += [
        "",
        "## 使用说明",
        "",
        "- 赛题硬指标（≥80% / ≥85%）默认只在 `eval_role=holdout` 上计算。",
        "- `dev_seen`（多为 18a 调试池）仅作附表对照。",
        "- PDF：`dataset/test/`；解析复用见 `test_set_v1_parse_plan.md`。",
        "- **不可**将本测试集比例直接外推为 565 家总体均值。",
        "",
    ]
    (OUTPUT_DIR / "test_set_v1_report.md").write_text("\n".join(lines), encoding="utf-8")

    # save dev_tuned codes
    bio_codes = sorted(load_code_sets()[1])
    (OUTPUT_DIR / "dev_tuned_codes.txt").write_text(
        "\n".join(bio_codes) + "\n", encoding="utf-8"
    )


def main():
    print("加载宇宙 + 恒生行业 + Wind…")
    universe = load_universe()
    samples_codes, bio_codes = load_code_sets()
    print(f"有行情宇宙: {len(universe)}; samples={len(samples_codes)}; 18a={len(bio_codes)}")

    print("分层抽样…")
    sample = stratified_sample(universe, samples_codes, bio_codes)
    print(
        f"抽中 {len(sample)}; holdout={(sample.eval_role=='holdout').sum()}; "
        f"bio={sample.is_biotech_quota.sum()}; "
        f"sources={sample.reuse_source.value_counts().to_dict()}"
    )

    print("复制 PDF + 解析映射…")
    # enrich sample with catalog fields already present
    final = attach_parse_and_copy(sample)
    write_outputs(final, universe)

    print(f"PDF → {DEST_TEST} ({len(list(DEST_TEST.glob('*.pdf')))} files)")
    print(f"清单 → {OUTPUT_DIR / 'test_set_v1.csv'}")
    print(f"报告 → {OUTPUT_DIR / 'test_set_v1_report.md'}")
    print(f"待解析 → {OUTPUT_DIR / 'to_parse_list.csv'}")


if __name__ == "__main__":
    main()
