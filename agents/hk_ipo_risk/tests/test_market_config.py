from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import IPOI_ROOT, resolve_market_agent_settings


class MarketAgentConfigTest(unittest.TestCase):
    def test_default_config_contains_only_fixed_parameters(self) -> None:
        settings = resolve_market_agent_settings()

        self.assertNotIn("stock_code", settings)
        self.assertNotIn("doc_id", settings)
        self.assertTrue(Path(settings["data"]["features_csv"]).is_absolute())
        self.assertTrue(Path(settings["data"]["news_dir"]).is_absolute())
        self.assertTrue(settings["cutoff"]["strict_prelisting"])
        self.assertIn("llm", settings)
        self.assertIn("firecrawl", settings)
        self.assertIn("output", settings)

    def test_local_config_deep_overrides_and_resolves_repo_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "market_agent.yaml"
            local = Path(tmp) / "market_agent.local.yaml"
            base.write_text(
                """
market_agent:
  data:
    features_csv: market/data/base.csv
    news_dir: market/data/news
  cutoff:
    strict_prelisting: true
  llm:
    enabled: true
  output:
    directory: agents/hk_ipo_risk/.runtime/base
""".strip()
                + "\n",
                encoding="utf-8",
            )
            local.write_text(
                """
market_agent:
  data:
    features_csv: market/data/local.csv
  llm:
    enabled: false
  output:
    directory: agents/hk_ipo_risk/.runtime/local
""".strip()
                + "\n",
                encoding="utf-8",
            )
            settings = resolve_market_agent_settings(
                settings_path=base,
                local_settings_path=local,
            )

        self.assertEqual(
            Path(settings["data"]["features_csv"]),
            IPOI_ROOT / "market/data/local.csv",
        )
        self.assertEqual(
            Path(settings["data"]["news_dir"]),
            IPOI_ROOT / "market/data/news",
        )
        self.assertFalse(settings["llm"]["enabled"])
        self.assertEqual(
            Path(settings["output"]["directory"]),
            IPOI_ROOT / "agents/hk_ipo_risk/.runtime/local",
        )


if __name__ == "__main__":
    unittest.main()

