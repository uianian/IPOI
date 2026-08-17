from __future__ import annotations

import json

from src.config import load_master_rules
from src.models.master import ConflictItem
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.llm_json import dumps_cards, json_payload_usable, llm_json
from src.skills.master_cards import checklist_text
from src.llm.master_prompts import MASTER_CONFLICT_SYSTEM, MASTER_CONFLICT_USER

_CONFLICT_JSON_KEYS = ("conflicts", "need_debate")


class DetectConflictsSkill(BaseSkill):
    skill_name = "master_detect_conflicts"
    version = "0.1.0"
    description = "总控 LLM 研判冲突/共振/证据缺口"

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        p = skill_input.params
        llm = p.get("llm")
        logger_ = p.get("run_logger")
        ref = p.get("reference_score")
        rules = load_master_rules()
        debate_cfg = rules.get("debate") or {}
        max_tokens = int(debate_cfg.get("conflict_max_tokens") or 2048)
        reasoning_max_tokens = int(debate_cfg.get("conflict_reasoning_max_tokens") or 512)
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
            max_tokens=max_tokens,
            reasoning_max_tokens=reasoning_max_tokens,
            required_keys=_CONFLICT_JSON_KEYS,
        )
        data = out.get("data") or {}
        usable = json_payload_usable(data, required_keys=_CONFLICT_JSON_KEYS) and bool(out.get("ok"))
        items: list[ConflictItem] = []
        if usable:
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
        # 空 JSON / 截断不得解读为 need_debate=false
        if usable:
            need_debate = bool(data.get("need_debate")) or any(c.need_discussion for c in items)
            observation = data.get("observation") or ""
            degraded = False
            degraded_reason = None
        else:
            need_debate = False
            observation = data.get("observation") or ""
            degraded = True
            degraded_reason = out.get("error") or "empty_json"
        if logger_ is not None:
            logger_.master_step(
                event="conflict_detection",
                utterance=observation
                or json.dumps([c.model_dump() for c in items], ensure_ascii=False),
                duration_ms=out.get("duration_ms"),
                reasoning=out.get("reasoning"),
                usage=out.get("usage"),
                extra={
                    "ok": bool(out.get("ok")) and usable,
                    "need_debate": need_debate,
                    "retries": out.get("retries"),
                    "finish_reason": out.get("finish_reason"),
                    "error": degraded_reason,
                },
                model=out.get("model"),
            )
        return SkillOutput(
            success=True,
            data={
                "conflicts": [c.model_dump() for c in items],
                "need_debate": need_debate,
                "observation": observation,
                "llm_ok": bool(out.get("ok")) and usable,
                "duration_ms": out.get("duration_ms"),
                "retries": out.get("retries") or 0,
            },
            degraded=degraded,
            degraded_reason=degraded_reason,
        )
