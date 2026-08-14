#!/usr/bin/env python3
"""配置化运行市场情绪 Agent；业务侧只传 stock_code 和 doc_id。"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

from src.agents.market_agent import MarketAgent  # noqa: E402
from src.config import (  # noqa: E402
    resolve_api_settings,
    resolve_firecrawl_settings,
    resolve_market_agent_settings,
    resolve_sina_finance_settings,
)
from src.tools.llm_client import LLMClient  # noqa: E402
from src.tools.market_data import normalize_stock_code  # noqa: E402
from src.storage.market_store import PostgresMarketStore  # noqa: E402

logger = logging.getLogger("run_market_agent")


def _safe_filename_token(value: str) -> str:
    # 保留中英文/数字/下划线/点/连字符，其余替换为下划线；公司名可直接进文件名。
    token = re.sub(r"[^\w.-]+", "_", str(value).strip())
    return token.strip("._") or "market"


def _output_path(
    output_cfg: dict,
    key: str,
    *,
    doc_id: str,
    stock_code: str,
    company: str = "",
) -> Path:
    directory = Path(output_cfg["directory"])
    filename = str(output_cfg[key]).format(
        doc_id=_safe_filename_token(doc_id),
        stock_code=stock_code,
        company=_safe_filename_token(company),
    )
    return directory / filename


async def _amain() -> int:
    parser = argparse.ArgumentParser(
        description="市场情绪 Agent：仅 stock_code 和 doc_id 为动态业务参数"
    )
    parser.add_argument("--stock-code", required=True, help="港股代码，例如 02097")
    parser.add_argument("--doc-id", required=True, help="主链路文档/任务标识")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="可选固定配置文件；默认 configs/market_agent.yaml",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "offline", "llm"],
        default="auto",
        help="LLM 开关：auto=按配置 llm.enabled；offline=强制纯确定性；llm=强制启用 LLM",
    )
    args = parser.parse_args()

    stock_code = normalize_stock_code(args.stock_code)
    market_settings = resolve_market_agent_settings(settings_path=args.config)
    if args.mode == "offline":
        (market_settings.setdefault("llm", {}))["enabled"] = False
    elif args.mode == "llm":
        (market_settings.setdefault("llm", {}))["enabled"] = True
    logging.basicConfig(
        level=getattr(
            logging,
            str((market_settings.get("logging") or {}).get("level") or "INFO"),
            logging.INFO,
        ),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    firecrawl_ref = market_settings.get("firecrawl") or {}
    firecrawl_settings = resolve_firecrawl_settings(
        settings_path=firecrawl_ref.get("settings_path"),
        local_settings_path=firecrawl_ref.get("local_settings_path"),
        enabled=bool(firecrawl_ref.get("enabled", True)),
    )
    logger.info(
        "Firecrawl configured=%s enabled=%s policy=%s",
        firecrawl_settings["configured"],
        firecrawl_settings["enabled"],
        firecrawl_settings["fetch_policy"],
    )
    sina_ref = market_settings.get("sina_finance") or {}
    sina_settings = resolve_sina_finance_settings(
        settings_path=sina_ref.get("settings_path"),
        local_settings_path=sina_ref.get("local_settings_path"),
        enabled=bool(sina_ref.get("enabled", False)),
    )
    logger.info(
        "Sina Finance configured=%s enabled=%s",
        sina_settings["configured"],
        sina_settings["enabled"],
    )

    llm = None
    llm_ref = market_settings.get("llm") or {}
    if llm_ref.get("enabled"):
        llm_settings = resolve_api_settings(
            api_key=llm_ref.get("api_key") or None,
            api_base=llm_ref.get("api_base") or None,
            chat_model=llm_ref.get("chat_model") or None,
            settings_path=llm_ref.get("settings_path") or None,
        )
        if llm_settings.get("api_key"):
            llm = LLMClient(llm_settings)
            await llm.init()
            logger.info(
                "LLM enabled provider=%s model=%s",
                llm_settings["provider"],
                llm_settings["chat_model"],
            )
        elif llm_ref.get("required") or args.mode == "llm":
            raise RuntimeError(
                "--mode llm 或 market_agent.llm.required=true，但未配置 LLM API Key"
            )
        else:
            logger.warning(
                "No LLM API key; deterministic sentiment remains available, "
                "but public opinion will not enter module weights"
            )

    try:
        result = await MarketAgent(
            llm=llm,
            market_settings=market_settings,
            firecrawl_settings=firecrawl_settings,
            sina_settings=sina_settings,
        ).run(
            args.doc_id,
            stock_code=stock_code,
        )
    finally:
        if llm is not None:
            await llm.close()

    output_cfg = market_settings["output"]
    company = (result.features.get("company") or "").strip() or stock_code
    json_path = _output_path(
        output_cfg,
        "json_filename",
        doc_id=args.doc_id,
        stock_code=stock_code,
        company=company,
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report_path = None
    if output_cfg.get("write_markdown", True):
        report_filename = str(output_cfg["report_filename"]).format(
            doc_id=_safe_filename_token(args.doc_id),
            stock_code=stock_code,
            company=_safe_filename_token(company),
        )
        report_path = Path(
            output_cfg.get("report_directory") or output_cfg["directory"]
        ) / report_filename
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            str(result.features.get("sentiment_report_markdown") or "") + "\n",
            encoding="utf-8",
        )

    database = market_settings.get("database") or {}
    database_run_id = None
    if database.get("enabled"):
        postgres_url = str(database.get("postgres_url") or "").strip()
        if not postgres_url:
            message = "database.enabled=true, but MARKET_DATABASE_URL/postgres_url is empty"
            if database.get("required"):
                raise RuntimeError(message)
            logger.warning("%s; result remains available in local artifacts", message)
        else:
            store = PostgresMarketStore(postgres_url, schema=str(database.get("schema") or "market_agent"))
            try:
                await store.initialize()
                database_run_id = await store.persist_prelisting_result(
                    result.model_dump(mode="json"),
                    artifact_json=str(json_path),
                    artifact_report=str(report_path) if report_path else None,
                )
            finally:
                await store.close()

    sentiment = result.features.get("sentiment_analysis") or {}
    print(f"stock_code={stock_code}")
    print(f"doc_id={args.doc_id}")
    print(f"sentiment_state={sentiment.get('overall_state')}")
    print(f"overall_net_support={sentiment.get('overall_net_support')}")
    print(f"prelisting_day1_break_risk_score={result.risk_score}")
    print(f"deterministic_score={result.features.get('deterministic_score')}")
    print(f"llm_score={result.features.get('llm_score')}")
    print(f"scoring_mode={result.features.get('scoring_mode')}")
    print(f"debate_dossier={result.features.get('debate_dossier_path')}")
    print(f"json={json_path}")
    if report_path:
        print(f"report={report_path}")
    if database_run_id:
        print(f"database_run_id={database_run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))

