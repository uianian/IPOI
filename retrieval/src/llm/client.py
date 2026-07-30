from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
import urllib3

from src.config import settings
from src.llm.local_embedding import LocalEmbeddingFallback

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# OpenRouter 兼容 OpenAI API，但需要额外 header 标识来源
_OPENROUTER_EXTRA_HEADERS: dict[str, str] = {
    "HTTP-Referer": "https://github.com/ipo-risk-agent",
    "X-Title": "IPO Risk Agent",
}


class VLLMClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._base_url: str = ""
        self._headers: dict[str, str] = {}
        self._embedding_available: bool | None = None
        self._local_embedding: LocalEmbeddingFallback | None = None
        self._embedding_source: str | None = None

    async def init(self) -> None:
        self._base_url = settings.llm.base_url.rstrip("/")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        provider = settings.llm.provider

        if provider == "openrouter":
            api_key = settings.llm.resolved_api_key
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            headers.update(_OPENROUTER_EXTRA_HEADERS)
            logger.info(f"LLM provider: OpenRouter, base_url={self._base_url}, model={settings.llm.chat_model}")
        elif provider == "openai":
            api_key = settings.llm.resolved_api_key
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            logger.info(f"LLM provider: OpenAI, base_url={self._base_url}, model={settings.llm.chat_model}")
        else:
            logger.info(f"LLM provider: vLLM, base_url={self._base_url}, model={settings.llm.chat_model}")
        self._headers = headers
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=settings.llm.timeout_seconds,
            headers=headers,
            verify=False,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("VLLMClient not initialized. Call init() first.")
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> str:
        model = model or settings.llm.chat_model
        temperature = temperature if temperature is not None else settings.llm.temperature
        max_tokens = max_tokens or settings.llm.max_tokens

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        last_error = None
        for attempt in range(settings.llm.max_retries):
            try:
                resp = await self.client.post("/chat/completions", json=payload)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                    logger.warning(f"Rate limited (429), waiting {retry_after:.1f}s before retry {attempt + 1}")
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in (429, 502, 503, 504):
                    backoff = 2 ** attempt + 1
                    logger.warning(f"LLM chat attempt {attempt + 1} failed ({e.response.status_code}), backing off {backoff}s")
                    await asyncio.sleep(backoff)
                else:
                    logger.warning(f"LLM chat attempt {attempt + 1} failed: {e}")
            except Exception as e:
                last_error = e
                logger.warning(f"LLM chat attempt {attempt + 1} failed: {e}")

        logger.error(f"LLM chat failed after {settings.llm.max_retries} retries: {last_error}")
        raise RuntimeError(f"LLM调用失败（重试{settings.llm.max_retries}次后）: {last_error}")

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        json_schema: dict[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]:
        # OpenRouter 兼容 OpenAI，但免费模型通常不支持 json_schema 模式，
        # 统一使用 json_object 模式以保证兼容性
        if settings.llm.provider in ("openai",):
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": "structured_output", "schema": json_schema},
            }
        else:
            # vLLM 和 OpenRouter 均使用 json_object 模式
            response_format = {
                "type": "json_object",
            }
        content = await self.chat(messages, model=model, response_format=response_format)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Structured output parse failed, attempting extraction")
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            raise

    async def _check_embedding_available(self) -> bool:
        if self._embedding_available is not None:
            return self._embedding_available

        try:
            payload = {"model": settings.llm.embedding_model, "input": ["ping"]}
            resp = await self.client.post("/embeddings", json=payload)
            resp.raise_for_status()
            self._embedding_available = True
            logger.info("远程 embedding 服务可用")
        except Exception as e:
            self._embedding_available = False
            logger.warning(f"远程 embedding 服务不可用: {e}，将尝试本地 fallback")

        return self._embedding_available

    def _get_local_embedding(self) -> LocalEmbeddingFallback:
        if self._local_embedding is None:
            self._local_embedding = LocalEmbeddingFallback()
        return self._local_embedding

    @property
    def embedding_source(self) -> str | None:
        return self._embedding_source

    def embedding_source_changed(self, previous_source: str | None) -> bool:
        return self._embedding_source != previous_source

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        previous_source = self._embedding_source

        if await self._check_embedding_available():
            try:
                result = await self._remote_embed(texts, model)
                self._embedding_source = "remote"
                if previous_source is not None and previous_source != "remote":
                    logger.warning(
                        "Embedding 来源从 '%s' 切换到 'remote'，向量维度可能变化，"
                        "建议重建 FAISS 索引以确保一致性",
                        previous_source,
                    )
                return result
            except Exception as e:
                logger.warning(f"远程 embedding 调用失败: {e}，切换到本地 fallback")
                self._embedding_available = False

        local = self._get_local_embedding()
        try:
            result = await local.embed(texts)
            self._embedding_source = "local"
            if previous_source is not None and previous_source != "local":
                logger.warning(
                    "Embedding 来源从 '%s' 切换到 'local'，向量维度可能变化，"
                    "建议重建 FAISS 索引以确保一致性",
                    previous_source,
                )
            return result
        except Exception as e:
            logger.error(f"本地 fallback embedding 也不可用: {e}，将降级为纯 BM25 检索")
            self._embedding_source = "unavailable"
            raise

    async def _remote_embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        model = model or settings.llm.embedding_model
        payload = {"model": model, "input": texts}

        last_error = None
        for attempt in range(settings.llm.max_retries):
            try:
                resp = await self.client.post("/embeddings", json=payload)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                    logger.warning(f"Embedding rate limited (429), waiting {retry_after:.1f}s before retry {attempt + 1}")
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in (429, 502, 503, 504):
                    backoff = 2 ** attempt + 1
                    logger.warning(f"Embedding attempt {attempt + 1} failed ({e.response.status_code}), backing off {backoff}s")
                    await asyncio.sleep(backoff)
                else:
                    logger.warning(f"Embedding attempt {attempt + 1} failed: {e}")
            except Exception as e:
                last_error = e
                logger.warning(f"Embedding attempt {attempt + 1} failed: {e}")

        raise RuntimeError(f"Embedding调用失败（重试{settings.llm.max_retries}次后）: {last_error}")

    async def health_check(self) -> bool:
        try:
            # 对于 OpenRouter，使用 /models 端点检测连通性
            # 部分 provider 返回 200/403 均表示服务可达（403 通常表示认证通过但权限不足）
            resp = await self.client.get("/models")
            return resp.status_code in (200, 403)
        except Exception:
            return False