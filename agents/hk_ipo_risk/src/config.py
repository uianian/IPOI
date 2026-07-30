from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PKG_ROOT = Path(__file__).resolve().parent.parent
IPOI_ROOT = PKG_ROOT.parent.parent
DEFAULT_IPO_SETTINGS = PKG_ROOT.parent / "ipo" / "configs" / "settings.yaml"


def load_yaml(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def resolve_api_settings(
    api_key: str | None = None,
    api_base: str | None = None,
    chat_model: str | None = None,
    settings_path: Path | str | None = None,
) -> dict[str, Any]:
    """API Key 优先级: CLI/env > agents/ipo/configs/settings.yaml。"""
    settings_file = Path(settings_path) if settings_path else DEFAULT_IPO_SETTINGS
    ipo = load_yaml(settings_file)
    llm = ipo.get("llm") or {}

    key = (
        api_key
        or os.environ.get("IPO_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or llm.get("api_key")
        or ""
    )
    base = (
        api_base
        or os.environ.get("IPO_LLM_API_BASE")
        or llm.get("api_base")
        or "https://openrouter.ai/api/v1"
    )
    model = (
        chat_model
        or os.environ.get("IPO_LLM_CHAT_MODEL")
        or llm.get("chat_model")
        or "google/gemma-4-31b-it"
    )
    provider = llm.get("provider") or "openrouter"
    return {
        "api_key": key,
        "api_base": base.rstrip("/"),
        "chat_model": model,
        "provider": provider,
        "max_tokens": int(llm.get("max_tokens") or 4096),
        "temperature": 0.0,  # 研判固定 0，不跟随 agents/ipo settings.yaml 的 temperature
        "timeout_seconds": int(llm.get("timeout_seconds") or 60),
        "max_retries": int(llm.get("max_retries") or 3),
        "settings_path": str(settings_file),
    }


def load_score_rules() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "score_rules.yaml")


def load_finance_schema() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "finance_schema.yaml")


def load_legal_schema() -> dict[str, Any]:
    return load_yaml(PKG_ROOT / "configs" / "legal_schema.yaml")
