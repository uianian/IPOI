#!/usr/bin/env python3
"""Build FAISS index from Infinity full_parse.json and smoke-test retrieval."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import VLLMClient
from src.retrieval.store import DocumentIndexStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("build_index")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Build FAISS index from full_parse.json")
    parser.add_argument("--parse", required=True, help="Path to full_parse.json")
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--listing-date", required=True)
    parser.add_argument("--doc-id", default=None, help="Reuse/override doc_id (uuid)")
    parser.add_argument("--force", action="store_true", help="Force rebuild even if index exists")
    parser.add_argument("--query", default="经营活动现金流量", help="Smoke retrieval query")
    parser.add_argument(
        "--grep-terms",
        default="對賭,赎回,对赌",
        help="Comma-separated Grep terms for smoke test",
    )
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    parse_path = Path(args.parse).resolve()
    if not parse_path.is_file():
        logger.error("Parse file not found: %s", parse_path)
        return 1

    client = VLLMClient()
    await client.init()
    store = DocumentIndexStore(client)

    existing = store.resolve_by_parse_path(str(parse_path))
    doc_id = args.doc_id or existing or str(uuid.uuid4())

    logger.info("Building index doc_id=%s parse=%s", doc_id, parse_path)
    result = await store.build_from_parse(
        doc_id=doc_id,
        parse_json_path=str(parse_path),
        company_name=args.company_name,
        stock_code=args.stock_code,
        listing_date=args.listing_date,
        force=args.force,
    )
    print("=== Build Result ===")
    for k, v in result.to_dict().items():
        print(f"  {k}: {v}")

    # Second call should reuse
    result2 = await store.build_from_parse(
        doc_id=result.doc_id,
        parse_json_path=str(parse_path),
        company_name=args.company_name,
        stock_code=args.stock_code,
        listing_date=args.listing_date,
        force=False,
    )
    print(f"\n=== Idempotent check: reused={result2.reused} (expect True) ===")
    print(f"  build_count={store.build_count} (expect 1 if first run created index)")

    embed_before = store.embed_call_count
    grep_terms = [t.strip() for t in args.grep_terms.split(",") if t.strip()]

    hits = await store.search(
        doc_id=result.doc_id,
        query=args.query,
        top_k=args.top_k,
        grep_terms=grep_terms,
    )
    print(f"\n=== Smoke retrieve: query={args.query!r} hits={len(hits)} ===")
    for i, h in enumerate(hits, 1):
        d = h.to_dict(content_limit=120)
        print(
            f"  [{i}] page={d['page_number']} sources={d['match_sources']} "
            f"score={d['score']:.4f} cat={d['category']}"
        )
        print(f"      {d['content']!r}")

    # Second search should not rebuild; query embed may increment by 1
    hits2 = await store.search(
        doc_id=result.doc_id,
        query=args.query,
        top_k=args.top_k,
        grep_terms=grep_terms,
    )
    print(
        f"\n=== Second search: hits={len(hits2)} "
        f"embed_calls_delta={store.embed_call_count - embed_before} "
        f"(query embeds only, no rebuild) ==="
    )

    await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
