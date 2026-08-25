import type {
  AgentId,
  AgentOutput,
  AnalysisPhase,
  DebateMessage,
  Thought,
} from "@/types";
import type { ReportData } from "@/data/reportData";
import { apiClient, getLlmConfigPayload } from "@/lib/api";

export interface AnalysisStartPayload {
  clientProjectId: string;
  taskId?: string;
  enableEmbellishment: boolean;
}

export interface AnalysisStartOptions {
  taskId?: string;
  enableEmbellishment: boolean;
}

export type IndexStatus = "indexing" | "ready" | "failed";

export interface IndexStatusData {
  status: IndexStatus;
  message?: string;
  progress?: number;
}

export interface AnalysisStreamHandlers {
  onAgentStatus?: (agentId: AgentId, status: string) => void;
  onThought?: (thought: Thought) => void;
  onPhaseChange?: (phase: AnalysisPhase, message?: string) => void;
  onAgentReport?: (
    agentId: AgentId,
    data: Pick<AgentOutput, "reportMarkdown" | "agentResult" | "financeDetail">
  ) => void;
  onDebateMessage?: (message: DebateMessage) => void;
  onDebateComplete?: (rounds: number) => void;
  onReportReady?: (report: ReportData) => void;
  onComplete?: (data: { overallScore?: number; riskLevel?: string }) => void;
  onError?: (err: Error) => void;
}

export async function fetchIndexStatus(
  clientProjectId: string,
  taskId?: string
): Promise<IndexStatusData> {
  const { data } = await apiClient.get<{
    success: boolean;
    data: IndexStatusData;
  }>(`/projects/${clientProjectId}/index-status`, {
    params: taskId ? { taskId } : undefined,
  });
  return data.data;
}

export async function startAnalysis(
  clientProjectId: string,
  options: AnalysisStartOptions
): Promise<string | undefined> {
  const llmConfig = getLlmConfigPayload();
  const { data } = await apiClient.post<{
    success: boolean;
    data?: { analysisId?: string; status?: string };
  }>(`/projects/${clientProjectId}/analysis/start`, {
    clientProjectId,
    taskId: options.taskId,
    enableEmbellishment: options.enableEmbellishment,
    ...(llmConfig ? { llmConfig } : {}),
  } satisfies AnalysisStartPayload);
  return data.data?.analysisId;
}

export function subscribeAnalysisStream(
  clientProjectId: string,
  handlers: AnalysisStreamHandlers,
  analysisId?: string
): () => void {
  const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
  const query = analysisId
    ? `?analysisId=${encodeURIComponent(analysisId)}`
    : "";
  const url = `${base.replace(/\/$/, "")}/projects/${clientProjectId}/analysis/stream${query}`;
  const es = new EventSource(url);

  es.addEventListener("agent_status", (e) => {
    const { agentId, status } = JSON.parse(e.data);
    handlers.onAgentStatus?.(agentId, status);
  });

  es.addEventListener("thought", (e) => {
    const { thought } = JSON.parse(e.data);
    handlers.onThought?.(thought);
  });

  es.addEventListener("phase_change", (e) => {
    const { phase, message } = JSON.parse(e.data);
    handlers.onPhaseChange?.(phase, message);
  });

  es.addEventListener("agent_report", (e) => {
    const { agentId, reportMarkdown, agentResult, financeDetail } =
      JSON.parse(e.data);
    handlers.onAgentReport?.(agentId, {
      reportMarkdown,
      agentResult,
      financeDetail,
    });
  });

  es.addEventListener("debate_message", (e) => {
    const { message } = JSON.parse(e.data);
    handlers.onDebateMessage?.(message);
  });

  es.addEventListener("debate_complete", (e) => {
    const { rounds } = JSON.parse(e.data);
    handlers.onDebateComplete?.(rounds);
  });

  es.addEventListener("report_ready", (e) => {
    const { report } = JSON.parse(e.data);
    handlers.onReportReady?.(report);
  });

  es.addEventListener("analysis_complete", (e) => {
    handlers.onComplete?.(JSON.parse(e.data));
    es.close();
  });

  es.onerror = () => {
    handlers.onError?.(new Error("分析流连接中断"));
    es.close();
  };

  return () => es.close();
}

export async function fetchAnalysisResult(
  clientProjectId: string,
  analysisId?: string
) {
  const { data } = await apiClient.get(
    `/projects/${clientProjectId}/analysis/result`,
    { params: analysisId ? { analysisId } : undefined }
  );
  return data.data;
}

export async function fetchReport(
  clientProjectId: string,
  analysisId?: string
): Promise<ReportData | null> {
  try {
    const { data } = await apiClient.get(
      `/projects/${clientProjectId}/report`,
      { params: analysisId ? { analysisId } : undefined }
    );
    return data.data ?? data;
  } catch {
    return null;
  }
}

function parseContentDispositionFilename(
  header: string | undefined
): string | null {
  if (!header) return null;
  const utf8 = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch {
      return utf8[1];
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/i);
  return plain?.[1] ?? null;
}

export async function fetchReportExport(
  clientProjectId: string,
  analysisId?: string
): Promise<{ blob: Blob; filename: string } | null> {
  try {
    const response = await apiClient.get(
      `/projects/${clientProjectId}/report/export`,
      {
        params: analysisId ? { analysisId } : undefined,
        responseType: "blob",
      }
    );
    const disposition = response.headers["content-disposition"] as
      | string
      | undefined;
    const filename =
      parseContentDispositionFilename(disposition) ??
      `IPO风险报告_${clientProjectId}.pdf`;
    return { blob: response.data as Blob, filename };
  } catch {
    return null;
  }
}
