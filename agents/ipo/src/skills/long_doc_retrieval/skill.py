from __future__ import annotations

import logging
from typing import Any

from src.models.prospectus import DocumentChunk
from src.retrieval.store import DocumentIndexStore, IndexNotFound
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.long_doc_retrieval.parser import ProspectusParser
from src.skills.long_doc_retrieval.indexer import DocumentIndexer
from src.skills.long_doc_retrieval.retriever import HybridRetriever as LegacyHybridRetriever
from src.skills.long_doc_retrieval.extractor import StructuredExtractor

logger = logging.getLogger(__name__)


class LongDocRetrievalSkill(BaseSkill):
    skill_name = "long_doc_retrieval"
    version = "0.2.0"
    description = "长文档检索Skill：full_parse 索引、三路混合检索与结构化抽取"

    def __init__(
        self,
        vllm_client: Any,
        index_store: DocumentIndexStore | None = None,
    ) -> None:
        self._vllm = vllm_client
        if index_store is None:
            from src.app_state import document_index_store

            index_store = document_index_store
        self._store = index_store
        # Legacy path (PyMuPDF) kept for backward compatibility
        self._indexer = DocumentIndexer(vllm_client)
        self._legacy_retriever = LegacyHybridRetriever(self._indexer)
        self._parser = ProspectusParser()
        self._extractor = StructuredExtractor(vllm_client, self._legacy_retriever)
        self._indexed_docs: set[str] = set()

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        action = skill_input.params.get("action", "retrieve")
        try:
            if action == "index":
                return await self._index_document(skill_input)
            elif action == "index_text":
                return await self._index_text(skill_input)
            elif action == "index_parsed":
                return await self._index_parsed(skill_input)
            elif action == "retrieve":
                return await self._retrieve(skill_input)
            elif action == "extract":
                return await self._extract_structured(skill_input)
            else:
                return SkillOutput(success=False, error=f"Unknown action: {action}")
        except IndexNotFound as e:
            return SkillOutput(
                success=False,
                error=str(e),
                degraded=True,
                degraded_reason="文档索引未找到，请先 index_parsed",
            )
        except Exception as e:
            logger.error(f"LongDocRetrievalSkill error: {e}")
            return SkillOutput(
                success=False,
                error=str(e),
                degraded=True,
                degraded_reason="PDF解析或检索异常",
            )

    async def _index_parsed(self, skill_input: SkillInput) -> SkillOutput:
        parse_json_path = skill_input.params.get("parse_json_path", "")
        doc_id = skill_input.doc_id
        if not parse_json_path:
            return SkillOutput(success=False, error="parse_json_path is required for index_parsed")

        result = await self._store.build_from_parse(
            doc_id=doc_id,
            parse_json_path=parse_json_path,
            company_name=skill_input.params.get("company_name", ""),
            stock_code=skill_input.params.get("stock_code", ""),
            listing_date=skill_input.params.get("listing_date", ""),
            force=bool(skill_input.params.get("force", False)),
        )
        return SkillOutput(success=True, data=result.to_dict())

    async def _index_document(self, skill_input: SkillInput) -> SkillOutput:
        """Deprecated: PyMuPDF path. Prefer index_parsed from full_parse.json."""
        file_path = skill_input.params.get("file_path", "")
        doc_id = skill_input.doc_id

        if not file_path:
            return SkillOutput(success=False, error="file_path is required for indexing")

        try:
            chunks, total_pages = self._parser.parse_pdf(file_path, doc_id)
        except RuntimeError as e:
            return SkillOutput(
                success=False,
                error=str(e),
                degraded=True,
                degraded_reason="PDF解析失败，文件不可解析",
            )

        await self._indexer.build_index(chunks)
        self._legacy_retriever.build_bm25(chunks)
        self._indexed_docs.add(doc_id)

        return SkillOutput(
            success=True,
            data={
                "doc_id": doc_id,
                "total_pages": total_pages,
                "chunk_count": len(chunks),
                "deprecated": True,
                "hint": "prefer action=index_parsed with full_parse.json",
            },
        )

    async def _index_text(self, skill_input: SkillInput) -> SkillOutput:
        text = skill_input.params.get("text", "")
        doc_id = skill_input.doc_id

        if not text:
            return SkillOutput(success=False, error="text is required for index_text")

        import re

        paragraphs = re.split(r"\n\s*\n", text)
        chunks: list[DocumentChunk] = []
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if not para or len(para) < 20:
                continue
            chunk_id = f"{doc_id}_t{i}"
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    page_number=1,
                    paragraph_index=i,
                    section_title=None,
                    content=para,
                    token_count=len(para) // 2,
                    chunk_type="text",
                )
            )

        await self._indexer.build_index(chunks)
        self._legacy_retriever.build_bm25(chunks)
        self._indexed_docs.add(doc_id)

        return SkillOutput(
            success=True,
            data={"doc_id": doc_id, "chunk_count": len(chunks), "source": "text"},
        )

    async def _retrieve(self, skill_input: SkillInput) -> SkillOutput:
        query = skill_input.params.get("query", "")
        top_k = skill_input.params.get("top_k", 10)
        section_filter = skill_input.params.get("section_filter")
        page_range = skill_input.params.get("page_range")
        category_filter = skill_input.params.get("category_filter")
        grep_terms = skill_input.params.get("grep_terms")

        if not query:
            return SkillOutput(success=False, error="query is required for retrieval")

        if isinstance(page_range, list) and len(page_range) == 2:
            page_range = (int(page_range[0]), int(page_range[1]))

        # Prefer disk-backed store (production path)
        if self._store.exists(skill_input.doc_id) or skill_input.doc_id in getattr(
            self._store, "_cache", {}
        ):
            hits = await self._store.search(
                doc_id=skill_input.doc_id,
                query=query,
                top_k=top_k,
                grep_terms=grep_terms,
                page_range=page_range,
                category_filter=category_filter,
                section_filter=section_filter,
            )
            chunks_data = [h.to_dict() for h in hits]
            return SkillOutput(
                success=True, data={"chunks": chunks_data, "total": len(chunks_data)}
            )

        # Legacy in-memory path
        if skill_input.doc_id not in self._indexed_docs:
            # last try: ensure_loaded may raise IndexNotFound
            try:
                hits = await self._store.search(
                    doc_id=skill_input.doc_id,
                    query=query,
                    top_k=top_k,
                    grep_terms=grep_terms,
                    page_range=page_range,
                    category_filter=category_filter,
                    section_filter=section_filter,
                )
                chunks_data = [h.to_dict() for h in hits]
                return SkillOutput(
                    success=True, data={"chunks": chunks_data, "total": len(chunks_data)}
                )
            except IndexNotFound:
                return SkillOutput(
                    success=False,
                    error=f"Document {skill_input.doc_id} not indexed",
                    degraded=True,
                    degraded_reason="文档未索引",
                )

        results = await self._legacy_retriever.retrieve(
            query, top_k=top_k, section_filter=section_filter, page_range=page_range
        )
        chunks_data = [
            {
                "chunk_id": c.chunk_id,
                "page_number": c.page_number,
                "section_title": c.section_title,
                "content": c.content[:500],
                "score": score,
                "bbox": (c.metadata or {}).get("bbox", []),
                "category": (c.metadata or {}).get("category", c.chunk_type),
                "match_sources": ["legacy"],
            }
            for c, score in results
        ]
        return SkillOutput(success=True, data={"chunks": chunks_data, "total": len(chunks_data)})

    async def _extract_structured(self, skill_input: SkillInput) -> SkillOutput:
        query = skill_input.params.get("query", "")
        extraction_prompt = skill_input.params.get("extraction_prompt", query)
        top_k = skill_input.params.get("top_k", 5)

        # Prefer store search for context
        try:
            hits = await self._store.search(
                doc_id=skill_input.doc_id, query=query, top_k=top_k
            )
            if hits:
                context = "\n\n".join(
                    f"[第{h.chunk.page_number}页] {h.chunk.content}" for h in hits
                )
                messages = [
                    {
                        "role": "system",
                        "content": "你是一名专业的金融文档信息抽取助手。请严格基于提供的文本内容进行抽取。",
                    },
                    {
                        "role": "user",
                        "content": extraction_prompt.format(text=context)
                        if "{text}" in extraction_prompt
                        else f"{extraction_prompt}\n\n{context}",
                    },
                ]
                import json

                content = await self._vllm.chat(messages, temperature=0.0)
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    parsed = json.loads(content[start:end]) if start >= 0 and end > start else {}
                items = (
                    parsed
                    if isinstance(parsed, list)
                    else parsed.get("items", parsed.get("risk_features", parsed.get("indicators", [])))
                )
                if isinstance(items, dict):
                    items = [items]
                return SkillOutput(
                    success=True, data={"extracted_items": items, "total": len(items)}
                )
        except IndexNotFound:
            pass

        if skill_input.doc_id not in self._indexed_docs:
            return SkillOutput(
                success=False, error=f"Document {skill_input.doc_id} not indexed"
            )

        items = await self._extractor.extract(
            doc_id=skill_input.doc_id,
            query=query,
            extraction_prompt=extraction_prompt,
            top_k=top_k,
        )
        return SkillOutput(success=True, data={"extracted_items": items, "total": len(items)})
