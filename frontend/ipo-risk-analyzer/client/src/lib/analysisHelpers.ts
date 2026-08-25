import type {
  AgentId,
  AgentOutput,
  AnalysisRecord,
  DebateMessage,
  DebateMessageType,
  Thought,
} from "@/types";
import type { ReportData } from "@/data/reportData";

export const SPECIALIST_AGENT_IDS = ["legal", "financial", "market"] as const;
export type SpecialistAgentId = (typeof SPECIALIST_AGENT_IDS)[number];

export function isSpecialistAgent(
  agentId: AgentId
): agentId is SpecialistAgentId {
  return SPECIALIST_AGENT_IDS.includes(agentId as SpecialistAgentId);
}

/** 左侧结论面板：辩论开始后冻结专家 Agent 结论，仅保留总控补充 */
export function filterThoughtsForLeftPanel(
  thoughts: Thought[],
  debateMessages: DebateMessage[]
): Thought[] {
  if (debateMessages.length === 0) return thoughts;

  const debateStartTs = debateMessages[0].timestamp;
  return thoughts.filter((t) => {
    if (t.agentId === "orchestrator") return true;
    if (isSpecialistAgent(t.agentId)) {
      return t.timestamp < debateStartTs;
    }
    return true;
  });
}

export function getAgentReportMarkdown(
  agents: Partial<Record<AgentId, AgentOutput>> | undefined,
  agentId: AgentId
): string | undefined {
  return agents?.[agentId]?.reportMarkdown;
}

export const DEBATE_TYPE_LABELS: Record<DebateMessageType, string> = {
  opening: "开场",
  rebuttal: "反驳",
  question: "提问",
  response: "回应",
  closing: "总结陈词",
  summary: "综合总结",
};

export function mergeAgentOutput(
  prev: Partial<Record<AgentId, AgentOutput>> | undefined,
  agentId: AgentId,
  patch: Partial<AgentOutput>
): Partial<Record<AgentId, AgentOutput>> {
  return {
    ...prev,
    [agentId]: {
      ...prev?.[agentId],
      ...patch,
    },
  };
}

/** 将 GET analysis/result 合并进本地记录（远程优先） */
export function mergeAnalysisFromResult(
  local: AnalysisRecord,
  remote: AnalysisRecord & { report?: ReportData }
): { record: AnalysisRecord; report: ReportData | null } {
  const hasRemoteAgents =
    remote.agents != null && Object.keys(remote.agents).length > 0;
  const hasRemoteDebate =
    remote.debate != null && remote.debate.messages.length > 0;

  return {
    record: {
      ...local,
      analysisId: remote.analysisId ?? local.analysisId,
      status: remote.status ?? local.status,
      phase: remote.phase ?? local.phase,
      thoughts: remote.thoughts?.length ? remote.thoughts : local.thoughts,
      agents: hasRemoteAgents ? remote.agents : local.agents,
      debate: hasRemoteDebate ? remote.debate : local.debate,
      overallScore: remote.overallScore ?? local.overallScore,
      riskLevel: remote.riskLevel ?? local.riskLevel,
      completedAt: remote.completedAt ?? local.completedAt,
    },
    report: remote.report ?? null,
  };
}
