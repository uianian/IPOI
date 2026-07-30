from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
import os

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
                or os.environ.get("OPENROUTER_API_KEY", "")
                or os.environ.get("OPENAI_API_KEY", "")
            )
        return ""


class RetrievalConfig(BaseSettings):
    chunk_size: int = 512
    chunk_overlap: int = 64
    faiss_index_type: str = "IndexFlatIP"
    top_k: int = 10
    index_root: str = ".runtime/indexes"
    bm25_weight: float = 0.3
    vector_weight: float = 0.5
    grep_weight: float = 0.2
    rrf_k: int = 60
    grep_boost_rank: int = 3

    model_config = {"env_prefix": "IPO_RETRIEVAL_", "extra": "ignore"}


class DebateConfig(BaseSettings):
    max_rounds: int = 3
    consensus_threshold: float = 0.8

    model_config = {"env_prefix": "IPO_DEBATE_", "extra": "ignore"}


class FusionConfig(BaseSettings):
    fundamental_weight: float = 0.65
    sentiment_weight: float = 0.35
    risk_levels: dict[str, list[float]] = Field(default_factory=dict)

    model_config = {"env_prefix": "IPO_FUSION_", "extra": "ignore"}


class SentimentConfig(BaseSettings):
    market_temperature_weight: float = 0.3
    sector_liquidity_weight: float = 0.25
    public_opinion_weight: float = 0.25
    ipo_subscription_weight: float = 0.2
    data_freshness_hours: int = 24
    extreme_move_threshold: float = 0.05

    model_config = {"env_prefix": "IPO_SENTIMENT_", "extra": "ignore"}


class DatabaseConfig(BaseSettings):
    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ipo_risk"
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_hours: int = 24

    model_config = {"env_prefix": "IPO_DB_", "extra": "ignore"}


class APIConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    model_config = {"env_prefix": "IPO_API_", "extra": "ignore"}


class SystemConfig(BaseSettings):
    app_name: str = "ipo-risk-agent"
    debug: bool = True
    log_level: str = "INFO"

    model_config = {"env_prefix": "IPO_SYSTEM_", "extra": "ignore"}


class Settings(BaseSettings):
    system: SystemConfig = Field(default_factory=SystemConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    debate: DebateConfig = Field(default_factory=DebateConfig)
    fusion: FusionConfig = Field(default_factory=FusionConfig)
    sentiment: SentimentConfig = Field(default_factory=SentimentConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    api: APIConfig = Field(default_factory=APIConfig)


def load_settings() -> Settings:
    llm_cfg = {**_raw.get("llm", {})}
    retrieval_cfg = {**_raw.get("retrieval", {})}
    debate_cfg = {**_raw.get("debate", {})}
    fusion_cfg = {**_raw.get("fusion", {})}
    sentiment_cfg = {**_raw.get("sentiment", {})}
    database_cfg = {**_raw.get("database", {})}
    api_cfg = {**_raw.get("api", {})}
    system_cfg = {**_raw.get("system", {})}

    return Settings(
        system=SystemConfig(**system_cfg),
        llm=LLMConfig(**llm_cfg),
        retrieval=RetrievalConfig(**retrieval_cfg),
        debate=DebateConfig(**debate_cfg),
        fusion=FusionConfig(**fusion_cfg),
        sentiment=SentimentConfig(**sentiment_cfg),
        database=DatabaseConfig(**database_cfg),
        api=APIConfig(**api_cfg),
    )


settings = load_settings()