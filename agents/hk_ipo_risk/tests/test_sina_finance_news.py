from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

import httpx

from src.tools.sina_finance_news import SinaFinanceNewsCollector


class SinaFinanceNewsCollectorTest(unittest.IsolatedAsyncioTestCase):
    async def test_normalizes_and_enforces_cutoff(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["X-Api-Key"], "secret")
            return httpx.Response(200, json={"data": {"items": [
                {"headline": "上市前报道", "body": "正文", "time": "2024-01-01", "link": "https://finance.sina.test/a"},
                {"headline": "上市后报道", "body": "未来", "time": "2024-02-01", "link": "https://finance.sina.test/b"},
            ]}})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        settings = {
            "enabled": True, "configured": True, "requested_enabled": True,
            "base_url": "https://api.test/search", "api_key": "secret",
            "auth": {"location": "header", "name": "X-Api-Key"},
            "response": {"items_path": "data.items", "fields": {
                "title": "headline", "content": "body", "published_at": "time", "url": "link"}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            status = await SinaFinanceNewsCollector(settings, client=client).collect(
                company="测试", stock_code="02451", as_of_date=date(2024, 1, 15), news_dir=tmp)
            with (Path(tmp) / "02451.csv").open("r", encoding="utf-8-sig") as stream:
                rows = list(csv.DictReader(stream))
        await client.aclose()
        self.assertEqual(status["accepted_articles"], 1)
        self.assertEqual(status["rejected_after_cutoff"], 1)
        self.assertEqual(rows[0]["抓取方式"], "sina_finance_api")


if __name__ == "__main__":
    unittest.main()

