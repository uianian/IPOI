from __future__ import annotations

import asyncio
import csv
import tempfile
from pathlib import Path

from src.agents.market_agent import MarketAgent


def _features(path: Path) -> None:
    fields = [
        "stock_code", "company", "listing_date", "as_of_date",
        "market_observation_date", "industry", "hsi_ret_20d",
        "mkt_turnover_chg_20d", "vhsi_avg_5d", "ind_ret_20d",
        "ind_excess_20d", "ipo_count_30d", "avg_day1_return_60d",
        "break_rate_60d", "subscription_multiple", "news_rows",
    ]
    row = {
        "stock_code": "2097", "company": "测试公司", "listing_date": "2025-03-03",
        "as_of_date": "2025-03-02", "market_observation_date": "2025-02-28",
        "industry": "必需性消费", "hsi_ret_20d": "0.05",
        "mkt_turnover_chg_20d": "0.10", "vhsi_avg_5d": "19",
        "ind_ret_20d": "0.08", "ind_excess_20d": "0.03", "ipo_count_30d": "6",
        "avg_day1_return_60d": "0.12", "break_rate_60d": "0.25",
        "subscription_multiple": "80", "news_rows": "0",
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)


def test_market_agent_emits_auditable_stage_pairs() -> None:
    async def run() -> list[dict]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            features = root / "features.csv"
            _features(features)
            events: list[dict] = []
            await MarketAgent(
                on_progress=events.append,
                market_settings={"llm": {"enabled": False}, "cutoff": {}, "data": {}},
                firecrawl_settings={"enabled": False, "search": {}},
                sina_settings={"enabled": False},
            ).run("doc-progress", stock_code="02097", features_csv=features, news_dir=root / "news")
            return events

    events = asyncio.run(run())
    steps = [event for event in events if event.get("event") == "step"]
    by_name: dict[str, list[str]] = {}
    for event in steps:
        by_name.setdefault(str(event["name"]), []).append(str(event["status"]))
    for name in (
        "load_market_snapshot",
        "inspect_public_opinion",
        "collect_sina_news",
        "firecrawl_public_opinion",
        "validate_public_opinion",
        "analyze_market_dimensions",
        "validate_llm_assessment",
        "score_market_rules",
        "build_market_report",
    ):
        assert name in by_name, name
        assert by_name[name][0] == "running", (name, by_name[name])
        assert by_name[name][-1] in {"ok", "degraded", "skipped", "error"}, (name, by_name[name])

    report_done = next(
        event for event in steps
        if event.get("name") == "build_market_report" and event.get("status") == "ok"
    )
    output = report_done.get("output") or {}
    assert output.get("summary")
    assert isinstance(output.get("evidence"), list)
    assert len(output["evidence"]) == min(int(output.get("evidence_count") or 0), 12)
