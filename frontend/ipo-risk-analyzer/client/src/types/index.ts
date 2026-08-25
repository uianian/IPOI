// ─── Project ──────────────────────────────────────────────────────────
export type ProjectStatus = "uploading" | "parsing" | "analyzing" | "completed";

export type ParseMode = "expert";

export interface Project {
  id: string;
  fileName: string;
  /** 用户自定义项目名称，仅前端展示与列表识别 */
  projectName?: string;
  ticker: string;
  uploadTime: string;
  parseCompleteTime?: string;
  status: ProjectStatus;
  parseProgress: number; // 0-100
  parseMode: ParseMode;
  isBiotech: boolean;
  /** 专业模式：纳入文本粉饰度评分；上传时选择，默认 false */
  enableEmbellishment: boolean;
  parseTaskId?: string;
  parseDone?: boolean;
  analysisDone?: boolean;
}

// ─── Parse result ─────────────────────────────────────────────────────
export interface CompanyInfo {
  companyName: string;
  ticker: string;
  industry: string;
  ipoDate?: string;
  offerPriceHkd?: number;
  sharesOffered?: number;
}

export interface ParseStats {
  totalPages: number;
  parsedPages: number;
  chartCount: number;
  tableCount: number;
  textChunkCount: number;
}

/** 后端 /result 返回并写入缓存的解析结果（仅 Markdown 展示层） */
export interface ParseResult {
  taskId: string;
  projectId: string;
  mode: ParseMode;
  status: "completed" | "failed";
  companyInfo?: CompanyInfo;
  stats: ParseStats;
  markdown: string;
  completedAt?: string;
}

// ─── Agent analysis ────────────────────────────────────────────────────
export type AgentId = "legal" | "financial" | "market" | "orchestrator";
export type AgentStatus = "idle" | "running" | "done" | "waiting";
export type ThoughtType = "thinking" | "finding" | "conclusion";

export interface ThoughtEvidence {
  page: number;
  excerpt: string;
  sourceType?: "text" | "table" | string;
  fieldCode?: string | null;
  sectionId?: string | null;
  confidence?: number;
}

export interface ThoughtMeta {
  kind?:
    | "tool_call"
    | "tool_result"
    | "model_think"
    | "risk_point"
    | "evidence"
    | string;
  toolName?: string;
  toolStatus?: string;
  toolArgs?: unknown;
  durationMs?: number;
  evidence?: ThoughtEvidence[];
  rawThink?: string;
}

export interface Thought {
  id: string;
  agentId: AgentId;
  type: ThoughtType;
  content: string;
  ref?: string;
  timestamp: number;
  meta?: ThoughtMeta;
}

export type AnalysisPhase = "analysis" | "debate" | "report";
export type AnalysisStatus =
  | "running"
  | "debating"
  | "reporting"
  | "completed"
  | "failed";

/** 与后端 agents.{id} 对齐 */
export interface AgentOutput {
  reportMarkdown?: string;
  agentResult?: Record<string, unknown>;
  financeDetail?: Record<string, unknown>;
}

export type DebateMessageType =
  | "opening"
  | "rebuttal"
  | "question"
  | "response"
  | "closing"
  | "summary";

export interface DebateMessage {
  id: string;
  agentId: AgentId;
  round: number;
  type: DebateMessageType;
  content: string;
  targetAgentId?: AgentId | null;
  timestamp: number;
}

export interface DebateSession {
  rounds: number;
  messages: DebateMessage[];
  completedAt?: string;
}

export interface AnalysisRecord {
  thoughts: Thought[];
  overallScore?: number;
  riskLevel?: string;
  completedAt?: string;
  analysisId?: string;
  status?: AnalysisStatus | string;
  phase?: AnalysisPhase;
  agents?: Partial<Record<AgentId, AgentOutput>>;
  debate?: DebateSession;
}

/** 单次分析历史版本元信息（IndexedDB analysis-history） */
export interface AnalysisHistoryMeta {
  id: string;
  completedAt: string;
  overallScore?: number;
  riskLevel?: string;
  label: string;
}

export interface AnalysisHistoryManifest {
  versions: AnalysisHistoryMeta[];
}

export interface AgentDefinition {
  id: AgentId;
  name: string;
  nameEn: string;
  icon: string;
  color: string;
  colorClass: string;
  borderClass: string;
  bgClass: string;
  role: string;
}

// ─── LLM settings ─────────────────────────────────────────────────────
export interface AgentLlmSettings {
  apiBaseUrl?: string;
  apiKey?: string;
  model?: string;
}

export interface LlmConfigPayload {
  apiBaseUrl: string;
  apiKey: string;
  model: string;
}

// ─── Wind 公司查询（company-lookup.json） ────────────────────────────
export interface CompanyRecord {
  windCode: string;
  stockCode?: string;
  name: string;
  fullName: string;
  listBoard: string;
  listDate: string;
  companyName: string;
  nameEng: string;
  foundDate: string;
  legalRep: string;
  country: string;
}

export interface CompanyLookupData {
  generatedAt: string;
  source?: string;
  total: number;
  matchedCompany?: number;
  aliasCount?: number;
  aliases?: Record<string, string>;
  records: Record<string, CompanyRecord>;
}

// ─── Display helpers ───────────────────────────────────────────────────
export const STATUS_LABELS: Record<ProjectStatus, string> = {
  uploading: "上传中",
  parsing: "解析中",
  analyzing: "分析中",
  completed: "已完成",
};

export const STATUS_COLORS: Record<ProjectStatus, string> = {
  uploading: "oklch(0.75 0.18 195)",
  parsing: "oklch(0.72 0.18 55)",
  analyzing: "oklch(0.65 0.15 270)",
  completed: "oklch(0.72 0.15 145)",
};
