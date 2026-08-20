from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.agents.market_agent import MarketAgent
from src.config import resolve_firecrawl_settings
from src.tools.firecrawl_news import FirecrawlNewsCollector


class FakeFirecrawl:
    def __init__(self) -> None:
        self.scraped: list[str] = []
        self.searches: list[tuple[str, dict]] = []
        self.scrape_options: list[dict] = []

    def search(self, query: str, **options):
        self.searches.append((query, options))
        return SimpleNamespace(
            web=[
                SimpleNamespace(
                    url="https://example.com/pre",
                    title="上市前报道",
                    publishedDate="2025-02-20",
                ),
                SimpleNamespace(
                    url="https://example.com/post",
                    title="上市后报道",
                    publishedDate="2025-03-04",
                ),
                SimpleNamespace(url="https://example.com/metadata-date", title="正文日期"),
                SimpleNamespace(url="https://example.com/no-date", title="无日期"),
                SimpleNamespace(
                    url="https://example.com/fifth",
                    title="第五篇报道",
                    publishedDate="2025-02-26",
                ),
            ],
            news=[],
        )

    def scrape(self, url: str, **options):
        self.scraped.append(url)
        self.scrape_options.append(options)
        if url.endswith("/pre"):
            return SimpleNamespace(
                markdown="上市前新闻正文",
                metadata={"title": "上市前报道", "publishedTime": "2025-02-20"},
            )
        if url.endswith("/metadata-date"):
            return SimpleNamespace(
                markdown="从HTML验证发布日期",
                raw_html='<meta property="article:published_time" content="2025-02-25">',
                metadata={"title": "正文日期"},
            )
        if url.endswith("/fifth"):
            return SimpleNamespace(
                markdown="第五篇新闻正文",
                metadata={"title": "第五篇报道", "publishedDate": "2025-02-26"},
            )
        return SimpleNamespace(markdown="日期不明正文", metadata={"title": "无日期"})


class FirecrawlConfigTest(unittest.TestCase):
    def test_local_yaml_and_environment_override_without_exposing_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "firecrawl.yaml"
            local = Path(tmp) / "firecrawl.local.yaml"
            base.write_text(
                "firecrawl:\n  api_key: base-key\n  enabled: true\n  search:\n    max_urls: 10\n    historical_lookback_years: 5\n",
                encoding="utf-8",
            )
            local.write_text(
                "firecrawl:\n  api_key: local-key\n  search:\n    max_urls: 12\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "env-key"}, clear=False):
                settings = resolve_firecrawl_settings(
                    settings_path=base,
                    local_settings_path=local,
                )

        self.assertEqual(settings["api_key"], "env-key")
        self.assertEqual(settings["search"]["max_urls"], 10)
        self.assertEqual(settings["search"]["limit_per_query"], 10)
        self.assertEqual(settings["scrape"]["max_requests"], 10)
        self.assertTrue(settings["search"]["use_tbs_date_filter"])
        self.assertEqual(settings["search"]["lookback_days"], 1825)
        self.assertTrue(settings["cache"]["reuse_raw_results"])
        self.assertTrue(settings["enabled"])
        public = FirecrawlNewsCollector(settings, client=FakeFirecrawl()).public_status()
        self.assertNotIn("api_key", public)
        self.assertNotIn("env-key", str(public))


class FirecrawlCollectorTest(unittest.TestCase):
    def test_ten_article_limits_and_rolling_window(self) -> None:
        class TenResultClient:
            def __init__(self) -> None:
                self.search_options = None
                self.scrape_urls = []

            def search(self, query: str, **options):
                self.search_options = options
                return SimpleNamespace(web=[
                    SimpleNamespace(
                        url=f"https://example.com/{index}",
                        title=f"新闻{index}",
                        publishedDate="2024-12-15",
                    )
                    for index in range(12)
                ])

            def scrape(self, url: str, **options):
                self.scrape_urls.append(url)
                return SimpleNamespace(
                    markdown="正文",
                    metadata={"publishedTime": "2024-12-15"},
                )

        client = TenResultClient()
        settings = {
            "enabled": True,
            "configured": True,
            "requested_enabled": True,
            "api_key": "test",
            "search": {
                "sources": ["web"], "limit_per_query": 10, "max_urls": 10,
                "lookback_days": 365, "use_tbs_date_filter": True,
            },
            "scrape": {"max_requests": 10},
            "cache": {"reuse_raw_results": False},
        }
        with tempfile.TemporaryDirectory() as tmp:
            status = FirecrawlNewsCollector(settings, client=client).collect(
                company="翰思艾泰", stock_code="03378",
                listing_date=date(2025, 12, 23), as_of_date=date(2025, 12, 15),
                news_dir=tmp,
            )

        self.assertEqual(client.search_options["limit"], 10)
        self.assertEqual(client.search_options["tbs"], "cdr:1,cd_min:12/15/2024,cd_max:12/15/2025")
        self.assertEqual(len(client.scrape_urls), 10)
        self.assertEqual(status["accepted_articles"], 10)
        self.assertEqual(status["window_start"], "2024-12-15")

    def test_search_scrape_cutoff_and_cache(self) -> None:
        fake = FakeFirecrawl()
        settings = {
            "enabled": True,
            "requested_enabled": True,
            "configured": True,
            "api_key": "not-returned",
            "api_url": "https://api.firecrawl.dev",
            "fetch_policy": "on_missing",
            "search": {
                "query_template": '"{company}" 风险 争议 监管 舆论 新闻',
                "sources": ["web", "news"],
                "limit_per_query": 5,
                "max_urls": 5,
                "timeout_ms": 120000,
                "location": "Hong Kong",
                "use_tbs_date_filter": True,
                "historical_lookback_years": 5,
                "lookback_days": 365,
            },
            "scrape": {
                "max_requests": 5,
                "only_main_content": True,
                "max_content_chars": 8000,
                "timeout_ms": 120000,
                "max_age_ms": 86400000,
            },
            "cache": {
                "merge_existing": True,
                "save_raw_results": True,
                "reuse_raw_results": True,
            },
            "settings_path": "test.yaml",
            "local_settings_path": "test.local.yaml",
        }
        with tempfile.TemporaryDirectory() as tmp:
            status = FirecrawlNewsCollector(settings, client=fake).collect(
                company="测试公司",
                stock_code="02097",
                listing_date=date(2025, 3, 3),
                as_of_date=date(2025, 3, 2),
                news_dir=tmp,
            )
            cache = Path(tmp) / "02097.csv"
            with cache.open("r", encoding="utf-8-sig", newline="") as source:
                rows = list(csv.DictReader(source))
            raw_cache = Path(status["raw_cache_file"])
            raw_payload = json.loads(raw_cache.read_text(encoding="utf-8"))
            calls_before_reuse = (len(fake.searches), len(fake.scraped))
            reused = FirecrawlNewsCollector(settings, client=fake).collect(
                company="测试公司",
                stock_code="02097",
                listing_date=date(2025, 3, 3),
                as_of_date=date(2025, 3, 2),
                news_dir=tmp,
            )

        self.assertEqual(status["accepted_articles"], 3)
        self.assertEqual(status["rejected_after_cutoff"], 1)
        self.assertEqual(status["rejected_missing_date"], 1)
        self.assertEqual(status["search_requests"], 1)
        self.assertEqual(status["scrape_requests"], 5)
        self.assertEqual(len(fake.searches), 1)
        self.assertEqual(fake.searches[0][0], '"测试公司" 风险 争议 监管 舆论 新闻')
        self.assertEqual(fake.searches[0][1]["limit"], 5)
        self.assertEqual(
            fake.searches[0][1]["tbs"],
            "cdr:1,cd_min:03/02/2024,cd_max:03/02/2025",
        )
        self.assertEqual(fake.scrape_options[0]["formats"], ["markdown", "rawHtml"])
        self.assertIn("https://example.com/post", fake.scraped)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["发布时间"] <= "2025-03-02" for row in rows))
        self.assertTrue(all(row["抓取方式"].startswith("firecrawl_search+scrape") for row in rows))
        self.assertEqual(len(raw_payload["articles"]), 5)
        missing = next(
            item for item in raw_payload["articles"]
            if item["url"].endswith("/no-date")
        )
        self.assertEqual(missing["markdown"], "日期不明正文")
        self.assertEqual(missing["rejection_reason"], "missing_publication_date")
        html_dated = next(
            item for item in raw_payload["articles"]
            if item["url"].endswith("/metadata-date")
        )
        self.assertEqual(html_dated["date_source"], "html_meta:article:published_time")
        self.assertEqual(calls_before_reuse, (len(fake.searches), len(fake.scraped)))
        self.assertTrue(reused["raw_cache_used"])
        self.assertEqual(reused["search_requests"], 0)
        self.assertEqual(reused["scrape_requests"], 0)
        self.assertEqual(reused["accepted_articles"], 3)
        self.assertNotIn("not-returned", str(status))

    def test_homepage_is_saved_but_not_scraped(self) -> None:
        class HomepageClient:
            def __init__(self) -> None:
                self.scraped: list[str] = []

            def search(self, query: str, **options):
                return SimpleNamespace(
                    web=[
                        SimpleNamespace(url="https://m.example.com/", title="网站首页"),
                        SimpleNamespace(url="https://example.com/2024/01/02/article", title="文章"),
                    ]
                )

            def scrape(self, url: str, **options):
                self.scraped.append(url)
                return SimpleNamespace(markdown="文章正文", raw_html="", metadata={})

        client = HomepageClient()
        settings = {
            "enabled": True,
            "requested_enabled": True,
            "configured": True,
            "fetch_policy": "on_missing",
            "search": {
                "query_template": '"{company}" 新闻', "sources": ["web"],
                "limit_per_query": 5, "max_urls": 5, "timeout_ms": 60000,
                "location": "Hong Kong", "use_tbs_date_filter": True,
                "historical_lookback_years": 5,
            },
            "scrape": {"max_requests": 5, "only_main_content": True, "timeout_ms": 30000},
            "cache": {"merge_existing": True, "reuse_raw_results": True},
        }
        with tempfile.TemporaryDirectory() as tmp:
            status = FirecrawlNewsCollector(settings, client=client).collect(
                company="测试公司", stock_code="02097",
                listing_date=date(2025, 3, 3), as_of_date=date(2025, 3, 2), news_dir=tmp,
            )
            payload = json.loads(Path(status["raw_cache_file"]).read_text(encoding="utf-8"))

        self.assertEqual(status["filtered_homepage_urls"], 1)
        self.assertEqual(status["scrape_requests"], 1)
        self.assertEqual(client.scraped, ["https://example.com/2024/01/02/article"])
        homepage = next(item for item in payload["articles"] if item["url"].endswith("/"))
        self.assertEqual(homepage["rejection_reason"], "homepage_url")


class FirecrawlMarketAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_accepts_any_positive_local_count_up_to_the_cap(self) -> None:
        settings = {
            "enabled": False,
            "requested_enabled": False,
            "configured": False,
            "fetch_policy": "on_missing",
            "search": {"max_urls": 10, "lookback_days": 365},
            "cache": {"reuse_raw_results": False},
        }
        snapshot = SimpleNamespace(
            company="翰思艾泰",
            stock_code="03378",
            listing_date=date(2025, 12, 23),
            as_of_date=date(2025, 12, 15),
        )
        agent = MarketAgent(firecrawl_settings=settings)
        with tempfile.TemporaryDirectory() as tmp:
            available = await agent._maybe_fetch_firecrawl_news(
                snapshot,
                news_dir=Path(tmp),
                local_news_status={
                    "pre_cutoff_rows": 1,
                    "in_window_rows": 1,
                    "max_articles": 10,
                },
            )
            missing = await agent._maybe_fetch_firecrawl_news(
                snapshot,
                news_dir=Path(tmp),
                local_news_status={
                    "pre_cutoff_rows": 0,
                    "in_window_rows": 0,
                    "max_articles": 10,
                },
            )

        self.assertEqual(available["skip_reason"], "usable_local_news_in_window")
        self.assertEqual(available["remaining_capacity"], 9)
        self.assertEqual(missing["skip_reason"], "firecrawl_disabled")
        self.assertEqual(missing["remaining_capacity"], 10)

    async def test_agent_fetches_cache_before_opinion_resolution(self) -> None:
        fake = FakeFirecrawl()
        settings = {
            "enabled": True,
            "requested_enabled": True,
            "configured": True,
            "api_key": "agent-test-key",
            "api_url": "https://api.firecrawl.dev",
            "fetch_policy": "on_missing",
            "search": {
                "query_template": '"{company}" 风险 争议 监管 舆论 新闻',
                "sources": ["web", "news"],
                "limit_per_query": 5,
                "max_urls": 5,
                "timeout_ms": 120000,
                "location": "Hong Kong",
                "use_tbs_date_filter": True,
                "historical_lookback_years": 5,
            },
            "scrape": {
                "max_requests": 5,
                "only_main_content": True,
                "max_content_chars": 8000,
                "timeout_ms": 120000,
                "max_age_ms": 86400000,
            },
            "cache": {
                "merge_existing": True,
                "save_raw_results": True,
                "reuse_raw_results": True,
            },
            "settings_path": "test.yaml",
            "local_settings_path": "test.local.yaml",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            features = root / "features.csv"
            with features.open("w", encoding="utf-8", newline="") as target:
                writer = csv.DictWriter(
                    target,
                    fieldnames=[
                        "stock_code",
                        "company",
                        "listing_date",
                        "as_of_date",
                        "market_observation_date",
                        "industry",
                        "hsi_ret_20d",
                        "ind_ret_20d",
                        "avg_day1_return_60d",
                        "subscription_multiple",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "stock_code": "02097",
                        "company": "测试公司",
                        "listing_date": "2025-03-03",
                        "as_of_date": "2025-03-02",
                        "market_observation_date": "2025-02-28",
                        "industry": "消费",
                        "hsi_ret_20d": "0.02",
                        "ind_ret_20d": "0.03",
                        "avg_day1_return_60d": "0.1",
                        "subscription_multiple": "5",
                    }
                )
            result = await MarketAgent(
                firecrawl_settings=settings,
                firecrawl_client=fake,
            ).run(
                "doc-firecrawl",
                stock_code="02097",
                features_csv=features,
                news_dir=root / "news",
            )

        self.assertEqual(result.features["firecrawl"]["accepted_articles"], 3)
        self.assertEqual(result.features["firecrawl"]["search_requests"], 1)
        self.assertEqual(result.features["firecrawl"]["scrape_requests"], 5)
        self.assertEqual(
            result.features["sentiment_analysis"]["data_boundary"]["news_pre_cutoff_rows"],
            3,
        )
        self.assertFalse(result.features["public_opinion_used"])
        self.assertEqual(
            result.features["public_opinion"]["unavailable_reason"],
            "prelisting_candidates_exist_but_relevance_not_verified",
        )
        report = result.features["sentiment_report_markdown"]
        self.assertIn("Firecrawl搜索1次", report)
        self.assertIn("原始正文已保存", report)
        self.assertIn("raw/02097_2025-03-02_firecrawl.json", report)
        self.assertNotIn("agent-test-key", str(result.model_dump(mode="json")))

if __name__ == "__main__":
    unittest.main()
