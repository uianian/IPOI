#!/usr/bin/env python3
"""Simulate Finance / Legal Agent hybrid retrieval.

Finance 2.1/2.2/2.3: whole-table Top-K per statement type.
Other sections / legal: per-field candidate recall.

Example:
  conda activate ipo-risk
  cd agents/ipo
  python scripts/simulate_agent_retrieval.py \\
    --doc-id 136ee620-0473-450b-a566-72172824cdec \\
    --agent all --issuer-type general --top-k 5 \\
    --out .runtime/agent_retrieval_mixue.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import VLLMClient
from src.retrieval.agent_simulator import AgentRetrievalSimulator
from src.retrieval.store import DocumentIndexStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("simulate_agent_retrieval")


def _print_agent_block(result: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"Agent: {result['agent']}")
    print(f"Desc:  {result.get('description', '')}")
    print(f"Issuer: {result.get('issuer_type')} gate={result.get('biotech_gate')}")
    print(f"Fusion: {result['fusion']['strategy']}")
    print(f"Weights: {result['fusion'].get('weights')}")
    print(
        f"Keys kept: {result.get('field_count')}  "
        f"tables: {result.get('table_count', 0)}  "
        f"total candidates: {result.get('total_unique_hits')}  "
        f"skipped: {len(result.get('skipped_fields') or [])}"
    )
    if result.get("skipped_fields"):
        print("- skipped (issuer gate) -")
        for s in result["skipped_fields"]:
            print(f"  {s['section']}/{s['field_code']}: {s['reason']}")
    if result.get("field_table_map"):
        print(f"- field→table map: {result['field_table_map']}")
    print("- per-query candidates -")
    by_field = result.get("evidence_by_field") or {}
    by_table = result.get("evidence_by_table") or {}
    for q in result.get("per_query", []):
        fc = q["field_code"]
        unit = q.get("recall_unit") or "field"
        hits = (by_table.get(fc) if unit == "table" else None) or by_field.get(fc) or []
        pages = [h["page"] for h in hits]
        cats = [h["category"] for h in hits]
        covers = q.get("covers_fields") or []
        cover_s = f" covers={covers}" if covers else ""
        print(
            f"  [{q['section']}/{fc}] unit={unit} n={len(hits)} pages={pages} "
            f"cats={cats} src={q['sources']}{cover_s}"
        )
        for h in hits[:2]:
            ex = h["excerpt"].replace("\n", " ")[:80]
            role = h.get("table_role") or ""
            stop = h.get("stop_reason") or ""
            extra = f" role={role}" + (f" stop={stop}" if stop else "")
            print(
                f"      p{h['page']} {h['category']}{extra} "
                f"{h['match_sources']}: {ex}"
            )


async def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate Agent hybrid retrieval")
    parser.add_argument(
        "--doc-id",
        default="136ee620-0473-450b-a566-72172824cdec",
        help="Indexed document id (default: mixue build)",
    )
    parser.add_argument(
        "--agent",
        choices=["finance", "legal", "all"],
        default="all",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Top-K per table type (2.1–2.3) or per field (other)",
    )
    parser.add_argument(
        "--issuer-type",
        choices=["general", "biotech"],
        default="general",
        help="general=skip/downweight 2.4&3.5; biotech=keep all",
    )
    parser.add_argument(
        "--biotech-mode",
        choices=["skip", "downweight"],
        default=None,
        help="How to treat 2.4/3.5 when issuer-type=general (default: profile/skip)",
    )
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    client = VLLMClient()
    await client.init()
    store = DocumentIndexStore(client)

    if not store.exists(args.doc_id):
        logger.error(
            "Index not found for doc_id=%s under %s. "
            "Run scripts/build_index_from_parse.py first.",
            args.doc_id,
            store.index_root,
        )
        await client.close()
        return 1

    sim = AgentRetrievalSimulator(store)
    embed_before = store.embed_call_count
    build_before = store.build_count
    kwargs = {
        "top_k": args.top_k,
        "issuer_type": args.issuer_type,
        "biotech_mode": args.biotech_mode,
    }

    if args.agent == "all":
        result = await sim.run_all(args.doc_id, **kwargs)
        _print_agent_block(result["finance"])
        _print_agent_block(result["legal"])
        print("\n=== Summary ===")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    else:
        result = await sim.run_agent(args.agent, args.doc_id, **kwargs)
        _print_agent_block(result)

    print(
        f"\n[lifecycle] build_delta={store.build_count - build_before} "
        f"embed_delta={store.embed_call_count - embed_before} "
        f"(search-only; no index rebuild)"
    )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Wrote {out_path}")

    await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
