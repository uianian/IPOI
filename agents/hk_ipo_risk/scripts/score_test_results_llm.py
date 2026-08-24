#!/usr/bin/env python3
"""用同一 DeepSeek API 对评测集分析结果进行专家量化评分。

评分依据来自东吴证券赛题：风险要素抽取、证据召回、全链路可追踪、
逻辑解释有效性，以及 D1/D5/D20/D60 预警业务价值（D5 权重最高）。
文本粉饰度不属于本脚本评分范围。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

AGENT_DIR = Path(__file__).resolve().parent.parent
IPOI_ROOT = AGENT_DIR.parent.parent
sys.path.insert(0, str(AGENT_DIR))

from src.config import resolve_api_settings  # noqa: E402
from src.tools.llm_client import LLMClient  # noqa: E402

DEFAULT_MANIFEST = IPOI_ROOT / "dataset/test/sample_manifest.csv"
DEFAULT_INPUT = AGENT_DIR / ".runtime/test_fullflow"

SYSTEM_PROMPT = """你是独立的港股IPO风控系统验收专家。请严格依据给定系统产物评分，不补造证据。
完全忽略“文本粉饰度”：不得因为该功能关闭、字段缺失或报告无相关章节而加减分。

评分维度（每项0-100）：
1. risk_extraction_score：关键风险要素抽取准确性与覆盖，包括对赌/赎回、关联交易、客户/供应商集中度、现金消耗压力；18A还应关注未商业化、现金跑道、核心管线/IP。赛题目标为准确率>=80%。
2. evidence_recall_score：结论是否有招股书原文/表格、准确页码或可核验证据支持，重大风险是否存在明显漏证。赛题目标为召回率>=85%。必须结合“定向原文核验”判断。
3. traceability_score：财务、法务、市场、总控的角色产物、工具调用/推理轨迹、证据来源是否可追踪。赛题目标为100%。
4. logic_score：跨专家冲突识别、查证/辩论、总控归因链、预测与证据之间是否逻辑自洽；规则托底或降级必须被如实披露。
5. business_value_score：上市风险预警与真实D1/D5/D20/D60表现的一致性及可操作性。D5显著下跌识别最重要；内部按D1 15%、D5 45%、D20 20%、D60 20%评价。不得因单一窗口偶然命中给满分。

原文核验要求：
- 对“引用页回查”逐条判断页码是否存在、原文是否支持对应风险，警惕错页、断章取义、数值/主体/期间错位。
- 对“独立主题检索”检查系统是否遗漏重大反向或高风险证据；关键词命中只是候选，不能自动认定为风险。
- citation_faithfulness_score 表示现有引文真实性与贴合度（0-100）。
- coverage_audit_score 表示独立主题抽查后的重大遗漏控制（0-100）。这两个诊断分必须实质影响 risk_extraction_score/evidence_recall_score。

总分由程序按 risk_extraction 25% + evidence_recall 20% + traceability 15% + logic 20% + business_value 20% 计算，你不要自行改变权重。
只输出一个JSON对象，禁止Markdown代码围栏。严格使用以下字段名与类型：
{"risk_extraction_score": 0, "evidence_recall_score": 0, "citation_faithfulness_score": 0, "coverage_audit_score": 0, "traceability_score": 0, "logic_score": 0, "business_value_score": 0, "summary": "120-300字", "strengths": ["..."], "weaknesses": ["..."]}
所有score必须是0-100的JSON数字，不能写“分”、百分号、区间或文字等级。"""

CSV_FIELDS = [
    "stock_code", "windcode", "company_display", "issuer_type", "industry_l1", "industry_l2",
    "industry_l3", "actual_list_date", "performance_class", "day1_return", "day5_return",
    "finance_risk_score", "legal_risk_score", "market_risk_score", "master_risk_score",
    "risk_extraction_score", "evidence_recall_score", "citation_faithfulness_score",
    "coverage_audit_score", "source_pages_checked", "thematic_hits_checked",
    "traceability_score", "logic_score",
    "business_value_score", "overall_score", "meets_extraction_target_80",
    "meets_evidence_target_85", "meets_traceability_target_100", "llm_summary",
    "strengths", "weaknesses", "status", "error",
]


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


THEMES_GENERAL = {
    "redemption_and_special_rights": ["贖回", "赎回", "對賭", "对赌", "優先股", "优先股", "特殊權利", "特殊权利"],
    "related_party": ["關連交易", "关联交易", "關聯方", "关联方", "持續關連", "持续关连"],
    "customer_supplier_concentration": ["最大客戶", "最大客户", "五大客戶", "五大客户", "最大供應商", "最大供应商", "五大供應商", "五大供应商"],
    "cash_burn_and_liquidity": ["經營活動所用現金", "经营活动所用现金", "現金消耗", "现金消耗", "流動資金", "流动资金", "持續經營", "持续经营"],
    "regulatory_litigation_ip": ["重大訴訟", "重大诉讼", "監管處罰", "监管处罚", "知識產權", "知识产权", "專利", "专利"],
}
THEMES_18A = {
    "pipeline_and_clinical": ["核心產品", "核心产品", "候選藥物", "候选药物", "臨床試驗", "临床试验", "商業化", "商业化"],
}
PAGE_KEYS = {"page", "page_number", "evidence_page"}


def resolve_parse_path(row: dict[str, str]) -> Path:
    path = Path(row.get("parse_dir", "").strip()).expanduser()
    path = path if path.is_absolute() else IPOI_ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"full_parse.json 不存在: {path}")
    return path


def page_text_map(parse_path: Path) -> dict[int, str]:
    data = json.loads(parse_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("pages") or data.get("content") or []
    pages: dict[int, str] = {}
    for fallback, item in enumerate(data if isinstance(data, list) else [], 1):
        if not isinstance(item, dict):
            continue
        try:
            page = int(item.get("page") or item.get("page_number") or fallback)
        except (TypeError, ValueError):
            continue
        parts = []
        for element in item.get("elements") or item.get("items") or []:
            if isinstance(element, dict):
                text = element.get("text") or element.get("content") or element.get("html") or ""
                if text:
                    parts.append(str(text))
        if not parts:
            parts.append(str(item.get("text") or item.get("content") or ""))
        pages[page] = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return pages


def cited_page_claims(result: dict[str, Any]) -> dict[int, list[str]]:
    found: dict[int, list[str]] = {}
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            context = " | ".join(str(value.get(k) or "") for k in
                                ("code", "title", "risk", "note", "summary", "evidence_excerpt", "excerpt")
                                if value.get(k))
            for key in PAGE_KEYS:
                raw = value.get(key)
                if raw is not None:
                    try:
                        page = int(raw)
                    except (TypeError, ValueError):
                        continue
                    if page > 0:
                        bucket = found.setdefault(page, [])
                        claim = clipped(re.sub(r"\s+", " ", context).strip(), 500) or "结构化结果引用此页"
                        if claim not in bucket:
                            bucket.append(claim)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(result)
    return found


def excerpt_around(text: str, keywords: list[str], limit: int = 1000) -> str:
    folded = text.casefold()
    positions = [folded.find(k.casefold()) for k in keywords if folded.find(k.casefold()) >= 0]
    start = max(0, (min(positions) if positions else 0) - limit // 3)
    return text[start:start + limit]


def build_source_audit(row: dict[str, str], result: dict[str, Any], *, max_cited_pages: int,
                       neighbor_pages: int, hits_per_theme: int, char_budget: int) -> dict[str, Any]:
    pages = page_text_map(resolve_parse_path(row))
    claims = cited_page_claims(result)
    cited = []
    for page in sorted(claims)[:max_cited_pages]:
        context = []
        for pageno in range(page - neighbor_pages, page + neighbor_pages + 1):
            if pageno in pages:
                context.append({"page": pageno, "text": clipped(pages[pageno], 1400)})
        cited.append({"cited_page": page, "claims": claims[page][:4], "page_exists": page in pages,
                      "source_context": context})
    themes = dict(THEMES_GENERAL)
    if row.get("issuer_type", "").lower() in {"18a", "18c", "biotech"}:
        themes.update(THEMES_18A)
    thematic = []
    for theme, keywords in themes.items():
        candidates = []
        for page, text in pages.items():
            matched = [k for k in keywords if k.casefold() in text.casefold()]
            if matched:
                candidates.append((len(matched), page, matched, text))
        candidates.sort(key=lambda x: (-x[0], x[1]))
        thematic.append({"theme": theme, "keywords": keywords,
                         "hits": [{"page": page, "matched": matched,
                                   "excerpt": excerpt_around(text, matched)}
                                  for _, page, matched, text in candidates[:hits_per_theme]]})
    audit = {"method": "full_parse定向页码回查+独立主题关键词候选检索；未输入完整PDF",
             "cited_pages_total": len(claims), "cited_pages_checked": len(cited),
             "cited_page_checks": cited, "thematic_search": thematic}
    encoded = json.dumps(audit, ensure_ascii=False)
    if len(encoded) > char_budget:
        audit["truncated_notice"] = f"原文核验包按 {char_budget} 字符预算压缩"
        for check in audit["cited_page_checks"]:
            exact = [x for x in check["source_context"] if x["page"] == check["cited_page"]]
            check["source_context"] = [{"page": x["page"], "text": clipped(x["text"], 700)} for x in exact]
        for theme in audit["thematic_search"]:
            theme["hits"] = [{**hit, "excerpt": clipped(hit["excerpt"], 600)} for hit in theme["hits"][:1]]
        encoded = json.dumps(audit, ensure_ascii=False)
        while len(encoded) > char_budget and len(audit["cited_page_checks"]) > 1:
            audit["cited_page_checks"].pop()
            audit["cited_pages_checked"] = len(audit["cited_page_checks"])
            encoded = json.dumps(audit, ensure_ascii=False)
    return audit


def compact_result(data: dict[str, Any]) -> dict[str, Any]:
    """保留评分所需字段，避免把全文 trace/原文重复发送给 LLM。"""
    packet: dict[str, Any] = {
        "doc_id": data.get("doc_id"),
        "reference_fundamental_score": data.get("reference_fundamental_score"),
        "cross_agent_features": data.get("cross_agent_features"),
    }
    for name in ("finance", "legal", "market"):
        src = data.get(name) or {}
        packet[name] = {k: src.get(k) for k in (
            "risk_score", "risk_level", "summary", "score_breakdown", "risk_points",
            "evidence_summary", "metrics", "gates",
        ) if src.get(k) is not None}
        trace = src.get("trace") or {}
        packet[name]["trace_review"] = {
            "keys": sorted(trace.keys()),
            "n_tool_calls": len(trace.get("tool_calls") or []),
            "n_turns": trace.get("n_turns"),
            "scoring_mode": trace.get("scoring_mode"),
            "structured_reasoning": clipped(str(trace.get("structured_reasoning") or ""), 1800),
        }
        features = src.get("features") or {}
        packet[name]["features_review"] = {k: features.get(k) for k in (
            "scoring_mode", "rules_floor", "think_status", "react_turns",
            "sentiment_analysis", "prediction", "post_listing",
        ) if features.get(k) is not None}
    master = data.get("master") or {}
    packet["master"] = {k: master.get(k) for k in (
        "judgment", "conflict_analysis", "debate_history", "predicted_windows",
        "price_path_forecast", "post_listing", "degraded", "degraded_reason",
    ) if master.get(k) is not None}
    return packet


def clipped(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n...[截断]"


def review_material(root: Path, row: dict[str, str], result: dict[str, Any], source_audit: dict[str, Any]) -> str:
    code = row["stock_code"].zfill(5)
    reports_dir = root / code / "reports"
    report_parts = []
    for kind in ("finance", "legal", "market", "ipo_risk_warning"):
        path = reports_dir / f"{code}_{kind}_report.md"
        if path.is_file():
            report_parts.append(f"## {path.name}\n{clipped(path.read_text(encoding='utf-8'), 9000)}")
    company = {k: row.get(k, "") for k in (
        "stock_code", "windcode", "company_display", "issuer_type", "hs_l1", "hs_l2", "hs_l3",
        "actual_list_date", "performance_class", "day1_return", "day5_return",
    )}
    return clipped(
        "公司与真实标签:\n" + json.dumps(company, ensure_ascii=False, indent=2)
        + "\n\n定向原文核验（full_parse.json，评分时优先使用）:\n" + json.dumps(source_audit, ensure_ascii=False)
        + "\n\n结构化分析结果:\n" + json.dumps(compact_result(result), ensure_ascii=False, default=str)
        + "\n\n最终报告:\n" + "\n\n".join(report_parts),
        90000,
    )


def number(value: Any, name: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} 缺失或不是数值")
    try:
        score = float(value)
    except (TypeError, ValueError):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:分|%|/100)?\s*", str(value))
        if not match:
            raise ValueError(f"{name} 不是数值: {value!r}")
        score = float(match.group(1))
    if not 0 <= score <= 100:
        raise ValueError(f"{name} 超出0-100: {score}")
    return round(score, 2)


SCORE_KEYS = (
    "risk_extraction_score", "evidence_recall_score", "citation_faithfulness_score",
    "coverage_audit_score", "traceability_score", "logic_score", "business_value_score",
)


def validate_judgment(data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or not data:
        raise ValueError("LLM未返回可解析的JSON对象")
    for key in SCORE_KEYS:
        number(data.get(key), key)


async def request_judgment(client: LLMClient, material: str, effort: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": material}]
    first = await client.chat_json(messages, enable_reasoning=True, reasoning_effort=effort,
                                   max_tokens=2600, reasoning_max_tokens=1200)
    attempts = [first]
    try:
        validate_judgment(first.get("data") or {})
        return first.get("data") or {}, attempts
    except ValueError as first_error:
        raw = str(first.get("content") or "").strip()
        repair_input = (
            "上一次输出不合格：" + str(first_error) + "。请重新输出完整评分JSON。\n"
            + ("上一次输出：\n" + raw if raw else "上一次正文为空，请依据原始评审材料重新评分。\n" + material)
        )
        second = await client.chat_json(
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": repair_input}],
            enable_reasoning=False, max_tokens=2200,
        )
        attempts.append(second)
        validate_judgment(second.get("data") or {})
        return second.get("data") or {}, attempts


def agent_score(data: dict[str, Any], name: str) -> Any:
    if name == "master":
        return ((data.get("master") or {}).get("judgment") or {}).get("overall_score")
    return (data.get(name) or {}).get("risk_score")


def base_row(row: dict[str, str], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "stock_code": row["stock_code"].zfill(5), "windcode": row.get("windcode", ""),
        "company_display": row.get("company_display", ""), "issuer_type": row.get("issuer_type", ""),
        "industry_l1": row.get("hs_l1", ""), "industry_l2": row.get("hs_l2", ""),
        "industry_l3": row.get("hs_l3", ""), "actual_list_date": row.get("actual_list_date", ""),
        "performance_class": row.get("performance_class", ""), "day1_return": row.get("day1_return", ""),
        "day5_return": row.get("day5_return", ""), "finance_risk_score": agent_score(result, "finance"),
        "legal_risk_score": agent_score(result, "legal"), "market_risk_score": agent_score(result, "market"),
        "master_risk_score": agent_score(result, "master"),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


async def main_async() -> int:
    p = argparse.ArgumentParser(description="DeepSeek LLM 专家量化评分（忽略文本粉饰度）")
    p.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--output-csv", type=Path, default=None)
    p.add_argument("--codes", default="", help="指定代码，逗号分隔")
    p.add_argument("--chat-model", default="deepseek-v4-flash")
    p.add_argument("--api-key", default=None, help="建议改用 DEEPSEEK_API_KEY 环境变量")
    p.add_argument("--api-base", default=None)
    p.add_argument("--reasoning-effort", choices=("low", "high", "max"), default="high")
    p.add_argument("--max-cited-pages", type=int, default=14, help="每家公司最多回查的引用页数")
    p.add_argument("--neighbor-pages", type=int, choices=(0, 1), default=1, help="引用页上下文页数")
    p.add_argument("--hits-per-theme", type=int, default=2, help="每个独立风险主题最多候选页数")
    p.add_argument("--source-char-budget", type=int, default=30000, help="定向原文核验包字符预算")
    p.add_argument("--continue-on-error", action="store_true")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()
    args.input_dir, args.manifest = args.input_dir.resolve(), args.manifest.resolve()
    output = (args.output_csv or args.input_dir / "llm_expert_scores.csv").resolve()
    rows = load_manifest(args.manifest)
    wanted = {x.strip().zfill(5) for x in args.codes.split(",") if x.strip()}
    if wanted:
        rows = [r for r in rows if r["stock_code"].zfill(5) in wanted]

    completed: dict[str, dict[str, Any]] = {}
    if args.resume and output.is_file():
        with output.open("r", encoding="utf-8-sig", newline="") as f:
            completed = {r["stock_code"].zfill(5): r for r in csv.DictReader(f) if r.get("status") == "ok"}
    out_rows: list[dict[str, Any]] = list(completed.values())
    settings = resolve_api_settings(api_key=args.api_key, api_base=args.api_base,
                                    chat_model=args.chat_model, provider="deepseek")
    client = LLMClient(settings); await client.init()
    try:
        for pos, row in enumerate(rows, 1):
            code = row["stock_code"].zfill(5)
            if code in completed:
                print(f"[{pos}/{len(rows)}] SKIP {code}")
                continue
            result_path = args.input_dir / code / "analysis_result.json"
            result: dict[str, Any] = {}
            source_audit = None
            response_attempts = None
            try:
                if not result_path.is_file():
                    raise FileNotFoundError(result_path)
                result = json.loads(result_path.read_text(encoding="utf-8"))
                print(f"[{pos}/{len(rows)}] scoring {code} {row['company_display']}", flush=True)
                source_audit = build_source_audit(
                    row, result, max_cited_pages=args.max_cited_pages,
                    neighbor_pages=args.neighbor_pages, hits_per_theme=args.hits_per_theme,
                    char_budget=args.source_char_budget,
                )
                raw_dir = args.input_dir / "llm_score_raw"; raw_dir.mkdir(parents=True, exist_ok=True)
                judged, response_attempts = await request_judgment(
                    client, review_material(args.input_dir, row, result, source_audit),
                    args.reasoning_effort,
                )
                response = response_attempts[-1]
                (raw_dir / f"{code}.attempts.json").write_text(json.dumps({
                    "source_audit": source_audit, "attempts": response_attempts,
                }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                names = ("risk_extraction_score", "evidence_recall_score", "traceability_score",
                         "logic_score", "business_value_score")
                scores = {name: number(judged.get(name), name) for name in names}
                diagnostics = {name: number(judged.get(name), name) for name in
                               ("citation_faithfulness_score", "coverage_audit_score")}
                overall = round(scores["risk_extraction_score"] * .25 + scores["evidence_recall_score"] * .20
                                + scores["traceability_score"] * .15 + scores["logic_score"] * .20
                                + scores["business_value_score"] * .20, 2)
                record = {**base_row(row, result), **scores, **diagnostics,
                          "source_pages_checked": source_audit["cited_pages_checked"],
                          "thematic_hits_checked": sum(len(x["hits"]) for x in source_audit["thematic_search"]),
                          "overall_score": overall,
                          "meets_extraction_target_80": scores["risk_extraction_score"] >= 80,
                          "meets_evidence_target_85": scores["evidence_recall_score"] >= 85,
                          "meets_traceability_target_100": scores["traceability_score"] == 100,
                          "llm_summary": str(judged.get("summary") or "").strip(),
                          "strengths": " | ".join(map(str, judged.get("strengths") or [])),
                          "weaknesses": " | ".join(map(str, judged.get("weaknesses") or [])),
                          "status": "ok", "error": ""}
                (raw_dir / f"{code}.json").write_text(json.dumps({"scores": record, "source_audit": source_audit,
                    "llm_response": response}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            except Exception as exc:
                raw_dir = args.input_dir / "llm_score_raw"; raw_dir.mkdir(parents=True, exist_ok=True)
                failure_payload = {"error": str(exc)}
                if source_audit is not None:
                    failure_payload["source_audit"] = source_audit
                if response_attempts is not None:
                    failure_payload["attempts"] = response_attempts
                (raw_dir / f"{code}.failed.json").write_text(
                    json.dumps(failure_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                record = {**base_row(row, result), "status": "failed", "error": str(exc)}
                print(f"ERROR [{code}] {exc}", file=sys.stderr)
                if not args.continue_on_error:
                    out_rows.append(record); write_csv(output, out_rows)
                    return 1
            out_rows.append(record); write_csv(output, out_rows)
    finally:
        await client.close()
    failures = sum(r.get("status") != "ok" for r in out_rows)
    print(f"Wrote {output} rows={len(out_rows)} failed={failures}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
