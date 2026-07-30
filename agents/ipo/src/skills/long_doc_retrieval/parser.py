from __future__ import annotations

import logging
import re
from typing import Any

import fitz

from src.config import settings
from src.models.prospectus import DocumentChunk

logger = logging.getLogger(__name__)


class ProspectusParser:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def parse_pdf(self, file_path: str, doc_id: str) -> tuple[list[DocumentChunk], int]:
        try:
            pdf_doc = fitz.open(file_path)
        except Exception as e:
            logger.error(f"PDF解析失败: {file_path}, 错误: {e}")
            raise RuntimeError(f"PDF解析失败: {e}")

        total_pages = len(pdf_doc)
        all_chunks: list[DocumentChunk] = []
        chunk_counter = 0

        for page_idx in range(total_pages):
            page = pdf_doc[page_idx]
            text = page.get_text()
            if not text.strip():
                continue

            page_number = page_idx + 1
            section_title = self._detect_section_title(text)
            chunks = self._split_text(text, page_number, section_title, doc_id, chunk_counter)
            all_chunks.extend(chunks)
            chunk_counter += len(chunks)

        pdf_doc.close()
        return all_chunks, total_pages

    def _detect_section_title(self, text: str) -> str | None:
        lines = text.strip().split("\n")[:5]
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) < 100:
                if any(kw in stripped for kw in ["风险", "财务", "业务", "管理层", "董事", "法律", "行业", "股本"]):
                    return stripped
        return None

    def _split_text(
        self,
        text: str,
        page_number: int,
        section_title: str | None,
        doc_id: str,
        start_counter: int,
    ) -> list[DocumentChunk]:
        paragraphs = re.split(r"\n\s*\n", text)
        filtered = [p.strip() for p in paragraphs if p.strip() and len(p.strip()) > 20]

        if not filtered:
            return []

        chunks: list[DocumentChunk] = []
        current_text = ""
        para_idx = 0

        for para in filtered:
            if len(current_text) + len(para) > self.chunk_size and current_text:
                chunk_id = f"{doc_id}_p{page_number}_c{start_counter + len(chunks)}"
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    page_number=page_number,
                    paragraph_index=para_idx,
                    section_title=section_title,
                    content=current_text.strip(),
                    token_count=len(current_text) // 2,
                    chunk_type=self._detect_chunk_type(current_text),
                ))
                overlap_text = current_text[-self.chunk_overlap * 2:] if self.chunk_overlap > 0 else ""
                current_text = overlap_text + "\n" + para
                para_idx += 1
            else:
                current_text += "\n" + para if current_text else para

        if current_text.strip():
            chunk_id = f"{doc_id}_p{page_number}_c{start_counter + len(chunks)}"
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                page_number=page_number,
                paragraph_index=para_idx,
                section_title=section_title,
                content=current_text.strip(),
                token_count=len(current_text) // 2,
                chunk_type=self._detect_chunk_type(current_text),
            ))

        return chunks

    @staticmethod
    def _detect_chunk_type(text: str) -> str:
        digit_ratio = sum(c.isdigit() for c in text) / max(len(text), 1)
        if digit_ratio > 0.3:
            return "table"
        return "text"