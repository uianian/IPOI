from __future__ import annotations

import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from service.thought_mapper import map_market_event


def _kinds(thoughts: list[dict]) -> list[str | None]:
    return [(item.get("meta") or {}).get("kind") for item in thoughts]


def test_market_step_statuses_match_shared_tool_contract() -> None:
    running = map_market_event(
        {
            "event": "step",
            "name": "firecrawl_public_opinion",
            "status": "running",
        }
    )
    assert _kinds(running) == ["tool_call"]
    assert running[0]["meta"]["toolStatus"] == "running"

    degraded = map_market_event(
        {
            "event": "step",
            "name": "firecrawl_public_opinion",
            "status": "degraded",
            "output": {"accepted_articles": 2},
        }
    )
    assert _kinds(degraded) == ["tool_result"]
    assert degraded[0]["meta"]["toolStatus"] == "degraded"
    assert degraded[0]["type"] == "finding"
    assert "已降級" in degraded[0]["content"] or "已降级" in degraded[0]["content"]


def test_market_news_evidence_preserves_safe_metadata() -> None:
    thoughts = map_market_event(
        {
            "event": "step",
            "name": "validate_public_opinion",
            "status": "ok",
            "output": {
                "evidence": [
                    {
                        "title": "示例新闻",
                        "url": "https://example.test/news/1",
                        "published_at": "2025-02-01",
                        "excerpt": "公司公告显示业务进展。",
                        "source_type": "web",
                    }
                ]
            },
        }
    )
    assert "tool_result" in _kinds(thoughts)
    evidence = next(item for item in thoughts if (item.get("meta") or {}).get("kind") == "evidence")
    snippet = evidence["meta"]["evidence"][0]
    assert snippet["title"] == "示例新闻"
    assert snippet["url"].startswith("https://")
    assert snippet["date"] == "2025-02-01"
    assert "公司公告" in snippet["excerpt"]


def test_market_skipped_reason_and_report_conclusion_are_visible() -> None:
    skipped = map_market_event(
        {
            "event": "step",
            "name": "firecrawl_public_opinion",
            "status": "skipped",
            "output": {"reason": "usable_local_news_in_window"},
        }
    )
    assert "usable_local_news_in_window" in skipped[0]["content"]
    assert ("检索 Firecrawl 舆情" in skipped[0]["content"]) or (
        "檢索 Firecrawl 輿情" in skipped[0]["content"]
    )

    report = map_market_event(
        {
            "event": "step",
            "name": "build_market_report",
            "status": "ok",
            "output": {"summary": "市场风险中等"},
        }
    )
    assert report[0]["type"] == "conclusion"
    assert report[0]["meta"]["kind"] == "model_think"


def test_market_risk_points_and_score_are_findings_and_conclusion() -> None:
    thoughts = map_market_event(
        {
            "event": "step",
            "name": "score_market_rules",
            "status": "ok",
            "output": {
                "final_score": 72,
                "risk_points": [
                    {
                        "code": "MARKET_NEWS_RISK",
                        "description": "舆情偏弱",
                        "evidence_page": 3,
                    }
                ],
            },
        }
    )
    assert "model_think" in _kinds(thoughts)
    risk = next(item for item in thoughts if (item.get("meta") or {}).get("kind") == "risk_point")
    assert risk["ref"] == "p.3"
    assert risk["agentId"] == "market"


def test_market_result_maps_risk_points() -> None:
    thoughts = map_market_event(
        {
            "event": "result",
            "payload": {
                "risk_score": 60,
                "summary": "市场风险中等",
                "risk_points": [{"code": "M1", "description": "波动较高"}],
            },
        }
    )
    assert thoughts[0]["type"] == "conclusion"
    assert any((item.get("meta") or {}).get("kind") == "risk_point" for item in thoughts)
