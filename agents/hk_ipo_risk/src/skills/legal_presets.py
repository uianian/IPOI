from __future__ import annotations

"""法务 Skill 预设骨架（本轮不跑 ReAct；下一阶段注册后由 LegalAgent 调用）。"""

from src.llm.prompts import LEGAL_DIMENSION_PROMPTS, LEGAL_SUBMIT_SCHEMA, LEGAL_SYSTEM
from src.skills.base import BaseSkill, SkillInput, SkillOutput

LEGAL_SKILL_NAMES = [
    "legal_governance",
    "legal_shareholder_rights",
    "legal_related_party",
    "legal_contracts_and_ip",
    "legal_regulatory_litigation",
]

LEGAL_SKILL_META = {
    "legal_governance": {
        "description": "股权结构与治理风险（控股股东/实控人/一致行动/AB股/董事）",
        "gpt_map": "Skill1 Corporate Governance",
    },
    "legal_shareholder_rights": {
        "description": "对赌/赎回与上市前权利清理",
        "gpt_map": "Skill2 Shareholder Right / 增强 3.1",
    },
    "legal_related_party": {
        "description": "关联交易公允性与依赖",
        "gpt_map": "Skill3 Related Party / 增强 3.2",
    },
    "legal_contracts_and_ip": {
        "description": "重大合同 + 知识产权（合并 GPT Skill4+7）",
        "gpt_map": "Skill4 Contract + Skill7 IP",
    },
    "legal_regulatory_litigation": {
        "description": "监管合规 + 诉讼仲裁（合并 GPT Skill5+6）",
        "gpt_map": "Skill5 Regulatory + Skill6 Litigation",
    },
}


class LegalSkillStub(BaseSkill):
    """预设骨架：记录 prompt 模板；execute 返回 not_implemented。"""

    def __init__(self, skill_name: str) -> None:
        meta = LEGAL_SKILL_META[skill_name]
        self.skill_name = skill_name
        self.version = "0.1.0-stub"
        self.description = meta["description"]
        self.gpt_map = meta["gpt_map"]
        self.prompt_template = LEGAL_DIMENSION_PROMPTS[skill_name]

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=False,
            degraded=True,
            degraded_reason="stub",
            error=(
                f"{self.skill_name} 为预设骨架，本轮 LegalAgent 仍走规则路径。"
                "下一阶段接入 ReAct 后实现检索+LLM 抽取。"
            ),
            data={
                "skill": self.skill_name,
                "gpt_map": self.gpt_map,
                "prompt_preview": self.prompt_template[:200],
                "legal_system": LEGAL_SYSTEM[:120],
                "submit_schema_hint": LEGAL_SUBMIT_SCHEMA[:160],
                "params": skill_input.params,
            },
        )


def build_legal_skill_stubs() -> list[LegalSkillStub]:
    return [LegalSkillStub(n) for n in LEGAL_SKILL_NAMES]


def register_legal_skill_stubs(registry: object) -> None:
    for skill in build_legal_skill_stubs():
        registry.register(skill)  # type: ignore[attr-defined]
