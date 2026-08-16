from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import PKG_ROOT, load_master_rules
from src.models.evidence import AgentResult
from src.models.master import (
    CompositeJudgment,
    ConflictItem,
    DebateRoundRecord,
    EmbellishmentResult,
    MasterResult,
    PredictedWindows,
    RiskFactorItem,
)
from src.skills.base import SkillInput
from src.skills.debate_reply import expert_respond_to_controller
from src.skills.detect_conflicts import DetectConflictsSkill
from src.skills.generate_warning_report import GenerateWarningReportSkill, render_master_markdown
from src.skills.master_cards import (
    agent_result_dossier_path,
    dossier_to_cards,
    load_dossier_optional,
    reference_fundamental,
)
from src.skills.master_decide import MasterDecideSkill
from src.skills.run_debate import RunDebateSkill
from src.skills.score_embellishment import ScoreEmbellishmentSkill

logger = logging.getLogger(__name__)


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, AgentResult):
        return obj.model_dump()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return {}


class MasterAgent:
    """总控决策 Agent：冲突研判 → 条件辩论 → 粉饰 → 终裁 → 报告排版。"""

    def __init__(
        self,
        llm: Any | None = None,
        *,
        run_logger: Any | None = None,
        debate_dir: Path | str | None = None,
        parse_json: Path | str | None = None,
        finance_agent: Any | None = None,
        legal_agent: Any | None = None,
        market_agent: Any | None = None,
        use_langgraph: bool = True,
    ) -> None:
        self._llm = llm
        self._run_logger = run_logger
        self._debate_dir = Path(debate_dir) if debate_dir else PKG_ROOT / ".runtime" / "debate"
        self._parse_json = parse_json
        self._finance_agent = finance_agent
        self._legal_agent = legal_agent
        self._market_agent = market_agent
        self._use_langgraph = use_langgraph
        self._detect = DetectConflictsSkill()
        self._debate = RunDebateSkill()
        self._embellish = ScoreEmbellishmentSkill()
        self._decide = MasterDecideSkill()
        self._report = GenerateWarningReportSkill()

    async def _respond(self, question: Any, claim_card: dict[str, Any] | None, *, round_no: int = 1):
        agent = question.target_agent
        inst = {
            "finance": self._finance_agent,
            "legal": self._legal_agent,
            "market": self._market_agent,
        }.get(agent)
        if inst is not None and hasattr(inst, "respond_to_controller"):
            return await inst.respond_to_controller(
                question,
                claim_card,
                round_no=round_no,
                doc_id=getattr(inst, "_doc_id", None) or "",
                parse_json=self._parse_json,
            )
        return await expert_respond_to_controller(
            agent=agent,
            question=question,
            claim_card=claim_card,
            llm=None if agent == "market" else self._llm,
            doc_id="",
            parse_json=self._parse_json,
            run_logger=self._run_logger if agent != "market" else None,
            round_no=round_no,
            demo_market=agent == "market",
        )

    async def run(
        self,
        *,
        doc_id: str,
        finance: AgentResult | dict[str, Any] | None,
        legal: AgentResult | dict[str, Any] | None,
        market: AgentResult | dict[str, Any] | None = None,
        parse_json: Path | str | None = None,
        doc_name: str | None = None,
    ) -> MasterResult:
        t0 = time.time()
        if parse_json is not None:
            self._parse_json = parse_json
        fin = _as_dict(finance)
        leg = _as_dict(legal)
        mkt = _as_dict(market)
        excerpt_max = int((load_master_rules().get("debate") or {}).get("excerpt_max_chars") or 200)
        fin_dos = load_dossier_optional(agent_result_dossier_path(fin))
        leg_dos = load_dossier_optional(agent_result_dossier_path(leg))
        mkt_dos = load_dossier_optional(agent_result_dossier_path(mkt))
        finance_cards = dossier_to_cards(fin_dos, excerpt_max=excerpt_max)
        if not finance_cards.get("claims"):
            finance_cards = {
                "agent": "finance",
                "risk_score": fin.get("risk_score"),
                "risk_level": fin.get("risk_level"),
                "summary": (fin.get("summary") or "")[:280],
                "claims": [],
            }
        legal_cards = dossier_to_cards(leg_dos, excerpt_max=excerpt_max)
        if not legal_cards.get("claims"):
            legal_cards = {
                "agent": "legal",
                "risk_score": leg.get("risk_score"),
                "risk_level": leg.get("risk_level"),
                "summary": (leg.get("summary") or "")[:280],
                "claims": [],
            }
        market_cards = dossier_to_cards(mkt_dos, excerpt_max=excerpt_max)
        if not market_cards.get("agent"):
            market_cards = {
                "agent": "market",
                "risk_score": mkt.get("risk_score") or 50,
                "risk_level": mkt.get("risk_level") or "medium",
                "summary": (mkt.get("summary") or "")[:280],
                "claims": [],
                "demo": True,
            }
        ref = reference_fundamental(float(fin.get("risk_score") or 0), float(leg.get("risk_score") or 0))
        state: dict[str, Any] = {
            "doc_id": doc_id,
            "doc_name": doc_name,
            "finance": fin,
            "legal": leg,
            "market": mkt,
            "finance_cards": finance_cards,
            "legal_cards": legal_cards,
            "market_cards": market_cards,
            "reference_score": ref,
            "need_debate": False,
            "conflicts": [],
            "debate_history": [],
            "embellishment": {},
            "judgment": {},
            "degraded": False,
            "degraded_reasons": [],
        }
        if self._use_langgraph:
            try:
                from src.graph.master_graph import run_master_subgraph

                state = await run_master_subgraph(self, state)
            except Exception as exc:
                logger.warning("master_graph fallback to sequential: %s", exc)
                state = await self.run_pipeline(state)
        else:
            state = await self.run_pipeline(state)

        judgment = CompositeJudgment(**(state.get("judgment") or {})) if state.get("judgment") else CompositeJudgment()
        emb = EmbellishmentResult(**(state.get("embellishment") or {})) if state.get("embellishment") else EmbellishmentResult()
        conflicts = [ConflictItem(**c) for c in (state.get("conflicts") or []) if isinstance(c, dict)]
        history = [
            DebateRoundRecord(**h) for h in (state.get("debate_history") or []) if isinstance(h, dict)
        ]
        factors = [RiskFactorItem(**f) for f in (state.get("risk_factors") or []) if isinstance(f, dict)]
        windows = PredictedWindows(**(state.get("predicted_windows") or {})) if state.get("predicted_windows") else PredictedWindows()
        result = MasterResult(
            doc_id=doc_id,
            degraded=bool(state.get("degraded")),
            degraded_reason=";".join(state.get("degraded_reasons") or []) or None,
            conflicts=conflicts,
            debate_history=history,
            embellishment=emb,
            judgment=judgment,
            risk_factors=factors,
            predicted_windows=windows,
            report_sections=state.get("report_sections") or {},
            report_markdown=state.get("report_markdown") or "",
            reference_fundamental_score=ref,
            trace={
                "elapsed_sec": round(time.time() - t0, 3),
                "need_debate": state.get("need_debate"),
                "run_log": self._run_logger.paths if self._run_logger is not None else {},
            },
        )
        if not result.report_markdown:
            result.report_markdown = render_master_markdown(result)
        self._debate_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = self._debate_dir / f"{doc_id}_master_{ts}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2, default=str)
        result.dossier_path = str(out_path)
        if self._run_logger is not None:
            self._run_logger.result(
                {
                    "overall_score": judgment.overall_score,
                    "level": judgment.level,
                    "degraded": result.degraded,
                    "dossier_path": result.dossier_path,
                }
            )
        return result

    async def run_pipeline(self, state: dict[str, Any]) -> dict[str, Any]:
        state = await self.step_detect(state)
        if state.get("need_debate"):
            state = await self.step_debate(state)
        state = await self.step_embellish(state)
        state = await self.step_decide(state)
        state = await self.step_report(state)
        return state

    async def step_detect(self, state: dict[str, Any]) -> dict[str, Any]:
        out = await self._detect.execute(
            SkillInput(
                doc_id=state.get("doc_id") or "",
                params={
                    "llm": self._llm,
                    "run_logger": self._run_logger,
                    "reference_score": state.get("reference_score"),
                    "finance_cards": state.get("finance_cards"),
                    "legal_cards": state.get("legal_cards"),
                    "market_cards": state.get("market_cards"),
                },
            )
        )
        state["conflicts"] = out.data.get("conflicts") or []
        state["need_debate"] = bool(out.data.get("need_debate"))
        if out.degraded:
            state["degraded"] = True
            state["degraded_reasons"].append(out.degraded_reason or "detect")
            # 无 LLM 时不辩论
            state["need_debate"] = False
        return state

    async def step_debate(self, state: dict[str, Any]) -> dict[str, Any]:
        out = await self._debate.execute(
            SkillInput(
                doc_id=state.get("doc_id") or "",
                params={
                    "llm": self._llm,
                    "run_logger": self._run_logger,
                    "respond_fn": self._respond,
                    "conflicts": state.get("conflicts"),
                    "finance_cards": state.get("finance_cards"),
                    "legal_cards": state.get("legal_cards"),
                    "market_cards": state.get("market_cards"),
                },
            )
        )
        state["debate_history"] = out.data.get("debate_history") or []
        if out.degraded:
            state["degraded"] = True
            state["degraded_reasons"].append(out.degraded_reason or "debate")
        return state

    async def step_embellish(self, state: dict[str, Any]) -> dict[str, Any]:
        out = await self._embellish.execute(
            SkillInput(
                doc_id=state.get("doc_id") or "",
                params={
                    "llm": self._llm,
                    "run_logger": self._run_logger,
                    "parse_json": self._parse_json,
                },
            )
        )
        state["embellishment"] = out.data.get("embellishment") or {}
        state["embellish_prompt_user"] = out.data.get("prompt_user")
        if out.degraded:
            state["degraded"] = True
            state["degraded_reasons"].append(out.degraded_reason or "embellishment")
        return state

    async def step_decide(self, state: dict[str, Any]) -> dict[str, Any]:
        out = await self._decide.execute(
            SkillInput(
                doc_id=state.get("doc_id") or "",
                params={
                    "llm": self._llm,
                    "run_logger": self._run_logger,
                    "reference_score": state.get("reference_score"),
                    "finance": state.get("finance"),
                    "legal": state.get("legal"),
                    "market": state.get("market"),
                    "finance_cards": state.get("finance_cards"),
                    "legal_cards": state.get("legal_cards"),
                    "market_cards": state.get("market_cards"),
                    "embellishment": state.get("embellishment"),
                    "debate_history": state.get("debate_history"),
                },
            )
        )
        state["judgment"] = out.data.get("judgment") or {}
        state["risk_factors"] = out.data.get("risk_factors") or []
        state["predicted_windows"] = out.data.get("predicted_windows") or {}
        state["report_sections"] = out.data.get("report_sections") or {}
        if out.degraded:
            state["degraded"] = True
            state["degraded_reasons"].append(out.degraded_reason or "decide")
        return state

    async def step_report(self, state: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "judgment": state.get("judgment"),
            "embellishment": state.get("embellishment"),
            "debate_history": state.get("debate_history"),
            "report_sections": state.get("report_sections"),
            "predicted_windows": state.get("predicted_windows"),
            "risk_factors": state.get("risk_factors"),
            "reference_fundamental_score": state.get("reference_score"),
            "degraded": state.get("degraded"),
            "degraded_reason": ";".join(state.get("degraded_reasons") or []) or None,
            "post_listing": {
                "day1": None,
                "day5": None,
                "day20": None,
                "day60": None,
                "hit": None,
                "note": "上市后真实行情验证本轮未接入",
            },
        }
        out = await self._report.execute(
            SkillInput(doc_id=state.get("doc_id") or "", params={"master": payload})
        )
        state["report_markdown"] = out.data.get("report_markdown") or ""
        return state
