"""外采港股 IPO 认购倍数，补齐宽表 subscription_multiple 列。

数据源优先级：
1. 主：致富证券详情页（无需登录，历史覆盖较好）
   https://www.chiefgroup.com.hk/cn/securities/hk-ipo-detail/dp?symbol={code5}
   字段：认购倍数（公开发售超额认购）、上市价、上市日期
2. 备：新股渔夫公开列表（未登录仅最近约 30 条，含 超购倍数/国配倍数）
   https://xinguyufu.cn/api/ipo
3. 披露易配发结果公告：权威但为 PDF/HTML，本期仅记录缺口代码，不批量解析

输出：
- data/external/ipo/subscription_multiples.csv
- data/external/ipo/subscription_fetch_log.csv

随后可运行 scripts/merge_subscription_into_features.py 写回宽表。
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import IPO_CATALOG_CSV, DATA_DIR, ensure_dirs, write_sidecar

OUT_DIR = DATA_DIR / "external" / "ipo"
CHIEF_URL = "https://www.chiefgroup.com.hk/cn/securities/hk-ipo-detail/dp?symbol={code}"
XINGUYUFU_URL = "https://xinguyufu.cn/api/ipo"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
SLEEP_SEC = 0.35


def parse_number(text):
    if text is None:
        return None
    s = str(text).strip().replace(",", "").replace("倍", "").replace("%", "")
    if s in ("", "-", "—", "N/A", "null", "None"):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def fetch_chief(session, code5):
    """返回 dict 或 None（页面无认购倍数）。"""
    url = CHIEF_URL.format(code=code5)
    r = session.get(url, headers={**HEADERS, "Referer": "https://www.chiefgroup.com.hk/"},
                    timeout=30)
    r.raise_for_status()
    if "认购倍数" not in r.text:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    fields = {}
    for tr in soup.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if len(tds) == 2 and tds[0] in ("认购倍数", "上市价", "上市日期", "公开发售股数", "国际发售股数"):
            fields[tds[0]] = tds[1]
        elif len(tds) >= 4:
            for i in range(0, len(tds) - 1, 2):
                if tds[i] in ("认购倍数", "上市价", "上市日期", "公开发售股数", "国际发售股数"):
                    fields[tds[i]] = tds[i + 1]
    mult = parse_number(fields.get("认购倍数"))
    if mult is None:
        return None
    return {
        "stock_code": code5,
        "public_subscription_multiple": mult,
        "international_placing_multiple": None,  # 致富页通常不披露国配倍数
        "offer_price": parse_number(fields.get("上市价")),
        "list_date_src": fields.get("上市日期"),
        "source": "chiefgroup",
        "source_url": url,
    }


def fetch_xinguyufu_recent(session):
    """未登录公开接口：仅最近约 30 条，作补充。"""
    r = session.get(XINGUYUFU_URL, headers={**HEADERS, "Referer": "https://xinguyufu.cn/"},
                    params={"limit": 100, "offset": 0}, timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or []
    out = []
    for item in data:
        code = str(item.get("代码") or "").zfill(5)
        if not code.strip("0"):
            continue
        # 优先超购倍数（公开发售），其次国配倍数
        pub = parse_number(item.get("超购倍数"))
        intl = parse_number(item.get("国配倍数") or item.get("国际配售倍数"))
        if pub is None and intl is None:
            continue
        out.append({
            "stock_code": code,
            "public_subscription_multiple": pub,
            "international_placing_multiple": intl,
            "offer_price": parse_number(item.get("发行价")),
            "list_date_src": item.get("上市日期"),
            "source": "xinguyufu_public",
            "source_url": XINGUYUFU_URL,
            "name": item.get("名称"),
        })
    return out


def main():
    ensure_dirs()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cat = pd.read_csv(IPO_CATALOG_CSV, dtype={"stock_code": str})
    cat["code5"] = cat["stock_code"].astype(str).str.zfill(5)

    out_path = OUT_DIR / "subscription_multiples.csv"
    log_path = OUT_DIR / "subscription_fetch_log.csv"

    # 断点续抓
    done = {}
    if out_path.exists():
        prev = pd.read_csv(out_path, dtype={"stock_code": str})
        for _, r in prev.iterrows():
            done[str(r["stock_code"]).zfill(5)] = r.to_dict()
        print(f"resume: {len(done)} already saved")

    logs = []
    session = requests.Session()

    # 1) 新股渔夫近期公开数据先写入（不覆盖已有 chiefgroup 结果）
    try:
        recent = fetch_xinguyufu_recent(session)
        print(f"xinguyufu public recent with multiples: {len(recent)}")
        for row in recent:
            code = row["stock_code"]
            if code not in done:
                done[code] = row
                logs.append({"stock_code": code, "status": "ok", "source": "xinguyufu_public",
                             "public_subscription_multiple": row["public_subscription_multiple"],
                             "note": "recent public list only"})
    except Exception as e:
        print(f"xinguyufu recent failed: {type(e).__name__}: {e}")

    # 2) 致富证券按 565 家逐只抓（主源）
    n_ok = n_empty = n_err = n_skip = 0
    for i, row in cat.iterrows():
        code5 = row["code5"]
        if code5 in done and done[code5].get("source") == "chiefgroup":
            n_skip += 1
            continue
        # 已有 xinguyufu 的也尝试用 chiefgroup 覆盖（字段更贴近“认购倍数”定义）
        try:
            rec = fetch_chief(session, code5)
            if rec:
                # 保留先前新股渔夫写入的国配倍数（致富页通常没有该字段）
                prev = done.get(code5) or {}
                if rec.get("international_placing_multiple") is None:
                    rec["international_placing_multiple"] = prev.get(
                        "international_placing_multiple")
                done[code5] = rec
                logs.append({"stock_code": code5, "status": "ok", "source": "chiefgroup",
                             "public_subscription_multiple": rec["public_subscription_multiple"],
                             "note": ""})
                n_ok += 1
            else:
                if code5 not in done:
                    logs.append({"stock_code": code5, "status": "empty", "source": "chiefgroup",
                                 "public_subscription_multiple": None,
                                 "note": "page has no 认购倍数"})
                n_empty += 1
        except Exception as e:
            logs.append({"stock_code": code5, "status": "error", "source": "chiefgroup",
                         "public_subscription_multiple": None,
                         "note": f"{type(e).__name__}: {e}"})
            n_err += 1
        if (n_ok + n_empty + n_err) % 25 == 0:
            print(f"progress ok={n_ok} empty={n_empty} err={n_err} skip={n_skip} saved={len(done)}")
            _flush(done, logs, out_path, log_path)
        time.sleep(SLEEP_SEC)

    _flush(done, logs, out_path, log_path)
    cat_codes = set(cat["code5"])
    hit = sum(1 for c in cat_codes
              if c in done and done[c].get("public_subscription_multiple") is not None)
    write_sidecar(
        out_path,
        source="chiefgroup detail pages + xinguyufu /api/ipo (public recent)",
        note="public_subscription_multiple ≈ 公开发售超额认购倍数; "
             "international_placing_multiple only from xinguyufu when available; "
             "HKEX allotment PDFs not parsed in this pass",
        extra={"n_universe": int(len(cat)), "n_with_public_multiple": int(hit),
               "coverage": round(hit / len(cat_codes), 4)},
    )
    print(f"FINISHED ok={n_ok} empty={n_empty} err={n_err} skip={n_skip}")
    print(f"catalog coverage: {hit}/{len(cat_codes)} ({hit / len(cat_codes):.1%})")
    miss = sorted(c for c in cat_codes
                  if c not in done or done[c].get("public_subscription_multiple") is None)
    (OUT_DIR / "subscription_missing_codes.txt").write_text(
        "\n".join(miss) + "\n", encoding="utf-8")
    print(f"missing codes written: {len(miss)} -> subscription_missing_codes.txt")
    print("NOTE: 披露易配发结果公告可作为缺口兜底，见 README")


def _flush(done, logs, out_path, log_path):
    df = pd.DataFrame(list(done.values()))
    # 只保留有倍数的行进主表；日志保留全部尝试
    keep_cols = ["stock_code", "public_subscription_multiple",
                 "international_placing_multiple", "offer_price",
                 "list_date_src", "source", "source_url", "name"]
    for c in keep_cols:
        if c not in df.columns:
            df[c] = None
    df = df[keep_cols].drop_duplicates("stock_code", keep="last")
    df = df[df["public_subscription_multiple"].notna() |
            df["international_placing_multiple"].notna()]
    df = df.sort_values("stock_code")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    if logs:
        pd.DataFrame(logs).drop_duplicates("stock_code", keep="last").to_csv(
            log_path, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
