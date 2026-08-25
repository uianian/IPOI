import type { Thought, ThoughtEvidence } from "@/types";

const FIELD_CODE_LABELS: Record<string, string> = {
  RELATED_PARTY: "关联交易",
  CONCENTRATION: "客户/供应商集中度",
  PIPELINE_RISK: "产品管线",
  REDEMPTION_CLAUSE: "赎回条款",
  REDEMPTION_MEDIUM: "赎回条款（中等风险）",
};

const CODE_LIKE = /^[A-Z][A-Z0-9_]+$/;

export interface PageEvidenceGroup {
  page: number;
  excerpts: string[];
  sourceTypes: string[];
  fieldCodes: string[];
}

export function isToolTraceThought(thought: Thought): boolean {
  const kind = thought.meta?.kind;
  return kind === "tool_call" || kind === "tool_result";
}

export function isReasoningThought(thought: Thought): boolean {
  if (thought.type !== "thinking") return false;
  if (isToolTraceThought(thought)) return false;

  const kind = thought.meta?.kind;
  if (!kind) {
    // 旧 Mock 或无 meta 的 thinking
    return true;
  }

  return kind === "model_think" || Boolean(thought.meta?.rawThink?.trim());
}

export function getFieldCodeLabel(code?: string | null): string | undefined {
  if (!code) return undefined;
  return FIELD_CODE_LABELS[code] ?? code;
}

export function getFindingTitle(thought: Thought): string {
  const content = thought.content.trim();
  const evidence = thought.meta?.evidence ?? [];
  const fieldCode = evidence.find((e) => e.fieldCode)?.fieldCode;

  if (content && !CODE_LIKE.test(content)) {
    return content;
  }

  const fromField = getFieldCodeLabel(fieldCode);
  if (fromField) return fromField;

  if (content) return content;
  return "风险发现";
}

function parseRefPage(ref?: string): number | null {
  if (!ref) return null;
  const match = ref.match(/p\.?\s*(\d+)/i);
  if (!match) return null;
  const page = Number.parseInt(match[1], 10);
  return Number.isFinite(page) ? page : null;
}

export function collectEvidence(thought: Thought): ThoughtEvidence[] {
  if (thought.meta?.evidence?.length) {
    return thought.meta.evidence;
  }

  const page = parseRefPage(thought.ref);
  if (page != null && thought.content.trim()) {
    return [
      {
        page,
        excerpt: thought.content.trim(),
      },
    ];
  }

  return [];
}

export function groupEvidenceByPage(
  evidence: ThoughtEvidence[]
): PageEvidenceGroup[] {
  const byPage = new Map<number, PageEvidenceGroup>();

  for (const item of evidence) {
    if (!Number.isFinite(item.page)) continue;
    const page = item.page;
    let group = byPage.get(page);
    if (!group) {
      group = { page, excerpts: [], sourceTypes: [], fieldCodes: [] };
      byPage.set(page, group);
    }

    const excerpt = item.excerpt?.trim();
    if (excerpt && !group.excerpts.includes(excerpt)) {
      group.excerpts.push(excerpt);
    }

    if (item.sourceType && !group.sourceTypes.includes(item.sourceType)) {
      group.sourceTypes.push(item.sourceType);
    }

    if (item.fieldCode && !group.fieldCodes.includes(item.fieldCode)) {
      group.fieldCodes.push(item.fieldCode);
    }
  }

  return [...byPage.values()].sort((a, b) => a.page - b.page);
}

export function splitAgentThoughtsForSummary(thoughts: Thought[]): {
  findings: Thought[];
  conclusions: Thought[];
  reasoning: Thought[];
  toolTraces: Thought[];
} {
  const findings: Thought[] = [];
  const conclusions: Thought[] = [];
  const reasoning: Thought[] = [];
  const toolTraces: Thought[] = [];

  for (const t of thoughts) {
    if (t.type === "finding") {
      findings.push(t);
    } else if (t.type === "conclusion") {
      conclusions.push(t);
    } else if (isToolTraceThought(t)) {
      toolTraces.push(t);
    } else if (isReasoningThought(t)) {
      reasoning.push(t);
    }
  }

  return { findings, conclusions, reasoning, toolTraces };
}

export interface ToolTraceDisplayItem {
  id: string;
  toolName?: string;
  kind: string;
  content: string;
  status?: string;
  durationMs?: number;
}

export function toToolTraceDisplayItems(
  traces: Thought[]
): ToolTraceDisplayItem[] {
  return traces.map((t) => ({
    id: t.id,
    toolName: t.meta?.toolName,
    kind: t.meta?.kind ?? "unknown",
    content: t.content.trim(),
    status: t.meta?.toolStatus,
    durationMs: t.meta?.durationMs,
  }));
}

export function getAgentSummaryLabel(thoughts: Thought[]): string | null {
  const { findings, conclusions, toolTraces } =
    splitAgentThoughtsForSummary(thoughts);
  const parts: string[] = [];
  if (findings.length) parts.push(`${findings.length} 项发现`);
  if (conclusions.length) parts.push(`${conclusions.length} 结论`);
  if (toolTraces.length) parts.push(`${toolTraces.length} 工具调用`);
  return parts.length ? parts.join(" · ") : null;
}

export function mergeReasoningText(thoughts: Thought[]): string {
  const segments: string[] = [];

  for (const t of thoughts) {
    if (t.meta?.rawThink?.trim()) {
      segments.push(t.meta.rawThink.trim());
    } else if (t.content.trim()) {
      segments.push(t.content.trim());
    }
  }

  const unique = [...new Set(segments)];
  return unique.join("\n\n");
}
