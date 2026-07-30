"""后台跑财务‖法务，映射 SSE 事件并打包 result。"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import httpx

from service.analysis_store import AnalysisStore
from service.config import (
    FINANCE_RULES_ONLY,
    PKG_ROOT,
    RETRIEVAL_BASE_URL,
    RETRIEVAL_RUNTIME,
)
from service.thought_mapper import (
    agent_bundle_from_result,
    map_finance_event,
    map_legal_event,
    new_thought,
    score_to_risk_level,
    to_zh_hant,
)

logger = logging.getLogger(__name__)

# 确保可 import src.*
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


class OrderedEmitter:
    """内部并行；对外先刷完 legal 再 financial。"""

    def __init__(self, store: AnalysisStore, analysis_id: str) -> None:
        self.store = store
        self.analysis_id = analysis_id
        self._lock = threading.Lock()
        self._legal_done = False
        self._fin_buf: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        agent = None
        if event_type == "thought":
            agent = (data.get("thought") or {}).get("agentId")

        with self._lock:
            # 仅缓冲 financial 的 thought；agent_status 立即发出
            if event_type == "thought" and agent == "financial" and not self._legal_done:
                self._fin_buf.append((event_type, data))
                return

            self.store.append_sse_event(self.analysis_id, event_type, data)

            if (
                event_type == "agent_status"
                and data.get("agentId") == "legal"
                and data.get("status") == "completed"
            ):
                self._legal_done = True
                for et, d in self._fin_buf:
                    self.store.append_sse_event(self.analysis_id, et, d)
                self._fin_buf.clear()

    def flush_financial(self) -> None:
        with self._lock:
            self._legal_done = True
            for et, d in self._fin_buf:
                self.store.append_sse_event(self.analysis_id, et, d)
            self._fin_buf.clear()


def _resolve_packages(task_id: str) -> tuple[Optional[Path], Optional[Path]]:
    fin = RETRIEVAL_RUNTIME / f"agent_retrieval_{task_id}_finance.json"
    leg = RETRIEVAL_RUNTIME / f"agent_retrieval_{task_id}_legal.json"
    return (fin if fin.is_file() else None, leg if leg.is_file() else None)


def _fetch_artifacts(task_id: str) -> dict[str, Any]:
    url = f"{RETRIEVAL_BASE_URL.rstrip('/')}/internal/retrieval/docs/{task_id}/artifacts"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url)
            if r.status_code == 200:
                body = r.json()
                return body.get("data") or body
    except Exception as exc:
        logger.warning("artifacts fetch failed: %s", exc)
    return {}


def _build_report_md(merged: dict[str, Any], *, doc_name: str, pdf_name: str) -> str:
    try:
        from scripts.generate_analysis_report import build_report

        return build_report(
            merged,
            doc_name=doc_name or merged.get("doc_id") or "issuer",
            pdf_name=pdf_name or "",
            finance_retrieval=None,
            legal_retrieval=None,
        )
    except Exception as exc:
        logger.warning("build_report failed: %s", exc)
        fin = merged.get("finance") or {}
        leg = merged.get("legal") or {}
        return (
            f"# {doc_name} 分析報告\n\n"
            f"- 參考基本面分：{merged.get('reference_fundamental_score')}\n"
            f"- 財務：{fin.get('risk_score')} ({fin.get('risk_level')}) — {fin.get('summary')}\n"
            f"- 法務：{leg.get('risk_score')} ({leg.get('risk_level')}) — {leg.get('summary')}\n"
        )


def _read_text(path: Optional[Path]) -> str:
    if path and path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


def _read_jsonl(path: Optional[Path]) -> list[dict[str, Any]]:
    if not path or not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


class AnalysisRunner:
    def __init__(self, store: AnalysisStore) -> None:
        self.store = store

    def start_background(
        self,
        *,
        analysis_id: str,
        parse_meta: dict[str, Any],
        llm_config: Optional[dict[str, Any]] = None,
        rules_only: bool = False,
    ) -> None:
        t = threading.Thread(
            target=self._thread_main,
            kwargs={
                "analysis_id": analysis_id,
                "parse_meta": parse_meta,
                "llm_config": llm_config,
                "rules_only": rules_only or FINANCE_RULES_ONLY,
            },
            name=f"analysis-{analysis_id}",
            daemon=True,
        )
        t.start()

    def _thread_main(
        self,
        *,
        analysis_id: str,
        parse_meta: dict[str, Any],
        llm_config: Optional[dict[str, Any]],
        rules_only: bool,
    ) -> None:
        try:
            asyncio.run(
                self._run(
                    analysis_id=analysis_id,
                    parse_meta=parse_meta,
                    llm_config=llm_config,
                    rules_only=rules_only,
                )
            )
        except Exception as exc:
            logger.exception("analysis failed %s", analysis_id)
            emitter = OrderedEmitter(self.store, analysis_id)
            emitter.flush_financial()
            self.store.update_meta(
                analysis_id,
                status="failed",
                error={"message": str(exc)},
            )
            self.store.append_sse_event(
                analysis_id,
                "analysis_complete",
                {"overallScore": 0, "riskLevel": "HIGH", "error": str(exc)},
            )

    async def _run(
        self,
        *,
        analysis_id: str,
        parse_meta: dict[str, Any],
        llm_config: Optional[dict[str, Any]],
        rules_only: bool,
    ) -> None:
        from src.config import resolve_api_settings
        from src.graph.parallel import run_finance_legal_parallel
        from src.tools.llm_client import LLMClient
        from src.tracing.run_logger import AgentRunLogger

        task_id = parse_meta.get("taskId") or ""
        emitter = OrderedEmitter(self.store, analysis_id)
        ad = self.store.analysis_dir(analysis_id)
        log_dir = ad / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        self.store.update_meta(analysis_id, status="running")

        emitter.emit("agent_status", {"agentId": "legal", "status": "running"})
        emitter.emit("agent_status", {"agentId": "financial", "status": "running"})

        artifacts = _fetch_artifacts(task_id)
        fin_path, leg_path = _resolve_packages(task_id)
        if artifacts.get("financePackagePath"):
            p = Path(artifacts["financePackagePath"])
            if p.is_file():
                fin_path = p
        if artifacts.get("legalPackagePath"):
            p = Path(artifacts["legalPackagePath"])
            if p.is_file():
                leg_path = p

        parse_json = parse_meta.get("parseJsonPath")
        parse_path = Path(parse_json) if parse_json else None
        if parse_path and not parse_path.is_file():
            parse_path = None

        issuer_type = parse_meta.get("issuerType") or "general"
        doc_name = parse_meta.get("companyName") or parse_meta.get("fileName") or task_id
        pdf_name = parse_meta.get("fileName") or ""

        # LLM：前端 llmConfig 优先（apiKey/apiBaseUrl/model），缺省用后端默认 google/gemma-4-31b-it
        finance_llm = None
        if not rules_only:
            try:
                cfg = llm_config or {}

                def _nonempty(key: str) -> str | None:
                    v = cfg.get(key)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
                    return None

                settings = resolve_api_settings(
                    api_key=_nonempty("apiKey"),
                    api_base=_nonempty("apiBaseUrl"),
                    chat_model=_nonempty("model"),
                )
                logger.info(
                    "analysis %s LLM model=%s base=%s key_from=%s",
                    analysis_id,
                    settings.get("chat_model"),
                    settings.get("api_base"),
                    "frontend" if _nonempty("apiKey") else "backend_default",
                )
                if not settings.get("api_key"):
                    logger.warning("No API key — finance rules_only fallback")
                    rules_only = True
                else:
                    finance_llm = LLMClient(settings)
                    await finance_llm.init()
            except Exception as exc:
                logger.warning("LLM init failed, rules_only fallback: %s", exc)
                rules_only = True
                finance_llm = None

        legal_events: list[dict[str, Any]] = []

        def on_finance_event(ev: dict[str, Any]) -> None:
            for th in map_finance_event(ev):
                emitter.emit("thought", {"thought": th})

        def on_legal_progress(ev: dict[str, Any]) -> None:
            legal_events.append(ev)
            for th in map_legal_event(ev):
                emitter.emit("thought", {"thought": th})

        run_logger = AgentRunLogger(
            agent="finance",
            doc_id=task_id,
            log_dir=log_dir,
            issuer_type=issuer_type,
            doc_name=doc_name,
            pdf_name=pdf_name,
            on_event=on_finance_event,
        )

        merged = await run_finance_legal_parallel(
            task_id,
            issuer_type=issuer_type,
            finance_retrieval_json=fin_path,
            legal_retrieval_json=leg_path,
            parse_json=parse_path,
            finance_llm=finance_llm,
            finance_run_logger=run_logger,
            legal_on_progress=on_legal_progress,
            finance_rules_only=rules_only,
            doc_name=doc_name,
            pdf_name=pdf_name,
        )
        run_logger.close(final_summary=(merged.get("finance") or {}).get("summary"))

        emitter.emit("agent_status", {"agentId": "legal", "status": "completed"})
        # legal completed 会触发 flush financial buffer
        emitter.emit("agent_status", {"agentId": "financial", "status": "completed"})
        emitter.flush_financial()

        # market skipped
        emitter.emit("agent_status", {"agentId": "market", "status": "skipped"})
        emitter.emit(
            "thought",
            {
                "thought": new_thought(
                    agent_id="market",
                    typ="thinking",
                    content="市場情緒 Agent 本輪跳過（未啓用）",
                    meta={"kind": "model_think"},
                )
            },
        )

        # orchestrator 收尾
        score = float(merged.get("reference_fundamental_score") or 0)
        overall = int(round(score))
        risk_level = score_to_risk_level(score)
        emitter.emit("agent_status", {"agentId": "orchestrator", "status": "running"})
        fin_s = (merged.get("finance") or {}).get("summary") or ""
        leg_s = (merged.get("legal") or {}).get("summary") or ""
        emitter.emit(
            "thought",
            {
                "thought": new_thought(
                    agent_id="orchestrator",
                    typ="conclusion",
                    content=to_zh_hant(
                        f"綜合參考基本面分 {overall}（{risk_level}）。"
                        f"法務：{leg_s}；財務：{fin_s}"
                    ),
                    meta={"kind": "model_think"},
                )
            },
        )
        emitter.emit("agent_status", {"agentId": "orchestrator", "status": "completed"})

        report_md = _build_report_md(merged, doc_name=str(doc_name), pdf_name=str(pdf_name))
        (ad / "report.md").write_text(report_md, encoding="utf-8")
        (ad / "merged.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        # 法务合成日志
        legal_log_lines = ["# Agent Run Log — legal", ""]
        for ev in legal_events:
            legal_log_lines.append(
                f"- [{ev.get('status')}] {ev.get('name')}: "
                f"{json.dumps(ev.get('output') or {}, ensure_ascii=False, default=str)[:500]}"
            )
        legal_log_text = "\n".join(legal_log_lines) + "\n"
        (ad / "logs" / "legal_run.log").write_text(legal_log_text, encoding="utf-8")
        (ad / "logs" / "legal_events.jsonl").write_text(
            "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in legal_events)
            + ("\n" if legal_events else ""),
            encoding="utf-8",
        )

        fin_log = Path(run_logger.log_path) if run_logger.log_path else None
        fin_jsonl = Path(run_logger.jsonl_path) if run_logger.jsonl_path else None

        # 分拆报告：整份报告两边各一份（前端按 agent 展示）
        agents = {
            "legal": agent_bundle_from_result(
                agent_key="legal",
                agent_result=merged.get("legal") or {},
                report_markdown=report_md,
                log_text=legal_log_text,
                log_events=legal_events,
            ),
            "financial": agent_bundle_from_result(
                agent_key="finance",
                agent_result=merged.get("finance") or {},
                report_markdown=report_md,
                log_text=_read_text(fin_log),
                log_events=_read_jsonl(fin_jsonl),
            ),
        }

        thoughts = self.store.read_thoughts(analysis_id)
        result = {
            "analysisId": analysis_id,
            "status": "completed",
            "overallScore": overall,
            "riskLevel": risk_level,
            "thoughts": thoughts,
            "agents": agents,
            "completedAt": self.store.read_meta(analysis_id).get("createdAt"),
        }
        from datetime import datetime, timezone

        result["completedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.write_result(analysis_id, result)
        self.store.update_meta(
            analysis_id,
            status="completed",
            overallScore=overall,
            riskLevel=risk_level,
            completedAt=result["completedAt"],
        )
        emitter.emit(
            "analysis_complete",
            {"overallScore": overall, "riskLevel": risk_level},
        )
        logger.info(
            "analysis %s completed score=%s level=%s",
            analysis_id,
            overall,
            risk_level,
        )
