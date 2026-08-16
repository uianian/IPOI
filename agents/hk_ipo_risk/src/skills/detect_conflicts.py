from __future__ import annotations

import json
import logging
from typing import Any

from src.models.master import ConflictItem
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.llm_json import dumps_cards, llm_json
from src.skills.master_cards import checklist_text
from src.llm.master_prompts import MASTER_CONFLICT_SYSTEM, MASTER_CONFLICT_USER

logger = logging.getLogger(__name__)


class DetectConflictsSkill(BaseSkill):
    skill_name = "master_detect_conflicts"
    version = "0.1.0"
    description = "总控 LLM 研判冲突/共振/证据缺口"

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        p = skill_input.params
        llm = p.get("llm")
        logger_ = p.get("run_logger")
        ref = p.get("reference_score")
        user = MASTER_CONFLICT_USER.format(
            reference_score=ref,
            checklist=checklist_text(),
            finance_cards=dumps_cards(p.get("finance_cards") or {}),
            legal_cards=dumps_cards(p.get("legal_cards") or {}),
            market_cards=dumps_cards(p.get("market_cards") or {}),
        )
        out = await llm_json(
            llm,
            [
                {"role": "system", "content": MASTER_CONFLICT_SYSTEM},
                {"role": "user", "content": user},
            ],
            max_tokens=800,
        )
        data = out.get("data") or {}
        items: list[ConflictItem] = []
        for raw in data.get("conflicts") or []:
            if not isinstance(raw, dict):
                continue
            try:
                items.append(
                    ConflictItem(
                        theme=str(raw.get("theme") or "other"),
                        kind=raw.get("kind") or "conflict",
                        source_agents=list(raw.get("source_agents") or []),
                        claim_ids=[str(x) for x in (raw.get("claim_ids") or [])],
                        need_discussion=bool(raw.get("need_discussion")),
                        priority=raw.get("priority") or "medium",
                        description=str(raw.get("description") or ""),
                    )
                )
            except Exception:
                continue
        need_debate = bool(data.get("need_debate")) or any(c.need_discussion for c in items)
        if logger_ is not None:
            logger_.master_step(
                event="conflict_detection",
                utterance=data.get("observation") or json.dumps([c.model_dump() for c in items], ensure_ascii=False),
                duration_ms=out.get("duration_ms"),
                reasoning=out.get("reasoning"),
                usage=out.get("usage"),
                extra={"ok": out.get("ok"), "need_debate": need_debate},
                model=out.get("model"),
            )
        return SkillOutput(
            success=True,
            data={
                "conflicts": [c.model_dump() for c in items],
                "need_debate": need_debate,
                "observation": data.get("observation") or "",
                "llm_ok": out.get("ok"),
                "duration_ms": out.get("duration_ms"),
            },
            degraded=not out.get("ok"),
            degraded_reason=out.get("error"),
        )
