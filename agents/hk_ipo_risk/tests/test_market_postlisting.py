from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from src.skills.score_postlisting import PostlistingRiskScorer


FIELDS = ["stock_code", "listing_date", "checkpoint", "trading_day", "observation_date",
          "first_trading_day_open", "issue_price", "below_issue_price",
          "cumulative_return_from_open", "issue_price_return", "excess_hsi_return",
          "excess_industry_return", "max_drawdown_from_open", "realized_volatility", "turnover_change"]


class PostlistingRiskScorerTest(unittest.TestCase):
    def test_scores_every_five_days_against_same_age_prior_ipos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoints.csv"
            rows = []
            for i in range(12):
                listing = date(2023, 1, 1) + timedelta(days=i * 20)
                for day in (5, 10):
                    rows.append({"stock_code": str(i + 1).zfill(5), "listing_date": listing,
                                 "checkpoint": f"D{day}", "trading_day": day,
                                 "observation_date": listing + timedelta(days=day + 2),
                                 "first_trading_day_open": 10, "issue_price": 9,
                                 "below_issue_price": "false", "cumulative_return_from_open": i / 100,
                                 "issue_price_return": i / 100, "excess_hsi_return": i / 100,
                                 "excess_industry_return": i / 100, "max_drawdown_from_open": -i / 100,
                                 "realized_volatility": i / 100, "turnover_change": i / 100})
            for day in (5, 10):
                rows.append({"stock_code": "02451", "listing_date": "2024-01-01",
                             "checkpoint": f"D{day}", "trading_day": day,
                             "observation_date": f"2024-01-{day + 2:02d}",
                             "first_trading_day_open": 10, "issue_price": 9,
                             "below_issue_price": "true", "cumulative_return_from_open": -0.3,
                             "issue_price_return": -0.2, "excess_hsi_return": -0.3,
                             "excess_industry_return": -0.3, "max_drawdown_from_open": -0.4,
                             "realized_volatility": 0.5, "turnover_change": -0.5})
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
            results = PostlistingRiskScorer().load_and_score("2451.HK", checkpoints_csv=path, through_day=10)

        self.assertEqual([item.trading_day for item in results], [5, 10])
        self.assertTrue(all(item.below_issue_price for item in results))
        self.assertTrue(all(item.risk_anchor == "issue_price" for item in results))
        primary = next(metric for metric in results[0].metrics if metric.metric == "below_issue_price")
        self.assertEqual(primary.risk_score, 100)
        self.assertEqual(primary.configured_weight, 0.35)
        self.assertGreater(results[0].realized_risk_score, 90)


if __name__ == "__main__":
    unittest.main()

