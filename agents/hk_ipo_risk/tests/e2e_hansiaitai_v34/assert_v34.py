#!/usr/bin/env python3
"""断言翰思艾泰 v3.4 stream / result / report。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _events(sse_path: Path) -> list[dict]:
    out = []
    event = None
    data_lines: list[str] = []
    for line in sse_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
        elif line.strip() == "":
            if event:
                raw = "\n".join(data_lines)
                try:
                    data = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    data = {"_raw": raw}
                out.append({"event": event, "data": data})
            event = None
            data_lines = []
    return out


def main() -> int:
    log_dir = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent / "logs")
    fe = log_dir / "frontend"
    be = log_dir / "backend"
    events = _events(fe / "analysis_stream.sse")
    result = _load(fe / "analysis_result.json")
    report = _load(fe / "report.json")
    if result.get("success") is False:
        raise SystemExit(f"result failed: {result}")
    data = result.get("data") or result
    report_data = report.get("data") if isinstance(report, dict) and "data" in report else report

    thoughts = [e for e in events if e["event"] == "thought"]
    statuses = [e for e in events if e["event"] == "agent_status"]
    reports = [e for e in events if e["event"] == "agent_report"]

    # 1) 财务 thought 早于 legal completed
    fin_ts = None
    legal_done_ts = None
    for i, e in enumerate(events):
        if e["event"] == "thought":
            th = (e["data"] or {}).get("thought") or {}
            if th.get("agentId") == "financial" and fin_ts is None:
                fin_ts = i
        if e["event"] == "agent_status":
            d = e["data"] or {}
            if d.get("agentId") == "legal" and d.get("status") == "completed" and legal_done_ts is None:
                legal_done_ts = i
    if fin_ts is None:
        raise SystemExit("no financial thought")
    if legal_done_ts is None:
        raise SystemExit("no legal completed")
    if fin_ts >= legal_done_ts:
        raise SystemExit(f"financial thought buffered: idx {fin_ts} >= legal completed {legal_done_ts}")

    # 2) 初评 thought / agent_report 无 category
    analysis_done = False
    debate_started = False
    for e in events:
        if e["event"] == "phase_change" and (e["data"] or {}).get("phase") == "debate":
            debate_started = True
            analysis_done = True
        if e["event"] in {"phase_change", "debate_message", "debate_complete"} and (e["data"] or {}).get("phase") == "debate":
            debate_started = True
        if not debate_started:
            if e["event"] == "thought":
                th = (e["data"] or {}).get("thought") or {}
                if "category" in th:
                    raise SystemExit(f"pre-debate thought has category: {th.get('agentId')} {th.get('category')}")
            if e["event"] == "agent_report" and "category" in (e["data"] or {}):
                raise SystemExit("agent_report has category")
            if e["event"] == "agent_status" and (e["data"] or {}).get("agentId") != "orchestrator":
                if "category" in (e["data"] or {}):
                    raise SystemExit("pre-debate agent_status has category")

    orch = [
        (e["data"] or {}).get("thought") or {}
        for e in thoughts
        if ((e["data"] or {}).get("thought") or {}).get("agentId") == "orchestrator"
    ]
    if not orch:
        raise SystemExit("missing orchestrator thoughts")

    cats = []
    for e in events:
        if e["event"] == "thought":
            th = (e["data"] or {}).get("thought") or {}
            if "category" in th:
                cats.append(th["category"])
        if e["event"] == "debate_message":
            msg = (e["data"] or {}).get("message") or e["data"] or {}
            if "category" in msg:
                cats.append(msg["category"])

    debate = data.get("debate") or {}
    rounds = int(debate.get("rounds") or 0)
    if debate_started:
        if "master" not in cats:
            raise SystemExit("debate started but no category=master")
        expert_cats = {"finance", "legal", "market"} & set(cats)
        if not expert_cats:
            raise SystemExit("debate started but no expert category")
        # 专家证据不应记成 master
        for e in thoughts:
            th = (e["data"] or {}).get("thought") or {}
            meta = th.get("meta") or {}
            if meta.get("kind") == "evidence" and th.get("category") == "master" and th.get("agentId") != "orchestrator":
                raise SystemExit("expert evidence tagged master")
    else:
        if cats:
            raise SystemExit(f"skip-debate but found category={cats}")
        if rounds != 0:
            raise SystemExit(f"skip-debate but rounds={rounds}")

    if len(reports) < 3:
        raise SystemExit(f"expected 3 agent_report, got {len(reports)}")

    score = data.get("overallScore")
    if not isinstance(score, (int, float)) or not (0 <= float(score) <= 100):
        raise SystemExit(f"overallScore not in 0-100: {score}")
    if 0 < float(score) <= 1:
        raise SystemExit(f"overallScore looks 0-1: {score}")

    legal_md = ((data.get("agents") or {}).get("legal") or {}).get("reportMarkdown") or ""
    fin_md = ((data.get("agents") or {}).get("financial") or {}).get("reportMarkdown") or ""
    if not legal_md or not fin_md:
        raise SystemExit("missing independent reportMarkdown")
    if legal_md == fin_md:
        raise SystemExit("legal.reportMarkdown == financial.reportMarkdown")

    for k in ("overallScore", "riskLevel", "riskLabel", "dimensions", "riskFactors", "comparableIPOs", "riskTimeline", "radarData"):
        if k not in report_data:
            raise SystemExit(f"report missing {k}")
        if k not in (data.get("report") or {}):
            raise SystemExit(f"result.report missing {k}")
        if report_data.get(k) != (data.get("report") or {}).get(k):
            raise SystemExit(f"result.report.{k} != /report.{k}")

    pdf = fe / "report.pdf"
    if not pdf.is_file() or pdf.stat().st_size < 100:
        raise SystemExit("PDF empty")
    if pdf.read_bytes()[:4] != b"%PDF":
        raise SystemExit("PDF magic missing")

    print(
        json.dumps(
            {
                "ok": True,
                "debate_started": debate_started,
                "debate_rounds": rounds,
                "overallScore": score,
                "financial_thought_idx": fin_ts,
                "legal_completed_idx": legal_done_ts,
                "agent_reports": len(reports),
                "orchestrator_thoughts": len(orch),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
