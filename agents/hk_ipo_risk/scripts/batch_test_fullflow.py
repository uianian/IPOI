#!/usr/bin/env python3
"""评测集批量端到端分析：索引→检索包→三专家→总控→四份报告。

默认读取 dataset/test/sample_manifest.csv 的完整 48 家。文本粉饰度固定关闭；
批次主产物统一写入 --output-dir/{stock_code}/。
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AGENT_DIR = Path(__file__).resolve().parent.parent
IPOI_ROOT = AGENT_DIR.parent.parent
RETRIEVAL_DIR = IPOI_ROOT / "retrieval"
DEFAULT_MANIFEST = IPOI_ROOT / "dataset/test/sample_manifest.csv"
DEFAULT_OUTPUT = AGENT_DIR / ".runtime/test_fullflow"
EFFORTS = ("low", "high", "max")


def _file(raw: str, field: str) -> Path:
    path = Path(raw.strip()).expanduser()
    path = path if path.is_absolute() else IPOI_ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{field} 不存在: {path}")
    return path


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = set(reader.fieldnames or [])
    required = {"stock_code", "company_display", "issuer_type", "actual_list_date",
                "pdf_filename", "pdf_path_relative", "parse_dir"}
    if required - fields:
        raise ValueError(f"manifest 缺少字段: {sorted(required - fields)}")
    if len(rows) != len({r["stock_code"] for r in rows}):
        raise ValueError("manifest stock_code 不唯一")
    return rows


def run(cmd: list[str], cwd: Path, dry_run: bool) -> None:
    print("+", " ".join(cmd), flush=True)
    if not dry_run:
        subprocess.run(cmd, cwd=str(cwd), check=True)


def write_status(root: Path, records: list[dict[str, Any]]) -> None:
    fields = ["stock_code", "company_name", "issuer_type", "status", "result_json", "error"]
    with (root / "batch_status.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{k: r.get(k, "") for k in fields} for r in records])


def collect_dossiers(result_json: Path, target: Path) -> None:
    """复制本次结果引用的 dossier，使批次目录成为可独立归档的产物集合。"""
    if not result_json.is_file():
        return
    data = json.loads(result_json.read_text(encoding="utf-8"))
    paths: set[Path] = set()
    for expert in ("finance", "legal", "market"):
        value = (((data.get(expert) or {}).get("features") or {}).get("debate_dossier_path"))
        if value:
            paths.add(Path(value))
    master_path = ((data.get("master") or {}).get("dossier_path"))
    if master_path:
        paths.add(Path(master_path))
    target.mkdir(parents=True, exist_ok=True)
    for source in paths:
        if source.is_file():
            shutil.copy2(source, target / source.name)


def process_one(args: argparse.Namespace, row: dict[str, str], pos: int, total: int) -> Path:
    code = row["stock_code"].zfill(5)
    company = row["company_display"].strip()
    issuer = row["issuer_type"].strip().lower() or "general"
    if issuer not in {"general", "18a", "18c", "biotech"}:
        raise ValueError(f"{code} issuer_type 非法: {issuer}")
    parse_json = _file(row["parse_dir"], f"{code}.parse_dir")
    _file(row["pdf_path_relative"], f"{code}.pdf_path_relative")
    listing = row["actual_list_date"].replace("-", "")

    base = args.output_dir / code
    retrieval_out, reports, logs = base / "retrieval", base / "reports", base / "logs"
    result = base / "analysis_result.json"
    fin = retrieval_out / f"agent_retrieval_{code}_finance.json"
    leg = retrieval_out / f"agent_retrieval_{code}_legal.json"
    for directory in (retrieval_out, reports, logs, base / "debate"):
        directory.mkdir(parents=True, exist_ok=True)
    print(f"\n===== [{pos}/{total}] {code} {company} ({issuer}) =====")

    expected = [reports / f"{code}_{x}_report.md" for x in
                ("finance", "legal", "market", "ipo_risk_warning")]
    if args.resume and result.is_file() and all(p.is_file() for p in expected):
        print(f"SKIP completed → {base}")
        return result

    if not args.skip_index:
        cmd = [sys.executable, str(RETRIEVAL_DIR / "scripts/build_index_from_parse.py"),
               "--parse", str(parse_json), "--company-name", company, "--stock-code", code,
               "--listing-date", listing, "--doc-id", code]
        if args.force_index:
            cmd.append("--force")
        run(cmd, RETRIEVAL_DIR, args.dry_run)

    if not args.skip_retrieval:
        for expert, out in (("finance", fin), ("legal", leg)):
            run([sys.executable, str(RETRIEVAL_DIR / "scripts/simulate_agent_retrieval.py"),
                 "--doc-id", code, "--agent", expert, "--issuer-type", issuer,
                 "--top-k", str(args.top_k), "--out", str(out)], RETRIEVAL_DIR, args.dry_run)
    elif not args.dry_run and (not fin.is_file() or not leg.is_file()):
        raise FileNotFoundError(f"{code} 跳过检索但批次目录内检索包不完整")

    cmd = [sys.executable, str(AGENT_DIR / "scripts/run_finance_legal.py"),
           "--agent", "all", "--stock-code", code, "--doc-id", code,
           "--doc-name", company, "--pdf-name", row["pdf_filename"], "--issuer-type", issuer,
           "--parse-json", str(parse_json), "--retrieval-finance-json", str(fin),
           "--retrieval-legal-json", str(leg), "--provider", "deepseek",
           "--chat-model", args.chat_model, "--finance-reasoning-effort", args.finance_effort,
           "--legal-reasoning-effort", args.legal_effort, "--max-turns", str(args.max_turns),
           "--skip-embellishment", "--log-dir", str(logs), "--out", str(result)]
    if args.api_key:
        cmd += ["--api-key", args.api_key]
    if args.api_base:
        cmd += ["--api-base", args.api_base]
    run(cmd, AGENT_DIR, args.dry_run)

    run([sys.executable, str(AGENT_DIR / "scripts/generate_analysis_report.py"),
         "--result", str(result), "--doc-name", company, "--pdf-name", row["pdf_filename"],
         "--stock-code", code, "--finance-retrieval", str(fin), "--legal-retrieval", str(leg),
         "--reports-dir", str(reports)], AGENT_DIR, args.dry_run)
    if not args.dry_run:
        collect_dossiers(result, base / "debate")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="评测集 48 家端到端全流程分析（固定关闭文本粉饰度）")
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--codes", default="", help="指定股票代码，逗号分隔")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--n", type=int, default=None, help="默认处理 start 后全部")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--chat-model", default="deepseek-v4-flash")
    p.add_argument("--api-key", default=None, help="建议改用 DEEPSEEK_API_KEY 环境变量")
    p.add_argument("--api-base", default=None)
    p.add_argument("--finance-effort", choices=EFFORTS, default="low")
    p.add_argument("--legal-effort", choices=EFFORTS, default="high")
    p.add_argument("--max-turns", type=int, default=10)
    p.add_argument("--no-force-index", dest="force_index", action="store_false")
    p.set_defaults(force_index=True)
    p.add_argument("--skip-index", action="store_true")
    p.add_argument("--skip-retrieval", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--continue-on-error", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    args.manifest, args.output_dir = args.manifest.resolve(), args.output_dir.resolve()
    rows = load_manifest(args.manifest)
    requested = [x.strip().zfill(5) for x in args.codes.split(",") if x.strip()]
    if requested:
        by_code = {r["stock_code"].zfill(5): r for r in rows}
        unknown = [x for x in requested if x not in by_code]
        if unknown:
            p.error(f"未知代码: {','.join(unknown)}")
        rows = [by_code[x] for x in requested]
    else:
        rows = rows[args.start:None if args.n is None else args.start + args.n]
    if not rows:
        p.error("没有待处理公司")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        (args.output_dir / "batch_config.json").write_text(json.dumps({
            "created_at": datetime.now(timezone.utc).isoformat(), "manifest": str(args.manifest),
            "company_count": len(rows), "provider": "deepseek", "model": args.chat_model,
            "embellishment_enabled": False,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    statuses: list[dict[str, Any]] = []
    for pos, row in enumerate(rows, 1):
        code = row["stock_code"].zfill(5)
        try:
            result = process_one(args, row, pos, len(rows))
            statuses.append({"stock_code": code, "company_name": row["company_display"],
                             "issuer_type": row["issuer_type"], "status": "ok",
                             "result_json": str(result), "error": ""})
        except Exception as exc:
            statuses.append({"stock_code": code, "company_name": row["company_display"],
                             "issuer_type": row["issuer_type"], "status": "failed",
                             "result_json": "", "error": str(exc)})
            print(f"ERROR [{code}] {exc}", file=sys.stderr)
            if not args.continue_on_error:
                if not args.dry_run:
                    write_status(args.output_dir, statuses)
                return 1
        if not args.dry_run:
            write_status(args.output_dir, statuses)
    failed = sum(x["status"] == "failed" for x in statuses)
    print(f"Done: ok={len(statuses)-failed} failed={failed} total={len(statuses)}")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
