from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from src.models.market import MarketSnapshot
from src.skills.score_market_history import HistoricalMarketRiskScorer


class HistoricalMarketRiskScorerTest(unittest.TestCase):
    def test_uses_only_prior_rows_and_exposes_issue_price_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"
            fields = ["stock_code", "as_of_date", "hsi_ret_20d", "ind_ret_20d", "break_rate_60d"]
            target_date = date(2025, 6, 30)
            rows = []
            for i in range(20):
                observed = target_date - timedelta(days=30 * (i + 1))
                rows.append({
                    "stock_code": str(i).zfill(5), "as_of_date": observed.isoformat(),
                    "hsi_ret_20d": str(-0.10 + i * 0.01),
                    "ind_ret_20d": str(-0.08 + i * 0.008),
                    "break_rate_60d": str(0.05 + i * 0.02),
                })
            # This future extreme must never enter the calibration cohort.
            rows.append({"stock_code": "99999", "as_of_date": "2025-07-01",
                         "hsi_ret_20d": "999", "ind_ret_20d": "999", "break_rate_60d": "999"})
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader(); writer.writerows(rows)
            snapshot = MarketSnapshot(
                stock_code="02097", company="测试", listing_date=date(2025, 7, 1),
                as_of_date=target_date, cutoff_verified=True,
                features={"hsi_ret_20d": -0.2, "ind_ret_20d": -0.15,
                          "break_rate_60d": 0.6, "issue_price": 10.0},
            )
            result = HistoricalMarketRiskScorer().score(snapshot, features_csv=path)

        self.assertEqual(result.risk_anchor, "issue_price")
        self.assertEqual(result.secondary_market_return_base, "first_trading_day_open")
        self.assertTrue(result.issue_price_available)
        self.assertAlmostEqual(result.effective_module_weights["macro"], 1 / 3, places=5)
        macro = result.module_scores["macro"].indicators[0]
        self.assertEqual(macro.history_sample_size, 20)
        self.assertGreater(macro.risk_score, 80)

    def test_missing_issue_price_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["as_of_date", "hsi_ret_20d"])
                writer.writeheader()
                for i in range(12):
                    writer.writerow({"as_of_date": f"2024-{i + 1:02d}-01", "hsi_ret_20d": i / 100})
            snapshot = MarketSnapshot(stock_code="00001", listing_date=date(2025, 2, 2),
                                      as_of_date=date(2025, 2, 1), cutoff_verified=True,
                                      features={"hsi_ret_20d": 0.0})
            result = HistoricalMarketRiskScorer().score(snapshot, features_csv=path)
        self.assertFalse(result.issue_price_available)
        self.assertEqual(result.break_anchor_status, "unavailable")
        self.assertTrue(any("issue_price unavailable" in item for item in result.limitations))


if __name__ == "__main__":
    unittest.main()

