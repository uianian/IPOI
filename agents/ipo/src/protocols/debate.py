from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from src.llm.prompts import CONSISTENCY_VERIFICATION
from src.models.conflict import ConflictItem, DebateMessage, DebateResult, DebateRound
from src.models.enums import AgentRole, ConflictType, DebateStance

logger = logging.getLogger(__name__)


class DebateProtocol:
    def __init__(self, vllm_client: Any, max_rounds: int = 3) -> None:
        self._vllm = vllm_client
        self._max_rounds = max_rounds

    async def detect_conflicts(
        self,
        legal_result: dict[str, Any],
        finance_result: dict[str, Any],
        sentiment_result: dict[str, Any],
    ) -> list[ConflictItem]:
        conflicts: list[ConflictItem] = []

        legal_summary = legal_result.get("summary", "")
        finance_summary = finance_result.get("summary", "")
        sentiment_summary = sentiment_result.get("summary", "")

        agent_conclusions = [
            (AgentRole.LEGAL.value, legal_summary),
            (AgentRole.FINANCE.value, finance_summary),
            (AgentRole.SENTIMENT.value, sentiment_summary),
        ]

        for i in range(len(agent_conclusions)):
            for j in range(i + 1, len(agent_conclusions)):
                agent_a, conclusion_a = agent_conclusions[i]
                agent_b, conclusion_b = agent_conclusions[j]

                if not conclusion_a or not conclusion_b:
                    continue

                conflict = await self._check_pair_conflict(agent_a, conclusion_a, agent_b, conclusion_b)
                if conflict:
                    conflicts.append(conflict)

        return conflicts

    async def _check_pair_conflict(
        self, agent_a: str, conclusion_a: str, agent_b: str, conclusion_b: str
    ) -> ConflictItem | None:
        messages = [
            {"role": "user", "content": CONSISTENCY_VERIFICATION.format(
                agent_a=agent_a, conclusion_a=conclusion_a,
                agent_b=agent_b, conclusion_b=conclusion_b,
            )},
        ]

        try:
            response = await self._vllm.chat(messages, temperature=0.0)
            parsed = json.loads(response)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Conflict detection LLM call failed: {e}")
            return None

        if parsed.get("has_conflict", False):
            conflict_type_str = parsed.get("conflict_type", "semantic")
            try:
                conflict_type = ConflictType(conflict_type_str)
            except ValueError:
                conflict_type = ConflictType.SEMANTIC

            return ConflictItem(
                conflict_id=str(uuid.uuid4()),
                conflict_type=conflict_type,
                description=parsed.get("conflict_description", ""),
                source_agents=[agent_a, agent_b],
                source_conclusions=[conclusion_a[:200], conclusion_b[:200]],
            )

        return None

    async def run_debate(
        self,
        conflict: ConflictItem,
        agent_analyze_results: dict[str, dict[str, Any]],
    ) -> DebateResult:
        debate_result = DebateResult(conflict_id=conflict.conflict_id)

        for round_num in range(1, self._max_rounds + 1):
            round_msgs: list[DebateMessage] = []

            for agent_name in conflict.source_agents:
                if agent_name not in agent_analyze_results:
                    continue

                original = agent_analyze_results[agent_name].get("summary", "")
                others = [
                    agent_analyze_results[a].get("summary", "")
                    for a in conflict.source_agents if a != agent_name
                ]
                challenge = "\n".join(others)

                from src.llm.prompts import CONFLICT_DEBATE
                debate_messages = [
                    {"role": "user", "content": CONFLICT_DEBATE.format(
                        agent_role=agent_name,
                        original_conclusion=original,
                        challenge=challenge,
                        additional_evidence="无",
                    )},
                ]

                try:
                    response = await self._vllm.chat(debate_messages)
                    parsed = json.loads(response)
                    stance_str = parsed.get("stance", "assert")
                    try:
                        stance = DebateStance(stance_str)
                    except ValueError:
                        stance = DebateStance.ASSERT

                    round_msgs.append(DebateMessage(
                        round_number=round_num,
                        agent_role=agent_name,
                        stance=stance,
                        content=parsed.get("content", ""),
                        evidence_supplement=parsed.get("evidence_supplement"),
                        conclusion_revised=parsed.get("conclusion_revised"),
                    ))
                except Exception as e:
                    logger.warning(f"Debate round {round_num} for {agent_name} failed: {e}")
                    round_msgs.append(DebateMessage(
                        round_number=round_num,
                        agent_role=agent_name,
                        stance=DebateStance.ASSERT,
                        content=f"辩论失败: {e}",
                    ))

            debate_round = DebateRound(
                round_number=round_num,
                messages=round_msgs,
            )

            all_concede = all(m.stance == DebateStance.CONCEDE for m in round_msgs if m.stance != DebateStance.CLARIFY)
            any_concede = any(m.stance == DebateStance.CONCEDE for m in round_msgs)

            if all_concede or any_concede:
                debate_round.is_resolved = True
                revised = [m.conclusion_revised for m in round_msgs if m.conclusion_revised]
                debate_round.consensus_conclusion = revised[0] if revised else "各方达成部分共识"
                debate_result.final_resolved = True
                debate_result.final_conclusion = debate_round.consensus_conclusion

            debate_result.rounds.append(debate_round)
            debate_result.total_rounds = round_num

            if debate_result.final_resolved:
                break

        if not debate_result.final_resolved:
            debate_result.is_irreconcilable = True
            debate_result.final_conclusion = "不可调和冲突，需人工审核"

        return debate_result