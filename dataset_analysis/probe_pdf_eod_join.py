#!/usr/bin/env python3
"""路径B探查：招股书 PDF 代码 → EOD WindCode 匹配测试。"""

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def windcode_candidates(code5: str) -> list:
    """PDF 文件名 5 位代码 → EOD S_INFO_WINDCODE 候选（按优先级）。"""
    base = code5.split("!")[0]
    if not base.isdigit():
        return [f"{base}.HK"]

    n = int(base)
    cands = [
        f"{n}.HK",                    # 去前导零：9926.HK（5位新股主规则）
        f"{str(n).zfill(4)}.HK",      # 4位补零：0300.HK（短代码老股）
        f"{base.zfill(5)}.HK",        # 保留5位：00300.HK（兜底）
    ]
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def resolve_windcode(code5: str, eod_codes: set):
    rules = ["strip_zero", "pad4", "pad5"]
    for i, w in enumerate(windcode_candidates(code5)):
        if w in eod_codes:
            return w, rules[i] if i < len(rules) else f"rule_{i}"
    return None, None


def parse_pdf_meta(path: Path):
    m = re.match(
        r"^(\d{5})_(\d{2})-(\d{2})-(\d{4})_(.+?)_"
        r"(全球發售|公開發售|股份發售|H股首次公開發售|售股章程.*|透過特殊目的.*|發售A類股份.*|以股份發售方式.*|.+發售.*|.+上市.*)$",
        path.stem,
    )
    if not m:
        m = re.match(r"^(\d{5})_(\d{2})-(\d{2})-(\d{4})_(.+)$", path.stem)
        if not m:
            return None
        code, dd, mm, yyyy, company = m.groups()
    else:
        code, dd, mm, yyyy, company, _ = m.groups()
    return {
        "stock_code": code,
        "company_name_pdf": company,
        "list_date_pdf": f"{yyyy}-{mm}-{dd}",
        "list_year": int(yyyy),
        "pdf_filename": path.name,
        "pdf_path": str(path),
    }


def load_eod_codes():
    codes = set()
    with open(DATASET_DIR / "hkshareeodprices.csv", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            codes.add(row["S_INFO_WINDCODE"])
    return codes


def classify_unmatched(row):
    code = row["stock_code"]
    notes = []
    if code == "06688":
        notes.append("蚂蚁集团IPO取消，EOD无行情属预期")
    if "SPAC" in row["pdf_filename"] or "收購" in row["pdf_filename"] or "ACQ" in row["pdf_filename"]:
        notes.append("SPAC/收购类标的，可能未上市或代码不同")
    if row["list_year"] >= 2025:
        notes.append("2025新股，需确认是否已上市或EOD截止日未覆盖")
    if not notes:
        notes.append("EOD全库无匹配WindCode，可能暂缓/取消上市或极短交易后摘牌")
    return "; ".join(notes)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    eod_codes = load_eod_codes()
    pdfs = sorted(p for p in DATASET_DIR.rglob("*.pdf") if p.parent != DATASET_DIR)

    rows = []
    for pdf in pdfs:
        meta = parse_pdf_meta(pdf)
        if not meta:
            rows.append({"pdf_filename": pdf.name, "match_status": "filename_parse_fail"})
            continue
        windcode, rule = resolve_windcode(meta["stock_code"], eod_codes)
        rows.append({
            **meta,
            "windcode_resolved": windcode,
            "windcode_rule": rule,
            "match_status": "matched" if windcode else "unmatched",
            "windcode_candidates": "|".join(windcode_candidates(meta["stock_code"])),
        })

    matched = [r for r in rows if r.get("match_status") == "matched"]
    unmatched = [r for r in rows if r.get("match_status") == "unmatched"]
    for r in unmatched:
        r["unmatched_reason"] = classify_unmatched(r)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "join_path": "B: PDF stock_code -> S_INFO_WINDCODE -> hkshareeodprices",
        "pdf_total": len(pdfs),
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "match_rate_pct": round(len(matched) / len(pdfs) * 100, 2),
        "windcode_rule_distribution": dict(Counter(r["windcode_rule"] for r in matched)),
        "conversion_rules": [
            "1. strip_zero: int(code5) + '.HK'  e.g. 02097 -> 2097.HK",
            "2. pad4: str(int(code5)).zfill(4) + '.HK'  e.g. 00300 -> 0300.HK",
            "3. pad5: code5.zfill(5) + '.HK'  e.g. 00300 -> 00300.HK (兜底)",
        ],
        "company_name_note": "匹配仅依赖股票代码，公司名称差异不影响关联；名称仅用于人工抽检",
        "by_year": {},
    }
    by_year = defaultdict(lambda: {"total": 0, "matched": 0})
    for r in rows:
        if r.get("list_year"):
            y = str(r["list_year"])
            by_year[y]["total"] += 1
            if r.get("match_status") == "matched":
                by_year[y]["matched"] += 1
    for y, v in sorted(by_year.items()):
        summary["by_year"][y] = {**v, "rate_pct": round(v["matched"] / v["total"] * 100, 1)}

    # write CSV
    out_csv = OUTPUT_DIR / "pdf_eod_join_probe.csv"
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    with open(OUTPUT_DIR / "pdf_eod_join_probe_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if unmatched:
        print("\n未匹配清单:")
        for r in unmatched:
            print(f"  {r['stock_code']} {r['list_date_pdf']} {r.get('unmatched_reason')}")


if __name__ == "__main__":
    main()
