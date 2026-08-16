from __future__ import annotations

import unittest

from src.tools.market_debate import MarketDebateToolbox


class MarketDebateToolboxTest(unittest.IsolatedAsyncioTestCase):
    async def test_prelisting_phase_blocks_realized_price_evidence(self) -> None:
        tools = MarketDebateToolbox(
            doc_id="doc", stock_code="02451", phase="prelisting",
            features_csv="unused.csv", news_dir="unused", checkpoints_csv="unused.csv",
        )
        result = await tools.execute("get_postlisting_checkpoint", {"trading_day": 5})
        self.assertFalse(result["available"])
        self.assertIn("temporal_guard", result["reason"])


if __name__ == "__main__":
    unittest.main()

