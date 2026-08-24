from __future__ import annotations

from src.skills.validate_postlisting_performance import build_postlisting_summary


def test_postlisting_summary_is_natural_chinese_without_backend_codes() -> None:
    checkpoints = [
        {"window": "D1", "alignment": "hit", "belowIssuePrice": True, "issuePriceReturn": -0.4625},
        {"window": "D5", "alignment": "partial", "belowIssuePrice": True, "issuePriceReturn": -0.500625},
        {"window": "D20", "alignment": "partial", "belowIssuePrice": True, "issuePriceReturn": -0.465625},
        {"window": "D60", "alignment": "hit", "belowIssuePrice": True, "issuePriceReturn": -0.15625},
    ]

    summary = build_postlisting_summary(
        checkpoints,
        weighted_hit_score=72.5,
        d5_priority_hit=False,
        status="completed",
    )

    assert summary == (
        "本次上市后表现验证覆盖上市首日、上市后5个交易日内、上市后20个交易日内和"
        "上市后60个交易日内，共4个检查点。预测加权命中分为72.5分。"
        "上市首日和上市后60个交易日内的预测与实际表现一致；"
        "上市后5个交易日内和上市后20个交易日内的预测与实际表现部分一致。"
        "上市后5个交易日重点预警未命中。4个检查点的实际价格低于发行价，"
        "其中上市后5个交易日内相对发行价跌幅最大，为50.06%。"
    )
    for backend_term in ("D1", "D5", "D20", "D60", "alignment", "partial", "hit"):
        assert backend_term not in summary


def test_postlisting_summary_handles_unavailable_data() -> None:
    summary = build_postlisting_summary(
        [], weighted_hit_score=None, d5_priority_hit=None, status="not_available"
    )
    assert summary == "尚未取得可用于验证的上市后行情数据，当前无法评估事前预测与实际表现的一致程度。"
