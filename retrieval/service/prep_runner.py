"""后台执行：build_from_parse + finance/legal 检索包。"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any

from service.config import FORCE_REBUILD, INDEX_ROOT, PACKAGE_TOP_K, PREPARE_AGENTS, ROOT
from service.prep_store import PrepStore

logger = logging.getLogger(__name__)

# 保证可 import src.*
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def package_path(task_id: str, agent: str) -> Path:
    return ROOT / ".runtime" / f"agent_retrieval_{task_id}_{agent}.json"


def index_dir(task_id: str) -> Path:
    return INDEX_ROOT / task_id


def doc_status(task_id: str, parse_json_path: str | None = None) -> dict[str, Any]:
    idx = index_dir(task_id)
    meta = idx / "meta.json"
    index_exists = meta.is_file() and (idx / "index.faiss").is_file()
    finance = package_path(task_id, "finance").is_file()
    legal = package_path(task_id, "legal").is_file()
    agents_ok = True
    for a in PREPARE_AGENTS:
        if a == "finance" and not finance:
            agents_ok = False
        if a == "legal" and not legal:
            agents_ok = False
    parse_path = parse_json_path
    section_embedded = False
    if meta.is_file():
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
            extra = m.get("extra") or {}
            section_embedded = bool(
                extra.get("section_map")
                or extra.get("section_map_version")
                or m.get("section_map")
                or m.get("section_map_version")
            )
            if parse_path is None:
                parse_path = m.get("parse_json_path")
        except Exception:
            pass
    return {
        "taskId": task_id,
        "indexExists": index_exists,
        "financePackageExists": finance,
        "legalPackageExists": legal,
        "readyForAnalysis": index_exists and agents_ok,
        "indexDir": str(idx.resolve()) if index_exists else None,
        "metaPath": str(meta.resolve()) if meta.is_file() else None,
        "parseJsonPath": parse_path,
        "financePackagePath": str(package_path(task_id, "finance").resolve())
        if finance
        else None,
        "legalPackagePath": str(package_path(task_id, "legal").resolve())
        if legal
        else None,
        "sectionMapEmbedded": section_embedded,
    }


class PrepRunner:
    def __init__(self, store: PrepStore) -> None:
        self.store = store

    def start(self, prep_id: str) -> None:
        t = threading.Thread(target=self._run_sync, args=(prep_id,), daemon=True)
        t.start()

    def _run_sync(self, prep_id: str) -> None:
        try:
            asyncio.run(self._run(prep_id))
        except Exception as e:
            logger.exception("prep failed %s", prep_id)
            try:
                self.store.update(
                    prep_id,
                    progress=0,
                    stage="FAILED",
                    error={"code": "INDEX_BUILD_FAILED", "message": str(e)},
                )
            except Exception:
                pass

    async def _run(self, prep_id: str) -> None:
        data = self.store.read(prep_id)
        if not data:
            return
        task_id = data["taskId"]
        parse_path = Path(data["parseJsonPath"])
        if not parse_path.is_file():
            self.store.update(
                prep_id,
                stage="FAILED",
                progress=0,
                error={
                    "code": "PARSE_NOT_FOUND",
                    "message": f"parseJsonPath not found: {parse_path}",
                },
            )
            return

        st = doc_status(task_id, str(parse_path))
        if st["readyForAnalysis"] and not FORCE_REBUILD:
            self.store.update(
                prep_id,
                progress=100,
                stage="READY",
                cached=True,
                error=None,
            )
            return

        from src.llm.client import VLLMClient
        from src.retrieval.agent_simulator import AgentRetrievalSimulator
        from src.retrieval.store import DocumentIndexStore

        self.store.update(prep_id, stage="BUILDING_SECTION", progress=5, message="准备章节映射")
        client = VLLMClient()
        await client.init()
        stop_hb = threading.Event()

        def _heartbeat() -> None:
            """建索引期间 progress 从 20 缓升到 65，避免前端误以为卡死。"""
            p = 20
            while not stop_hb.wait(8.0):
                p = min(p + 3, 65)
                try:
                    cur = self.store.read(prep_id) or {}
                    if (cur.get("stage") or "").upper() != "BUILDING_INDEX":
                        break
                    self.store.update(
                        prep_id,
                        progress=p,
                        stage="BUILDING_INDEX",
                        message="正在计算向量嵌入并写入 FAISS（大文档可能需数分钟）",
                    )
                except Exception:
                    break

        try:
            store = DocumentIndexStore(client)
            self.store.update(
                prep_id,
                stage="BUILDING_INDEX",
                progress=20,
                message="正在计算向量嵌入并写入 FAISS（大文档可能需数分钟）",
            )
            hb = threading.Thread(target=_heartbeat, name=f"hb-{prep_id}", daemon=True)
            hb.start()
            try:
                result = await store.build_from_parse(
                    doc_id=task_id,
                    parse_json_path=str(parse_path),
                    company_name=data["companyName"],
                    stock_code=data["stockCode"],
                    listing_date=data["listingDate"],
                    force=FORCE_REBUILD,
                )
            finally:
                stop_hb.set()
            logger.info(
                "index built taskId=%s reused=%s chunks=%s",
                task_id,
                getattr(result, "reused", None),
                getattr(result, "chunk_count", None),
            )
            self.store.update(
                prep_id,
                stage="BUILDING_PACKAGES",
                progress=70,
                message="正在生成财务/法务检索包",
            )
            sim = AgentRetrievalSimulator(store)
            for i, agent in enumerate(PREPARE_AGENTS):
                out = await sim.run_agent(
                    agent,
                    task_id,
                    top_k=PACKAGE_TOP_K,
                    issuer_type=data.get("issuerType") or "general",
                )
                out_path = package_path(task_id, agent)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(out, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                pct = 70 + int(25 * (i + 1) / max(len(PREPARE_AGENTS), 1))
                self.store.update(
                    prep_id,
                    progress=min(pct, 95),
                    stage="BUILDING_PACKAGES",
                    message=f"正在生成检索包（{agent}）",
                )
            self.store.update(
                prep_id,
                stage="READY",
                progress=100,
                error=None,
                message="向量索引已就绪",
            )
        except Exception as e:
            logger.exception("prep async failed %s", prep_id)
            code = "PACKAGE_FAILED" if "BUILDING_PACKAGES" in str(
                (self.store.read(prep_id) or {}).get("stage")
            ) else "INDEX_BUILD_FAILED"
            self.store.update(
                prep_id,
                stage="FAILED",
                error={"code": code, "message": str(e)},
            )
        finally:
            await client.close()
