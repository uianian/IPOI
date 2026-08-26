/**
 * AnalysisSessionContext — 将分析 SSE 会话提升到路由外，换页不断流
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  isSpecialistAgent,
  mergeAgentOutput,
  mergeAnalysisFromResult,
} from "@/lib/analysisHelpers";
import { updateProject } from "@/data/projects";
import { markAnalysisDone } from "@/data/projectState";
import {
  saveAnalysis,
  saveAnalysisProgress,
  saveReport,
} from "@/data/projectStore";
import type { ReportData } from "@/data/reportData";
import {
  startAnalysis as startAnalysisApi,
  subscribeAnalysisStream,
  fetchAnalysisResult,
  fetchReport,
  fetchReportExport,
} from "@/services/analysisService";
import type {
  AgentId,
  AgentOutput,
  AgentStatus,
  AnalysisPhase,
  AnalysisRecord,
  DebateMessage,
  Thought,
} from "@/types";
import { toast } from "sonner";

const IDLE_STATUSES: Record<AgentId, AgentStatus> = {
  legal: "idle",
  financial: "idle",
  market: "idle",
  orchestrator: "idle",
};

const DONE_STATUSES: Record<AgentId, AgentStatus> = {
  legal: "done",
  financial: "done",
  market: "done",
  orchestrator: "done",
};

export type AnalysisSessionStatus = "idle" | "running" | "done" | "error";

export interface AnalysisSessionState {
  projectId: string;
  status: AnalysisSessionStatus;
  analysisId?: string;
  thoughts: Thought[];
  agents: Partial<Record<AgentId, AgentOutput>>;
  debateMessages: DebateMessage[];
  debateRounds?: number;
  phase?: AnalysisPhase;
  phaseMessage?: string;
  agentStatuses: Record<AgentId, AgentStatus>;
  overallScore?: number;
  riskLevel?: string;
}

interface CollectedBuffers {
  thoughts: Thought[];
  agents: Partial<Record<AgentId, AgentOutput>>;
  debate: DebateMessage[];
  phase?: AnalysisPhase;
  debateRounds?: number;
  pendingReport: ReportData | null;
  analysisId?: string;
}

interface AnalysisSessionContextValue {
  getSession: (projectId: string) => AnalysisSessionState | undefined;
  isRunning: (projectId: string) => boolean;
  /** 用本地/远程缓存覆盖会话快照（不启动 SSE） */
  hydrateSession: (
    projectId: string,
    snapshot: Partial<AnalysisSessionState> & { status: AnalysisSessionStatus }
  ) => void;
  startSession: (
    projectId: string,
    options: { taskId?: string; enableEmbellishment: boolean }
  ) => Promise<boolean>;
}

const AnalysisSessionContext =
  createContext<AnalysisSessionContextValue | null>(null);

function emptySession(projectId: string): AnalysisSessionState {
  return {
    projectId,
    status: "idle",
    thoughts: [],
    agents: {},
    debateMessages: [],
    agentStatuses: { ...IDLE_STATUSES },
  };
}

export function AnalysisSessionProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<
    Record<string, AnalysisSessionState>
  >({});
  const unsubRef = useRef<Record<string, () => void>>({});
  const buffersRef = useRef<Record<string, CollectedBuffers>>({});

  const patchSession = useCallback(
    (projectId: string, patch: Partial<AnalysisSessionState>) => {
      setSessions((prev) => {
        const base = prev[projectId] ?? emptySession(projectId);
        return {
          ...prev,
          [projectId]: { ...base, ...patch, projectId },
        };
      });
    },
    []
  );

  const hydrateSession = useCallback(
    (
      projectId: string,
      snapshot: Partial<AnalysisSessionState> & {
        status: AnalysisSessionStatus;
      }
    ) => {
      // 进行中的 SSE 会话优先，不覆盖
      setSessions((prev) => {
        if (prev[projectId]?.status === "running") return prev;
        const base = prev[projectId] ?? emptySession(projectId);
        return {
          ...prev,
          [projectId]: {
            ...base,
            ...snapshot,
            projectId,
            agentStatuses:
              snapshot.agentStatuses ??
              (snapshot.status === "done"
                ? { ...DONE_STATUSES }
                : base.agentStatuses),
          },
        };
      });
    },
    []
  );

  const persistProgress = useCallback((projectId: string) => {
    const buf = buffersRef.current[projectId];
    if (!buf) return;
    void saveAnalysisProgress(projectId, {
      analysisId: buf.analysisId,
      thoughts: [...buf.thoughts],
      agents: buf.agents,
      phase: buf.phase,
      debate: buf.debate.length
        ? {
            rounds: buf.debateRounds ?? 0,
            messages: [...buf.debate],
          }
        : undefined,
    });
  }, []);

  const finishSession = useCallback(
    async (
      projectId: string,
      record: AnalysisRecord,
      reportFromStream?: ReportData | null
    ) => {
      markAnalysisDone(projectId);
      updateProject(projectId, { status: "completed", analysisDone: true });

      let finalRecord = record;
      let report = reportFromStream ?? null;
      const buf = buffersRef.current[projectId];
      if (!report && buf?.pendingReport) {
        report = buf.pendingReport;
      }

      try {
        const result = await fetchAnalysisResult(
          projectId,
          finalRecord.analysisId ?? record.analysisId
        );
        if (result) {
          const merged = mergeAnalysisFromResult(finalRecord, result);
          finalRecord = merged.record;
          if (merged.report) report = merged.report;
        }
      } catch {
        toast.error("无法拉取 analysis/result，已保存流式分析数据");
      }

      if (!report) {
        report = await fetchReport(
          projectId,
          finalRecord.analysisId ?? record.analysisId
        );
      }

      await saveAnalysis(projectId, {
        ...finalRecord,
        completedAt: finalRecord.completedAt ?? new Date().toISOString(),
        status: "completed",
        phase: "report",
      });

      if (report) {
        const exported = await fetchReportExport(
          projectId,
          finalRecord.analysisId ?? record.analysisId
        );
        await saveReport(projectId, report, exported?.blob);
      }

      patchSession(projectId, {
        status: "done",
        thoughts: finalRecord.thoughts,
        agents: finalRecord.agents ?? {},
        debateMessages: finalRecord.debate?.messages ?? [],
        debateRounds: finalRecord.debate?.rounds,
        phase: "report",
        phaseMessage: undefined,
        agentStatuses: { ...DONE_STATUSES },
        overallScore: finalRecord.overallScore,
        riskLevel: finalRecord.riskLevel,
        analysisId: finalRecord.analysisId,
      });

      if (buffersRef.current[projectId]) {
        buffersRef.current[projectId].pendingReport = null;
        buffersRef.current[projectId].analysisId = undefined;
      }
      delete unsubRef.current[projectId];
    },
    [patchSession]
  );

  const startSession = useCallback(
    async (
      projectId: string,
      options: { taskId?: string; enableEmbellishment: boolean }
    ): Promise<boolean> => {
      const existing = unsubRef.current[projectId];
      if (existing) {
        existing();
        delete unsubRef.current[projectId];
      }

      buffersRef.current[projectId] = {
        thoughts: [],
        agents: {},
        debate: [],
        phase: "analysis",
        pendingReport: null,
        analysisId: undefined,
      };

      patchSession(projectId, {
        status: "running",
        thoughts: [],
        agents: {},
        debateMessages: [],
        debateRounds: undefined,
        phase: "analysis",
        phaseMessage: undefined,
        agentStatuses: { ...IDLE_STATUSES },
        overallScore: undefined,
        riskLevel: undefined,
        analysisId: undefined,
      });

      updateProject(projectId, { status: "analyzing" });

      let analysisId: string | undefined;
      try {
        analysisId = await startAnalysisApi(projectId, {
          taskId: options.taskId,
          enableEmbellishment: options.enableEmbellishment,
        });
        buffersRef.current[projectId].analysisId = analysisId;
        patchSession(projectId, { analysisId });
        await saveAnalysisProgress(projectId, {
          analysisId,
          thoughts: [],
          agents: {},
          phase: "analysis",
        });
      } catch {
        toast.error("启动分析失败，请重试");
        updateProject(projectId, { status: "parsing" });
        patchSession(projectId, { status: "error" });
        return false;
      }

      const unsub = subscribeAnalysisStream(
        projectId,
        {
          onAgentStatus: (agentId, status) => {
            setSessions((prev) => {
              const cur = prev[projectId] ?? emptySession(projectId);
              return {
                ...prev,
                [projectId]: {
                  ...cur,
                  agentStatuses: {
                    ...cur.agentStatuses,
                    [agentId]:
                      status === "running"
                        ? "running"
                        : status === "done"
                          ? "done"
                          : cur.agentStatuses[agentId],
                  },
                },
              };
            });
          },
          onThought: (thought) => {
            const buf = buffersRef.current[projectId];
            if (!buf) return;
            if (
              isSpecialistAgent(thought.agentId) &&
              (buf.phase === "debate" || buf.phase === "report")
            ) {
              return;
            }
            buf.thoughts.push(thought);
            patchSession(projectId, { thoughts: [...buf.thoughts] });
            persistProgress(projectId);
          },
          onPhaseChange: (phase, message) => {
            const buf = buffersRef.current[projectId];
            if (buf) buf.phase = phase;
            patchSession(projectId, {
              phase,
              phaseMessage: message,
            });
            persistProgress(projectId);
          },
          onAgentReport: (agentId, data) => {
            const buf = buffersRef.current[projectId];
            if (!buf) return;
            buf.agents = mergeAgentOutput(buf.agents, agentId, data);
            patchSession(projectId, { agents: { ...buf.agents } });
            persistProgress(projectId);
          },
          onDebateMessage: (message) => {
            const buf = buffersRef.current[projectId];
            if (!buf) return;
            buf.debate.push(message);
            patchSession(projectId, {
              debateMessages: [...buf.debate],
            });
            persistProgress(projectId);
          },
          onDebateComplete: (rounds) => {
            const buf = buffersRef.current[projectId];
            if (buf) buf.debateRounds = rounds;
            patchSession(projectId, { debateRounds: rounds });
            persistProgress(projectId);
          },
          onReportReady: (report) => {
            const buf = buffersRef.current[projectId];
            if (buf) buf.pendingReport = report;
          },
          onComplete: async (data) => {
            const buf = buffersRef.current[projectId];
            if (!buf) return;

            const streamRecord: AnalysisRecord = {
              analysisId: buf.analysisId,
              thoughts: buf.thoughts,
              agents: buf.agents,
              debate: buf.debate.length
                ? {
                    rounds: buf.debateRounds ?? 0,
                    messages: buf.debate,
                  }
                : undefined,
              overallScore: data.overallScore,
              riskLevel: data.riskLevel,
              phase: "report",
            };

            patchSession(projectId, {
              status: "done",
              agentStatuses: { ...DONE_STATUSES },
              overallScore: data.overallScore,
              riskLevel: data.riskLevel,
              phase: "report",
              phaseMessage: undefined,
            });

            await finishSession(projectId, streamRecord, buf.pendingReport);
          },
          onError: () => {
            toast.error("分析流连接失败，请重试");
            updateProject(projectId, { status: "parsing" });
            patchSession(projectId, { status: "error" });
            delete unsubRef.current[projectId];
          },
        },
        analysisId
      );

      unsubRef.current[projectId] = unsub;
      return true;
    },
    [finishSession, patchSession, persistProgress]
  );

  const getSession = useCallback(
    (projectId: string) => sessions[projectId],
    [sessions]
  );

  const isRunning = useCallback(
    (projectId: string) => sessions[projectId]?.status === "running",
    [sessions]
  );

  const value = useMemo(
    () => ({ getSession, isRunning, hydrateSession, startSession }),
    [getSession, isRunning, hydrateSession, startSession]
  );

  return (
    <AnalysisSessionContext.Provider value={value}>
      {children}
    </AnalysisSessionContext.Provider>
  );
}

export function useAnalysisSession() {
  const ctx = useContext(AnalysisSessionContext);
  if (!ctx) {
    throw new Error(
      "useAnalysisSession must be used within AnalysisSessionProvider"
    );
  }
  return ctx;
}

export { DONE_STATUSES, IDLE_STATUSES };
