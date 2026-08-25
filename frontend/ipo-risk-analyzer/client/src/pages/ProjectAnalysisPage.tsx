/**
 * ProjectAnalysisPage — 多Agent协作分析 + 专家辩论（项目上下文）
 * SSE 会话由 AnalysisSessionProvider 保活，换路由不断流。
 */
import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useParams, useLocation } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  ChevronRight,
  CheckCircle2,
  Sparkles,
  Activity,
  BarChart3,
  History,
  RotateCcw,
  Loader2,
  Download,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import AgentDebatePanel from "@/components/debate/AgentDebatePanel";
import AnalysisThoughtsPanel from "@/components/analysis/AnalysisThoughtsPanel";
import AgentReportDialog from "@/components/analysis/AgentReportDialog";
import AnalysisHistoryDialog from "@/components/analysis/AnalysisHistoryDialog";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import {
  filterThoughtsForLeftPanel,
  mergeAnalysisFromResult,
} from "@/lib/analysisHelpers";
import { toast } from "sonner";
import { useActiveProject } from "@/contexts/ActiveProjectContext";
import {
  useAnalysisSession,
  DONE_STATUSES,
  IDLE_STATUSES,
} from "@/contexts/AnalysisSessionContext";
import { getProjectById, getProjectDisplayName } from "@/data/projects";
import {
  getAnalysis,
  saveAnalysis,
  saveReport,
  exportAnalysisLog,
  archiveCurrentAnalysis,
  listAnalysisHistory,
} from "@/data/projectStore";
import {
  fetchIndexStatus,
  fetchAnalysisResult,
  type IndexStatus,
} from "@/services/analysisService";
import type { AgentId } from "@/types";

export default function ProjectAnalysisPage() {
  const { id } = useParams();
  const [, navigate] = useLocation();
  const { setActiveProjectId } = useActiveProject();
  const { getSession, isRunning, hydrateSession, startSession } =
    useAnalysisSession();

  const project = id ? getProjectById(id) : undefined;
  const session = id ? getSession(id) : undefined;

  const [historyCount, setHistoryCount] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [restartConfirmOpen, setRestartConfirmOpen] = useState(false);
  const [reportDialogAgent, setReportDialogAgent] = useState<AgentId | null>(
    null
  );
  const [indexStatus, setIndexStatus] = useState<IndexStatus | "unknown">(
    "unknown"
  );
  const [indexProgress, setIndexProgress] = useState<number | undefined>();
  const [indexMessage, setIndexMessage] = useState<string | undefined>();

  const indexPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isAnalysisStarted =
    session != null &&
    (session.status === "running" ||
      session.status === "done" ||
      session.thoughts.length > 0);
  const isAnalysisDone = session?.status === "done";
  const thoughts = session?.thoughts ?? [];
  const agents = session?.agents ?? {};
  const debateMessages = session?.debateMessages ?? [];
  const analysisPhase = session?.phase;
  const phaseMessage = session?.phaseMessage;
  const agentStatuses = session?.agentStatuses ?? IDLE_STATUSES;
  const latestScore = session?.overallScore;
  const latestRiskLevel = session?.riskLevel;

  const panelThoughts = useMemo(
    () => filterThoughtsForLeftPanel(thoughts, debateMessages),
    [thoughts, debateMessages]
  );

  const refreshHistoryCount = useCallback(async () => {
    if (!id) return;
    const list = await listAnalysisHistory(id);
    setHistoryCount(list.length);
  }, [id]);

  useEffect(() => {
    if (!id) return;
    setActiveProjectId(id);

    async function restore() {
      await refreshHistoryCount();

      // 进行中的内存会话优先，不覆盖
      if (isRunning(id!)) return;

      let analysis = await getAnalysis(id!);
      if (!analysis?.thoughts.length) return;

      if (analysis.completedAt) {
        try {
          const remote = await fetchAnalysisResult(id!, analysis.analysisId);
          if (remote) {
            const { record, report } = mergeAnalysisFromResult(
              analysis,
              remote
            );
            analysis = record;
            await saveAnalysis(id!, {
              ...record,
              completedAt: record.completedAt ?? analysis.completedAt,
            });
            if (report) {
              await saveReport(id!, report);
            }
          }
        } catch {
          // 保留本地缓存
        }
      }

      hydrateSession(id!, {
        status: analysis.completedAt ? "done" : "idle",
        analysisId: analysis.analysisId,
        thoughts: analysis.thoughts,
        agents: analysis.agents ?? {},
        debateMessages: analysis.debate?.messages ?? [],
        debateRounds: analysis.debate?.rounds,
        phase: analysis.phase,
        overallScore: analysis.overallScore,
        riskLevel: analysis.riskLevel,
        agentStatuses: analysis.completedAt
          ? { ...DONE_STATUSES }
          : { ...IDLE_STATUSES },
      });
    }

    void restore();
  }, [
    id,
    setActiveProjectId,
    refreshHistoryCount,
    isRunning,
    hydrateSession,
  ]);

  // 会话完成后刷新历史计数
  useEffect(() => {
    if (session?.status === "done") {
      void refreshHistoryCount();
    }
  }, [session?.status, refreshHistoryCount]);

  useEffect(() => {
    if (!id) return;

    let cancelled = false;

    const stopPoll = () => {
      if (indexPollRef.current) {
        clearInterval(indexPollRef.current);
        indexPollRef.current = null;
      }
    };

    const applyStatus = (data: {
      status: IndexStatus;
      message?: string;
      progress?: number;
    }) => {
      if (cancelled) return;
      setIndexStatus(data.status);
      setIndexProgress(data.progress);
      setIndexMessage(data.message);
      if (data.status === "ready" || data.status === "failed") {
        stopPoll();
      }
    };

    async function tick() {
      try {
        const p = getProjectById(id!);
        const data = await fetchIndexStatus(id!, p?.parseTaskId);
        applyStatus(data);
      } catch {
        if (!cancelled) {
          setIndexStatus("unknown");
          setIndexMessage("无法获取索引状态");
        }
      }
    }

    if (isAnalysisDone) {
      setIndexStatus("ready");
      stopPoll();
      return () => {
        cancelled = true;
        stopPoll();
      };
    }

    void tick();
    indexPollRef.current = setInterval(() => {
      void tick();
    }, 3000);

    return () => {
      cancelled = true;
      stopPoll();
    };
  }, [id, isAnalysisDone]);

  const ensureIndexReady = useCallback(async (): Promise<boolean> => {
    if (!id) return false;
    if (indexStatus === "ready") return true;

    try {
      const p = getProjectById(id);
      const data = await fetchIndexStatus(id, p?.parseTaskId);
      setIndexStatus(data.status);
      setIndexProgress(data.progress);
      setIndexMessage(data.message);
      if (data.status === "ready") return true;
      if (data.status === "failed") {
        toast.error(
          data.message || "索引建立失败，请稍后重试或联系后端排查"
        );
        return false;
      }
      toast.info("索引建立中，还需要等几分钟，请稍后");
      return false;
    } catch {
      toast.info("索引建立中，还需要等几分钟，请稍后");
      return false;
    }
  }, [id, indexStatus]);

  const handleStartAnalysis = async () => {
    if (!id) return;
    if (isRunning(id)) return;
    const ready = await ensureIndexReady();
    if (!ready) return;
    const projectLocal = getProjectById(id);
    await startSession(id, {
      taskId: projectLocal?.parseTaskId,
      enableEmbellishment: projectLocal?.enableEmbellishment ?? false,
    });
  };

  const handleConfirmRestart = async () => {
    if (!id) return;
    setRestartConfirmOpen(false);
    const ready = await ensureIndexReady();
    if (!ready) return;
    try {
      await archiveCurrentAnalysis(id);
      await refreshHistoryCount();
      const projectLocal = getProjectById(id);
      await startSession(id, {
        taskId: projectLocal?.parseTaskId,
        enableEmbellishment: projectLocal?.enableEmbellishment ?? false,
      });
      toast.success("已开始新一轮分析，原结果已保存到历史版本");
    } catch {
      toast.error("归档失败，请重试");
    }
  };

  const handleExportLog = async () => {
    if (!id) return;
    const ok = await exportAnalysisLog(id, project);
    if (ok) {
      toast.success("分析日志已导出");
    } else {
      toast.error("暂无分析日志可导出");
    }
  };

  const doneCount = Object.values(agentStatuses).filter(
    (s) => s === "done"
  ).length;

  const scoreDisplay =
    latestScore != null
      ? `${latestScore}/100${latestRiskLevel ? ` ${latestRiskLevel}` : ""}`
      : "—";

  return (
    <div className="h-[calc(100vh-3rem)] overflow-hidden">
      <ResizablePanelGroup
        direction="horizontal"
        autoSaveId="analysis-agent-debate-layout"
        className="h-full"
      >
        <ResizablePanel defaultSize={35} minSize={20} className="min-h-0">
          <div className="flex h-full min-w-0 flex-col overflow-hidden">
            <div className="px-5 py-4 border-b border-border flex-shrink-0">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <Brain className="w-4 h-4 text-primary" />
                  <span className="text-sm font-semibold text-foreground">
                    多Agent协作分析
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {thoughts.length > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-[10px] gap-1 px-2"
                      onClick={() => void handleExportLog()}
                    >
                      <Download className="w-3 h-3" />
                      导出分析日志
                    </Button>
                  )}
                  {historyCount > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-[10px] gap-1 px-2"
                      onClick={() => setHistoryOpen(true)}
                    >
                      <History className="w-3 h-3" />
                      历史版本
                    </Button>
                  )}
                  <div className="flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace]">
                      {doneCount}/4 DONE
                    </span>
                  </div>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground">
                {project
                  ? `${project.fileName} · ${project.ticker}`
                  : "解析完成"}
              </p>
            </div>

            {!isAnalysisStarted && (
              <div className="px-5 py-4 border-b border-border flex-shrink-0 space-y-2">
                <Button
                  onClick={handleStartAnalysis}
                  className="w-full h-10 text-sm font-semibold gap-2"
                  style={{
                    background: "oklch(0.75 0.18 195)",
                    color: "oklch(0.10 0.012 240)",
                    boxShadow: "0 0 20px oklch(0.75 0.18 195 / 0.4)",
                  }}
                >
                  {indexStatus === "indexing" || indexStatus === "unknown" ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4" />
                  )}
                  启动多Agent分析
                </Button>
                {indexStatus === "indexing" && (
                  <p className="text-[11px] text-muted-foreground text-center">
                    索引建立中
                    {indexProgress != null ? ` · ${indexProgress}%` : ""}
                    {indexMessage ? ` · ${indexMessage}` : ""}
                    ，请稍候再启动分析
                  </p>
                )}
                {indexStatus === "failed" && (
                  <p className="text-[11px] text-[oklch(0.65_0.22_25)] text-center">
                    {indexMessage || "索引建立失败，请稍后重试"}
                  </p>
                )}
                {indexStatus === "ready" && (
                  <p className="text-[11px] text-[oklch(0.72_0.15_145)] text-center">
                    索引已就绪，可以开始分析
                  </p>
                )}
              </div>
            )}

            {isAnalysisDone && (
              <div className="px-5 py-3 border-b border-border flex-shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full h-9 text-xs gap-1.5"
                  onClick={() => setRestartConfirmOpen(true)}
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  重新分析
                </Button>
              </div>
            )}

            <AnalysisThoughtsPanel
              className="flex-1 min-h-0"
              thoughts={panelThoughts}
              agentStatuses={agentStatuses}
              agents={agents}
              onViewReport={setReportDialogAgent}
              scrollOnUpdate={isAnalysisStarted && !isAnalysisDone}
              footer={
                <AnimatePresence>
                  {isAnalysisDone && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mx-3 mb-3 p-4 rounded-lg border border-[oklch(0.72_0.15_145)/0.4] bg-[oklch(0.72_0.15_145)/0.08]"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <CheckCircle2 className="w-4 h-4 text-[oklch(0.72_0.15_145)]" />
                        <span className="text-sm font-semibold text-[oklch(0.72_0.15_145)]">
                          分析完成
                        </span>
                      </div>
                      <p className="text-[11px] text-muted-foreground mb-3">
                        综合风险评分：
                        <span className="text-[oklch(0.65_0.22_25)] font-bold font-['JetBrains_Mono',monospace] ml-1">
                          {scoreDisplay}
                        </span>
                      </p>
                      <Button
                        onClick={() => navigate(`/project/${id}/report`)}
                        size="sm"
                        className="w-full h-8 text-xs gap-1.5"
                        style={{
                          background: "oklch(0.75 0.18 195)",
                          color: "oklch(0.10 0.012 240)",
                        }}
                      >
                        <BarChart3 className="w-3.5 h-3.5" />
                        查看风险预警报告
                        <ChevronRight className="w-3.5 h-3.5" />
                      </Button>
                    </motion.div>
                  )}
                </AnimatePresence>
              }
            />
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel defaultSize={65} minSize={20} className="min-h-0">
          <div className="h-full min-w-0 overflow-hidden">
            <AgentDebatePanel
              messages={debateMessages}
              phase={analysisPhase}
              isLive={isAnalysisStarted && !isAnalysisDone}
              phaseMessage={phaseMessage}
            />
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>

      <AgentReportDialog
        open={reportDialogAgent != null}
        onOpenChange={(open) => {
          if (!open) setReportDialogAgent(null);
        }}
        agentId={reportDialogAgent}
        reportMarkdown={
          reportDialogAgent
            ? agents[reportDialogAgent]?.reportMarkdown
            : undefined
        }
      />

      {id && (
        <AnalysisHistoryDialog
          projectId={id}
          open={historyOpen}
          onOpenChange={setHistoryOpen}
          defaultTab="thoughts"
          ticker={project?.ticker}
          companyName={project ? getProjectDisplayName(project) : undefined}
        />
      )}

      <AlertDialog open={restartConfirmOpen} onOpenChange={setRestartConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>重新分析</AlertDialogTitle>
            <AlertDialogDescription>
              当前分析结果与报告将保存到历史版本，并开始新一轮多 Agent
              分析。辩论记录将随新一轮分析重置。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmRestart}>
              确认重新分析
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
