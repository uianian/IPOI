#!/usr/bin/env python3
"""跑财务 ‖ 法务 Agent。

财务默认 ReAct：多轮选工具 → submit_finance_report。
可用 --finance-pipeline 回退旧单次 LLM；--finance-rules-only 规则兜底。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.agents.finance_agent import FinanceAgent  # noqa: E402
from src.agents.legal_agent import LegalAgent  # noqa: E402
from src.agents.market_agent import MarketAgent  # noqa: E402
from src.config import (  # noqa: E402
    resolve_api_settings,
    resolve_firecrawl_settings,
    resolve_market_agent_settings,
    resolve_sina_finance_settings,
)
from src.graph.parallel import (  # noqa: E402
    run_finance_legal_market_parallel,
    run_finance_legal_parallel,
    run_master_from_saved,
)
from src.tools.llm_client import LLMClient  # noqa: E402
from src.tracing.run_logger import AgentRunLogger  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("run_finance_legal")


def _default_paths() -> dict[str, Path]:
    return {
        "finance_json": PKG_ROOT.parent.parent
        / "retrieval"
        / ".runtime"
        / "agent_retrieval_mixue.json",
        "legal_json": PKG_ROOT.parent / "ipo" / ".runtime" / "agent_retrieval_mixue_legal.json",
        "log_dir": PKG_ROOT / "logs",
    }


async def _amain() -> int:
    defaults = _default_paths()
    parser = argparse.ArgumentParser(description="Finance ‖ Legal IPO risk agents")
    parser.add_argument("--doc-id", default="136ee620-0473-450b-a566-72172824cdec")
    parser.add_argument("--doc-name", default="蜜雪集團")
    parser.add_argument("--pdf-name", default="02097_21-02-2025_蜜雪集團_全球發售.pdf")
    parser.add_argument(
        "--stock-code",
        default=None,
        help="市场 Agent 所需港股代码；未提供时尝试从 --pdf-name 开头识别",
    )
    parser.add_argument(
        "--issuer-type",
        choices=["general", "biotech", "18a", "18c"],
        default="general",
    )
    parser.add_argument("--retrieval-finance-json", type=Path, default=None)
    parser.add_argument("--retrieval-legal-json", type=Path, default=None)
    parser.add_argument(
        "--parse-json",
        type=Path,
        default=PKG_ROOT.parent.parent
        / "pdf_parsing"
        / "output"
        / "samples_batch"
        / "02097_21-02-2025_蜜雪集團_全球發售"
        / "full_parse.json",
        help="结构化 full_parse.json：财务章节检索与法务证据召回共用",
    )
    parser.add_argument(
        "--agent",
        choices=["finance", "legal", "market", "all"],
        default="all",
        help="选定 Agent：finance/legal/market/all（默认三者并行后接总控）",
    )
    parser.add_argument(
        "--use-live-retrieval",
        action="store_true",
        help="忽略离线 JSON，调用 retrieval/ 对 --doc-id 做 Grep∪BM25∪向量混合检索（需已建 index）",
    )
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--api-key", default=None, help="覆盖默认 agents/ipo settings.yaml")
    parser.add_argument("--api-base", default=None)
    parser.add_argument("--chat-model", default=None)
    parser.add_argument(
        "--provider",
        default=None,
        choices=["deepseek", "openrouter", "openai", "vllm"],
        help="LLM 提供商；deepseek 时默认 api_base=https://api.deepseek.com、model=deepseek-v4-flash",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["low", "high", "max"],
        help="全局默认思考强度（可被 --finance/--legal-reasoning-effort 覆盖）",
    )
    parser.add_argument(
        "--finance-reasoning-effort",
        default=None,
        choices=["low", "high", "max"],
        help="财务 ReAct reasoning_effort（默认 low）",
    )
    parser.add_argument(
        "--legal-reasoning-effort",
        default=None,
        choices=["low", "high", "max"],
        help="法务 ReAct reasoning_effort（默认 high）",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="（旧开关）法务规则流水线的 LLM 增强；默认法务已走 ReAct，仅与 --legal-rules-only 联用有意义",
    )
    parser.add_argument(
        "--legal-rules-only",
        action="store_true",
        help="法务强制规则流水线，不走 ReAct（对比/回归用）",
    )
    parser.add_argument(
        "--finance-rules-only",
        action="store_true",
        help="财务强制规则打分，不走 LLM（对比用）",
    )
    parser.add_argument(
        "--no-finance-llm",
        action="store_true",
        help="同 --finance-rules-only",
    )
    parser.add_argument(
        "--finance-pipeline",
        action="store_true",
        help="财务使用旧流水线（单次 LLM 分析），不用 ReAct 多轮选工具",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="ReAct 最大轮次（默认：财务 8 / 法务 8）",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=defaults["log_dir"],
        help="推理日志目录（默认 agents/hk_ipo_risk/logs）",
    )
    parser.add_argument(
        "--no-run-log",
        action="store_true",
        help="关闭文件推理日志",
    )
    parser.add_argument(
        "--skip-master",
        action="store_true",
        help="专家探查后不跑总控（旧行为：master=null）",
    )
    parser.add_argument(
        "--skip-experts",
        action="store_true",
        help="跳过财务/法务/市场探查，直接总控；必须配合 --from-result",
    )
    parser.add_argument(
        "--from-result",
        type=Path,
        default=None,
        help="已有专家 merged JSON（含 finance/legal）；供 --skip-experts 复用",
    )
    parser.add_argument("--master-provider", default=None, choices=["deepseek", "openrouter", "openai", "vllm"])
    parser.add_argument("--master-chat-model", default=None, help="覆盖总控 chat model；默认与专家共用")
    parser.add_argument("--out", type=Path, default=PKG_ROOT / ".runtime" / "mixue_finance_legal.json")
    args = parser.parse_args()
    if args.skip_experts and args.skip_master:
        parser.error("--skip-experts 与 --skip-master 互斥")
    if args.skip_experts and not args.from_result:
        parser.error("--skip-experts 需要 --from-result 指向已有专家结果 JSON")
    if args.skip_experts and args.from_result and not Path(args.from_result).is_file():
        parser.error(f"--from-result 不存在: {args.from_result}")

    stock_code = args.stock_code
    if not stock_code:
        code_match = __import__("re").match(r"^\s*(\d{4,5})", args.pdf_name or "")
        stock_code = code_match.group(1) if code_match else None
    if args.agent in {"market", "all"} and not stock_code:
        parser.error("--agent market/all 需要 --stock-code，或 --pdf-name 必须以股票代码开头")

    finance_rules_only = args.finance_rules_only or args.no_finance_llm

    fin_json = None if args.use_live_retrieval else (args.retrieval_finance_json or defaults["finance_json"])
    leg_json = None if args.use_live_retrieval else (args.retrieval_legal_json or defaults["legal_json"])
    if fin_json and not Path(fin_json).is_file():
        logger.warning("finance retrieval json missing: %s", fin_json)
        fin_json = None
    if leg_json and not Path(leg_json).is_file():
        logger.warning("legal retrieval json missing: %s", leg_json)
        leg_json = None
    parse_json = args.parse_json if args.parse_json and Path(args.parse_json).is_file() else None
    if parse_json is None:
        logger.warning("parse-json missing or unset; legal grep fallback disabled")

    # 财务默认启 LLM；法务默认 ReAct（--legal-rules-only 关闭）
    legal_react = not args.legal_rules_only
    need_llm = (
        (not args.skip_experts and args.agent in {"finance", "all"} and not finance_rules_only)
        or (not args.skip_experts and args.agent in {"legal", "all"} and legal_react)
        or (not args.skip_experts and args.agent in {"market", "all"})
        or (args.skip_experts)
        or (args.agent == "all" and not args.skip_master)
        or args.use_llm
    )
    llm = None
    if need_llm:
        settings = resolve_api_settings(
            api_key=args.api_key,
            api_base=args.api_base,
            chat_model=args.chat_model,
            provider=args.provider,
        )
        if args.reasoning_effort:
            settings["reasoning_effort"] = args.reasoning_effort
        llm = LLMClient(settings)
        await llm.init()
        logger.info(
            "LLM ready provider=%s model=%s key=%s finance_llm=%s legal_react=%s",
            settings["provider"],
            settings["chat_model"],
            "yes" if settings["api_key"] else "no",
            not finance_rules_only and args.agent in {"finance", "all"},
            legal_react and args.agent in {"legal", "all"},
        )
        if not settings["api_key"] and settings.get("provider") != "vllm":
            if args.skip_experts:
                logger.warning("No API key — master will degrade (rules fallback)")
            else:
                if args.agent in {"finance", "all"} and not finance_rules_only:
                    logger.warning("No API key — finance will fall back to rules scoring")
                if args.agent in {"legal", "all"} and legal_react:
                    logger.warning("No API key — legal will fall back to rules pipeline")
                if args.agent == "all" and not args.skip_master:
                    logger.warning("No API key — master will degrade (rules fallback)")

    finance_logger = None
    if not args.no_run_log and (
        args.skip_experts or args.agent in {"finance", "all"}
    ):
        finance_logger = AgentRunLogger(
            agent="finance",
            doc_id=args.doc_id,
            log_dir=args.log_dir,
            issuer_type=args.issuer_type,
            doc_name=args.doc_name,
            pdf_name=args.pdf_name,
        )
        logger.info("Finance run log → %s", finance_logger.log_path)

    legal_logger = None
    if not args.no_run_log and (
        args.skip_experts or (args.agent in {"legal", "all"} and legal_react)
    ):
        legal_logger = AgentRunLogger(
            agent="legal",
            doc_id=args.doc_id,
            log_dir=args.log_dir,
            issuer_type=args.issuer_type,
            doc_name=args.doc_name,
            pdf_name=args.pdf_name,
        )
        logger.info("Legal run log → %s", legal_logger.log_path)

    master_logger = None
    if not args.no_run_log and (
        args.skip_experts or (args.agent == "all" and not args.skip_master)
    ):
        master_logger = AgentRunLogger(
            agent="master",
            doc_id=args.doc_id,
            log_dir=args.log_dir,
            issuer_type=args.issuer_type,
            doc_name=args.doc_name,
            pdf_name=args.pdf_name,
        )
        logger.info("Master run log → %s", master_logger.log_path)

    market_logger = None
    if not args.no_run_log and (args.skip_experts or args.agent in {"market", "all"}):
        market_logger = AgentRunLogger(
            agent="market",
            doc_id=args.doc_id,
            log_dir=args.log_dir,
            issuer_type=args.issuer_type,
            doc_name=args.doc_name,
            pdf_name=args.pdf_name,
        )
        logger.info("Market run log → %s", market_logger.log_path)

    finance_llm = None if finance_rules_only else llm
    legal_llm = llm if (legal_react or args.use_llm) else None
    finance_max_turns = args.max_turns if args.max_turns is not None else 10
    legal_max_turns = args.max_turns if args.max_turns is not None else 10
    finance_effort = args.finance_reasoning_effort or args.reasoning_effort or "low"
    legal_effort = args.legal_reasoning_effort or args.reasoning_effort or "high"
    debate_dir = Path(PKG_ROOT) / ".runtime" / "debate"
    debate_dir.mkdir(parents=True, exist_ok=True)
    market_settings = resolve_market_agent_settings()
    firecrawl_ref = market_settings.get("firecrawl") or {}
    firecrawl_settings = resolve_firecrawl_settings(
        settings_path=firecrawl_ref.get("settings_path"),
        local_settings_path=firecrawl_ref.get("local_settings_path"),
        enabled=bool(firecrawl_ref.get("enabled", True)),
    )
    sina_ref = market_settings.get("sina_finance") or {}
    sina_settings = resolve_sina_finance_settings(
        settings_path=sina_ref.get("settings_path"),
        local_settings_path=sina_ref.get("local_settings_path"),
        enabled=bool(sina_ref.get("enabled", False)),
    )
    result: dict = {}

    try:
        if args.skip_experts:
            master_llm = llm
            if args.master_provider or args.master_chat_model:
                mset = resolve_api_settings(
                    api_key=args.api_key,
                    api_base=args.api_base,
                    chat_model=args.master_chat_model or args.chat_model,
                    provider=args.master_provider or args.provider,
                )
                master_llm = LLMClient(mset)
                await master_llm.init()
            logger.info("skip-experts from %s", args.from_result)
            result = await run_master_from_saved(
                args.from_result,
                master_llm=master_llm,
                parse_json=parse_json,
                debate_dir=debate_dir,
                finance_run_logger=finance_logger,
                legal_run_logger=legal_logger,
                market_run_logger=market_logger,
                master_run_logger=master_logger,
                doc_name=args.doc_name,
                finance_reasoning_effort=finance_effort,
                legal_reasoning_effort=legal_effort,
            )
        elif args.agent == "all":
            master_llm = llm
            if args.master_provider or args.master_chat_model:
                mset = resolve_api_settings(
                    api_key=args.api_key,
                    api_base=args.api_base,
                    chat_model=args.master_chat_model or args.chat_model,
                    provider=args.master_provider or args.provider,
                )
                master_llm = LLMClient(mset)
                await master_llm.init()
            result = await run_finance_legal_market_parallel(
                args.doc_id,
                stock_code=str(stock_code),
                market_llm=llm,
                market_settings=market_settings,
                firecrawl_settings=firecrawl_settings,
                sina_settings=sina_settings,
                market_run_logger=market_logger,
                issuer_type=args.issuer_type,
                finance_retrieval_json=fin_json,
                legal_retrieval_json=leg_json,
                parse_json=parse_json,
                finance_llm=finance_llm,
                legal_llm=legal_llm,
                master_llm=master_llm,
                top_k=args.top_k,
                finance_run_logger=finance_logger,
                finance_rules_only=finance_rules_only,
                finance_pipeline=args.finance_pipeline,
                legal_react=legal_react,
                legal_run_logger=legal_logger,
                master_run_logger=master_logger,
                legal_max_turns=legal_max_turns,
                finance_max_turns=finance_max_turns,
                debate_dir=debate_dir,
                doc_name=args.doc_name,
                pdf_name=args.pdf_name,
                legal_reasoning_effort=legal_effort,
                finance_reasoning_effort=finance_effort,
                skip_master=args.skip_master,
            )
        elif args.agent == "market":
            mkt = await MarketAgent(
                llm=llm,
                market_settings=market_settings,
                firecrawl_settings=firecrawl_settings,
                sina_settings=sina_settings,
                run_logger=market_logger,
            ).run(args.doc_id, stock_code=str(stock_code))
            result = {"doc_id": args.doc_id, "market": mkt.model_dump(), "master": None}
        elif args.agent == "finance":
            fin = await FinanceAgent(
                llm=finance_llm,
                run_logger=finance_logger,
                rules_only=finance_rules_only,
                pipeline=args.finance_pipeline,
                max_turns=finance_max_turns,
                debate_dir=debate_dir,
                reasoning_effort=finance_effort,
            ).run(
                args.doc_id,
                issuer_type=args.issuer_type,
                retrieval_json=fin_json,
                parse_json=parse_json,
                top_k=args.top_k,
                doc_name=args.doc_name,
                pdf_name=args.pdf_name,
            )
            result = {
                "doc_id": args.doc_id,
                "finance": fin.model_dump(),
                "cross_agent_features": [],
                "master": None,
            }
        elif args.agent == "legal":
            leg = await LegalAgent(
                llm=legal_llm,
                react=legal_react,
                run_logger=legal_logger,
                max_turns=legal_max_turns,
                debate_dir=debate_dir,
                reasoning_effort=legal_effort,
            ).run(
                args.doc_id,
                issuer_type=args.issuer_type,
                retrieval_json=leg_json,
                parse_json=parse_json,
                top_k=args.top_k,
                doc_name=args.doc_name,
                pdf_name=args.pdf_name,
            )
            result = {"doc_id": args.doc_id, "legal": leg.model_dump()}
    finally:
        extra_master = locals().get("master_llm")
        if extra_master is not None and extra_master is not llm:
            try:
                await extra_master.close()
            except Exception:
                pass
        if llm is not None:
            await llm.close()
        fin_sum = (result.get("finance") or {}).get("summary") if isinstance(locals().get("result"), dict) else None
        leg_sum = (result.get("legal") or {}).get("summary") if isinstance(locals().get("result"), dict) else None
        mas = (result.get("master") or {}) if isinstance(locals().get("result"), dict) else {}
        mas_sum = ((mas.get("judgment") or {}).get("verdict_reasoning") if isinstance(mas, dict) else None) or "done"
        if finance_logger is not None and not finance_logger._closed:
            finance_logger.close(final_summary=fin_sum or "done")
        if legal_logger is not None and not legal_logger._closed:
            legal_logger.close(final_summary=leg_sum or "done")
        if market_logger is not None and not market_logger._closed:
            mkt_sum = (
                (result.get("market") or {}).get("summary")
                if isinstance(locals().get("result"), dict)
                else None
            )
            market_logger.close(final_summary=mkt_sum or "done")
        if master_logger is not None and not master_logger._closed:
            master_logger.close(final_summary=str(mas_sum)[:200])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n=== Output: {args.out} ===")
    if "finance" in result:
        fin = result["finance"]
        mode = (fin.get("features") or {}).get("scoring_mode") or (fin.get("trace") or {}).get("scoring_mode")
        print(f"[finance] score={fin['risk_score']} level={fin['risk_level']} mode={mode}")
        print(f"  summary: {fin.get('summary')}")
        gates = fin.get("gates") or {}
        print(
            f"  gates: unprofitable={gates.get('is_unprofitable')} "
            f"skip_3_4={gates.get('skip_3_4')}({gates.get('skip_3_4_reason')}) "
            f"skip_2_4={gates.get('skip_2_4')}"
        )
        think = (fin.get("features") or {}).get("think_status")
        print(f"  think_status: {think}")
        n_turns = (fin.get("features") or {}).get("react_turns") or (fin.get("trace") or {}).get("n_turns")
        if n_turns:
            print(f"  react_turns: {n_turns}")
        logp = (fin.get("features") or {}).get("run_log") or {}
        if logp:
            print(f"  run_log: {logp.get('log')}")
        sr = (fin.get("trace") or {}).get("structured_reasoning")
        if sr:
            print(f"  reasoning: {str(sr)[:200]}…")
        print(f"  metrics: {list((fin.get('metrics') or {}).keys())}")
        for b in (fin.get("score_breakdown") or [])[:8]:
            print(f"  +{b.get('delta')} {b.get('code')} ({b.get('rule_ref')}) {b.get('note') or ''}")
    if "legal" in result:
        leg = result["legal"]
        mode = (leg.get("features") or {}).get("scoring_mode") or (leg.get("trace") or {}).get("scoring_mode") or "rules"
        print(f"[legal] score={leg['risk_score']} level={leg['risk_level']} mode={mode}")
        print(f"  summary: {leg.get('summary')}")
        n_turns = (leg.get("features") or {}).get("react_turns") or (leg.get("trace") or {}).get("n_turns")
        if n_turns:
            print(f"  react_turns: {n_turns}")
        dossier = (leg.get("features") or {}).get("debate_dossier_path")
        if dossier:
            print(f"  debate_dossier: {dossier}")
        logp = (leg.get("features") or {}).get("run_log") or {}
        if logp:
            print(f"  run_log: {logp.get('log')}")
        for b in (leg.get("score_breakdown") or [])[:10]:
            print(f"  +{b.get('delta')} {b.get('code')} ({b.get('rule_ref')}) {b.get('note') or ''}")
    if result.get("market"):
        market = result["market"]
        features = market.get("features") or {}
        print(
            f"[market] day1_break_risk={market['risk_score']} "
            f"level={market['risk_level']} mode={features.get('scoring_mode')}"
        )
        print(f"  summary: {market.get('summary')}")
        print(f"  deterministic_score: {features.get('deterministic_score')}")
        print(f"  llm_score: {features.get('llm_score')}")
        print(f"  debate_dossier: {features.get('debate_dossier_path')}")
    if result.get("market_error"):
        print(f"[market] ERROR: {result['market_error']}")
    if "reference_fundamental_score" in result:
        print(f"[ref] fundamental≈{result['reference_fundamental_score']}")
    master = result.get("master")
    if isinstance(master, dict) and master:
        j = master.get("judgment") or {}
        print(
            f"[master] score={j.get('overall_score')} level={j.get('risk_level_http')} "
            f"degraded={master.get('degraded')} debate_rounds={len(master.get('debate_history') or [])}"
        )
        if master.get("dossier_path"):
            print(f"  dossier: {master.get('dossier_path')}")
        emb = master.get("embellishment") or {}
        print(f"  embellishment: {emb.get('score')} ({emb.get('level')})")
    elif "master" in result:
        print(f"[master] {master} cross_agent_n={len(result.get('cross_agent_features') or [])}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
