from __future__ import annotations

import json
import logging
from typing import Any

from src.models.evidence import EvidenceRef
from src.skills.long_doc_retrieval.retriever import HybridRetriever

logger = logging.getLogger(__name__)


class StructuredExtractor:
    def __init__(self, vllm_client: Any, retriever: HybridRetriever) -> None:
        self._vllm = vllm_client
        self._retriever = retriever

    async def extract(
        self,
        doc_id: str,
        query: str,
        extraction_prompt: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        results = await self._retriever.retrieve(query, top_k=top_k)
        if not results:
            return []

        context = "\n\n".join(
            f"[第{c.page_number}页] {c.content}" for c, _ in results
        )

        messages = [
            {"role": "system", "content": "你是一名专业的金融文档信息抽取助手。请严格基于提供的文本内容进行抽取。"},
            {"role": "user", "content": extraction_prompt.format(text=context)},
        ]

        try:
            content = await self._vllm.chat(messages, temperature=0.0)
            parsed = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
            else:
                logger.warning("Failed to parse extraction result")
                return []
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return []

        items = parsed if isinstance(parsed, list) else parsed.get("items", parsed.get("risk_features", parsed.get("indicators", [])))
        if isinstance(items, dict):
            items = [items]

        for item in items:
            if "evidence_text" in item and item["evidence_text"]:
                evidence_page = None
                for chunk, score in results:
                    if item["evidence_text"][:30] in chunk.content:
                        evidence_page = chunk.page_number
                        break
                item["_evidence_page"] = evidence_page
                item["_confidence"] = 1.0 if evidence_page else 0.3
            else:
                item["_evidence_page"] = None
                item["_confidence"] = 0.2

        return items