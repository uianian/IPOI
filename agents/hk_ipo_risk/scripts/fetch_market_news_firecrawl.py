#!/usr/bin/env python3
"""用 Firecrawl 搜索并缓存单家公司的上市前新闻正文。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.config import resolve_firecrawl_settings  # noqa: E402
from src.tools.firecrawl_news import FirecrawlNewsCollector  # noqa: E402
from src.tools.market_data import MarketDataLoader  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Firecrawl 上市前舆情抓取")
    parser.add_argument("--stock-code", required=True, help="五位港股代码")
    parser.add_argument("--features-csv", type=Path, default=None)
    parser.add_argument("--news-dir", type=Path, default=None)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="默认读取 configs/firecrawl.yaml，并叠加 firecrawl.local.yaml",
    )
    parser.add_argument("--out", type=Path, default=None, help="可选：保存不含密钥的抓取状态 JSON")
    parser.add_argument(
        "--refresh-firecrawl",
        action="store_true",
        help="忽略原始缓存并重新调用Firecrawl；默认禁止重复消耗额度",
    )
    args = parser.parse_args()

    loader_kwargs = {}
    if args.features_csv:
        loader_kwargs["features_csv"] = args.features_csv
    if args.news_dir:
        loader_kwargs["news_dir"] = args.news_dir
    loader = MarketDataLoader(**loader_kwargs)
    snapshot = loader.load_snapshot(args.stock_code)
    settings = resolve_firecrawl_settings(settings_path=args.config)
    if args.refresh_firecrawl:
        settings["fetch_policy"] = "always"
        settings.setdefault("cache", {})["reuse_raw_results"] = False
    collector = FirecrawlNewsCollector(settings)
    status = collector.collect(
        company=snapshot.company,
        stock_code=snapshot.stock_code,
        listing_date=snapshot.listing_date,
        as_of_date=snapshot.as_of_date,
        news_dir=loader.news_dir,
    )
    payload = json.dumps(status, ensure_ascii=False, indent=2)
    print(payload)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    return 0 if status.get("accepted_articles", 0) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

