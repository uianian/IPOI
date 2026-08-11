#!/usr/bin/env python3
"""对 18a_batch 前 N 家做批量联合分析：建索引 → 检索包 → finance‖legal → 报告。

与 README §8.1 单样本推荐对齐：财务 reasoning=low、法务=high、max-turns=10。

示例：
  conda activate ipo-risk
  cd agents/hk_ipo_risk
  python scripts/batch_finance_legal_18a.py --n 3
  python scripts/batch_finance_legal_18a.py --n 10 --no-force-index
  python scripts/batch_finance_legal_18a.py --n 5 --skip-index --skip-retrieval
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
IPOI_ROOT = AGENT_DIR.parent.parent
DEFAULT_BATCH_DIR = IPOI_ROOT / "pdf_parsing" / "output" / "18a_batch"
DEFAULT_RETRIEVAL_DIR = IPOI_ROOT / "retrieval"
EFFORT_CHOICES = ("low", "high", "max")


def parse_stem(stem: str) -> tuple[str, str, str]:
    """从目录名解析股票代码、上市日、展示名。

    约定：``{股票代码}_{DD-MM-YYYY}_{公司名}_全球發售``
    例：``01244_29-11-2022_3D MEDICINES-B_全球發售``
    """
    m = re.match(r"^(\d{5})_(\d{2})-(\d{2})-(\d{4})_(.+)$", stem)
    if not m:
        raise ValueError(f"unexpected stem: {stem}")
    stock, dd, mm, yyyy, rest = m.groups()
    listing = f"{yyyy}{mm}{dd}"
    name = re.sub(r"[_－\-]?[ＢB]?_?全球發售$", "", rest).strip("_- ")
    return stock, listing, name or rest


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd), check=True)


def process_one(
    *,
    py: str,
    retrieval: Path,
    agent: Path,
    rec: dict,
    i: int,
    n: int,
    force_index: bool,
    skip_index: bool,
    skip_retrieval: bool,
    top_k: int,
    provider: str,
    chat_model: str,
    finance_reasoning_effort: str,
    legal_reasoning_effort: str,
    max_turns: int,
    api_key: str | None,
    api_base: str | None,
) -> bool:
    stem = rec["stem"]
    out_dir = Path(rec["out_dir"])
    parse_json = out_dir / "full_parse.json"
    if not parse_json.is_file():
        print(f"[{i}/{n}] SKIP missing parse: {parse_json}")
        return False

    stock, listing, doc_name = parse_stem(stem)
    doc_id = stock  # 批量用股票代码当 doc_id，避免中文路径
    pdf_name = f"{stem}.pdf"
    runtime = retrieval / ".runtime"
    fin_json = runtime / f"agent_retrieval_{doc_id}_finance.json"
    leg_json = runtime / f"agent_retrieval_{doc_id}_legal.json"
    result_json = agent / ".runtime" / f"18a_{doc_id}_finance_legal.json"
    report_md = agent / "reports" / f"18a_{doc_id}_finance_legal_report.md"

    print(f"\n===== [{i}/{n}] {doc_id} {doc_name} =====")

    # 1) 构建向量索引
    if not skip_index:
        index_cmd = [
            py,
            str(retrieval / "scripts" / "build_index_from_parse.py"),
            "--parse",
            str(parse_json),
            "--company-name",
            doc_name,
            "--stock-code",
            stock,
            "--listing-date",
            listing,
            "--doc-id",
            doc_id,
        ]
        if force_index:
            index_cmd.append("--force")
        run(index_cmd, cwd=retrieval)
    else:
        print(f"[{i}/{n}] skip index (reuse existing)")

    # 2) 财务 / 法务检索包
    if not skip_retrieval:
        for agent_name, out_path in (("finance", fin_json), ("legal", leg_json)):
            run(
                [
                    py,
                    str(retrieval / "scripts" / "simulate_agent_retrieval.py"),
                    "--doc-id",
                    doc_id,
                    "--agent",
                    agent_name,
                    "--issuer-type",
                    "18a",
                    "--top-k",
                    str(top_k),
                    "--out",
                    str(out_path),
                ],
                cwd=retrieval,
            )
    else:
        print(f"[{i}/{n}] skip retrieval packs")

    # 3) 财务 ‖ 法务联合 ReAct（与 README §8.1 对齐）
    joint_cmd = [
        py,
        str(agent / "scripts" / "run_finance_legal.py"),
        "--agent",
        "all",
        "--doc-id",
        doc_id,
        "--doc-name",
        doc_name,
        "--pdf-name",
        pdf_name,
        "--issuer-type",
        "18a",
        "--parse-json",
        str(parse_json),
        "--retrieval-finance-json",
        str(fin_json),
        "--retrieval-legal-json",
        str(leg_json),
        "--provider",
        provider,
        "--chat-model",
        chat_model,
        "--finance-reasoning-effort",
        finance_reasoning_effort,
        "--legal-reasoning-effort",
        legal_reasoning_effort,
        "--max-turns",
        str(max_turns),
        "--out",
        str(result_json),
    ]
    if api_key:
        joint_cmd.extend(["--api-key", api_key])
    if api_base:
        joint_cmd.extend(["--api-base", api_base])
    run(joint_cmd, cwd=agent)

    # 4) Markdown 报告
    run(
        [
            py,
            str(agent / "scripts" / "generate_analysis_report.py"),
            "--result",
            str(result_json),
            "--doc-name",
            doc_name,
            "--pdf-name",
            pdf_name,
            "--finance-retrieval",
            str(fin_json),
            "--legal-retrieval",
            str(leg_json),
            "--out",
            str(report_md),
        ],
        cwd=agent,
    )
    print(f"OK → {result_json}")
    print(f"OK → {report_md}")
    print(f"OK → debate dossiers under {agent / '.runtime' / 'debate'} (auto)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量联合分析：18a_batch 前 N 家（索引→检索包→finance‖legal→报告）",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=3,
        help="取 batch_summary.json 中 status=ok 的前 N 家（默认 3）",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="从 status=ok 列表的第 start 家开始（0-based，默认 0）",
    )
    parser.add_argument(
        "--batch-dir",
        type=Path,
        default=DEFAULT_BATCH_DIR,
        help=f"解析输出目录（默认 {DEFAULT_BATCH_DIR}）",
    )
    parser.add_argument(
        "--retrieval-dir",
        type=Path,
        default=DEFAULT_RETRIEVAL_DIR,
        help=f"retrieval 工程根目录（默认 {DEFAULT_RETRIEVAL_DIR}）",
    )
    parser.add_argument(
        "--agent-dir",
        type=Path,
        default=AGENT_DIR,
        help=f"hk_ipo_risk 根目录（默认 {AGENT_DIR}）",
    )
    parser.add_argument(
        "--force-index",
        action="store_true",
        default=True,
        help="建索引时传 --force（默认开启）",
    )
    parser.add_argument(
        "--no-force-index",
        action="store_true",
        help="建索引时不传 --force，复用已有索引",
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="跳过步骤1（构建向量索引）",
    )
    parser.add_argument(
        "--skip-retrieval",
        action="store_true",
        help="跳过步骤2（财务/法务检索包）",
    )
    parser.add_argument("--top-k", type=int, default=5, help="检索包 top-k（默认 5）")
    parser.add_argument(
        "--provider",
        default="deepseek",
        choices=["deepseek", "openrouter", "openai", "vllm"],
    )
    parser.add_argument("--chat-model", default="deepseek-v4-flash")
    parser.add_argument("--api-key", default=None, help="覆盖 LLM API key")
    parser.add_argument("--api-base", default=None, help="覆盖 LLM API base")
    parser.add_argument(
        "--finance-reasoning-effort",
        default="low",
        choices=EFFORT_CHOICES,
        help="财务 ReAct 思考强度（默认 low，与 §8.1 一致）",
    )
    parser.add_argument(
        "--legal-reasoning-effort",
        default="high",
        choices=EFFORT_CHOICES,
        help="法务 ReAct 思考强度（默认 high，与 §8.1 一致）",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=10,
        help="ReAct 最大轮次（默认 10，与 §8.1 一致）",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="单家失败时继续下一家（默认遇错即退出）",
    )
    args = parser.parse_args()

    batch = args.batch_dir.resolve()
    retrieval = args.retrieval_dir.resolve()
    agent = args.agent_dir.resolve()
    summary_path = batch / "batch_summary.json"
    if not summary_path.is_file():
        print(f"ERROR: missing {summary_path}", file=sys.stderr)
        return 1

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    all_ok = [r for r in summary["records"] if r.get("status") == "ok"]
    records = all_ok[args.start : args.start + args.n]
    if not records:
        print(
            f"ERROR: no ok records in range start={args.start} n={args.n} "
            f"(total ok={len(all_ok)})",
            file=sys.stderr,
        )
        return 1

    force_index = args.force_index and not args.no_force_index
    py = sys.executable

    (retrieval / ".runtime").mkdir(parents=True, exist_ok=True)
    (agent / ".runtime").mkdir(parents=True, exist_ok=True)
    (agent / ".runtime" / "debate").mkdir(parents=True, exist_ok=True)
    (agent / "reports").mkdir(parents=True, exist_ok=True)

    print(
        f"Batch joint analysis: {len(records)} companies "
        f"(start={args.start}, n={args.n}, total_ok={len(all_ok)})"
    )
    print(f"  batch_dir     = {batch}")
    print(f"  retrieval_dir = {retrieval}")
    print(f"  agent_dir     = {agent}")
    print(f"  force_index   = {force_index}  skip_index={args.skip_index}")
    print(
        f"  finance_effort={args.finance_reasoning_effort}  "
        f"legal_effort={args.legal_reasoning_effort}  max_turns={args.max_turns}"
    )

    ok_count = 0
    fail_count = 0
    for i, rec in enumerate(records, 1):
        try:
            if process_one(
                py=py,
                retrieval=retrieval,
                agent=agent,
                rec=rec,
                i=i,
                n=len(records),
                force_index=force_index,
                skip_index=args.skip_index,
                skip_retrieval=args.skip_retrieval,
                top_k=args.top_k,
                provider=args.provider,
                chat_model=args.chat_model,
                finance_reasoning_effort=args.finance_reasoning_effort,
                legal_reasoning_effort=args.legal_reasoning_effort,
                max_turns=args.max_turns,
                api_key=args.api_key,
                api_base=args.api_base,
            ):
                ok_count += 1
            else:
                fail_count += 1
                if not args.continue_on_error:
                    return 1
        except subprocess.CalledProcessError as e:
            fail_count += 1
            print(
                f"ERROR on {rec.get('stem')}: exit={e.returncode}",
                file=sys.stderr,
            )
            if not args.continue_on_error:
                return e.returncode or 1

    print(f"\nDone: ok={ok_count} fail={fail_count} total={len(records)}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
