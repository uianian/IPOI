from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PKG_ROOT = Path(__file__).resolve().parent.parent
IPOI_ROOT = PKG_ROOT.parent.parent
DEFAULT_IPO_SETTINGS = PKG_ROOT.parent / "ipo" / "configs" / "settings.yaml"
DEFAULT_FIRECRAWL_SETTINGS = PKG_ROOT / "configs" / "firecrawl.yaml"
DEFAULT_FIRECRAWL_LOCAL_SETTINGS = PKG_ROOT / "configs" / "firecrawl.local.yaml"
DEFAULT_MARKET_AGENT_SETTINGS = PKG_ROOT / "configs" / "market_agent.yaml"
DEFAULT_MARKET_AGENT_LOCAL_SETTINGS = PKG_ROOT / "configs" / "market_agent.local.yaml"
DEFAULT_SINA_SETTINGS = PKG_ROOT / "configs" / "sina_finance.yaml"
DEFAULT_SINA_LOCAL_SETTINGS = PKG_ROOT / "configs" / "sina_finance.local.yaml"

DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
OPENROUTER_DEFAULT_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "google/gemma-4-31b-it"


def load_yaml(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _looks_like_deepseek_model(model: str | None) -> bool:
    m = (model or "").strip().lower()
    return m.startswith("deepseek")


def _provider_block(llm: dict[str, Any], provider: str) -> dict[str, Any]:
    """取出 llm.providers.<provider>；无则空 dict。"""
    providers = llm.get("providers")
    if not isinstance(providers, dict):
        return {}
    block = providers.get(provider)
    return block if isinstance(block, dict) else {}


def resolve_api_settings(
    api_key: str | None = None,
    api_base: str | None = None,
    chat_model: str | None = None,
    provider: str | None = None,
    settings_path: Path | str | None = None,
) -> dict[str, Any]:
    """API Key 优先级: CLI/env > settings.yaml providers[provider] > 扁平 llm 字段。

    settings.yaml 可用 llm.providers.openrouter / llm.providers.deepseek 并存，
    用 llm.provider 切换；CLI --provider / IPO_LLM_PROVIDER 可覆盖。
    """
    settings_file = Path(settings_path) if settings_path else DEFAULT_IPO_SETTINGS
    ipo = load_yaml(settings_file)
    llm = ipo.get("llm") or {}

    # CLI / 环境变量显式 base
    explicit_base = (api_base or os.environ.get("IPO_LLM_API_BASE") or "").strip()
    provider_from = (
        provider
        or os.environ.get("IPO_LLM_PROVIDER")
        or llm.get("provider")
        or ""
    )
    provider_l = str(provider_from).strip().lower()
    if "deepseek.com" in explicit_base.lower():
        provider_l = "deepseek"
    if not provider_l:
        provider_l = "openrouter"

    prov = _provider_block(llm, provider_l)
    # 扁平字段作兼容回退（旧 yaml / agents/ipo）
    flat_key = str(llm.get("api_key") or "")
    flat_base = str(llm.get("api_base") or "").strip()
    flat_model = str(llm.get("chat_model") or "")

    key = (
        api_key
        or os.environ.get("IPO_LLM_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or (str(prov.get("api_key") or "").strip() or None)
        or flat_key
        or ""
    )

    yaml_base = str(prov.get("api_base") or flat_base or "").strip()
    yaml_model = str(prov.get("chat_model") or flat_model or "")
    yaml_effort = prov.get("reasoning_effort") or llm.get("reasoning_effort")

    model_from = (
        chat_model
        or os.environ.get("IPO_LLM_CHAT_MODEL")
        or ""
    ).strip()

    if provider_l == "vllm":
        base = (explicit_base or yaml_base or "http://127.0.0.1:8000/v1").rstrip("/")
        model = model_from or yaml_model or "Qwen3.6-35B"
        reasoning_effort = (
            os.environ.get("IPO_LLM_REASONING_EFFORT")
            or yaml_effort
            or "low"
        )
    elif provider_l == "deepseek":
        if explicit_base:
            base = explicit_base.rstrip("/")
        elif "deepseek.com" in yaml_base.lower():
            base = yaml_base.rstrip("/")
        else:
            base = DEEPSEEK_DEFAULT_BASE
        if model_from:
            model = model_from
        elif _looks_like_deepseek_model(yaml_model):
            model = yaml_model
        else:
            model = DEEPSEEK_DEFAULT_MODEL
        reasoning_effort = (
            os.environ.get("IPO_LLM_REASONING_EFFORT")
            or yaml_effort
            or "high"
        )
    else:
        base = (explicit_base or yaml_base or OPENROUTER_DEFAULT_BASE).rstrip("/")
        model = model_from or yaml_model or OPENROUTER_DEFAULT_MODEL
        reasoning_effort = (
            os.environ.get("IPO_LLM_REASONING_EFFORT")
            or yaml_effort
            or "low"
        )

    return {
        "api_key": key,
        "api_base": base,
        "chat_model": model,
        "provider": provider_l,
        "max_tokens": int(llm.get("max_tokens") or 4096),
        "temperature": 0.0,  # 研判固定 0，不跟随 agents/ipo settings.yaml 的 temperature
        "timeout_seconds": int(llm.get("timeout_seconds") or 60),
        "max_retries": int(llm.get("max_retries") or 3),
        "reasoning_effort": reasoning_effort,
        "settings_path": str(settings_file),
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _repo_path(value: Any, default: Path) -> Path:
    text = str(value or "").strip()
    path = Path(text).expanduser() if text else default
    return path if path.is_absolute() else IPOI_ROOT / path


def resolve_market_agent_settings(
    *,
    settings_path: Path | str | None = None,
    local_settings_path: Path | str | None = None,
) -> dict[str, Any]:
    """Load fixed market-agent parameters from tracked + local YAML files.

    ``stock_code`` and ``doc_id`` deliberately do not belong to this config;
    they identify each run and remain runtime inputs. All relative paths are
    resolved from the IPOI repository root so commands are independent of cwd.
    """
    base_path = Path(settings_path) if settings_path else DEFAULT_MARKET_AGENT_SETTINGS
    local_path = (
        Path(local_settings_path)
        if local_settings_path
        else DEFAULT_MARKET_AGENT_LOCAL_SETTINGS
    )
    base = load_yaml(base_path).get("market_agent") or {}
    local = load_yaml(local_path).get("market_agent") or {}
    merged = _deep_merge(base, local)

    data = merged.get("data") if isinstance(merged.get("data"), dict) else {}
    cutoff = merged.get("cutoff") if isinstance(merged.get("cutoff"), dict) else {}
    llm = merged.get("llm") if isinstance(merged.get("llm"), dict) else {}
    firecrawl = (
        merged.get("firecrawl")
        if isinstance(merged.get("firecrawl"), dict)
        else {}
    )
    sina = merged.get("sina_finance") if isinstance(merged.get("sina_finance"), dict) else {}
    output = merged.get("output") if isinstance(merged.get("output"), dict) else {}
    logging_cfg = (
        merged.get("logging")
        if isinstance(merged.get("logging"), dict)
        else {}
    )
    database = (
        merged.get("database")
        if isinstance(merged.get("database"), dict)
        else {}
    )

    return {
        "data": {
            "features_csv": str(
                _repo_path(
                    data.get("features_csv"),
                    IPOI_ROOT / "market" / "data" / "derived" / "ipo_sentiment_features.csv",
                )
            ),
            "news_dir": str(
                _repo_path(
                    data.get("news_dir"),
                    IPOI_ROOT / "market" / "data" / "external" / "news",
                )
            ),
            "postlisting_checkpoints_csv": str(
                _repo_path(
                    data.get("postlisting_checkpoints_csv"),
                    IPOI_ROOT / "market" / "data" / "derived" / "ipo_postlisting_checkpoints.csv",
                )
            ),
        },
        "cutoff": {
            "strict_prelisting": bool(cutoff.get("strict_prelisting", True)),
        },
        "llm": {
            "enabled": bool(llm.get("enabled", True)),
            "required": bool(llm.get("required", False)),
            "settings_path": str(
                _repo_path(llm.get("settings_path"), DEFAULT_IPO_SETTINGS)
            ),
            "api_key": str(llm.get("api_key") or "").strip(),
            "api_base": str(llm.get("api_base") or "").strip(),
            "chat_model": str(llm.get("chat_model") or "").strip(),
            "max_turns": int(llm.get("max_turns") or 10),
        },
        "firecrawl": {
            "enabled": bool(firecrawl.get("enabled", True)),
            "settings_path": str(
                _repo_path(firecrawl.get("settings_path"), DEFAULT_FIRECRAWL_SETTINGS)
            ),
            "local_settings_path": str(
                _repo_path(
                    firecrawl.get("local_settings_path"),
                    DEFAULT_FIRECRAWL_LOCAL_SETTINGS,
                )
            ),
        },
        "sina_finance": {
            "enabled": bool(sina.get("enabled", False)),
            "settings_path": str(_repo_path(sina.get("settings_path"), DEFAULT_SINA_SETTINGS)),
            "local_settings_path": str(
                _repo_path(sina.get("local_settings_path"), DEFAULT_SINA_LOCAL_SETTINGS)
            ),
        },
        "output": {
            "directory": str(
                _repo_path(
                    output.get("directory"),
                    PKG_ROOT / ".runtime" / "market",
                )
            ),
            "report_directory": str(
                _repo_path(
                    output.get("report_directory"),
                    PKG_ROOT / "reports",
                )
            ),
            "json_filename": str(
                output.get("json_filename") or "{doc_id}_{stock_code}_market.json"
            ),
            "report_filename": str(
                output.get("report_filename")
                or "{doc_id}_market_report.md"
            ),
            "postlisting_json_filename": str(
                output.get("postlisting_json_filename")
                or "{doc_id}_{stock_code}_postlisting.json"
            ),
            "postlisting_report_filename": str(
                output.get("postlisting_report_filename")
                or "{doc_id}_{stock_code}_postlisting_report.md"
            ),
            "write_markdown": bool(output.get("write_markdown", True)),
            "debate_directory": str(
                _repo_path(
                    output.get("debate_directory"),
                    PKG_ROOT / ".runtime" / "debate",
                )
            ),
        },
        "logging": {
            "level": str(logging_cfg.get("level") or "INFO").upper(),
        },
        "database": {
            "enabled": bool(database.get("enabled", False)),
            "required": bool(database.get("required", False)),
            "schema": str(database.get("schema") or "market_agent"),
            "postgres_url": str(
                os.environ.get("MARKET_DATABASE_URL")
                or database.get("postgres_url")
                or ""
            ),
        },
        "settings_path": str(base_path),
        "local_settings_path": str(local_path),
    }


def resolve_sina_finance_settings(
    *,
    settings_path: Path | str | None = None,
    local_settings_path: Path | str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Resolve a deployment-specific Sina Finance JSON news API adapter."""
    base_path = Path(settings_path) if settings_path else DEFAULT_SINA_SETTINGS
    local_path = Path(local_settings_path) if local_settings_path else DEFAULT_SINA_LOCAL_SETTINGS
    base = load_yaml(base_path).get("sina_finance") or {}
    local = load_yaml(local_path).get("sina_finance") or {}
    merged = _deep_merge(base, local)
    api_key = str(os.environ.get("SINA_FINANCE_API_KEY") or merged.get("api_key") or "").strip()
    base_url = str(os.environ.get("SINA_FINANCE_API_URL") or merged.get("base_url") or "").strip()
    requested = bool(merged.get("enabled", False) if enabled is None else enabled)
    return {
        **merged,
        "api_key": api_key,
        "base_url": base_url,
        "requested_enabled": requested,
        "configured": bool(base_url),
        "enabled": bool(requested and base_url),
        "settings_path": str(base_path),
        "local_settings_path": str(local_path),
    }


def resolve_firecrawl_settings(
    *,
    api_key: str | None = None,
    api_url: str | None = None,
    settings_path: Path | str | None = None,
    local_settings_path: Path | str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Resolve Firecrawl without ever requiring a secret in source control.

    Precedence for credentials is explicit argument, environment, local YAML,
    then the tracked default YAML. ``firecrawl.local.yaml`` is intentionally
    git-ignored, but ``firecrawl.yaml`` also supports ``api_key`` for deployments
    that inject a private configuration file at runtime.
    """
    base_path = Path(settings_path) if settings_path else DEFAULT_FIRECRAWL_SETTINGS
    local_path = (
        Path(local_settings_path)
        if local_settings_path
        else DEFAULT_FIRECRAWL_LOCAL_SETTINGS
    )
    base = load_yaml(base_path).get("firecrawl") or {}
    local = load_yaml(local_path).get("firecrawl") or {}
    merged = _deep_merge(base, local)

    resolved_key = str(
        api_key
        or os.environ.get("FIRECRAWL_API_KEY")
        or merged.get("api_key")
        or ""
    ).strip()
    resolved_url = str(
        api_url
        or os.environ.get("FIRECRAWL_API_URL")
        or merged.get("api_url")
        or "https://api.firecrawl.dev"
    ).rstrip("/")
    requested_enabled = bool(merged.get("enabled", True)) if enabled is None else enabled
    search = merged.get("search") if isinstance(merged.get("search"), dict) else {}
    scrape = merged.get("scrape") if isinstance(merged.get("scrape"), dict) else {}
    cache = merged.get("cache") if isinstance(merged.get("cache"), dict) else {}

    return {
        "enabled": bool(requested_enabled and resolved_key),
        "requested_enabled": bool(requested_enabled),
        "configured": bool(resolved_key),
        "api_key": resolved_key,
        "api_url": resolved_url,
        "fetch_policy": str(merged.get("fetch_policy") or "on_missing"),
        "search": {
            "query_template": str(
                search.get("query_template")
                or '"{company}" 风险 争议 监管 舆论 新闻'
            ),
            "sources": list(search.get("sources") or ["web"]),
            "limit_per_query": max(1, min(5, int(search.get("limit_per_query") or 5))),
            "max_urls": max(1, min(5, int(search.get("max_urls") or 5))),
            "timeout_ms": max(1000, int(search.get("timeout_ms") or 60000)),
            "location": str(search.get("location") or "Hong Kong"),
            "use_tbs_date_filter": bool(search.get("use_tbs_date_filter", True)),
            "historical_lookback_years": max(
                1, min(20, int(search.get("historical_lookback_years") or 5))
            ),
            "exclude_domains": list(search.get("exclude_domains") or []),
        },
        "scrape": {
            "max_requests": max(1, min(5, int(scrape.get("max_requests") or 5))),
            "only_main_content": bool(scrape.get("only_main_content", True)),
            "max_content_chars": max(500, int(scrape.get("max_content_chars") or 8000)),
            "timeout_ms": max(1000, int(scrape.get("timeout_ms") or 30000)),
            "max_age_ms": max(0, int(scrape.get("max_age_ms") or 86400000)),
            "max_raw_content_chars": max(
                8000, int(scrape.get("max_raw_content_chars") or 100000)
            ),
            "max_raw_html_chars": max(
                20000, int(scrape.get("max_raw_html_chars") or 250000)
            ),
        },
        "cache": {
            "merge_existing": bool(cache.get("merge_existing", True)),
            "save_raw_results": bool(cache.get("save_raw_results", True)),
            "reuse_raw_results": bool(cache.get("reuse_raw_results", True)),
        },
        "settings_path": str(base_path),
        "local_settings_path": str(local_path),
    }


def load_score_rules() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "score_rules.yaml")


def load_finance_schema() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "finance_schema.yaml")


def load_legal_schema() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "legal_schema.yaml")


def load_master_rules() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "master_rules.yaml")
