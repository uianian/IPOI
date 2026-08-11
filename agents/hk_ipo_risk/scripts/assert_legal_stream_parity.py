#!/usr/bin/env python3
"""断言法务 stream/result thoughts 与财务对齐：中段证据、工具、推理。

用法示例：
  # result JSON（含 data.thoughts）
  python scripts/assert_legal_stream_parity.py --result /tmp/analysis_result.json

  # 直接 thoughts 数组 JSON
  python scripts/assert_legal_stream_parity.py --thoughts path/to/thoughts.json

  # SSE 落盘：每行 JSON 或 events 目录下的 NDJSON
  python scripts/assert_legal_stream_parity.py --events .runtime/analyses/<aid>/events

  # 离线：用 mapper 重放 pipeline 样例（翰思场景冒烟，无需起服务）
  python scripts/assert_legal_stream_parity.py --self-check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _thoughts_from_result(obj: dict[str, Any]) -> list[dict[str, Any]]:
    data = obj.get("data") if isinstance(obj.get("data"), dict) else obj
    thoughts = data.get("thoughts") if isinstance(data, dict) else None
    if not isinstance(thoughts, list):
        raise SystemExit("result JSON 中未找到 thoughts 数组")
    return [t for t in thoughts if isinstance(t, dict)]


def _thoughts_from_events(path: Path) -> list[dict[str, Any]]:
    """支持：单文件 NDJSON / JSON 数组，或目录内 *.jsonl / events.jsonl。"""
    if not path.exists():
        raise SystemExit(f"events 路径不存在: {path}")
    files: list[Path]
    if path.is_dir():
        files = sorted(path.glob("*.jsonl")) + sorted(path.glob("*.ndjson"))
        if not files:
            # 目录内每个文件可能是单条 SSE data
            files = sorted(p for p in path.iterdir() if p.is_file())
        if not files:
            raise SystemExit(f"events 目录为空: {path}")
    else:
        files = [path]

    thoughts: list[dict[str, Any]] = []
    for f in files:
        text = f.read_text(encoding="utf-8").strip()
        if not text:
            continue
        # 尝试整体 JSON
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                for item in obj:
                    th = _extract_thought(item)
                    if th:
                        thoughts.append(th)
                continue
            th = _extract_thought(obj)
            if th:
                thoughts.append(th)
                continue
        except json.JSONDecodeError:
            pass
        # NDJSON
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            th = _extract_thought(obj)
            if th:
                thoughts.append(th)
    return thoughts


def _extract_thought(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    if "thought" in obj and isinstance(obj["thought"], dict):
        return obj["thought"]
    if obj.get("agentId") and obj.get("type") in {"thinking", "finding", "conclusion"}:
        return obj
    return None


def assert_legal_parity(thoughts: list[dict[str, Any]]) -> dict[str, Any]:
    legal = [t for t in thoughts if t.get("agentId") == "legal"]
    if not legal:
        raise AssertionError("没有 agentId=legal 的 thought")

    kinds = [(t.get("meta") or {}).get("kind") for t in legal]
    types = [t.get("type") for t in legal]

    has_think = "model_think" in kinds or any(t == "thinking" for t in types)
    has_tool_call = "tool_call" in kinds
    has_tool_result = "tool_result" in kinds
    evidence_idxs = [i for i, k in enumerate(kinds) if k == "evidence"]
    has_evidence = bool(evidence_idxs)

    # 中段证据：至少一条 evidence 不在最后 2 条 thought 内（避免只在终局出现）
    mid_evidence = False
    if evidence_idxs:
        last = len(legal) - 1
        mid_evidence = any(i < max(0, last - 1) for i in evidence_idxs)

    # 证据字段完整
    bad_snips = []
    for t in legal:
        if (t.get("meta") or {}).get("kind") != "evidence":
            continue
        for s in (t.get("meta") or {}).get("evidence") or []:
            if not isinstance(s, dict):
                bad_snips.append("non-dict")
                continue
            if s.get("page") is None:
                bad_snips.append("missing page")
            if not (s.get("excerpt") or "").strip():
                bad_snips.append("empty excerpt")

    report = {
        "legal_thought_count": len(legal),
        "kinds": {k: kinds.count(k) for k in sorted(set(kinds), key=lambda x: (x is None, x or ""))},
        "has_model_think_or_thinking": has_think,
        "has_tool_call": has_tool_call,
        "has_tool_result": has_tool_result,
        "has_evidence": has_evidence,
        "has_mid_stream_evidence": mid_evidence,
        "bad_evidence_snippets": bad_snips[:10],
    }

    errors: list[str] = []
    if not has_think:
        errors.append("缺少 model_think / thinking 推理气泡")
    if not has_tool_call and not has_tool_result:
        errors.append("缺少 tool_call / tool_result")
    elif not has_tool_result:
        errors.append("缺少 tool_result")
    if not has_evidence:
        errors.append("缺少 meta.kind=evidence 证据卡")
    elif not mid_evidence:
        errors.append("证据卡仅出现在末尾，缺少中段实时证据")
    if bad_snips:
        errors.append(f"证据片段字段不完整: {bad_snips[:5]}")

    report["ok"] = not errors
    report["errors"] = errors
    return report


def _self_check() -> dict[str, Any]:
    from service.thought_mapper import map_legal_event

    thoughts: list[dict[str, Any]] = []
    # 模拟翰思法务 ReAct/流水线关键步
    seq = [
        {
            "event": "react_turn",
            "turn": 1,
            "reasoning": "Retrieve legal package.",
            "reasoning_display": "先檢索法務資料包。",
            "tool_calls": [{"name": "retrieve_legal", "arguments": {}}],
        },
        {
            "event": "step",
            "name": "retrieve_legal",
            "status": "running",
        },
        {
            "event": "step",
            "name": "retrieve_legal",
            "status": "ok",
            "output": {
                "grep_hits": 2,
                "hits": [
                    {
                        "page": 88,
                        "excerpt": "翰思艾泰控股股東持股超過百分之五十",
                        "source_type": "text",
                    }
                ],
            },
        },
        {
            "event": "step",
            "name": "parse_grep",
            "status": "ok",
            "output": {"hits": 2},
            "evidence_hits": [
                {"page": 120, "excerpt": "關連交易披露", "source_type": "text"},
            ],
        },
        {
            "event": "step",
            "name": "run_legal_skill",
            "status": "ok",
            "output": {
                "skill": "legal_related_party",
                "risk_points": [
                    {
                        "code": "RPT",
                        "description": "關聯交易",
                        "evidence_page": 120,
                        "evidence": [
                            {"page": 120, "excerpt": "關連交易披露", "source_type": "text"}
                        ],
                    }
                ],
                "evidence": [
                    {"page": 120, "excerpt": "關連交易披露", "source_type": "text"}
                ],
            },
        },
        {
            "event": "result",
            "payload": {
                "risk_score": 60.9,
                "risk_level": "high",
                "summary": "法務參考分",
                "risk_points": [],
            },
        },
    ]
    for ev in seq:
        thoughts.extend(map_legal_event(ev))
    return assert_legal_parity(thoughts)


def main() -> int:
    ap = argparse.ArgumentParser(description="断言法务 stream thoughts 与财务对齐")
    ap.add_argument("--result", type=Path, help="analysis/result JSON")
    ap.add_argument("--thoughts", type=Path, help="Thought[] JSON 文件")
    ap.add_argument("--events", type=Path, help="SSE events 文件或目录")
    ap.add_argument("--self-check", action="store_true", help="离线 mapper 样例自检")
    args = ap.parse_args()

    if args.self_check:
        report = _self_check()
    elif args.result:
        report = assert_legal_parity(_thoughts_from_result(_load_json(args.result)))
    elif args.thoughts:
        obj = _load_json(args.thoughts)
        if isinstance(obj, dict) and "thoughts" in obj:
            thoughts = obj["thoughts"]
        elif isinstance(obj, list):
            thoughts = obj
        else:
            raise SystemExit("--thoughts 需为数组或含 thoughts 字段的对象")
        report = assert_legal_parity([t for t in thoughts if isinstance(t, dict)])
    elif args.events:
        report = assert_legal_parity(_thoughts_from_events(args.events))
    else:
        ap.print_help()
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
