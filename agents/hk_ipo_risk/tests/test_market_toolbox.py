from __future__ import annotations

import unittest

from src.tools.schemas import MARKET_TOOL_SCHEMAS, ToolRegistry


class MarketToolSchemaTest(unittest.TestCase):
    def test_first_version_exposes_required_tools_but_not_retrieval(self) -> None:
        names = {(item.get("function") or {}).get("name") for item in MARKET_TOOL_SCHEMAS}
        self.assertEqual(names, {
            "lookup_market_row",
            "run_market_skill",
            "search_market_evidence",
            "run_market_rule_checks",
            "score_market_with_llm",
            "submit_market_report",
        })
        self.assertNotIn("retrieve_market", names)

    def test_tool_registry_returns_structured_unknown_tool_error(self) -> None:
        registry = ToolRegistry()
        result = __import__("asyncio").run(registry.execute("missing", {}, {}))
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()

