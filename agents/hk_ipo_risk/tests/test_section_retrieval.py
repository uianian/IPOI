from __future__ import annotations

import asyncio
from pathlib import Path
import unittest

from src.skills.finance_toolbox import build_finance_tool_registry
from src.tools.retrieval_tool import retrieve_section_evidence

IPOI_ROOT = Path(__file__).resolve().parents[3]
MIXUE = (
    IPOI_ROOT
    / "pdf_parsing"
    / "output"
    / "samples_batch"
    / "02097_21-02-2025_蜜雪集團_全球發售"
    / "full_parse.json"
)


class SectionRetrievalTests(unittest.TestCase):
    @unittest.skipUnless(MIXUE.is_file(), "Mixue sample is not available")
    def test_franchise_query_routes_to_business_and_returns_pages(self) -> None:
        result = asyncio.run(
            retrieve_section_evidence(
                doc_id="mixue-test",
                intent="franchise",
                query="加盟 商业模式 风险 依赖",
                parse_json=MIXUE,
                top_k=5,
            )
        )
        self.assertEqual(
            [route["section_id"] for route in result["route"]][:3],
            ["business", "risk_factors", "summary"],
        )
        self.assertEqual(result["n"], 5)
        self.assertTrue(all(hit["page"] for hit in result["hits"]))
        self.assertTrue(
            any(hit["section_id"] == "business" for hit in result["hits"])
        )

    def test_finance_registry_replaces_retrieve_text(self) -> None:
        names = build_finance_tool_registry().names()
        self.assertIn("retrieve_context_evidence", names)
        self.assertNotIn("retrieve_text", names)


if __name__ == "__main__":
    unittest.main()
