from __future__ import annotations

from src.config import load_master_rules
from src.llm.master_prompts import MASTER_EMBELLISHMENT_SYSTEM
from src.models.master import EmbellishmentHit, EmbellishmentResult
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.llm_json import llm_json
from src.skills.master_cards import first_pages_text


def buzzword_hits(text: str, words: list[str]) -> list[str]:
    found: list[str] = []
    for w in words:
        if w and w in (text or "") and w not in found:
            found.append(w)
    return found


class ScoreEmbellishmentSkill(BaseSkill):
    skill_name = "master_score_embellishment"
    version = "0.1.0"
    description = "总控按第四章维度打粉饰分 0–10，引用前五页原文"

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        p = skill_input.params
        llm = p.get("llm")
        logger_ = p.get("run_logger")
        rules = load_master_rules()
        emb = rules.get("embellishment") or {}
        n_pages = int(emb.get("first_pages") or 5)
        cap = int(emb.get("page_char_cap") or 1200)
        buzz = list(emb.get("buzzwords") or [])
        pages_text = p.get("pages_text")
        if not pages_text:
            pages_text = first_pages_text(
                p.get("parse_json"), n_pages=n_pages, page_char_cap=cap
            )
        hints = buzzword_hits(str(pages_text or ""), buzz)
        max_tokens = int((rules.get("debate") or {}).get("embellishment_max_tokens") or 1024)
        user = (
            f"【前{n_pages}页截断原文】\n{pages_text or '（无解析文本）'}\n\n"
            f"【词表提示命中（非分数本身）】{hints or '无'}\n"
            "请按第四章维度打 0–10 分，并引用原文 hits（禁止编造页码）。"
        )
        # 暴露 prompt 便于单测
        prompt_user = user
        out = await llm_json(
            llm,
            [
                {"role": "system", "content": MASTER_EMBELLISHMENT_SYSTEM},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )
        data = out.get("data") or {}
        try:
            score = int(data.get("score") if data.get("score") is not None else 0)
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(10, score))
        level = str(data.get("level") or ("high" if score >= 7 else "medium" if score >= 4 else "low"))
        if level not in {"low", "medium", "high"}:
            level = "high" if score >= 7 else "medium" if score >= 4 else "low"
        hits: list[EmbellishmentHit] = []
        for h in data.get("hits") or []:
            if not isinstance(h, dict):
                continue
            try:
                page = int(h["page"]) if h.get("page") is not None else None
            except (TypeError, ValueError):
                page = None
            hits.append(
                EmbellishmentHit(
                    page=page,
                    excerpt=str(h.get("excerpt") or "")[:400],
                    dimension=str(h.get("dimension") or ""),
                    note=str(h.get("note") or ""),
                )
            )
        result = EmbellishmentResult(
            score=score,
            level=level,  # type: ignore[arg-type]
            reason=str(data.get("reason") or ""),
            hits=hits,
            dimensions=data.get("dimensions") if isinstance(data.get("dimensions"), dict) else {},
            buzzword_hints=hints,
        )
        if logger_ is not None:
            logger_.master_step(
                event="embellishment",
                utterance=result.reason or f"粉飾分 {score}",
                duration_ms=out.get("duration_ms"),
                reasoning=out.get("reasoning"),
                usage=out.get("usage"),
                extra={"score": score, "level": level, "buzzword_hints": hints},
                model=out.get("model"),
            )
        return SkillOutput(
            success=True,
            data={
                "embellishment": result.model_dump(),
                "prompt_user": prompt_user,
                "llm_ok": out.get("ok"),
            },
            degraded=not out.get("ok"),
            degraded_reason=out.get("error"),
        )
