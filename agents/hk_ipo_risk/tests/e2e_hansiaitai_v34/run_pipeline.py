#!/usr/bin/env python3
"""只打 9100，走翰思艾泰 parse → index → analysis → report。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx

BASE = "http://127.0.0.1:9100"
BACKEND = "http://127.0.0.1:9102"
PDF = Path("/nfs/users/wuqianqian/IPOI/pdf_parsing/pdf/03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf")
TICKER = "03378.HK"


def save(path: Path, content: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)


def dump_json(path: Path, obj) -> None:
    save(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    log_root = Path(__file__).resolve().parent / "logs"
    fe = log_root / "frontend"
    be = log_root / "backend"
    fe.mkdir(parents=True, exist_ok=True)
    be.mkdir(parents=True, exist_ok=True)

    timeout = httpx.Timeout(connect=30.0, read=600.0, write=60.0, pool=30.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        health = client.get(f"{BASE}/api/v1/health").json()
        dump_json(fe / "health.json", health)
        try:
            dump_json(be / "health.json", client.get(f"{BACKEND}/api/v1/health").json())
        except Exception as exc:
            save(be / "health.json", json.dumps({"error": str(exc)}))
        if not (health.get("data") or {}).get("stubMode", True):
            raise SystemExit("STUB_MODE is not true; refusing to start GPU parse")

        status = client.get(f"{BASE}/api/v1/agents/status").json()
        dump_json(fe / "agents_status.json", status)
        try:
            dump_json(be / "agents_status.json", client.get(f"{BACKEND}/api/v1/agents/status").json())
        except Exception as exc:
            save(be / "agents_status.json", json.dumps({"error": str(exc)}))

        proj = f"proj-{int(time.time()):x}"
        save(fe / "client_project_id.txt", proj)
        files = {"file": (PDF.name, PDF.read_bytes(), "application/pdf")}
        data = {
            "ticker": TICKER,
            "clientProjectId": proj,
            "fileName": PDF.name,
            "isBiotech": "true",
            "enableEmbellishment": "false",
            "companyName": "翰思艾泰",
            "listDate": "2025-12-15",
        }
        start = client.post(f"{BASE}/api/v1/parse/expert/start", files=files, data=data)
        parse_start = start.json()
        dump_json(fe / "parse_start.json", parse_start)
        task_id = (parse_start.get("data") or {}).get("taskId")
        if not task_id:
            raise SystemExit(f"parse start failed: {parse_start}")

        stage = ""
        for _ in range(120):
            prog = client.get(f"{BASE}/api/v1/parse/expert/tasks/{task_id}/progress").json()
            dump_json(fe / "parse_progress.json", prog)
            stage = (prog.get("data") or {}).get("stage") or ""
            if stage in {"READY", "FAILED"}:
                break
            time.sleep(1)
        if stage != "READY":
            raise SystemExit(f"parse not READY: {stage}")

        parse_result = client.get(f"{BASE}/api/v1/parse/expert/tasks/{task_id}/result").json()
        dump_json(fe / "parse_result.json", parse_result)

        idx_status = ""
        for _ in range(180):
            idx = client.get(f"{BASE}/api/v1/projects/{proj}/index-status", params={"taskId": task_id}).json()
            dump_json(fe / "index_status.json", idx)
            idx_status = (idx.get("data") or {}).get("status") or ""
            if idx_status in {"ready", "failed"}:
                break
            time.sleep(5)
        if idx_status != "ready":
            raise SystemExit(f"index not ready: {idx_status}")

        astart = client.post(
            f"{BASE}/api/v1/projects/{proj}/analysis/start",
            json={
                "clientProjectId": proj,
                "taskId": task_id,
                "ticker": TICKER,
                "isBiotech": True,
            },
        )
        astart_body = astart.json()
        dump_json(fe / "analysis_start.json", astart_body)
        analysis_id = (astart_body.get("data") or {}).get("analysisId")
        if not analysis_id:
            raise SystemExit(f"analysis start failed: {astart_body}")
        save(fe / "analysis_id.txt", analysis_id)

        sse_path = fe / "analysis_stream.sse"
        sse_path.write_text("", encoding="utf-8")
        deadline = time.time() + 90 * 60
        complete = False
        url = f"{BASE}/api/v1/projects/{proj}/analysis/stream?analysisId={quote(analysis_id)}"
        while time.time() < deadline and not complete:
            try:
                with client.stream("GET", url, timeout=httpx.Timeout(None, connect=30.0)) as resp:
                    resp.raise_for_status()
                    with sse_path.open("ab") as fp:
                        for chunk in resp.iter_bytes():
                            fp.write(chunk)
                            fp.flush()
                            if b"event: analysis_complete" in sse_path.read_bytes()[-4096:]:
                                complete = True
                                break
            except httpx.HTTPError as exc:
                with (fe / "sse_reconnect.txt").open("a", encoding="utf-8") as rf:
                    rf.write(f"{time.time()} {exc}\n")
                time.sleep(2)
            if sse_path.is_file() and b"event: analysis_complete" in sse_path.read_bytes():
                complete = True
            elif not complete:
                sse_path.write_text("", encoding="utf-8")
        if not complete:
            raise SystemExit("SSE timeout without analysis_complete")

        result = client.get(
            f"{BASE}/api/v1/projects/{proj}/analysis/result",
            params={"analysisId": analysis_id},
        ).json()
        dump_json(fe / "analysis_result.json", result)
        if (result.get("data") or {}).get("status") == "failed":
            raise SystemExit(f"analysis failed: {(result.get('data') or {}).get('error')}")
        try:
            dump_json(
                be / "analysis_result.json",
                client.get(
                    f"{BACKEND}/api/v1/projects/{proj}/analysis/result",
                    params={"analysisId": analysis_id},
                ).json(),
            )
        except Exception as exc:
            save(be / "analysis_result.json", json.dumps({"error": str(exc)}))

        report = client.get(
            f"{BASE}/api/v1/projects/{proj}/report",
            params={"analysisId": analysis_id},
        )
        dump_json(fe / "report.json", report.json())
        pdf = client.get(
            f"{BASE}/api/v1/projects/{proj}/report/export",
            params={"analysisId": analysis_id},
        )
        save(fe / "report.pdf", pdf.content)
        save(fe / "report_export_headers.json", json.dumps(dict(pdf.headers), ensure_ascii=False, indent=2))

    print(json.dumps({"ok": True, "proj": proj, "analysisId": analysis_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
