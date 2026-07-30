#!/usr/bin/env python3
"""港股IPO数据集探索性分析：结构化画像 + PDF体检 + 分层抽样。"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import fitz
import pandas as pd

DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

SEED_KEYWORDS = ["蜜雪", "古茗", "恒瑞", "宁德", "赛力斯", "三一", "海天", "網易", "螞蟻", "康方", "再鼎"]
# 2025 年部分 PDF 文件名乱码，用代码映射正式公司名
SEED_STOCK_CODES = {
    "02097": "蜜雪集团",
    "06031": "三一重工",
    "03750": "宁德时代",
    "06099": "赛力斯",
    "01364": "古茗",
    "03288": "海天味业",
    "01276": "恒瑞医药",
    "01828": "富卫集团",
    "01384": "滴普科技",
    "02589": "沪上阿姨",
}
YEAR_RANGE = (2020, 2025)
TARGET_SAMPLE_SIZE = 54


def windcode_candidates(code5: str) -> list:
    """PDF 5位代码 → EOD WindCode 候选（按优先级）。"""
    base = str(code5).split("!")[0]
    if not base.isdigit():
        return [f"{base}.HK"]
    n = int(base)
    cands = [f"{n}.HK", f"{str(n).zfill(4)}.HK", f"{base.zfill(5)}.HK"]
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def norm_windcode(code5: str, eod_codes: set = None) -> str:
    """解析 PDF 代码为 EOD WindCode；若提供 eod_codes 则按多规则择优。"""
    if eod_codes is None:
        return f"{int(code5)}.HK"
    for w in windcode_candidates(code5):
        if w in eod_codes:
            return w
    return f"{int(code5)}.HK"


def resolve_windcode(code5: str, eod_codes: set):
    """返回 (windcode, rule)。"""
    rules = ["strip_zero", "pad4", "pad5"]
    for i, w in enumerate(windcode_candidates(code5)):
        if w in eod_codes:
            return w, rules[i] if i < len(rules) else f"rule_{i}"
    return norm_windcode(code5), None


def is_garbled_company_name(name: str) -> bool:
    """判断 PDF 文件名解析出的公司名是否为乱码。"""
    if not isinstance(name, str) or not name.strip():
        return True
    if re.search(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", name):
        return False
    if re.match(r"^[A-Za-z0-9－\-ＷＳＢ\s\.]+$", name):
        return False
    return bool(re.search(r"[^\x00-\x7f]", name))


def resolve_company_names(code: str, company: str):
    """返回 (展示名, 原始文件名公司名)。"""
    raw = company
    company = re.sub(r"_(全球發售|公開發售|股份發售|H股首次公開發售)$", "", company)
    if code in SEED_STOCK_CODES:
        return SEED_STOCK_CODES[code], raw
    if not is_garbled_company_name(company):
        return company, raw
    ascii_prefix = re.match(r"^([A-Za-z0-9－\-]+)", company)
    if ascii_prefix:
        return ascii_prefix.group(1), raw
    return f"待补全_{code}", raw


def to_relative_path(path: Path | str, base: Path = PROJECT_ROOT) -> str:
    try:
        return str(Path(path).resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def parse_pdf_filename(path: Path, eod_codes: set = None):
    """从文件名解析：代码、上市日期、公司名。"""
    name = path.stem
    m = re.match(
        r"^(\d{5})_(\d{2})-(\d{2})-(\d{4})_(.+?)_"
        r"(全球發售|公開發售|股份發售|H股首次公開發售|售股章程.*|透過特殊目的.*|發售A類股份.*|以股份發售方式.*|.+發售.*|.+上市.*)$",
        name,
    )
    if not m:
        m = re.match(r"^(\d{5})_(\d{2})-(\d{2})-(\d{4})_(.+)$", name)
        if not m:
            return None
        code, dd, mm, yyyy, company = m.groups()
    else:
        code, dd, mm, yyyy, company, _ = m.groups()
    company = re.sub(r"_(全球發售|公開發售|股份發售|H股首次公開發售)$", "", company)
    company_clean, company_raw = resolve_company_names(code, company)
    list_date = pd.Timestamp(int(yyyy), int(mm), int(dd))
    if eod_codes is not None:
        windcode, windcode_rule = resolve_windcode(code, eod_codes)
    else:
        windcode, windcode_rule = norm_windcode(code), None
    return {
        "stock_code": code,
        "windcode": windcode,
        "windcode_rule": windcode_rule,
        "company_name": company_clean,
        "company_name_raw": company_raw,
        "company_display": company_clean,
        "list_date": list_date,
        "list_year": int(yyyy),
        "pdf_filename": path.name,
        "pdf_path": str(path),
        "pdf_path_relative": to_relative_path(path),
        "folder_year": path.parent.name,
        "filename_parsed": True,
    }


def is_unprofitable_marker(name: str) -> bool:
    """未盈利/生物科技常见命名：－Ｂ / -B / －ＳＢ 等。"""
    markers = ["－Ｂ", "-B", "－ＳＢ", "-SB", "生物", "醫藥", "医药"]
    return any(m in name for m in markers)


def coarse_industry(scope: str) -> str:
    if not isinstance(scope, str) or not scope.strip():
        return "未知"
    rules = [
        ("生物科技/医药", ["生物", "医药", "醫藥", "制药", "製藥", "医疗", "醫療", "疫苗"]),
        ("TMT/互联网", ["互联网", "互聯網", "软件", "軟件", "信息", "資訊", "科技", "電商", "游戏", "遊戲"]),
        ("金融", ["银行", "銀行", "保险", "保險", "证券", "證券", "金融", "投资", "投資"]),
        ("消费/零售", ["餐饮", "餐飲", "食品", "饮料", "飲料", "零售", "消费", "消費", "服装", "服裝"]),
        ("地产/建筑", ["地产", "地產", "房地产", "房地產", "建筑", "建築", "物业", "物業"]),
        ("工业/制造", ["制造", "製造", "工业", "工業", "机械", "機械", "汽车", "汽車", "能源", "化工"]),
    ]
    for label, kws in rules:
        if any(k in scope for k in kws):
            return label
    return "其他"


def classify_performance(day1_ret, day5_ret):
    if pd.isna(day1_ret) and pd.isna(day5_ret):
        return "无行情"
    ref = day5_ret if pd.notna(day5_ret) else day1_ret
    if ref <= -0.20:
        return "暴跌"
    if ref <= -0.05:
        return "破发/走弱"
    if ref >= 0.30:
        return "暴涨"
    return "平稳"


def classify_page_count(pages: int) -> str:
    if pages < 100:
        return "短篇(<100页)"
    if pages < 300:
        return "中篇(100-299页)"
    if pages < 500:
        return "长篇(300-499页)"
    return "超长篇(≥500页)"


def load_share_table():
    path = DATASET_DIR / "hksharedescription.csv"
    # 文件为繁体中文；用 utf-8(replace) 读取可避免 cp1252 乱码，且能读满 803 行
    df = pd.read_csv(path, encoding="gb18030", engine="python", error_bad_lines=False)
    for col in ["S_INFO_LISTDATE", "S_INFO_DELISTDATE"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["list_date"] = pd.to_datetime(df["S_INFO_LISTDATE"].astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
    df["delist_date"] = pd.to_datetime(df["S_INFO_DELISTDATE"].astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
    df["code5"] = df["S_INFO_CODE"].astype(str).str.replace(r"!.*$", "", regex=True).str.zfill(5)
    return df


def load_company_table():
    path = DATASET_DIR / "hkcompanyinfo.csv"
    df = pd.read_csv(path, encoding="gb18030", engine="python", error_bad_lines=False)
    return df


def load_eod_table():
    path = DATASET_DIR / "hkshareeodprices.csv"
    usecols = ["S_INFO_WINDCODE", "TRADE_DT", "S_DQ_OPEN", "S_DQ_CLOSE", "S_DQ_VOLUME"]
    df = pd.read_csv(path, usecols=usecols)
    df["trade_date"] = pd.to_datetime(df["TRADE_DT"].astype(str), format="%Y%m%d", errors="coerce")
    return df.sort_values(["S_INFO_WINDCODE", "trade_date"])


def load_eod_windcodes(eod_df=None):
    if eod_df is None:
        eod_df = load_eod_table()
    return set(eod_df["S_INFO_WINDCODE"].unique())


def compute_post_listing_returns(eod_df, windcode, list_date):
    sub = eod_df[eod_df["S_INFO_WINDCODE"] == windcode].copy()
    if sub.empty:
        return {}
    if pd.notna(list_date):
        sub = sub[sub["trade_date"] >= list_date - pd.Timedelta(days=30)]
    sub = sub.sort_values("trade_date").drop_duplicates("trade_date")
    if sub.empty:
        return {}
    row0 = sub.iloc[0]
    open0 = row0["S_DQ_OPEN"]
    close0 = row0["S_DQ_CLOSE"]
    if pd.isna(open0) or open0 == 0:
        return {"first_trade_date": row0["trade_date"]}

    out = {
        "first_trade_date": row0["trade_date"],
        "day0_open": open0,
        "day0_close": close0,
        "day1_return": (close0 - open0) / open0,
        "day0_break_issue": close0 < open0,
    }
    for n, label in [(5, "day5"), (20, "day20"), (60, "day60")]:
        if len(sub) > n:
            px = sub.iloc[n]["S_DQ_CLOSE"]
            if pd.notna(px):
                out[f"{label}_close"] = px
                out[f"{label}_return"] = (px - open0) / open0
    return out


def check_pdf_health(path: Path):
    result = {
        "openable": False,
        "encrypted": False,
        "page_count": None,
        "file_size_mb": round(path.stat().st_size / 1024 / 1024, 2),
        "has_text_layer": None,
        "text_chars_page1": 0,
        "likely_scanned": None,
        "error": None,
    }
    try:
        doc = fitz.open(path)
        result["openable"] = True
        result["encrypted"] = doc.is_encrypted
        result["page_count"] = doc.page_count
        if doc.page_count > 0:
            text = doc[0].get_text("text")
            result["text_chars_page1"] = len(text.strip())
            result["has_text_layer"] = result["text_chars_page1"] > 50
            result["likely_scanned"] = result["text_chars_page1"] < 50
        doc.close()
    except Exception as exc:
        result["error"] = str(exc)
    return result


def build_ipo_catalog(eod_codes: set):
    records = []
    for pdf in sorted(DATASET_DIR.rglob("*.pdf")):
        if pdf.parent == DATASET_DIR:
            continue
        parsed = parse_pdf_filename(pdf, eod_codes=eod_codes)
        if parsed:
            records.append(parsed)
    return pd.DataFrame(records)


def merge_structured_data(ipo_df, share_df, company_df, eod_df):
    share_by_code = share_df.set_index("code5")
    merged = ipo_df.copy()
    merged["share_matched"] = merged["stock_code"].isin(share_by_code.index)
    merged["list_price"] = merged["stock_code"].map(
        share_by_code["S_INFO_LISTPRICE"].to_dict() if "S_INFO_LISTPRICE" in share_by_code else {}
    )
    merged["listboard"] = merged["stock_code"].map(
        share_by_code["S_INFO_LISTBOARD"].to_dict() if "S_INFO_LISTBOARD" in share_by_code else {}
    )
    merged["delisted"] = merged["stock_code"].map(
        lambda c: pd.notna(share_by_code.loc[c, "delist_date"]) if c in share_by_code.index else False
    )
    merged["is_unprofitable_proxy"] = merged["company_name"].map(is_unprofitable_marker)
    merged["eod_matched"] = merged["windcode_rule"].notna()

    perf_rows = []
    for _, row in merged.iterrows():
        perf = compute_post_listing_returns(eod_df, row["windcode"], row["list_date"])
        perf_rows.append(perf)
    perf_df = pd.DataFrame(perf_rows)
    merged = pd.concat([merged.reset_index(drop=True), perf_df], axis=1)
    merged["performance_class"] = merged.apply(
        lambda r: classify_performance(r.get("day1_return"), r.get("day5_return")), axis=1
    )

    comp_names = company_df.set_index("COMP_SNAME")["BUSINESSSCOPE"].to_dict()

    def match_business_scope(name):
        if not isinstance(name, str):
            return None
        for k, scope in comp_names.items():
            if k and isinstance(k, str) and k in name:
                return scope
        return None

    merged["business_scope"] = merged["company_name"].map(match_business_scope)
    merged["industry_coarse"] = merged["business_scope"].map(coarse_industry)
    return merged


def stratified_sample(df, target_size=TARGET_SAMPLE_SIZE):
    selected = []
    used_codes = set()
    if "company_display" not in df.columns:
        df = df.copy()
        df["company_display"] = df.apply(
            lambda r: SEED_STOCK_CODES.get(r["stock_code"], r.get("company_name", "")), axis=1
        )
    df = df.copy()
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(5)

    def pick(mask, reason, limit, prefer_with_eod=False):
        nonlocal selected, used_codes
        pool = df[mask & ~df["stock_code"].isin(used_codes)].copy()
        if prefer_with_eod and "performance_class" in pool.columns:
            pool["_sort"] = pool["performance_class"].map(lambda x: 0 if x != "无行情" else 1)
            pool = pool.sort_values(["_sort", "list_date"], ascending=[True, True])
        for _, row in pool.head(limit).iterrows():
            row_dict = row.to_dict()
            row_dict["stock_code"] = str(row_dict["stock_code"]).zfill(5)
            selected.append({**row_dict, "sample_reason": reason})
            used_codes.add(row_dict["stock_code"])

    # 年份覆盖优先，避免配额被其他层占满
    for year in range(YEAR_RANGE[0], YEAR_RANGE[1] + 1):
        pick(df["list_year"] == year, f"年份覆盖:{year}", 2, prefer_with_eod=True)

    for code, name in SEED_STOCK_CODES.items():
        pick(df["stock_code"] == code, f"种子样本:{name}", 1)

    for kw in SEED_KEYWORDS:
        pick(
            df["company_display"].str.contains(kw, na=False) | df["company_name"].str.contains(kw, na=False),
            f"种子样本:{kw}",
            1,
        )

    pick(df["is_unprofitable_proxy"], "未盈利/生物科技代理标记", 10)
    pick(df["performance_class"] == "暴跌", "上市后暴跌", 6)
    pick(df["performance_class"] == "暴涨", "上市后暴涨", 6)
    pick(df["performance_class"] == "破发/走弱", "破发/走弱", 6)
    pick(df["likely_scanned"] == True, "疑似扫描件", 4)
    pick(df["page_count"] < 100, "短篇招股书", 4)
    pick(df["page_count"] >= 500, "超长篇招股书", 4)

    pick(df["share_matched"] == False, "结构化表未匹配(需人工核对)", 3)
    pick(df["openable"] == False, "PDF打开异常", 1)

    remaining = target_size - len(selected)
    if remaining > 0:
        rest = df[~df["stock_code"].isin(used_codes)].sample(
            n=min(remaining, len(df) - len(used_codes)), random_state=42
        )
        for _, row in rest.iterrows():
            selected.append({**row.to_dict(), "sample_reason": "随机补足"})

    sample_df = pd.DataFrame(selected).drop_duplicates("stock_code")
    if not sample_df.empty:
        sample_df["stock_code"] = sample_df["stock_code"].astype(str).str.zfill(5)
    return sample_df.head(target_size)


def summarize_structured(df):
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ipo_pdf_total": int(len(df)),
        "year_distribution": df["list_year"].value_counts().sort_index().to_dict(),
        "unprofitable_proxy_count": int(df["is_unprofitable_proxy"].sum()),
        "unprofitable_proxy_ratio": round(df["is_unprofitable_proxy"].mean(), 3),
        "share_table_match_count": int(df["share_matched"].sum()),
        "share_table_match_ratio": round(df["share_matched"].mean(), 3),
        "share_table_listdate_max": str(df.get("share_listdate_max", pd.Series([None])).iloc[0])
        if "share_listdate_max" in df.columns and len(df) else None,
        "share_table_note": (
            "hksharedescription 是存量港股证券快照(约803条)，S_INFO_LISTDATE 为首次上市日(最大约2009)，"
            "OPDATE/S_INFO_DELISTDATE 可出现2024-2026，不代表2020-2025新股全覆盖"
        ),
        "delisted_count": int(df["delisted"].sum()) if "delisted" in df else 0,
        "eod_coverage_count": int(df["first_trade_date"].notna().sum()) if "first_trade_date" in df else 0,
        "eod_windcode_match_count": int(df["eod_matched"].sum()) if "eod_matched" in df else 0,
        "eod_windcode_match_ratio": round(df["eod_matched"].mean(), 3) if "eod_matched" in df else 0,
        "windcode_rule_distribution": df["windcode_rule"].value_counts().to_dict() if "windcode_rule" in df else {},
        "performance_distribution": df["performance_class"].value_counts().to_dict() if "performance_class" in df else {},
        "industry_distribution": df["industry_coarse"].value_counts().to_dict() if "industry_coarse" in df else {},
        "list_price_available": int(df["list_price"].notna().sum()) if "list_price" in df else 0,
    }
    if "day1_return" in df:
        summary["day1_return_stats"] = df["day1_return"].describe().to_dict()
    if "day5_return" in df:
        summary["day5_return_stats"] = df["day5_return"].describe().to_dict()
    return summary


def summarize_pdf_health(df):
    return {
        "total_pdfs_checked": int(len(df)),
        "openable_count": int(df["openable"].sum()),
        "encrypted_count": int(df["encrypted"].sum()),
        "open_error_count": int(df["error"].notna().sum()),
        "likely_scanned_count": int((df["likely_scanned"] == True).sum()),
        "text_layer_count": int((df["has_text_layer"] == True).sum()),
        "page_count_stats": df["page_count"].describe().to_dict(),
        "file_size_mb_stats": df["file_size_mb"].describe().to_dict(),
        "page_length_distribution": df["page_length_class"].value_counts().to_dict(),
        "filename_parse_fail_count": int((df["stock_code"].isna()).sum()) if "stock_code" in df else 0,
        "estimated_parse_hours_1min_per_page": round(df["page_count"].sum() / 60, 1),
    }


def write_markdown_report(struct_summary, health_summary, sample_df, merged_df):
    lines = [
        "# 港股IPO数据集探索性分析报告",
        "",
        f"> 生成时间：{struct_summary['generated_at']}",
        "",
        "## 数据资产概览",
        "",
        f"- 招股书 PDF：**{struct_summary['ipo_pdf_total']}** 份（2020–2025，按文件夹年份组织）",
        f"- 结构化表：`hksharedescription.csv`（803行，**存量证券快照**；`S_INFO_LISTDATE` 最大约2009年，`OPDATE`/`S_INFO_DELISTDATE` 可到2026年）",
        f"- 结构化表：`hkcompanyinfo.csv`（4501行）",
        f"- 行情表：`hkshareeodprices.csv`（约411万行，3756个WindCode）",
        "",
        "## 第一步：结构化数据画像（以PDF元数据 + EOD行情为主）",
        "",
        "### 按年份上市数量（PDF文件名解析）",
        "",
    ]
    for year, cnt in sorted(struct_summary["year_distribution"].items()):
        lines.append(f"- {year}：{cnt} 份")
    lines += [
        "",
        "### 未盈利/生物科技代理标记",
        "",
        f"- 命中 `-B` / `生物` / `醫藥` 等命名规则：**{struct_summary['unprofitable_proxy_count']}** 家（{struct_summary['unprofitable_proxy_ratio']*100:.1f}%）",
        "",
        "### 结构化表关联情况",
        "",
        f"- PDF 股票代码匹配 `hksharedescription`：**{struct_summary['share_table_match_count']}** / {struct_summary['ipo_pdf_total']}（{struct_summary['share_table_match_ratio']*100:.1f}%）",
        f"- PDF→EOD WindCode 匹配（路径B，多规则）：**{struct_summary.get('eod_windcode_match_count', 'N/A')}** / {struct_summary['ipo_pdf_total']}（{struct_summary.get('eod_windcode_match_ratio', 0)*100:.1f}%）",
        f"- WindCode 转换规则分布：{struct_summary.get('windcode_rule_distribution', {})}",
        f"- 有 EOD 行情数据（可算涨跌幅）：**{struct_summary['eod_coverage_count']}** 家",
        f"- 发行价字段可用数：**{struct_summary['list_price_available']}**（近年IPO基本缺失，上市后涨跌幅以首日开盘价作基准）",
        "",
        "### 上市后表现初筛（首日开盘→收盘/第5日收盘）",
        "",
    ]
    for k, v in struct_summary.get("performance_distribution", {}).items():
        lines.append(f"- {k}：{v}")
    lines += ["", "### 粗行业分布（经营范围匹配，覆盖率有限）", ""]
    for k, v in struct_summary.get("industry_distribution", {}).items():
        lines.append(f"- {k}：{v}")

    lines += [
        "",
        "## 第二步：PDF 批量体检",
        "",
        f"- 可正常打开：{health_summary['openable_count']} / {health_summary['total_pdfs_checked']}",
        f"- 加密 PDF：{health_summary['encrypted_count']}",
        f"- 打开失败：{health_summary['open_error_count']}",
        f"- 首页几乎无文字层（疑似扫描件）：{health_summary['likely_scanned_count']}",
        f"- 页数中位数：{health_summary['page_count_stats'].get('50%', 'N/A')}",
        f"- 页数最大值：{health_summary['page_count_stats'].get('max', 'N/A')}",
        f"- 总页数：{int(health_summary['page_count_stats'].get('count', 0) * health_summary['page_count_stats'].get('mean', 0))}",
        f"- 按 1min/页 粗估全量解析耗时：**约 {health_summary['estimated_parse_hours_1min_per_page']} 小时**",
        "",
        "### 篇幅分布",
        "",
    ]
    for k, v in health_summary.get("page_length_distribution", {}).items():
        lines.append(f"- {k}：{v}")

    lines += [
        "",
        "## 第三步：分层抽样清单（精读/标注候选）",
        "",
        f"共选出 **{len(sample_df)}** 份，详见 `sample_list.csv`。",
        "",
        "| 代码 | 公司 | 上市日 | 未盈利代理 | 表现分类 | 页数 | 抽样理由 |",
        "|------|------|--------|------------|----------|------|----------|",
    ]
    for _, r in sample_df.iterrows():
        lines.append(
            f"| {r.get('stock_code','')} | {r.get('company_display', r.get('company_name',''))} | "
            f"{str(r.get('list_date',''))[:10]} | {r.get('is_unprofitable_proxy','')} | "
            f"{r.get('performance_class','')} | {r.get('page_count','')} | {r.get('sample_reason','')} |"
        )

    lines += [
        "",
        "## 重要发现与后续建议",
        "",
        "1. **`hksharedescription.csv` 不是2020–2025新股清单**：表中 `OPDATE` 可到2026年，但 `S_INFO_LISTDATE`（首次上市日）最大约2009年；2020–2025招股书对应公司需以 PDF+EOD 为主关联。",
        "2. **蜜雪集团已在 dataset/2025/**（代码 `02097`，文件名因编码显示乱码）；已用代码映射补全显示名。",
        "3. **未盈利识别**暂用股票简称后缀（`-B`）及行业关键词代理，正式标注应回溯招股书「未盈利」章节。",
        "4. **破发判断**受限于发行价缺失，当前以首日开盘价作基准；有发行价后应改用 `S_INFO_LISTPRICE`。",
        "5. 全量565份PDF中约 **{scan}** 份首页无文字层，解析Pipeline需保留OCR分支。".format(
            scan=health_summary["likely_scanned_count"]
        ),
        "6. 路径B关联请用多规则 WindCode 转换（`strip_zero` + `pad4`），短代码如 `00300` 需映射为 `0300.HK` 而非 `300.HK`。",
        "",
    ]
    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[1/4] 解析 PDF 文件名目录...")
    print("[2/4] 加载结构化表与行情...")
    eod_df = load_eod_table()
    eod_codes = load_eod_windcodes(eod_df)
    ipo_df = build_ipo_catalog(eod_codes)
    print(f"  -> {len(ipo_df)} 份招股书，EOD匹配 {ipo_df['windcode_rule'].notna().sum()} 份")

    share_df = load_share_table()
    company_df = load_company_table()

    print("[3/4] 合并画像 + 批量 PDF 体检...")
    merged = merge_structured_data(ipo_df, share_df, company_df, eod_df)

    health_rows = []
    all_pdfs = sorted([p for p in DATASET_DIR.rglob("*.pdf") if p.parent != DATASET_DIR])
    code_by_path = dict(zip(merged["pdf_path"], merged["stock_code"])) if not merged.empty else {}
    for i, pdf in enumerate(all_pdfs, 1):
        h = check_pdf_health(pdf)
        h["pdf_path"] = str(pdf)
        h["pdf_filename"] = pdf.name
        h["stock_code"] = code_by_path.get(str(pdf))
        health_rows.append(h)
        if i % 100 == 0:
            print(f"  体检进度 {i}/{len(all_pdfs)}")
    health_df = pd.DataFrame(health_rows)
    health_df["page_length_class"] = health_df["page_count"].map(
        lambda x: classify_page_count(x) if pd.notna(x) else "未知"
    )

    full_df = merged.merge(
        health_df.drop(columns=["pdf_filename"], errors="ignore"),
        on=["pdf_path", "stock_code"],
        how="left",
    )

    print("[4/4] 分层抽样...")
    sample_df = stratified_sample(full_df)

    struct_summary = summarize_structured(full_df)
    health_summary = summarize_pdf_health(health_df)

    full_df.to_csv(OUTPUT_DIR / "ipo_catalog_with_metrics.csv", index=False, encoding="utf-8-sig")
    health_df.to_csv(OUTPUT_DIR / "pdf_health_check.csv", index=False, encoding="utf-8-sig")

    # 样本清单用精简列导出，避免 company_name_raw 乱码干扰阅读
    sample_export_cols = [
        "stock_code", "windcode", "windcode_rule", "company_name", "company_display",
        "list_date", "list_year", "performance_class", "is_unprofitable_proxy",
        "day1_return", "day5_return", "page_count", "likely_scanned",
        "pdf_filename", "pdf_path_relative", "sample_reason",
    ]
    sample_export = sample_df[[c for c in sample_export_cols if c in sample_df.columns]]
    sample_export.to_csv(OUTPUT_DIR / "sample_list.csv", index=False, encoding="utf-8-sig")
    with open(OUTPUT_DIR / "structured_summary.json", "w", encoding="utf-8") as f:
        json.dump(struct_summary, f, ensure_ascii=False, indent=2, default=str)
    with open(OUTPUT_DIR / "pdf_health_summary.json", "w", encoding="utf-8") as f:
        json.dump(health_summary, f, ensure_ascii=False, indent=2, default=str)

    report = write_markdown_report(struct_summary, health_summary, sample_df, full_df)
    (OUTPUT_DIR / "dataset_analysis_report.md").write_text(report, encoding="utf-8")

    print("\n=== 完成 ===")
    print(f"输出目录: {OUTPUT_DIR}")
    print(json.dumps(struct_summary, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(health_summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
