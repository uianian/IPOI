from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.agents.market_agent import MarketAgent
from src.models.market import MarketEvidence, PublicOpinionAssessment
from src.skills.explain_market import MarketEvidenceBuilder
from src.skills.score_market import MarketRiskScorer
from src.tools.market_data import MarketDataLoader


FIELDS = [
    "stock_code",
    "company",
    "listing_date",
    "as_of_date",
    "market_observation_date",
    "industry",
    "hsi_ret_20d",
    "mkt_turnover_chg_20d",
    "vhsi_avg_5d",
    "ind_ret_20d",
    "ind_excess_20d",
    "ipo_count_30d",
    "avg_day1_return_60d",
    "break_rate_60d",
    "subscription_multiple",
    "news_rows",
    "outcome_day1_return",
]


def _write_features(path: Path, *, include_as_of: bool = True) -> None:
    row = {
        "stock_code": "2097",
        "company": "测试公司",
        "listing_date": "2025-03-03",
        "as_of_date": "2025-03-02" if include_as_of else "",
        "market_observation_date": "2025-02-28",
        "industry": "必需性消费",
        "hsi_ret_20d": "0.05",
        "mkt_turnover_chg_20d": "0.10",
        "vhsi_avg_5d": "19.0",
        "ind_ret_20d": "0.08",
        "ind_excess_20d": "0.03",
        "ipo_count_30d": "6",
        "avg_day1_return_60d": "0.12",
        "break_rate_60d": "0.25",
        "subscription_multiple": "80",
        "news_rows": "4",
        "outcome_day1_return": "0.99",
    }
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(row)


class MarketDataLoaderTest(unittest.TestCase):
    def test_loader_enforces_cutoff_and_excludes_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"
            _write_features(path)
            snapshot = MarketDataLoader(path).load_snapshot("02097.HK")

        self.assertEqual(snapshot.stock_code, "02097")
        self.assertTrue(snapshot.cutoff_verified)
        self.assertNotIn("outcome_day1_return", snapshot.features)
        self.assertNotIn("news_rows", snapshot.features)
        self.assertEqual(snapshot.features["hsi_ret_20d"], 0.05)

    def test_strict_loader_rejects_legacy_snapshot_without_as_of(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"
            _write_features(path, include_as_of=False)
            with self.assertRaisesRegex(ValueError, "unverified market cutoff"):
                MarketDataLoader(path, strict_cutoff=True).load_snapshot("02097")

    def test_news_availability_explains_post_cutoff_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "features.csv"
            news_dir = root / "news"
            news_dir.mkdir()
            _write_features(path)
            with (news_dir / "02097.csv").open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["新闻标题", "新闻内容", "发布时间", "文章来源", "新闻链接"])
                writer.writeheader()
                writer.writerow({
                    "新闻标题": "上市后新闻",
                    "新闻内容": "不应进入上市前分析",
                    "发布时间": "2025-03-04 10:00:00",
                    "文章来源": "测试媒体",
                    "新闻链接": "https://example.com/post-listing",
                })
            loader = MarketDataLoader(path, news_dir=news_dir)
            status = loader.inspect_news_availability(loader.load_snapshot("02097"))

        self.assertEqual(status["total_rows"], 1)
        self.assertEqual(status["pre_cutoff_rows"], 0)
        self.assertEqual(status["unavailable_reason"], "all_local_news_after_as_of_date")


class MarketWeightPolicyTest(unittest.TestCase):
    def _snapshot(self):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "features.csv"
        _write_features(path)
        return tmp, MarketDataLoader(path).load_snapshot("02097")

    def test_without_reliable_public_opinion_uses_three_equal_weights(self) -> None:
        tmp, snapshot = self._snapshot()
        self.addCleanup(tmp.cleanup)
        pack = MarketRiskScorer().score(snapshot)

        self.assertFalse(pack.public_opinion_used)
        self.assertAlmostEqual(pack.effective_weights["macro"], 1 / 3, places=5)
        self.assertAlmostEqual(pack.effective_weights["industry"], 1 / 3, places=5)
        self.assertAlmostEqual(pack.effective_weights["ipo_market"], 1 / 3, places=5)
        self.assertEqual(pack.effective_weights["public_opinion"], 0.0)

    def test_with_reliable_public_opinion_uses_four_equal_weights(self) -> None:
        tmp, snapshot = self._snapshot()
        self.addCleanup(tmp.cleanup)
        opinion = PublicOpinionAssessment(
            available=True,
            risk_score=72,
            relevant_articles=3,
            direction_score=75,
            attention_score=60,
        )
        pack = MarketRiskScorer().score(snapshot, opinion)

        self.assertTrue(pack.public_opinion_used)
        self.assertEqual(pack.effective_weights, {
            "macro": 0.25,
            "industry": 0.25,
            "ipo_market": 0.25,
            "public_opinion": 0.25,
        })


class MarketAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_runs_without_llm_and_is_debate_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"
            _write_features(path)
            result = await MarketAgent().run(
                "doc-1",
                stock_code="02097",
                features_csv=path,
                news_dir=Path(tmp) / "news",
            )

        self.assertEqual(result.agent, "market")
        self.assertTrue(result.features["cutoff_verified"])
        self.assertTrue(result.features["debate_ready"])
        self.assertFalse(result.features["public_opinion_used"])
        self.assertNotIn("outcome_day1_return", result.metrics)
        sentiment = result.features["sentiment_analysis"]
        self.assertIn(sentiment["overall_state"], {"supportive", "neutral", "mixed", "pressured"})
        self.assertGreaterEqual(sentiment["overall_net_support"], -1)
        self.assertLessEqual(sentiment["overall_net_support"], 1)
        self.assertTrue(sentiment["aggregation_policy"]["not_a_0_100_score"])
        self.assertAlmostEqual(
            sentiment["aggregation_policy"]["effective_module_weights"]["macro"],
            1 / 3,
            places=5,
        )
        self.assertEqual(
            sentiment["aggregation_policy"]["effective_module_weights"]["public_opinion"],
            0.0,
        )
        self.assertEqual(
            set(sentiment["module_signal_balances"]),
            {"macro", "industry", "ipo_market", "public_opinion"},
        )
        self.assertIn("逐指标证据账本", sentiment["report_markdown"])
        evidence = next(
            item for item in sentiment["evidence_ledger"]
            if item["evidence_id"] == "MACRO-HSI-20D"
        )
        self.assertEqual(evidence["derived_field"], "hsi_ret_20d")
        self.assertIn("market/data/external/macro/hsi.csv", evidence["upstream_files"])
        self.assertTrue(evidence["formula"])
        self.assertIn("evidence_ledger", result.evidence_summary)
        self.assertEqual(result.features["rules_floor"], result.risk_score)
        self.assertIsNone(result.features["llm_score"])
        self.assertEqual(result.features["scoring_mode"], "historical_rules_floor")
        self.assertTrue(Path(result.features["debate_dossier_path"]).is_file())

        debate = await MarketAgent().challenge(result, "总控认为市场风险被高估")
        self.assertEqual(debate.stance, "maintain")
        self.assertTrue(debate.requires_new_evidence)

    async def test_agent_rejects_supplied_opinion_with_future_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"
            _write_features(path)
            opinion = PublicOpinionAssessment(
                available=True,
                risk_score=80,
                relevant_articles=1,
                evidence=[
                    MarketEvidence(
                        source="test",
                        field="public_opinion",
                        observation_date=date(2025, 3, 4),
                    )
                ],
            )
            result = await MarketAgent().run(
                "doc-1",
                stock_code="02097",
                features_csv=path,
                public_opinion=opinion,
            )

        self.assertFalse(result.features["public_opinion_used"])
        self.assertEqual(result.features["effective_weights"]["public_opinion"], 0.0)
        self.assertEqual(
            result.features["public_opinion"]["unavailable_reason"],
            "supplied_public_opinion_failed_cutoff_or_evidence_validation",
        )

    async def test_llm_prose_without_evidence_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"
            _write_features(path)
            snapshot = MarketDataLoader(path).load_snapshot("02097")
            score_pack = MarketRiskScorer().score(snapshot)
            opinion = PublicOpinionAssessment(available=False, unavailable_reason="test")
            analysis = MarketEvidenceBuilder().build(
                snapshot,
                score_pack,
                opinion,
                features_file=path,
                news_status={
                    "file": str(Path(tmp) / "news" / "02097.csv"),
                    "exists": False,
                    "total_rows": 0,
                    "pre_cutoff_rows": 0,
                    "unavailable_reason": "local_news_file_missing",
                },
            )
        original = analysis.overall_summary
        MarketAgent._apply_llm_sentiment_analysis(
            analysis,
            {"summary": "市场很好，但没有引用任何证据"},
        )
        self.assertEqual(analysis.overall_summary, original)
        MarketAgent._apply_llm_sentiment_analysis(
            analysis,
            {
                "summary": "恒指证据支持该判断[MACRO-HSI-20D]",
                "sentiment_state": "pressured",
            },
        )
        self.assertEqual(analysis.overall_summary, "恒指证据支持该判断[MACRO-HSI-20D]")
        self.assertNotEqual(analysis.overall_state, "pressured")

    def test_grounded_llm_score_is_audited_against_rules_floor(self) -> None:
        accepted = MarketAgent._validate_llm_risk_assessment(
            {
                "risk_score": 72,
                "confidence": 0.8,
                "score_reason": "行业承压 [IND-RET-20D]",
            },
            evidence_ids={"IND-RET-20D"},
        )
        self.assertIsNotNone(accepted)
        merged = MarketAgent._reconcile_scores(
            deterministic_score=58.5,
            deterministic_level="medium",
            llm_assessment=accepted,
        )
        self.assertEqual(merged["final_score"], 72.0)
        self.assertEqual(merged["method"], "max_llm_and_rules_floor")

        rejected = MarketAgent._validate_llm_risk_assessment(
            {"risk_score": 90, "score_reason": "没有引用证据"},
            evidence_ids={"IND-RET-20D"},
        )
        self.assertIsNone(rejected)
        non_numeric = MarketAgent._validate_llm_risk_assessment(
            {"risk_score": "unknown", "score_reason": "行业承压 [IND-RET-20D]"},
            evidence_ids={"IND-RET-20D"},
        )
        self.assertIsNone(non_numeric)


if __name__ == "__main__":
    unittest.main()

