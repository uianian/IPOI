from __future__ import annotations

from typing import Any


def _series_values(series: dict[str, float | None] | None) -> list[tuple[str, float]]:
    """Only full-year keys (pure digits); ignore interim suffixes like 2023_i1."""
    if not series:
        return []
    items: list[tuple[str, float]] = []
    for k, v in series.items():
        if v is None:
            continue
        if str(k).isdigit():
            items.append((str(k), float(v)))
    items.sort(key=lambda x: int(x[0]))
    return items


def _period_sort_key(year_key: str) -> tuple[int, int]:
    s = str(year_key)
    if "_i" in s:
        base, _, rest = s.partition("_i")
        try:
            return (int(base), int(rest or 1))
        except ValueError:
            return (0, 0)
    try:
        return (int(s), 0)
    except ValueError:
        return (0, 0)


def _period_values(series: dict[str, float | None] | None) -> list[tuple[str, float]]:
    """Full-year + interim keys, chronological (interim after its year-end)."""
    if not series:
        return []
    items: list[tuple[str, float]] = []
    for k, v in series.items():
        if v is None:
            continue
        ks = str(k)
        if ks.isdigit() or "_i" in ks:
            items.append((ks, float(v)))
    items.sort(key=lambda x: _period_sort_key(x[0]))
    return items


def _period_months(year_key: str) -> int:
    """HK track-record stub 默认按 8 个月；完整年度 12 个月。"""
    return 8 if "_i" in str(year_key) else 12


def detect_profitability(metrics: dict[str, dict[str, float | None]]) -> dict[str, Any]:
    """基于 NET_LOSS/期内利润：正数视为盈利（港股「年內利潤」）。

    无有效年度序列时标 profitability_known=False，不得默认「已盈利」。
    """
    net = metrics.get("NET_LOSS") or {}
    vals = _series_values(net)
    full_year_vals = [(y, v) for y, v in vals if y.isdigit()]
    latest_full_year_loss = False
    continuous_loss = False
    is_unprofitable = False

    if not full_year_vals:
        return {
            "is_unprofitable": False,
            "latest_full_year_loss": False,
            "continuous_net_loss": False,
            "net_series": {},
            "profitability_known": False,
            "profitability_status": "unknown",
            "profitability_basis": "NET_LOSS/年內利潤 series missing; do not assume profitable",
        }

    latest_y, latest_v = full_year_vals[-1]
    latest_full_year_loss = latest_v < 0
    if len(full_year_vals) >= 2:
        continuous_loss = all(v < 0 for _, v in full_year_vals[-3:])
    is_unprofitable = latest_full_year_loss or continuous_loss
    # 若最近完整年度盈利，则整体视为已盈利（蜜雪）
    if latest_v > 0:
        is_unprofitable = False

    return {
        "is_unprofitable": is_unprofitable,
        "latest_full_year_loss": latest_full_year_loss,
        "continuous_net_loss": continuous_loss,
        "net_series": {y: v for y, v in full_year_vals},
        "profitability_known": True,
        "profitability_status": "unprofitable" if is_unprofitable else "profitable",
        "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit",
    }


def resolve_issuer_gates(
    issuer_type: str,
    metrics: dict[str, dict[str, float | None]],
) -> dict[str, Any]:
    profit = detect_profitability(metrics)
    is_biotech = issuer_type.strip().lower() in {"biotech", "18a", "18c"}
    # 仅在确认已盈利时跳过 3.4；unknown / 未盈利均不 skip
    if not profit.get("profitability_known"):
        skip_3_4 = False
        skip_3_4_reason = "profitability_unknown"
    elif profit["is_unprofitable"]:
        skip_3_4 = False
        skip_3_4_reason = None
    else:
        skip_3_4 = True
        skip_3_4_reason = "profitable"
    skip_2_4 = not is_biotech
    skip_3_5 = not is_biotech
    return {
        **profit,
        "issuer_type": issuer_type,
        "is_biotech_18a": is_biotech,
        "skip_3_4": skip_3_4,
        "skip_3_4_reason": skip_3_4_reason,
        "skip_2_4": skip_2_4,
        "skip_2_4_reason": "non-biotech" if skip_2_4 else None,
        "skip_3_5": skip_3_5,
        "skip_3_5_reason": "non-biotech" if skip_3_5 else None,
    }


def compute_cash_burn(
    metrics: dict[str, dict[str, float | None]],
    gates: dict[str, Any],
) -> dict[str, Any]:
    """文档 3.4：仅未盈利时计算。CASH_RUNWAY = END_CASH / monthly_burn。"""
    if gates.get("skip_3_4"):
        return {
            "skipped": True,
            "reason": gates.get("skip_3_4_reason") or "gate",
            "BURN_RATE": None,
            "CASH_RUNWAY_MONTHS": None,
        }

    # 现金优先用最新一期（含中期）；消耗用可比期间年化，避免把 stub 当全年 CFO
    cash_series = _period_values(metrics.get("CASH_EQ") or metrics.get("END_CASH"))
    if not cash_series:
        cash_series = _series_values(metrics.get("CASH_EQ") or metrics.get("END_CASH"))
    cfo_periods = _period_values(metrics.get("CFO"))
    cfo_full = _series_values(metrics.get("CFO"))
    end_cash = cash_series[-1][1] if cash_series else None

    monthly_burn = None
    runway = None
    burn_yoy_up_gt_30 = False
    burn_basis: str | None = None

    if cfo_periods:
        last_y, last_v = cfo_periods[-1]
        months = _period_months(last_y)
        if last_v < 0:
            monthly_burn = abs(last_v) / float(months)
            burn_basis = f"{last_y}/{months}m"
        # YoY：优先同口径中期（2024_i1 vs 2025_i1），否则完整年度
        interim_tail = [p for p in cfo_periods if "_i" in p[0]]
        cmp_series = interim_tail if len(interim_tail) >= 2 else cfo_full
        if len(cmp_series) >= 2:
            prev, cur = cmp_series[-2][1], cmp_series[-1][1]
            if prev < 0 and cur < 0 and abs(prev) > 0:
                growth = (abs(cur) - abs(prev)) / abs(prev)
                burn_yoy_up_gt_30 = growth > 0.30

    if end_cash is not None and monthly_burn and monthly_burn > 0:
        runway = round(end_cash / monthly_burn, 2)

    return {
        "skipped": False,
        "reason": None,
        "END_CASH": end_cash,
        "BURN_RATE_MONTHLY": monthly_burn,
        "CASH_RUNWAY_MONTHS": runway,
        "burn_yoy_up_gt_30": burn_yoy_up_gt_30,
        "burn_basis": burn_basis,
    }
