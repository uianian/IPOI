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
    DEBATE_DIR,
    FINANCE_RULES_ONLY,
    LEGAL_RULES_ONLY,
    PKG_ROOT,
    RETRIEVAL_BASE_URL,
    RETRIEVAL_RUNTIME,
)
from service.thought_mapper import (
    agent_bundle_from_result,
    debate_message_from_event,
    map_debate_expert_event,
    map_finance_event,
    map_legal_event,
    map_market_event,
    map_master_event,
    new_thought,
    score_to_risk_level,
)

logger = logging.getLogger(__name__)

# 确保可 import src.*
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


class StreamHub:
    """三路实时混流；仅辩论窗口给 thought / debate_message 加 category。"""

    def __init__(self, store: AnalysisStore, analysis_id: str) -> None:
        self.store = store
        self.analysis_id = analysis_id
        self._lock = threading.Lock()
        self.phase = "analysis"
        self.debate_started = False
        self.debate_complete_sent = False
        self.debate_messages: list[dict[str, Any]] = []
        self._seen: set[str] = set()

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        with self._lock:
            self.store.append_sse_event(self.analysis_id, event_type, data)

    def set_phase(self, phase: str, *, message: str | None = None) -> None:
        self.phase = phase
        payload: dict[str, Any] = {"phase": phase}
        if message:
            payload["message"] = message
        self.emit("phase_change", payload)
        self.store.update_meta(self.analysis_id, phase=phase)

    def emit_thoughts(self, thoughts: list[dict[str, Any]], *, in_debate: bool | None = None) -> None:
        keep_cat = self.phase == "debate" if in_debate is None else in_debate
        for th in thoughts:
            if not isinstance(th, dict):
                continue
            if not keep_cat:
                th.pop("category", None)
            self.emit("thought", {"thought": th})

    def emit_debate_message(self, msg: dict[str, Any] | None) -> None:
        if not msg:
            return
        self.debate_messages.append(msg)
        self.emit("debate_message", {"message": msg})

    def enter_debate(self) -> None:
        if self.debate_started:
            return
        self.debate_started = True
        self.set_phase("debate", message="进入辩论环节")
        self.store.update_meta(self.analysis_id, status="debating", phase="debate")

    def maybe_complete_debate(self, rounds: int | None = None) -> None:
        if not self.debate_started or self.debate_complete_sent:
            return
        self.debate_complete_sent = True
        n = rounds
        if n is None:
            rounds_seen = {m.get("round") for m in self.debate_messages if m.get("round") is not None}
            n = len(rounds_seen)
        self.emit("debate_complete", {"rounds": int(n or 0)})

    def handle_expert_event(self, event: dict[str, Any], mapper) -> None:
        if not isinstance(event, dict):
            return
        ev = str(event.get("event") or "")
        if ev in {"run_meta", "run_start", "run_end"}:
            return
        if ev in {"debate_search", "debate_reply"}:
            self.emit_thoughts(
                map_debate_expert_event(event, with_category=True),
                in_debate=True,
            )
            self.emit_debate_message(debate_message_from_event(event, with_category=True))
            return
        thoughts = mapper(event)
        if self.phase == "debate":
            from service.thought_mapper import category_for_agent_id

            for th in thoughts:
                if isinstance(th, dict) and "category" not in th:
                    th["category"] = category_for_agent_id(str(th.get("agentId") or ""))
        self.emit_thoughts(thoughts, in_debate=self.phase == "debate")

    def handle_master_event(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        ev = str(event.get("event") or "")
        if ev in {"run_meta", "run_start", "run_end", "result", "step"}:
            return
        key = "|".join(
            [
                ev,
                str(event.get("target_agent") or ""),
                str(event.get("question_id") or ""),
                str(event.get("round") or ""),
                str((event.get("utterance") or "")[:60]),
            ]
        )
        with self._lock:
            if key in self._seen:
                return
            self._seen.add(key)

        if ev in {"debate_search", "debate_reply"}:
            # 专家 logger 已实时推过，master_logger 在 gather 后的重复记录不再二次映射。
            return

        if ev == "conflict_detection":
            need = bool(event.get("need_debate"))
            self.emit_thoughts(map_master_event(event, in_debate=False), in_debate=False)
            if need:
                self.enter_debate()
            else:
                self.emit_thoughts(
                    [
                        new_thought(
                            agent_id="orchestrator",
                            typ="thinking",
                            content="纯共振/无需辩论，进入粉饰与终裁。",
                            meta={"kind": "model_think", "event": "skip_debate"},
                        )
                    ],
                    in_debate=False,
                )
            return

        if ev == "embellishment":
            self.maybe_complete_debate()
            if self.phase == "debate":
                self.phase = "analysis"
                self.store.update_meta(self.analysis_id, status="reporting", phase="analysis")

        in_debate = self.phase == "debate" and ev in {
            "debate_plan",
            "debate_question",
            "debate_followup",
        }
        self.emit_thoughts(map_master_event(event, in_debate=in_debate), in_debate=in_debate)
        if in_debate:
            self.emit_debate_message(debate_message_from_event(event, with_category=True))
        if ev == "debate_followup" and event.get("continue_debate") is False:
            self.maybe_complete_debate(int(event.get("round") or 0))


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


def _dump_agent(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    return {}


def _overall_score_100(judgment: dict[str, Any]) -> int | None:
    raw = judgment.get("overall_score")
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if 0 < val <= 1:
        val *= 100.0
    return int(round(val))


def _write_split_reports(
    merged: dict[str, Any],
    *,
    dest_dirs: list[Path],
    stock_code: str,
    doc_name: str,
    pdf_name: str,
) -> dict[str, str]:
    from scripts.generate_analysis_report import (
        build_finance_report,
        build_legal_report,
        build_market_report,
        resolve_report_stock_code,
        write_agent_reports,
    )

    code = resolve_report_stock_code(merged, stock_code=stock_code, pdf_name=pdf_name)
    finance_md = build_finance_report(
        merged, doc_name=doc_name, pdf_name=pdf_name, finance_retrieval=None
    )
    legal_md = build_legal_report(
        merged, doc_name=doc_name, pdf_name=pdf_name, legal_retrieval=None
    )
    market_md = build_market_report(merged) if merged.get("market") else ""
    for d in dest_dirs:
        try:
            write_agent_reports(
                merged,
                reports_dir=d,
                stock_code=code,
                doc_name=doc_name,
                pdf_name=pdf_name,
            )
        except Exception as exc:
            logger.warning("write_agent_reports %s failed: %s", d, exc)
    return {"finance": finance_md, "legal": legal_md, "market": market_md, "stock_code": code}


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
        from src.config import (
            resolve_api_settings,
            resolve_firecrawl_settings,
            resolve_market_agent_settings,
            resolve_sina_finance_settings,
        )
        from src.graph.parallel import (
            run_finance_legal_market_parallel,
            run_finance_legal_parallel,
        )
        from src.tools.llm_client import LLMClient
        from src.tracing.run_logger import AgentRunLogger

        task_id = parse_meta.get("taskId") or ""
        hub = StreamHub(self.store, analysis_id)
        ad = self.store.analysis_dir(analysis_id)
        log_dir = ad / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        self.store.update_meta(analysis_id, status="running", phase="analysis")

        hub.emit("agent_status", {"agentId": "legal", "status": "running"})
        hub.emit("agent_status", {"agentId": "financial", "status": "running"})

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
        stock_code = str(parse_meta.get("stockCode") or parse_meta.get("ticker") or "").strip()
        if stock_code:
            hub.emit("agent_status", {"agentId": "market", "status": "running"})
        else:
            hub.emit("agent_status", {"agentId": "market", "status": "skipped"})

        # LLM：前端 llmConfig 优先（apiKey/apiBaseUrl/model/provider），缺省用后端默认
        # 财务/法务/总控共用同一 client；vLLM 允许空 key
        shared_llm = None
        need_llm = (not rules_only) or (not LEGAL_RULES_ONLY)
        if need_llm:
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
                    provider=_nonempty("provider"),
                )
                logger.info(
                    "analysis %s LLM provider=%s model=%s base=%s key_from=%s",
                    analysis_id,
                    settings.get("provider"),
                    settings.get("chat_model"),
                    settings.get("api_base"),
                    "frontend" if _nonempty("apiKey") else "backend_default",
                )
                vllm_ok = str(settings.get("provider") or "").lower() == "vllm" and bool(
                    settings.get("api_base")
                )
                if not settings.get("api_key") and not vllm_ok:
                    logger.warning("No API key — finance/legal rules fallback; master degraded")
                    rules_only = True
                    shared_llm = None
                else:
                    shared_llm = LLMClient(settings)
                    await shared_llm.init()
            except Exception as exc:
                logger.warning("LLM init failed, rules_only fallback: %s", exc)
                rules_only = True
                shared_llm = None

        finance_llm = None if rules_only else shared_llm
        legal_react = (not LEGAL_RULES_ONLY) and shared_llm is not None
        legal_llm = shared_llm if legal_react else None

        legal_events: list[dict[str, Any]] = []
        market_events: list[dict[str, Any]] = []
        early_reports: dict[str, str] = {}
        expert_done: dict[str, bool] = {"legal": False, "financial": False, "market": not bool(stock_code)}

        def on_finance_event(ev: dict[str, Any]) -> None:
            hub.handle_expert_event(ev, map_finance_event)

        def on_legal_event(ev: dict[str, Any]) -> None:
            legal_events.append(ev)
            hub.handle_expert_event(ev, map_legal_event)

        def on_legal_progress(ev: dict[str, Any]) -> None:
            on_legal_event(ev)

        def on_market_event(ev: dict[str, Any]) -> None:
            market_events.append(ev)
            hub.handle_expert_event(ev, map_market_event)

        def on_master_event(ev: dict[str, Any]) -> None:
            et = str((ev or {}).get("event") or "")
            if et in {"run_start", "run_end", "run_meta"}:
                return
            if not getattr(on_master_event, "_started", False):
                on_master_event._started = True  # type: ignore[attr-defined]
                hub.emit("agent_status", {"agentId": "orchestrator", "status": "running"})
            hub.handle_master_event(ev)

        def _emit_agent_report(agent_id: str, dumped: dict[str, Any], markdown: str) -> None:
            payload: dict[str, Any] = {
                "agentId": agent_id,
                "reportMarkdown": markdown,
                "agentResult": dumped,
            }
            hub.emit("agent_report", payload)

        def on_finance_done(result: Any) -> None:
            dumped = _dump_agent(result)
            try:
                from scripts.generate_analysis_report import build_finance_report

                md = build_finance_report(
                    {"finance": dumped, "doc_id": dumped.get("doc_id"), "note": ""},
                    doc_name=str(doc_name),
                    pdf_name=str(pdf_name),
                    finance_retrieval=None,
                )
            except Exception:
                md = str(dumped.get("summary") or "")
            early_reports["finance"] = md
            expert_done["financial"] = True
            hub.emit("agent_status", {"agentId": "financial", "status": "completed"})
            _emit_agent_report("financial", dumped, md)

        def on_legal_done(result: Any) -> None:
            dumped = _dump_agent(result)
            try:
                from scripts.generate_analysis_report import build_legal_report

                md = build_legal_report(
                    {"legal": dumped, "doc_id": dumped.get("doc_id"), "note": ""},
                    doc_name=str(doc_name),
                    pdf_name=str(pdf_name),
                    legal_retrieval=None,
                )
            except Exception:
                md = str(dumped.get("summary") or "")
            early_reports["legal"] = md
            expert_done["legal"] = True
            hub.emit("agent_status", {"agentId": "legal", "status": "completed"})
            _emit_agent_report("legal", dumped, md)

        def on_market_done(result: Any, err: str | None) -> None:
            if result is None:
                expert_done["market"] = True
                hub.emit("agent_status", {"agentId": "market", "status": "failed" if stock_code else "skipped"})
                return
            dumped = _dump_agent(result)
            try:
                from scripts.generate_analysis_report import build_market_report

                md = build_market_report({"market": dumped})
            except Exception:
                md = str(((dumped.get("features") or {}).get("sentiment_report_markdown")) or dumped.get("summary") or "")
            early_reports["market"] = md
            expert_done["market"] = True
            hub.emit("agent_status", {"agentId": "market", "status": "completed"})
            _emit_agent_report("market", dumped, md)

        run_logger = AgentRunLogger(
            agent="finance",
            doc_id=task_id,
            log_dir=log_dir,
            issuer_type=issuer_type,
            doc_name=doc_name,
            pdf_name=pdf_name,
            on_event=on_finance_event,
        )
        legal_run_logger = None
        if legal_react:
            legal_run_logger = AgentRunLogger(
                agent="legal",
                doc_id=task_id,
                log_dir=log_dir,
                issuer_type=issuer_type,
                doc_name=doc_name,
                pdf_name=pdf_name,
                on_event=on_legal_event,
            )
        master_run_logger = AgentRunLogger(
            agent="master",
            doc_id=task_id,
            log_dir=log_dir,
            issuer_type=issuer_type,
            doc_name=doc_name,
            pdf_name=pdf_name,
            on_event=on_master_event,
        )

        market_run_logger = None
        if stock_code:
            market_run_logger = AgentRunLogger(
                agent="market",
                doc_id=task_id,
                log_dir=log_dir,
                issuer_type=issuer_type,
                doc_name=doc_name,
                pdf_name=pdf_name,
                on_event=on_market_event,
            )

        client_project_id = parse_meta.get("clientProjectId")
        DEBATE_DIR.mkdir(parents=True, exist_ok=True)

        parallel_kwargs = {
            "issuer_type": issuer_type,
            "finance_retrieval_json": fin_path,
            "legal_retrieval_json": leg_path,
            "parse_json": parse_path,
            "finance_llm": finance_llm,
            "legal_llm": legal_llm,
            "master_llm": shared_llm,
            "finance_run_logger": run_logger,
            "legal_run_logger": legal_run_logger,
            "master_run_logger": master_run_logger,
            "legal_on_progress": on_legal_progress,
            "finance_rules_only": rules_only,
            "legal_react": legal_react,
            "debate_dir": DEBATE_DIR,
            "client_project_id": str(client_project_id) if client_project_id else None,
            "task_id": task_id,
            "analysis_id": analysis_id,
            "doc_name": doc_name,
            "pdf_name": pdf_name,
            "skip_master": False,
            "on_finance_done": on_finance_done,
            "on_legal_done": on_legal_done,
        }
        if stock_code:
            market_settings = resolve_market_agent_settings()
            firecrawl_ref = market_settings.get("firecrawl") or {}
            firecrawl_settings = resolve_firecrawl_settings(
                settings_path=firecrawl_ref.get("settings_path"),
                local_settings_path=firecrawl_ref.get("local_settings_path"),
                enabled=bool(firecrawl_ref.get("enabled", True)),
            )
            sina_ref = market_settings.get("sina_finance") or {}
            sina_settings = resolve_sina_finance_settings(
                settings_path=sina_ref.get("settings_path"),
                local_settings_path=sina_ref.get("local_settings_path"),
                enabled=bool(sina_ref.get("enabled", False)),
            )
            merged = await run_finance_legal_market_parallel(
                task_id,
                stock_code=stock_code,
                market_llm=shared_llm,
                market_settings=market_settings,
                firecrawl_settings=firecrawl_settings,
                sina_settings=sina_settings,
                market_run_logger=market_run_logger,
                market_on_progress=on_market_event,
                on_market_done=on_market_done,
                include_market=False,
                **parallel_kwargs,
            )
        else:
            merged = await run_finance_legal_parallel(
                task_id, include_market=False, **parallel_kwargs
            )
            merged["market"] = None
            merged["market_error"] = "missing_stock_code"
        run_logger.close(final_summary=(merged.get("finance") or {}).get("summary"))
        if legal_run_logger is not None:
            legal_run_logger.close(
                final_summary=(merged.get("legal") or {}).get("summary")
            )
        if market_run_logger is not None:
            market_run_logger.close(
                final_summary=(merged.get("market") or {}).get("summary")
            )
        master_j = ((merged.get("master") or {}).get("judgment") or {})
        master_run_logger.close(final_summary=str(master_j.get("verdict_reasoning") or "master"))
        hub.maybe_complete_debate(
            len((merged.get("master") or {}).get("debate_history") or [])
        )

        market_status = "completed" if merged.get("market") else "failed"
        if not stock_code:
            market_status = "skipped"
        if not expert_done["legal"]:
            hub.emit("agent_status", {"agentId": "legal", "status": "completed"})
        if not expert_done["financial"]:
            hub.emit("agent_status", {"agentId": "financial", "status": "completed"})
        if not expert_done["market"]:
            hub.emit("agent_status", {"agentId": "market", "status": market_status})
        if not merged.get("market"):
            hub.emit_thoughts(
                [
                    new_thought(
                        agent_id="market",
                        typ="thinking",
                        content=f"市场情绪 Agent 未产出结果：{merged.get('market_error')}",
                        meta={"kind": "model_think"},
                    )
                ],
                in_debate=False,
            )

        master = merged.get("master") if isinstance(merged.get("master"), dict) else {}
        judgment = master.get("judgment") or {}
        overall = _overall_score_100(judgment)
        if overall is None:
            overall = 0
        risk_level = str(
            judgment.get("risk_level_http") or judgment.get("risk_level") or ""
        ).upper()
        if risk_level not in {"HIGH", "MEDIUM", "LOW"}:
            risk_level = score_to_risk_level(float(overall))

        split = _write_split_reports(
            merged,
            dest_dirs=[ad, PKG_ROOT / "reports"],
            stock_code=stock_code,
            doc_name=str(doc_name),
            pdf_name=str(pdf_name),
        )
        finance_md = split.get("finance") or early_reports.get("finance") or ""
        legal_md = split.get("legal") or early_reports.get("legal") or ""
        market_md = split.get("market") or early_reports.get("market") or ""
        (ad / "merged.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        from service.report_data import build_report_data

        debate_block = {
            "rounds": (
                0
                if not hub.debate_started
                else len(master.get("debate_history") or [])
                or len({m.get("round") for m in hub.debate_messages if m.get("round") is not None})
            ),
            "messages": hub.debate_messages if hub.debate_started else [],
            "completedAt": None,
        }
        from datetime import datetime, timezone

        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if hub.debate_started:
            debate_block["completedAt"] = completed_at

        report = build_report_data(
            merged,
            overall_score=overall,
            risk_level=risk_level,
            debate=debate_block,
        )
        (ad / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        hub.set_phase("report", message="生成风险报告")
        self.store.update_meta(analysis_id, status="reporting", phase="report")
        hub.emit("report_ready", {"report": report})
        hub.emit("agent_status", {"agentId": "orchestrator", "status": "completed"})

        # 法务日志：优先 ReAct run_logger，否则合成 on_progress 事件
        leg_log = (
            Path(legal_run_logger.log_path)
            if legal_run_logger is not None and legal_run_logger.log_path
            else None
        )
        leg_jsonl = (
            Path(legal_run_logger.jsonl_path)
            if legal_run_logger is not None and legal_run_logger.jsonl_path
            else None
        )
        if leg_log and leg_log.is_file():
            legal_log_text = _read_text(leg_log)
            legal_log_events = _read_jsonl(leg_jsonl) or legal_events
        else:
            legal_log_lines = ["# Agent Run Log — legal", ""]
            for ev in legal_events:
                legal_log_lines.append(
                    f"- [{ev.get('status')}] {ev.get('name')}: "
                    f"{json.dumps(ev.get('output') or {}, ensure_ascii=False, default=str)[:500]}"
                )
            legal_log_text = "\n".join(legal_log_lines) + "\n"
            legal_log_events = legal_events
            (ad / "logs" / "legal_run.log").write_text(legal_log_text, encoding="utf-8")
            (ad / "logs" / "legal_events.jsonl").write_text(
                "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in legal_events)
                + ("\n" if legal_events else ""),
                encoding="utf-8",
            )

        fin_log = Path(run_logger.log_path) if run_logger.log_path else None
        fin_jsonl = Path(run_logger.jsonl_path) if run_logger.jsonl_path else None

        fin_dossier = (
            ((merged.get("finance") or {}).get("features") or {}).get("debate_dossier_path")
            or ((merged.get("finance") or {}).get("trace") or {}).get("debate_dossier_path")
        )
        leg_dossier = (
            ((merged.get("legal") or {}).get("features") or {}).get("debate_dossier_path")
            or ((merged.get("legal") or {}).get("trace") or {}).get("debate_dossier_path")
        )
        dossier_paths = {
            "finance": fin_dossier,
            "legal": leg_dossier,
            "market": (
                ((merged.get("market") or {}).get("features") or {}).get("debate_dossier_path")
                or ((merged.get("market") or {}).get("trace") or {}).get("debate_dossier_path")
            ),
            "master": (merged.get("master") or {}).get("dossier_path"),
        }

        agents = {
            "legal": agent_bundle_from_result(
                agent_key="legal",
                agent_result=merged.get("legal") or {},
                report_markdown=legal_md,
                log_text=legal_log_text,
                log_events=legal_log_events,
            ),
            "financial": agent_bundle_from_result(
                agent_key="finance",
                agent_result=merged.get("finance") or {},
                report_markdown=finance_md,
                log_text=_read_text(fin_log),
                log_events=_read_jsonl(fin_jsonl),
            ),
            "market": (
                agent_bundle_from_result(
                    agent_key="market",
                    agent_result=merged.get("market") or {},
                    report_markdown=market_md,
                    log_text=_read_text(
                        Path(market_run_logger.log_path)
                        if market_run_logger is not None and market_run_logger.log_path
                        else None
                    ),
                    log_events=_read_jsonl(
                        Path(market_run_logger.jsonl_path)
                        if market_run_logger is not None and market_run_logger.jsonl_path
                        else None
                    ),
                )
                if merged.get("market")
                else {
                    "agentId": "market",
                    "status": market_status,
                    "reason": merged.get("market_error"),
                }
            ),
            "orchestrator": {
                "agentId": "orchestrator",
                "status": "completed",
                "overallScore": overall,
                "riskLevel": risk_level,
                "note": "master_verdict",
                "degraded": bool((merged.get("master") or {}).get("degraded")),
                "referenceFundamentalScore": merged.get("reference_fundamental_score"),
                "logText": _read_text(Path(master_run_logger.log_path)),
                "logEvents": _read_jsonl(Path(master_run_logger.jsonl_path)),
                "master": merged.get("master") or {},
                "agentResult": {
                    "synthesisNotes": str(judgment.get("verdict_reasoning") or ""),
                    "judgment": judgment,
                    "degraded": bool((merged.get("master") or {}).get("degraded")),
                },
            },
        }

        thoughts = self.store.read_thoughts(analysis_id)
        result = {
            "analysisId": analysis_id,
            "status": "completed",
            "phase": "report",
            "overallScore": overall,
            "riskLevel": risk_level,
            "thoughts": thoughts,
            "agents": agents,
            "debate": debate_block,
            "report": report,
            "dossierPaths": dossier_paths,
            "completedAt": completed_at,
        }
        self.store.write_result(analysis_id, result)
        self.store.update_meta(
            analysis_id,
            status="completed",
            phase="report",
            overallScore=overall,
            riskLevel=risk_level,
            completedAt=completed_at,
            dossierPaths=dossier_paths,
        )
        hub.emit(
            "analysis_complete",
            {"overallScore": overall, "riskLevel": risk_level},
        )
        logger.info(
            "analysis %s completed score=%s level=%s",
            analysis_id,
            overall,
            risk_level,
        )
        if shared_llm is not None:
            try:
                await shared_llm.close()
            except Exception:
                pass
