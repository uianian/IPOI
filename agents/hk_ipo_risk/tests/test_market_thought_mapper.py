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
    assert report == []


def test_market_risk_points_and_score_are_findings_and_conclusion() -> None:
    thoughts = map_market_event(
        {
            "event": "step",
            "name": "validate_public_opinion",
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
    assert "model_think" not in _kinds(thoughts)
    risk = next(item for item in thoughts if (item.get("meta") or {}).get("kind") == "risk_point")
    assert "ref" not in risk
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
    assert thoughts[0]["content"] in {"市场风险中等", "市場風險中等"}
    assert thoughts[0]["meta"]["sourceField"] == "agents.market.summary"
    assert len(thoughts) == 1


def test_market_dimension_evidence_is_compact_chinese_only_and_has_no_pages() -> None:
    thoughts = map_market_event(
        {
            "event": "step",
            "name": "run_market_skill",
            "status": "ok",
            "output": {
                "module": "industry",
                "result": {"risk_score": 78.32},
                "evidence": [
                    {
                        "evidence_id": "INDUSTRY-RETURN-20D",
                        "module": "industry",
                        "indicator": "ind_ret_20d",
                        "label": "行业20日收益",
                        "display_value": "-4.94%",
                        "direction": "pressure",
                        "interpretation": "所属行业中期下跌",
                        "as_of_date": "2025-12-22",
                        "page": 99,
                    },
                    *[
                        {
                            "evidence_id": f"INDUSTRY-{index}",
                            "label": f"行业指标{index}",
                            "display_value": f"{index}%",
                            "direction": "support",
                            "interpretation": "对发行形成支持",
                            "as_of_date": "2025-12-22",
                        }
                        for index in range(2, 7)
                    ],
                ],
            },
        }
    )
    assert len(thoughts) == 1
    thought = thoughts[0]
    assert thought["meta"]["kind"] == "market_dimension_evidence"
    assert thought["meta"]["riskScore"] == 78.32
    assert thought["meta"]["evidence"][0]["evidenceId"] == "INDUSTRY-RETURN-20D"
    assert "page" not in thought["meta"]["evidence"][0]
    assert thought["meta"]["evidenceCount"] == 6
    assert thought["meta"]["displayEvidenceCount"] == 4
    assert "展示 4/6 条" in thought["content"] or "展示 4/6 條" in thought["content"]
    assert "所属行业情绪" in thought["content"] or "所屬行業情緒" in thought["content"]
    assert "行业20日收益：-4.94%" in thought["content"] or "行業20日收益：-4.94%" in thought["content"]
    assert "压制" in thought["content"] or "壓制" in thought["content"]
    assert "Industry" not in thought["content"]
    assert "ind_ret_20d" not in thought["content"]
    assert "Pressure" not in thought["content"]
    assert "行业指标5" not in thought["content"] and "行業指標5" not in thought["content"]
    assert "ref" not in thought


def test_market_internal_scoring_and_submit_steps_are_hidden() -> None:
    for name in ("score_market_with_llm", "score_market_rules", "submit_market_report", "build_market_report"):
        assert map_market_event({"event": "step", "name": name, "status": "ok", "output": {}}) == []
    assert map_market_event({
        "event": "step",
        "name": "build_market_report",
        "status": "ok",
        "output": {"evidence": [{"evidence_id": "MACRO-HSI-5D", "label": "恒指5日收益"}]},
    }) == []
