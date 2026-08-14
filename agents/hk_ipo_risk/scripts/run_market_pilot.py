#!/usr/bin/env python3
"""Run the evidence-first market agent on the curated 15-company history pilot."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PKG_ROOT = Path(__file__).resolve().parent.parent
IPOI_ROOT = PKG_ROOT.parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.agents.market_agent import MarketAgent  # noqa: E402
from src.config import load_yaml  # noqa: E402


DEFAULT_MANIFEST = IPOI_ROOT / "market" / "configs" / "market_pilot_15.yaml"
DEFAULT_FEATURES = IPOI_ROOT / "market" / "data" / "derived" / "ipo_sentiment_features.csv"
DEFAULT_COMPLETENESS = IPOI_ROOT / "market" / "data" / "derived" / "ipo_sentiment_completeness.csv"


def _rows_by_code(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {str(row.get("stock_code") or "").zfill(5): row for row in csv.DictReader(f)}


def _number(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    if text.lower() in {"true", "false"}:
        return 1.0 if text.lower() == "true" else 0.0
    try:
        return float(text)
    except ValueError:
        return None


def _mean(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return statistics.fmean(clean) if clean else None


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.2%}"


def _escape(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


async def run_pilot(
    manifest_path: Path,
    features_path: Path,
    completeness_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    manifest = load_yaml(manifest_path)
    companies = manifest.get("companies") or []
    if len(companies) != 15:
        raise ValueError(f"pilot manifest must contain exactly 15 companies, got {len(companies)}")
    feature_rows = _rows_by_code(features_path)
    completeness_rows = _rows_by_code(completeness_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    agent = MarketAgent(strict_cutoff=True)

    async def one(company: dict[str, Any]):
        code = str(company["stock_code"]).zfill(5)
        return company, await agent.run(
            f"market-pilot-{code}",
            stock_code=code,
            features_csv=features_path,
        )

    outputs = await asyncio.gather(*(one(company) for company in companies), return_exceptions=True)
    summaries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for item in outputs:
        if isinstance(item, BaseException):
            errors.append({"stock_code": "unknown", "error": str(item)})
            continue
        company, result = item
        code = str(company["stock_code"]).zfill(5)
        feature_row = feature_rows.get(code) or {}
        completeness = completeness_rows.get(code) or {}
        sentiment = result.features["sentiment_analysis"]
        boundary = sentiment["data_boundary"]
        result_payload = result.model_dump(mode="json")
        result_payload["pilot_metadata"] = company
        result_payload["evaluation_only_outcomes"] = {
            "warning": "post-listing labels; never passed to MarketAgent",
            "day1_return": _number(feature_row.get("outcome_day1_return")),
            "day5_return": _number(feature_row.get("outcome_day5_return")),
            "day20_return": _number(feature_row.get("outcome_day20_return")),
            "day60_return": _number(feature_row.get("outcome_day60_return")),
            "is_break": _number(feature_row.get("outcome_is_break")),
            "mdd20": _number(feature_row.get("outcome_mdd20")),
        }
        (output_dir / f"{code}_market_result.json").write_text(
            json.dumps(result_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / f"{code}_market_report.md").write_text(
            sentiment["report_markdown"],
            encoding="utf-8",
        )
        summaries.append(
            {
                "stock_code": code,
                "company": result.features.get("company") or company.get("company"),
                "listing_date": result.features["listing_date"],
                "listing_year": int(str(result.features["listing_date"])[:4]),
                "industry": feature_row.get("industry"),
                "completeness_tier": completeness.get("tier"),
                "completeness_score": completeness.get("score"),
                "overall_state": sentiment["overall_state"],
                "overall_net_support": sentiment["overall_net_support"],
                "macro_state": sentiment["module_states"].get("macro"),
                "industry_state": sentiment["module_states"].get("industry"),
                "ipo_market_state": sentiment["module_states"].get("ipo_market"),
                "public_opinion_state": sentiment["module_states"].get("public_opinion"),
                "macro_net_support": sentiment["module_signal_balances"]["macro"]["net_support"],
                "industry_net_support": sentiment["module_signal_balances"]["industry"]["net_support"],
                "ipo_market_net_support": sentiment["module_signal_balances"]["ipo_market"]["net_support"],
                "macro_coverage": sentiment["module_coverage"].get("macro"),
                "industry_coverage": sentiment["module_coverage"].get("industry"),
                "ipo_market_coverage": sentiment["module_coverage"].get("ipo_market"),
                "cutoff_verified": boundary["cutoff_verified"],
                "as_of_date": boundary["as_of_date"],
                "market_observation_date": boundary["market_observation_date"],
                "news_total_rows": boundary["news_total_rows"],
                "news_pre_cutoff_rows": boundary["news_pre_cutoff_rows"],
                "public_opinion_used": result.features["public_opinion_used"],
                "support_evidence_count": len(sentiment["support_evidence_ids"]),
                "pressure_evidence_count": len(sentiment["pressure_evidence_ids"]),
                "contradiction_count": len(sentiment["contradictions"]),
                "evidence_count": len(sentiment["evidence_ledger"]),
                "compatibility_risk_score": result.risk_score,
                "outcome_day1_return_eval_only": _number(feature_row.get("outcome_day1_return")),
                "outcome_day20_return_eval_only": _number(feature_row.get("outcome_day20_return")),
                "outcome_is_break_eval_only": _number(feature_row.get("outcome_is_break")),
                "selection_rationale": company.get("rationale"),
                "summary": result.summary,
            }
        )

    if summaries:
        with (output_dir / "market_pilot_summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
            writer.writeheader()
            writer.writerows(summaries)
    report = _build_report(manifest, summaries, errors)
    (output_dir / "market_pilot_report.md").write_text(report, encoding="utf-8")
    return {"summaries": summaries, "errors": errors, "report": report}


def _build_report(
    manifest: dict[str, Any],
    summaries: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> str:
    state_counts = Counter(row["overall_state"] for row in summaries)
    module_counts: dict[str, Counter[str]] = {
        key: Counter(row[key] for row in summaries)
        for key in ("macro_state", "industry_state", "ipo_market_state", "public_opinion_state")
    }
    by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in summaries:
        by_state[row["overall_state"]].append(row)
    lines = [
        "# 市场情绪 Agent：15家公司跨年份首轮实验",
        "",
        "## 实验边界",
        "",
        "- 覆盖年份：2020–2025；样本数：15。",
        "- Agent仅使用上市前T−1结构化数据和合格舆情；`outcome_*` 在Agent完成后才加入本实验报告，仅作评价标签。",
        "- 本轮不使用LLM，因此没有经过LLM相关性验证的舆情不会参与权重。",
        "- 市场情绪结论以证据账本为主；兼容风险分不作为主结论。",
        "",
        "## 样本选择原则",
        "",
    ]
    lines.extend(f"- {item}" for item in manifest.get("selection_principles") or [])
    lines += [
        "",
        "## 总体结果",
        "",
        f"- 成功：{len(summaries)}/15；失败：{len(errors)}。",
        f"- 截止日校验通过：{sum(bool(row['cutoff_verified']) for row in summaries)}/{len(summaries)}。",
        f"- 整体状态分布：{dict(state_counts)}。",
        f"- 模块状态分布：{ {key: dict(value) for key, value in module_counts.items()} }。",
        f"- 有效上市前舆情：{sum(bool(row['public_opinion_used']) for row in summaries)}/{len(summaries)}。",
        "",
        "## 逐公司汇总",
        "",
        "| 年份 | 代码 | 公司 | 行业 | 完整度 | 整体状态 | 净支持度 | 宏观 | 行业 | IPO市场 | 舆情 | 截止校验 | 首日收益（评价） | 20日收益（评价） |",
        "|---:|---|---|---|---|---|---:|---|---|---|---|---|---:|---:|",
    ]
    for row in sorted(summaries, key=lambda value: (value["listing_year"], value["stock_code"])):
        lines.append(
            f"| {row['listing_year']} | {row['stock_code']} | {_escape(row['company'])} | {_escape(row['industry'])} | "
            f"{_escape(row['completeness_tier'])} | {row['overall_state']} | {float(row['overall_net_support']):+.1%} | {row['macro_state']} | "
            f"{row['industry_state']} | {row['ipo_market_state']} | {row['public_opinion_state']} | "
            f"{'Y' if row['cutoff_verified'] else 'N'} | {_pct(row['outcome_day1_return_eval_only'])} | "
            f"{_pct(row['outcome_day20_return_eval_only'])} |"
        )
    lines += ["", "## 按市场情绪状态的上市后表现（仅描述，不作因果推断）", ""]
    for state, rows in sorted(by_state.items()):
        lines.append(
            f"- `{state}`：n={len(rows)}，平均首日收益="
            f"{_pct(_mean([row['outcome_day1_return_eval_only'] for row in rows]))}，"
            f"平均20日收益={_pct(_mean([row['outcome_day20_return_eval_only'] for row in rows]))}。"
        )
    mixed_share = state_counts.get("mixed", 0) / len(summaries) if summaries else 0.0
    supportive_day1 = _mean([
        row["outcome_day1_return_eval_only"] for row in by_state.get("supportive", [])
    ])
    pressured_day1 = _mean([
        row["outcome_day1_return_eval_only"] for row in by_state.get("pressured", [])
    ])
    lines += [
        "",
        "## 初步观察",
        "",
        (
            "- 当前多数样本仍为 `mixed`，定性规则区分度不足，需继续校准。"
            if mixed_share > 0.6
            else "- 净支持度聚合后，样本已能区分支持、压制与真正均衡的多空状态；反向证据仍完整保留在逐公司报告中。"
        ),
        "- 2020样本的VHSI缺失应体现在证据账本和覆盖率中，不应补0或直接判为负面。",
        "- 舆情模块全部不可用时，本轮只能验证结构化三模块；接入Firecrawl后应单独比较舆情加入前后的结论变化。",
        (
            "- 本小样本中，支持状态的平均首日收益并未高于压制状态；这说明市场情绪描述不能替代公司基本面、定价和法务/财务判断，也不应被解释为单独的涨跌预测。"
            if supportive_day1 is not None and pressured_day1 is not None and supportive_day1 <= pressured_day1
            else "- 市场情绪状态与上市后表现的关系仍需更大样本验证，当前结果不作预测或因果解释。"
        ),
        "- 上市后收益只用于观察，不得回写到任何Agent输入或解释中。",
        "",
        "## 文件说明",
        "",
        "- `market_pilot_summary.csv`：15家公司机器可读汇总。",
        "- `{code}_market_result.json`：完整Agent输出、证据账本及隔离的评价标签。",
        "- `{code}_market_report.md`：逐公司完整证据报告。",
    ]
    if errors:
        lines += ["", "## 失败记录", ""]
        lines.extend(f"- {_escape(item)}" for item in errors)
    return "\n".join(lines) + "\n"


async def _amain() -> int:
    parser = argparse.ArgumentParser(description="Run the 15-company market sentiment pilot")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--completeness", type=Path, default=DEFAULT_COMPLETENESS)
    parser.add_argument("--output-dir", type=Path, default=PKG_ROOT / ".runtime" / "market_pilot_15")
    args = parser.parse_args()
    result = await run_pilot(args.manifest, args.features, args.completeness, args.output_dir)
    print(f"completed={len(result['summaries'])} errors={len(result['errors'])}")
    print(f"report={args.output_dir / 'market_pilot_report.md'}")
    return 1 if result["errors"] else 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()

