"""法务 Thought 映射单测：evidence_hits / risk_points / tool_call 与财务对齐。"""

from __future__ import annotations

import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from service.thought_mapper import map_legal_event  # noqa: E402


def _kinds(thoughts: list[dict]) -> list[str]:
    return [(t.get("meta") or {}).get("kind") for t in thoughts]


def test_pipeline_evidence_hits_maps_to_evidence_finding():
    event = {
        "event": "step",
        "agent": "legal",
        "name": "parse_grep",
        "status": "ok",
        "output": {"tool": "parse_grep", "hits": 3, "pages": [80, 120]},
        "evidence_hits": [
            {
                "page": 80,
                "excerpt": "關連交易須經獨立股東批准",
                "source_type": "text",
                "field_code": "RPT",
            },
            {
                "page": 120,
                "excerpt": "優先股赎回条款",
                "source_type": "text",
            },
        ],
    }
    thoughts = map_legal_event(event)
    kinds = _kinds(thoughts)
    assert "tool_result" in kinds
    assert "evidence" in kinds
    ev = next(t for t in thoughts if (t.get("meta") or {}).get("kind") == "evidence")
    snips = (ev.get("meta") or {}).get("evidence") or []
    assert len(snips) == 2
    assert snips[0]["page"] == 80
    assert "關連交易" in snips[0]["excerpt"]
    assert ev.get("ref") == "p.80"


def test_output_hits_list_not_int_count():
    """output.hits 为 int 时不得误当证据；为 list 时才出 evidence 卡。"""
    as_int = map_legal_event(
        {
            "event": "step",
            "name": "parse_grep",
            "status": "ok",
            "output": {"hits": 5},
        }
    )
    assert "evidence" not in _kinds(as_int)

    as_list = map_legal_event(
        {
            "event": "step",
            "name": "retrieve_legal",
            "status": "ok",
            "output": {
                "grep_hits": 2,
                "hits": [
                    {"page": 10, "excerpt": "控股股東持有超過50%", "source_type": "text"},
                ],
            },
        }
    )
    assert "evidence" in _kinds(as_list)


def test_output_risk_points_become_finding():
    event = {
        "event": "step",
        "name": "run_legal_skill",
        "status": "ok",
        "output": {
            "skill": "legal_related_party",
            "risk_point_count": 1,
            "risk_points": [
                {
                    "code": "RPT_RATIO_HIGH",
                    "description": "關聯交易佔比偏高",
                    "evidence_page": 95,
                    "evidence": [
                        {
                            "page": 95,
                            "excerpt": "關連交易佔收益約15%",
                            "source_type": "table",
                        }
                    ],
                }
            ],
            "evidence": [
                {"page": 95, "excerpt": "關連交易佔收益約15%", "source_type": "table"},
            ],
        },
    }
    thoughts = map_legal_event(event)
    kinds = _kinds(thoughts)
    assert "tool_result" in kinds
    assert "evidence" in kinds
    assert "risk_point" in kinds
    rp = next(t for t in thoughts if (t.get("meta") or {}).get("kind") == "risk_point")
    assert rp.get("ref") == "p.95"
    assert "關聯交易" in rp["content"] or "关连" in rp["content"].lower() or "關聯" in rp["content"]


def test_react_turn_model_think():
    thoughts = map_legal_event(
        {
            "event": "react_turn",
            "turn": 1,
            "reasoning": "I will retrieve legal package first.",
            "reasoning_display": "我將先檢索法務資料包。",
            "tool_calls": [{"name": "retrieve_legal", "arguments": {"reason": "基線"}}],
        }
    )
    assert len(thoughts) == 1
    t = thoughts[0]
    assert t["type"] == "thinking"
    assert t["agentId"] == "legal"
    assert (t.get("meta") or {}).get("kind") == "model_think"
    assert (t.get("meta") or {}).get("rawThink")
    assert "法務" in t["content"] or "檢索" in t["content"]


def test_tool_call_running_and_result():
    running = map_legal_event(
        {
            "event": "step",
            "name": "search_legal_evidence",
            "status": "running",
            "input_summary": {"query": "對賭", "reason": "補證"},
        }
    )
    assert _kinds(running) == ["tool_call"]
    assert "正在執行" in running[0]["content"]

    done = map_legal_event(
        {
            "event": "step",
            "name": "search_legal_evidence",
            "status": "ok",
            "output": {
                "n": 1,
                "hits": [{"page": 200, "excerpt": "對賭協議已終止", "source_type": "text"}],
            },
        }
    )
    kinds = _kinds(done)
    assert "tool_result" in kinds
    assert "evidence" in kinds
