from __future__ import annotations

import logging
import re
from typing import Any

from src.config import load_finance_schema
from src.models.evidence import EvidenceRef
from src.skills.table_utils import (
    extract_year_headers,
    find_row_values,
    html_table_to_rows,
    plaintext_row_search,
)
from src.tools.retrieval_tool import iter_field_hits

logger = logging.getLogger(__name__)

# 分项合计 → 回填总资产/总负债（18A 等常无单独「总资产」行）
_ASSET_PARTS = {
    "NONCURRENT_ASSETS": ["非流動資產總值", "非流动资产总值"],
    "CURRENT_ASSETS": ["流動資產總值", "流动资产总值"],
}
_LIAB_PARTS = {
    "NONCURRENT_LIAB": ["非流動負債總額", "非流动负债总额"],
    "CURRENT_LIAB": ["流動負債總額", "流动负债总额"],
}
# IS 未召回时，CF 间接法调节起点常见「税前虧損」行（维昇等）
_CF_NET_LOSS_PROXY_LABELS = [
    "税前虧損",
    "稅前虧損",
    "除税前虧損",
    "除稅前虧損",
    "除税前溢利／（虧損）",
    "除稅前溢利／（虧損）",
    "除税前溢利/(虧損)",
    "除稅前溢利/(虧損)",
    "年內虧損",
    "期內虧損",
]


def _has_metric_series(series: dict[str, float | None] | None) -> bool:
    return bool(series) and any(v is not None for v in series.values())


def _short_excerpt(text: str, min_len: int = 50, max_len: int = 200) -> str:
    """赛题证据切片：优先 50–200 字；text/html 一视同仁（上游解析形态不可控）。"""
    t = (text or "").replace("\n", " ")
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= max_len:
        return t if len(t) >= min_len or not t else t
    return t[: max_len - 1] + "…"


def _label_map_from_schema() -> dict[str, dict[str, list[str]]]:
    schema = load_finance_schema()
    out: dict[str, dict[str, list[str]]] = {}
    for sec, body in (schema.get("sections") or {}).items():
        table_code = body.get("table_code")
        if not table_code:
            continue
        fmap: dict[str, list[str]] = {}
        for field, meta in (body.get("fields") or {}).items():
            if isinstance(meta, dict) and meta.get("labels"):
                fmap[field] = list(meta["labels"])
        out[table_code] = fmap
    return out


def _map_nums_to_years(
    nums: list[float], years: list[str]
) -> dict[str, float | None]:
    use_years = list(years) if years else [f"p{i}" for i in range(len(nums))]
    if len(nums) != len(use_years) and len(nums) >= 3:
        use_years = (
            use_years[: len(nums)]
            if len(use_years) >= len(nums)
            else use_years + [f"p{i}" for i in range(len(use_years), len(nums))]
        )
    return {use_years[i]: nums[i] for i in range(min(len(use_years), len(nums)))}


def _extract_labeled_series(
    excerpt: str,
    labels: list[str],
    years: list[str],
    *,
    field: str,
    rows: list[list[str]],
) -> tuple[dict[str, float | None], str | None]:
    vals = find_row_values(rows, labels, years, field=field)
    if vals and any(v is not None for v in vals.values()):
        return vals, None
    pt = plaintext_row_search(excerpt, labels, field=field)
    nums = pt.get("numbers") or []
    if nums:
        return _map_nums_to_years(nums, years), pt.get("line")
    return {}, None


def _sum_component_series(
    excerpt: str,
    years: list[str],
    parts: dict[str, list[str]],
    rows: list[list[str]],
) -> dict[str, float | None]:
    series_list: list[dict[str, float | None]] = []
    for _name, labels in parts.items():
        vals, _ = _extract_labeled_series(excerpt, labels, years, field="", rows=rows)
        if vals:
            series_list.append(vals)
    if len(series_list) < 2:
        return {}
    years_u = sorted(
        {y for s in series_list for y in s.keys()},
        key=lambda y: (0, int(y)) if str(y).isdigit() else (1, str(y)),
    )
    out: dict[str, float | None] = {}
    for y in years_u:
        nums = [s.get(y) for s in series_list]
        if any(v is None for v in nums):
            out[y] = None
        else:
            out[y] = round(sum(float(v) for v in nums if v is not None), 2)
    return out


def reconcile_balance_sheet(metrics: dict[str, dict[str, float | None]]) -> dict[str, Any]:
    """交叉校验：TOTAL_ASSETS 缺失/偏小时用 NET+LIAB 或分项合计回填。"""
    ta = dict(metrics.get("TOTAL_ASSETS") or {})
    tl = metrics.get("TOTAL_LIAB") or {}
    na = metrics.get("NET_ASSETS") or {}
    notes: list[str] = []
    reconciled: dict[str, float | None] = {}
    changed = False
    years = sorted(
        {*ta.keys(), *tl.keys(), *na.keys()},
        key=lambda y: (0, int(y)) if str(y).isdigit() else (1, str(y)),
    )
    for y in years:
        a, l, e = ta.get(y), tl.get(y), na.get(y)
        if a is None and e is not None and l is not None:
            recon = round(float(e) + float(l), 2)
            ta[y] = recon
            reconciled[y] = recon
            changed = True
            notes.append(f"{y}: TOTAL_ASSETS 缺失 → 回填 NET+LIAB={recon}")
        elif a is not None and e is not None and a < e and l is not None:
            recon = round(float(e) + float(l), 2)
            reconciled[y] = recon
            ta[y] = recon
            changed = True
            notes.append(f"{y}: TOTAL_ASSETS {a} < NET_ASSETS {e} → 回填 NET+LIAB={recon}")
        elif a is not None and e is not None and l is not None:
            expected = float(e) + float(l)
            if expected and abs(float(a) - expected) / max(abs(expected), 1) > 0.15:
                notes.append(
                    f"{y}: TOTAL_ASSETS={a} 与 NET+LIAB={expected} 偏差>15% → 采用 NET+LIAB"
                )
                ta[y] = round(expected, 2)
                reconciled[y] = ta[y]
                changed = True
            else:
                reconciled[y] = a
        else:
            reconciled[y] = a
    if changed:
        metrics["TOTAL_ASSETS"] = ta
        metrics["TOTAL_ASSETS_RECONCILED"] = reconciled
    return {"changed": changed, "notes": notes, "TOTAL_ASSETS_RECONCILED": reconciled if changed else {}}


def extract_financials_from_retrieval(bundle: dict[str, Any]) -> dict[str, Any]:
    """从 finance retrieval 的整表证据抽取 2.1/2.2/2.3 指标序列。"""
    label_maps = _label_map_from_schema()
    metrics: dict[str, dict[str, float | None]] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}
    table_meta: dict[str, Any] = {}
    extract_notes: list[str] = []

    def _register_table_meta(
        table_code: str, hits: list[dict[str, Any]]
    ) -> tuple[str, list[str], str, list[list[str]], Any]:
        best = hits[0]
        excerpt = best.get("excerpt") or best.get("content") or ""
        page = best.get("page") or best.get("page_number")
        rows = html_table_to_rows(excerpt)
        years = extract_year_headers(rows)
        if not years:
            years = extract_year_headers([[line] for line in excerpt.splitlines()[:12]])
        years_uncertain = False
        if not years:
            # 禁止硬编码真实会计年度（会把 2020 数据静默挂到 2021）
            n_cols = max((len(r) for r in rows[:6]), default=0)
            n_data = max(n_cols - 1, 2)
            years = [f"p{i}" for i in range(min(n_data, 6))]
            years_uncertain = True
            extract_notes.append(f"{table_code}:years_uncertain")
        src = "table" if "<table" in excerpt.lower() else "text"
        short = _short_excerpt(excerpt)
        table_meta[table_code] = {
            "page": page,
            "years": years,
            "years_uncertain": years_uncertain,
            "category": best.get("category") or src,
            "n_hits": len(hits),
            "excerpt": short,
            "source_type": src,
        }
        evidence[table_code] = [
            {
                "page": page,
                "excerpt": short,
                "source_type": src,
                "field_code": table_code,
            }
        ]
        return excerpt, years, src, rows, page

    for table_code, fmap in label_maps.items():
        hits = iter_field_hits(bundle, table_code)
        if not hits:
            continue
        excerpt, years, src, rows, page = _register_table_meta(table_code, hits)
        for field, labels in fmap.items():
            vals, line = _extract_labeled_series(
                excerpt, labels, years, field=field, rows=rows
            )
            if vals and any(v is not None for v in vals.values()):
                metrics[field] = vals
                if line:
                    evidence.setdefault(field, []).append(
                        {
                            "page": page,
                            "excerpt": _short_excerpt(line),
                            "source_type": src,
                            "field_code": field,
                        }
                    )

        if table_code == "TBL_IS" and "OTHER_INCOME" not in metrics:
            oi, oi_line = _extract_labeled_series(
                excerpt,
                ["其他收入及收益", "其他收入", "其他收益"],
                years,
                field="OTHER_INCOME",
                rows=rows,
            )
            if oi:
                metrics["OTHER_INCOME"] = oi
                if oi_line:
                    evidence.setdefault("OTHER_INCOME", []).append(
                        {
                            "page": page,
                            "excerpt": _short_excerpt(oi_line),
                            "source_type": src,
                            "field_code": "OTHER_INCOME",
                        }
                    )

        if table_code == "TBL_BS":
            if "TOTAL_ASSETS" not in metrics or not any(
                (metrics.get("TOTAL_ASSETS") or {}).values()
            ):
                summed = _sum_component_series(excerpt, years, _ASSET_PARTS, rows)
                if summed and any(v is not None for v in summed.values()):
                    metrics["TOTAL_ASSETS"] = summed
                    extract_notes.append("TOTAL_ASSETS ← 非流動資產總值+流動資產總值")
            if "TOTAL_LIAB" not in metrics or not any(
                (metrics.get("TOTAL_LIAB") or {}).values()
            ):
                summed_l = _sum_component_series(excerpt, years, _LIAB_PARTS, rows)
                if summed_l and any(v is not None for v in summed_l.values()):
                    metrics["TOTAL_LIAB"] = summed_l
                    extract_notes.append("TOTAL_LIAB ← 流動負債總額+非流動負債總額")
            # 若误抽了「资产总值减流动负债」，用分项或 NET+LIAB 覆盖
            ta = metrics.get("TOTAL_ASSETS") or {}
            na = metrics.get("NET_ASSETS") or {}
            if ta and na:
                bad = False
                for y, a in ta.items():
                    e = na.get(y)
                    if a is not None and e is not None and float(a) < float(e):
                        bad = True
                        break
                if bad:
                    summed = _sum_component_series(excerpt, years, _ASSET_PARTS, rows)
                    if summed:
                        metrics["TOTAL_ASSETS"] = summed
                        extract_notes.append(
                            "TOTAL_ASSETS 疑似「减流动负债」误匹配 → 改用分项合计"
                        )

    # 贵公司 BS 等：只登记证据元数据，不并入综合表指标
    for table_code in ("TBL_BS_COMPANY",):
        if table_code in table_meta:
            continue
        hits = iter_field_hits(bundle, table_code)
        if hits:
            _register_table_meta(table_code, hits)

    # IS 未召回 NET_LOSS 时：从现金流量表「税前虧損」等行代理回填（间接法起点）
    if not _has_metric_series(metrics.get("NET_LOSS")):
        cf_hits = list(iter_field_hits(bundle, "TBL_CF"))
        if cf_hits:
            best = cf_hits[0]
            excerpt = best.get("excerpt") or best.get("content") or ""
            page = best.get("page") or best.get("page_number")
            rows = html_table_to_rows(excerpt)
            if "TBL_CF" in table_meta and table_meta["TBL_CF"].get("years"):
                years = list(table_meta["TBL_CF"]["years"])
                src = str(table_meta["TBL_CF"].get("source_type") or "table")
            else:
                _, years, src, rows, page = _register_table_meta("TBL_CF", cf_hits)
            is_labels = list((label_maps.get("TBL_IS") or {}).get("NET_LOSS") or [])
            labels = list(dict.fromkeys(_CF_NET_LOSS_PROXY_LABELS + is_labels))
            vals, line = _extract_labeled_series(
                excerpt, labels, years, field="NET_LOSS", rows=rows
            )
            if vals and any(v is not None for v in vals.values()):
                metrics["NET_LOSS"] = vals
                extract_notes.append(
                    "NET_LOSS ← TBL_CF 税前/除税前虧損（IS未召回代理）"
                )
                evidence.setdefault("NET_LOSS", []).append(
                    {
                        "page": page,
                        "excerpt": _short_excerpt(line or excerpt),
                        "source_type": src,
                        "field_code": "NET_LOSS",
                    }
                )

    # 18A：无产品收入行时不要把 OTHER_INCOME 当成 REV
    if "REV" in metrics and "OTHER_INCOME" in metrics:
        rev, oi = metrics["REV"], metrics["OTHER_INCOME"]
        if rev and oi and all(
            rev.get(y) == oi.get(y) for y in rev.keys() if rev.get(y) is not None
        ):
            extract_notes.append("REV 与 OTHER_INCOME 相同 → 清除 REV（无产品收入）")
            del metrics["REV"]
            evidence.pop("REV", None)

    if "GP" in metrics and "REV" in metrics:
        gp_m: dict[str, float | None] = {}
        for y, gp in metrics["GP"].items():
            rev = (metrics["REV"] or {}).get(y)
            if gp is not None and rev:
                gp_m[y] = round(gp / rev * 100.0, 2)
            else:
                gp_m[y] = None
        metrics["GP_MARGIN"] = gp_m

    bs_check = reconcile_balance_sheet(metrics)
    if extract_notes:
        bs_check = {**bs_check, "extract_notes": extract_notes}

    return {
        "metrics": metrics,
        "evidence": evidence,
        "table_meta": table_meta,
        "bs_reconcile": bs_check,
        "years": sorted(
            {y for m in metrics.values() for y in m.keys() if str(y).isdigit()},
            key=lambda x: int(x),
        ),
    }


def evidence_refs_for(field_or_table: str, extracted: dict[str, Any]) -> list[EvidenceRef]:
    items = (extracted.get("evidence") or {}).get(field_or_table) or []
    if not items and field_or_table in {
        "REV",
        "GP",
        "NET_LOSS",
        "COGS",
        "GP_MARGIN",
        "RD_EXP",
        "SGA",
        "OTHER_INCOME",
    }:
        items = (extracted.get("evidence") or {}).get("TBL_IS") or []
    if not items and field_or_table == "NET_LOSS":
        # IS 缺失时 NET_LOSS 可能来自 CF 税前虧損代理
        items = (extracted.get("evidence") or {}).get("TBL_CF") or []
    if not items and field_or_table in {
        "TOTAL_ASSETS",
        "TOTAL_LIAB",
        "NET_ASSETS",
        "CASH_EQ",
        "CV_PREF",
        "TOTAL_ASSETS_RECONCILED",
    }:
        items = (extracted.get("evidence") or {}).get("TBL_BS") or []
    if not items and field_or_table in {"CFO", "CFI", "CFF", "END_CASH"}:
        items = (extracted.get("evidence") or {}).get("TBL_CF") or []
    out: list[EvidenceRef] = []
    for it in items:
        out.append(
            EvidenceRef(
                page=it.get("page"),
                excerpt=it.get("excerpt") or "",
                source_type=it.get("source_type") or "unknown",
                field_code=it.get("field_code"),
            )
        )
    return out
