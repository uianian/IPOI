"""Slim settings for the standalone IPO retrieval project.

Only LLM + retrieval (+ minimal system) are needed.
API keys: set via env ``IPO_LLM_API_KEY`` / ``OPENAI_API_KEY``, do not hardcode.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "settings.yaml"


def _load_yaml() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_raw = _load_yaml()


class LLMConfig(BaseSettings):
    provider: str = "vllm"
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    vllm_base_url: str = "http://localhost:8000/v1"
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    chat_model: str = "Qwen2.5-72B-Instruct"
    fallback_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    fallback_embedding_cache: str = "~/.cache/ipo_risk/embedding_fallback"
    fallback_embedding_mirror: str = "https://hf-mirror.com"
    max_retries: int = 3
    timeout_seconds: int = 60
    max_tokens: int = 4096
    temperature: float = 0.1

    model_config = {"env_prefix": "IPO_LLM_", "extra": "ignore"}

    @property
    def base_url(self) -> str:
        if self.provider in ("openai", "openrouter"):
            return self.api_base
        return self.vllm_base_url

    @property
    def resolved_api_key(self) -> str:
        if self.provider in ("openai", "openrouter"):
            return (
                self.api_key
                or os.environ.get("IPO_LLM_API_KEY", "")
                or os.environ.get("OPENAI_API_KEY", "")
            )
        return ""


class RetrievalConfig(BaseSettings):
    chunk_size: int = 512
    chunk_overlap: int = 64
    faiss_index_type: str = "IndexFlatIP"
    top_k: int = 10
    # Private to this project: retrieval/.runtime/indexes
    index_root: str = ".runtime/indexes"
    bm25_weight: float = 0.3
    vector_weight: float = 0.5
    grep_weight: float = 0.2
    rrf_k: int = 60
    grep_boost_rank: int = 3

    model_config = {"env_prefix": "IPO_RETRIEVAL_", "extra": "ignore"}


class SystemConfig(BaseSettings):
    app_name: str = "ipo-retrieval"
    debug: bool = True
    log_level: str = "INFO"

    model_config = {"env_prefix": "IPO_SYSTEM_", "extra": "ignore"}


class Settings(BaseSettings):
    system: SystemConfig = Field(default_factory=SystemConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)


def load_settings() -> Settings:
    return Settings(
        system=SystemConfig(**(_raw.get("system") or {})),
        llm=LLMConfig(**(_raw.get("llm") or {})),
        retrieval=RetrievalConfig(**(_raw.get("retrieval") or {})),
    )


settings = load_settings()
