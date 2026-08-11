from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PKG_ROOT = Path(__file__).resolve().parent.parent
IPOI_ROOT = PKG_ROOT.parent.parent
DEFAULT_IPO_SETTINGS = PKG_ROOT.parent / "ipo" / "configs" / "settings.yaml"

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

    if provider_l == "deepseek":
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


def load_score_rules() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "score_rules.yaml")


def load_finance_schema() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "finance_schema.yaml")


def load_legal_schema() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "legal_schema.yaml")
