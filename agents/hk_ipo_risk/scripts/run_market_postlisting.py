#!/usr/bin/env python3
"""Score realized D1,D5,D10,...,D60 market performance for one IPO."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.config import resolve_market_agent_settings  # noqa: E402
from src.skills.score_postlisting import PostlistingRiskScorer  # noqa: E402
from src.tools.market_data import normalize_stock_code  # noqa: E402
from src.storage.market_store import PostgresMarketStore  # noqa: E402


def _safe(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._") or "market"


def _report(stock_code: str, doc_id: str, results) -> str:
    lines = [
        f"# {stock_code} 上市后真实市场风险验证",
        "",
        f"- doc_id：`{doc_id}`",
        "- 主要风险锚点：发行价（检查点收盘价是否低于发行价）",
        "- 二级市场收益基准：上市首日开盘价",
        "- 检查点：D1 以及每5个交易日一次，D5至D60",
        "",
        "| 检查点 | 日期 | 真实风险分 | 风险等级 | 开盘基准累计收益 | 是否低于发行价 | 最大回撤 |",
        "|---|---|---:|---|---:|---|---:|",
    ]
    for item in results:
        below = "不可用" if item.below_issue_price is None else ("是" if item.below_issue_price else "否")
        mdd = "—" if item.max_drawdown_from_open is None else f"{item.max_drawdown_from_open:.2%}"
        lines.append(
            f"| {item.checkpoint} | {item.observation_date} | {item.realized_risk_score:.2f} | "
            f"{item.risk_level} | {item.cumulative_return_from_open:.2%} | {below} | {mdd} |"
        )
    lines.extend(["", "## 逐检查点证据", ""])
    for item in results:
        lines.extend([f"### {item.checkpoint}", ""])
        for metric in item.metrics:
            lines.append(
                f"- `{metric.evidence_id}` {metric.metric}={metric.raw_value}，"
                f"风险分={metric.risk_score}，历史样本={metric.history_sample_size}"
            )
        for limitation in item.limitations:
            lines.append(f"- 限制：{limitation}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


async def _amain() -> int:
    parser = argparse.ArgumentParser(description="上市后D1及每5交易日真实市场风险评分")
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--through-day", type=int, choices=[1] + list(range(5, 61, 5)), default=60)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    code = normalize_stock_code(args.stock_code)
    settings = resolve_market_agent_settings(settings_path=args.config)
    results = PostlistingRiskScorer().load_and_score(
        code,
        checkpoints_csv=settings["data"]["postlisting_checkpoints_csv"],
        through_day=args.through_day,
    )
    output = settings["output"]
    directory = Path(output["directory"])
    directory.mkdir(parents=True, exist_ok=True)
    variables = {"doc_id": _safe(args.doc_id), "stock_code": code}
    json_path = directory / output["postlisting_json_filename"].format(**variables)
    report_path = directory / output["postlisting_report_filename"].format(**variables)
    payload = {
        "doc_id": args.doc_id,
        "stock_code": code,
        "risk_anchor": "issue_price",
        "secondary_market_return_base": "first_trading_day_open",
        "checkpoints": [item.model_dump(mode="json") for item in results],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(_report(code, args.doc_id, results), encoding="utf-8")
    database = settings.get("database") or {}
    database_run_ids: list[str] = []
    if database.get("enabled"):
        postgres_url = str(database.get("postgres_url") or "").strip()
        if not postgres_url:
            if database.get("required"):
                raise RuntimeError(
                    "database.enabled=true, but MARKET_DATABASE_URL/postgres_url is empty"
                )
        else:
            store = PostgresMarketStore(
                postgres_url,
                schema=str(database.get("schema") or "market_agent"),
            )
            try:
                await store.initialize()
                database_run_ids = await store.persist_postlisting_checkpoints(
                    doc_id=args.doc_id,
                    stock_code=code,
                    checkpoints=payload["checkpoints"],
                )
            finally:
                await store.close()
    print(f"stock_code={code} checkpoints={len(results)}")
    print(f"json={json_path}")
    print(f"report={report_path}")
    if database_run_ids:
        print(f"database_run_ids={','.join(database_run_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
