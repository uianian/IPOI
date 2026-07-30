from __future__ import annotations

import asyncio
from pathlib import Path
import unittest

from src.models.prospectus import DocumentChunk
from src.retrieval.evidence_expand import build_page_index, collect_cross_page_pack
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.parse_adapter import full_parse_to_chunks
from src.retrieval.section_map import build_section_map_from_parse

IPOI_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = IPOI_ROOT / "pdf_parsing" / "output" / "samples_batch"
MIXUE = (
    SAMPLES
    / "02097_21-02-2025_蜜雪集團_全球發售"
    / "full_parse.json"
)
XIAOMI = SAMPLES / "xiaomi" / "full_parse.json"


class SectionMapTests(unittest.TestCase):
    def test_section_filter_excludes_other_and_unmapped_chunks(self) -> None:
        chunks = [
            DocumentChunk(
                chunk_id="business",
                doc_id="test",
                page_number=10,
                section_title="business",
                content="加盟模式與加盟商協議",
                token_count=8,
                metadata={"section_id": "business", "category": "text"},
            ),
            DocumentChunk(
                chunk_id="risk",
                doc_id="test",
                page_number=20,
                section_title="risk_factors",
                content="加盟模式可能帶來風險",
                token_count=8,
                metadata={"section_id": "risk_factors", "category": "text"},
            ),
            DocumentChunk(
                chunk_id="legacy",
                doc_id="test",
                page_number=30,
                content="加盟模式舊索引",
                token_count=8,
            ),
        ]
        retriever = HybridRetriever()
        retriever.build_bm25(chunks)

        async def no_vector(query: str, top_k: int):
            return []

        hits = asyncio.run(
            retriever.retrieve(
                "加盟模式",
                chunks,
                no_vector,
                top_k=5,
                section_filter="business",
            )
        )
        self.assertEqual([hit.chunk.chunk_id for hit in hits], ["business"])

    @unittest.skipUnless(MIXUE.is_file(), "Mixue sample is not available")
    def test_mixue_core_sections_and_appendix_boundary(self) -> None:
        section_map = build_section_map_from_parse(MIXUE)
        self.assertEqual(section_map.toc_pages, [8, 9])
        self.assertEqual(section_map.page_offset, 9)
        self.assertEqual(section_map.span_for("business").start_page, 191)
        self.assertEqual(section_map.span_for("financial_information").start_page, 318)
        appendix = section_map.span_for("appendix_one")
        self.assertEqual((appendix.start_page, appendix.end_page), (424, 506))

    @unittest.skipUnless(MIXUE.is_file(), "Mixue sample is not available")
    def test_parse_adapter_writes_section_metadata(self) -> None:
        chunks, _, stats = full_parse_to_chunks(MIXUE, "mixue-test")
        business = next(chunk for chunk in chunks if chunk.page_number == 228)
        self.assertEqual(business.section_title, "business")
        self.assertEqual(business.metadata["section_id"], "business")
        self.assertEqual(business.metadata["section_start_page"], 191)
        self.assertTrue(business.metadata["element_category"])
        self.assertGreaterEqual(stats["section_count"], 20)

    @unittest.skipUnless(XIAOMI.is_file(), "Xiaomi sample is not available")
    def test_xiaomi_income_pack_includes_comprehensive_income(self) -> None:
        chunks, _, stats = full_parse_to_chunks(XIAOMI, "xiaomi-test")
        page_index = build_page_index(chunks)
        appendix = next(
            span
            for span in stats["section_map"]["section_spans"]
            if span["canonical_section"] == "appendix_one"
        )
        seed = next(
            chunk
            for chunk in page_index[467]
            if (chunk.metadata or {}).get("category") in {"table", "text"}
            and len(chunk.content) > 500
        )
        pack = collect_cross_page_pack(
            seed,
            page_index,
            max_pages=3,
            appendix_only=False,
            table_type="income_statement",
            allowed_page_range=(appendix["start_page"], appendix["end_page"]),
        )
        self.assertEqual(pack.pages, [467, 468])
        self.assertIn("其他綜合收益", pack.merged_content())


if __name__ == "__main__":
    unittest.main()
