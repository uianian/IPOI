import type { AgentLlmSettings, LlmConfigPayload } from "@/types";
import { readJSON, writeJSON } from "@/lib/storage";

const STORAGE_KEY = "ipo:agentLlmSettings";

export function getAgentLlmSettings(): AgentLlmSettings {
  return readJSON<AgentLlmSettings>(STORAGE_KEY, {});
}

export function saveAgentLlmSettings(settings: AgentLlmSettings): void {
  writeJSON(STORAGE_KEY, settings);
}

/** 有完整配置时返回 llmConfig，否则 undefined（使用后端默认） */
export function getLlmConfigPayload(): LlmConfigPayload | undefined {
  const s = getAgentLlmSettings();
  if (!s.apiBaseUrl?.trim() || !s.apiKey?.trim() || !s.model?.trim()) {
    return undefined;
  }
  return {
    apiBaseUrl: s.apiBaseUrl.trim(),
    apiKey: s.apiKey.trim(),
    model: s.model.trim(),
  };
}
