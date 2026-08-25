// ─── ReportData — aligned with backend report_data.py / frontend_response_contract §6 ─

export type HttpRiskLevel = "HIGH" | "MEDIUM" | "LOW";

export interface ReportDimension {
  id: string;
  name: string;
  score: number;
}

export interface RiskFactor {
  id: string;
  title: string;
  sourceAgent: string;
  reason: string;
  weight?: number | null;
  evidencePage?: number | null;
  evidenceExcerpt?: string;
}

export interface RiskTimelinePoint {
  window: string;
  label: string;
  risk: string;
}

export interface PricePathForecastItem {
  window: string;
  riskLabel: string;
  expectedDirection: string;
  expectedPattern: string;
  volatilityView: string;
  keyDrivers: string[];
  confidence: string;
}

export interface PostListingCheckpoint {
  window?: string | null;
  predictionLabel?: string | null;
  predictionText?: string | null;
  actualSeverity?: string | null;
  hit?: boolean | null;
  alignment?: string | null;
  observationDate?: string | null;
  belowIssuePrice?: boolean | null;
  cumulativeReturnFromOpen?: number | null;
  issuePriceReturn?: number | null;
  maxDrawdownFromOpen?: number | null;
  realizedRiskScore?: number | null;
  note?: string;
}

export interface PostListingValidation {
  status: string;
  source: string;
  summary: string;
  businessValueScore?: number | null;
  weightedHitScore?: number | null;
  d5PriorityHit?: boolean | null;
  forecastAlignmentSummary: string;
  weights: Record<string, unknown>;
  checkpoints: PostListingCheckpoint[];
  limitations: string[];
}

export interface RadarPoint {
  axis: string;
  value: number;
}

export interface DebateHighlight {
  agentId?: string;
  type?: string;
  content: string;
  category?: string | null;
}

/** Backend currently returns empty array; kept for contract compatibility. */
export interface ComparableIPO {
  name: string;
  score: number;
  result: number | null;
}

export interface ReportData {
  overallScore: number;
  riskLevel: HttpRiskLevel;
  riskLabel: string;
  dimensions: ReportDimension[];
  riskFactors: RiskFactor[];
  comparableIPOs: ComparableIPO[];
  riskTimeline: RiskTimelinePoint[];
  pricePathForecast: PricePathForecastItem[];
  postListingValidation: PostListingValidation;
  radarData: RadarPoint[];
  executiveSummary: string;
  debateHighlights: DebateHighlight[];
  agentScores: { legal: number; financial: number; market: number };
  degraded: boolean;
  gateWarning: string | null;
  referenceFundamentalScore: number | null;
  embellishmentAnalysis?: Record<string, unknown>;
}

export interface EmbellishmentDisplay {
  score?: number;
  level?: string;
}

/** 报告是否包含可展示的文本粉饰度数据（与 backend 契约一致） */
export function hasEmbellishmentData(report: ReportData): boolean {
  const dim = report.dimensions.find((d) => d.id === "embellishment");
  const raw = report.embellishmentAnalysis;
  if (raw && typeof raw === "object") {
    if (typeof raw.score === "number") return true;
    if (typeof raw.level === "string" && raw.level) return true;
  }
  return dim != null && typeof dim.score === "number";
}

export function getEmbellishmentDisplay(
  report: ReportData
): EmbellishmentDisplay | null {
  if (!hasEmbellishmentData(report)) return null;
  const raw = report.embellishmentAnalysis;
  const dim = report.dimensions.find((d) => d.id === "embellishment");
  let score: number | undefined;
  let level: string | undefined;
  if (raw && typeof raw === "object") {
    if (typeof raw.score === "number") score = raw.score;
    if (typeof raw.level === "string" && raw.level) level = raw.level;
  }
  if (score == null && dim && typeof dim.score === "number") score = dim.score;
  if (score == null && !level) return null;
  return { score, level };
}

/** Agent 风险维度（百分制，不含 embellishment） */
export function getAgentDimensions(report: ReportData): ReportDimension[] {
  return report.dimensions.filter((d) => d.id !== "embellishment");
}

/** 概览维度条：有粉饰数据则保留第 4 维，否则仅三 Agent 维 */
export function getOverviewDimensions(report: ReportData): ReportDimension[] {
  if (hasEmbellishmentData(report)) return report.dimensions;
  return report.dimensions.filter((d) => d.id !== "embellishment");
}

export function formatReportScore(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  if (Number.isInteger(n)) return String(n);
  const rounded = Math.round(n * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function formatReportScoreOneDecimal(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  return (Math.round(n * 10) / 10).toFixed(1);
}

export function formatReportScoreRaw(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  return String(n);
}

export function riskLevelColor(level: string): string {
  const s = level.toUpperCase();
  if (s === "HIGH") return "oklch(0.65 0.22 25)";
  if (s === "LOW") return "oklch(0.72 0.15 145)";
  return "oklch(0.72 0.18 55)";
}

export function agentLabel(agentId: string): string {
  const map: Record<string, string> = {
    legal: "法务",
    financial: "财务",
    finance: "财务",
    market: "市场",
    orchestrator: "总控",
    master: "总控",
  };
  const normalized =
    agentId === "finance"
      ? "financial"
      : agentId === "master"
        ? "orchestrator"
        : agentId;
  return map[normalized] ?? map[agentId] ?? agentId;
}

export function riskTagLabel(risk: string): string {
  const s = risk.toLowerCase();
  if (s === "high") return "高";
  if (s === "low") return "低";
  return "中";
}

export function riskTagColor(risk: string): string {
  const s = risk.toLowerCase();
  if (s === "high") return "oklch(0.65 0.22 25)";
  if (s === "low") return "oklch(0.72 0.15 145)";
  return "oklch(0.72 0.18 55)";
}
