import {
  Scale,
  TrendingUp,
  Globe,
  ShieldAlert,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { AGENTS } from "@/data/agentDefinitions";
import type { AgentDefinition } from "@/types";

export const AGENT_ICON_MAP: Record<string, LucideIcon> = {
  Scale,
  TrendingUp,
  Globe,
  ShieldAlert,
};

export function normalizeAgentId(agentId: string): string {
  if (agentId === "finance") return "financial";
  if (agentId === "master") return "orchestrator";
  return agentId;
}

export function getAgentDef(agentId?: string | null): AgentDefinition | undefined {
  if (!agentId) return undefined;
  const normalized = normalizeAgentId(agentId);
  return AGENTS.find((a) => a.id === normalized);
}

export function agentLabel(agentId: string): string {
  const map: Record<string, string> = {
    legal: "法务",
    financial: "财务",
    finance: "财务",
    market: "市场",
    orchestrator: "总控",
  };
  const normalized = normalizeAgentId(agentId);
  return map[normalized] ?? map[agentId] ?? agentId;
}
