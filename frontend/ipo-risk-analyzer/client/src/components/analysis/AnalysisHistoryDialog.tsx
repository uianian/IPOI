/**
 * AnalysisHistoryDialog — 分析历史版本列表与只读查看
 */
import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import AnalysisThoughtsPanel from "@/components/analysis/AnalysisThoughtsPanel";
import AgentReportDialog from "@/components/analysis/AgentReportDialog";
import ReportViewer from "@/components/report/ReportViewer";
import { filterThoughtsForLeftPanel } from "@/lib/analysisHelpers";
import {
  listAnalysisHistory,
  getAnalysisHistorySnapshot,
  getAnalysisHistoryReportPdf,
  downloadBlob,
} from "@/data/projectStore";
import type { AnalysisHistoryMeta } from "@/types";
import type { AgentId, AgentStatus } from "@/types";
import type { AnalysisHistorySnapshot } from "@/data/projectStore";
import { toast } from "sonner";

const DONE_STATUSES: Record<AgentId, AgentStatus> = {
  legal: "done",
  financial: "done",
  market: "done",
  orchestrator: "done",
};

export interface AnalysisHistoryDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultTab?: "thoughts" | "report";
  ticker?: string;
  companyName?: string;
}

export default function AnalysisHistoryDialog({
  projectId,
  open,
  onOpenChange,
  defaultTab = "thoughts",
  ticker,
  companyName,
}: AnalysisHistoryDialogProps) {
  const [versions, setVersions] = useState<AnalysisHistoryMeta[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<AnalysisHistorySnapshot | null>(
    null
  );
  const [activeTab, setActiveTab] = useState(defaultTab);
  const [reportDialogAgent, setReportDialogAgent] = useState<AgentId | null>(
    null
  );

  useEffect(() => {
    if (!open) return;
    setActiveTab(defaultTab);
    listAnalysisHistory(projectId).then((list) => {
      setVersions(list);
      if (list.length > 0) {
        setSelectedId(list[0].id);
      } else {
        setSelectedId(null);
        setSnapshot(null);
      }
    });
  }, [open, projectId, defaultTab]);

  useEffect(() => {
    if (!selectedId || !open) {
      setSnapshot(null);
      return;
    }
    getAnalysisHistorySnapshot(projectId, selectedId).then(setSnapshot);
  }, [selectedId, projectId, open]);

  const handleExportHistoryPdf = async () => {
    if (!selectedId) return;
    const pdf = await getAnalysisHistoryReportPdf(projectId, selectedId);
    if (pdf) {
      downloadBlob(
        pdf,
        `IPO风险报告_历史_${ticker ?? selectedId}.pdf`
      );
      toast.success("历史报告已下载");
    } else {
      toast.info("该历史版本无 PDF 缓存");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[90vh] h-[min(90vh,900px)] flex flex-col p-0 gap-0 overflow-hidden">
        <DialogHeader className="px-6 py-4 border-b border-border shrink-0">
          <DialogTitle className="text-base">分析历史版本</DialogTitle>
          <DialogDescription className="text-xs">
            只读查看过往分析结果；主界面始终展示最新一次分析。
          </DialogDescription>
        </DialogHeader>

        {versions.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
            暂无历史版本
          </div>
        ) : (
          <div className="flex flex-1 min-h-0 overflow-hidden">
            <div className="w-44 border-r border-border shrink-0 flex flex-col min-h-0">
              <div className="px-3 py-2 text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider">
                VERSIONS
              </div>
              <ScrollArea className="flex-1 min-h-0">
                <div className="p-2 space-y-1">
                  {versions.map((v) => (
                    <button
                      key={v.id}
                      type="button"
                      onClick={() => setSelectedId(v.id)}
                      className={`w-full text-left px-3 py-2.5 rounded-lg text-xs transition-colors ${
                        selectedId === v.id
                          ? "bg-primary/10 border border-primary/30 text-foreground"
                          : "hover:bg-secondary/60 text-muted-foreground border border-transparent"
                      }`}
                    >
                      <div className="font-medium truncate">{v.label}</div>
                      {v.overallScore != null && (
                        <div className="mt-1 flex items-center gap-1.5">
                          <Badge variant="outline" className="text-[10px] h-5">
                            {v.overallScore}/100
                          </Badge>
                          {v.riskLevel && (
                            <span className="text-[10px] truncate">
                              {v.riskLevel}
                            </span>
                          )}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </div>

            <div className="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden">
              {snapshot ? (
                <Tabs
                  value={activeTab}
                  onValueChange={(v) =>
                    setActiveTab(v as "thoughts" | "report")
                  }
                  className="flex-1 flex flex-col min-h-0 overflow-hidden"
                >
                  <TabsList className="mx-4 mt-3 mb-0 w-fit shrink-0">
                    <TabsTrigger value="thoughts" className="text-xs">
                      Agent 思考
                    </TabsTrigger>
                    <TabsTrigger value="report" className="text-xs">
                      风险报告
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent
                    value="thoughts"
                    className="flex-1 min-h-0 m-0 overflow-hidden data-[state=inactive]:hidden"
                  >
                    <AnalysisThoughtsPanel
                      thoughts={filterThoughtsForLeftPanel(
                        snapshot.analysis.thoughts,
                        snapshot.analysis.debate?.messages ?? []
                      )}
                      agentStatuses={DONE_STATUSES}
                      agents={snapshot.analysis.agents}
                      onViewReport={setReportDialogAgent}
                      readOnly
                      className="h-full min-h-0"
                    />
                  </TabsContent>

                  <TabsContent
                    value="report"
                    className="flex-1 min-h-0 m-0 flex flex-col overflow-hidden data-[state=inactive]:hidden"
                  >
                    <div className="flex justify-end px-4 py-2 shrink-0">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={handleExportHistoryPdf}
                      >
                        导出该版 PDF
                      </Button>
                    </div>
                    <div className="flex-1 min-h-0 overflow-hidden">
                      <ReportViewer
                        reportData={snapshot.report}
                        agents={snapshot.analysis.agents}
                        companyName={companyName}
                        ticker={ticker}
                        embedded
                        showActions={false}
                      />
                    </div>
                  </TabsContent>
                </Tabs>
              ) : (
                <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                  加载中...
                </div>
              )}
            </div>
          </div>
        )}
      </DialogContent>

      <AgentReportDialog
        open={reportDialogAgent != null}
        onOpenChange={(open) => {
          if (!open) setReportDialogAgent(null);
        }}
        agentId={reportDialogAgent}
        reportMarkdown={
          reportDialogAgent
            ? snapshot?.analysis.agents?.[reportDialogAgent]?.reportMarkdown
            : undefined
        }
      />
    </Dialog>
  );
}
