/**
 * ReportPage — 风险报告页（展示最新一次分析的报告）
 */
import { useState, useEffect } from "react";
import { useParams } from "wouter";
import { History } from "lucide-react";
import { Button } from "@/components/ui/button";
import ReportViewer from "@/components/report/ReportViewer";
import AnalysisHistoryDialog from "@/components/analysis/AnalysisHistoryDialog";
import type { ReportData } from "@/data/reportData";
import type { AgentId, AgentOutput } from "@/types";
import { getProjectById, getProjectDisplayName } from "@/data/projects";
import {
  getReport,
  getReportPdf,
  getAnalysis,
  saveReport,
  downloadBlob,
  listAnalysisHistory,
} from "@/data/projectStore";
import { fetchReport, fetchReportExport } from "@/services/analysisService";
import { toast } from "sonner";

type LoadState = "loading" | "ready" | "empty";

export default function ReportPage() {
  const { id } = useParams();
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [agents, setAgents] = useState<
    Partial<Record<AgentId, AgentOutput>> | undefined
  >();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyCount, setHistoryCount] = useState(0);
  const [analysisId, setAnalysisId] = useState<string | undefined>();

  const project = id ? getProjectById(id) : undefined;
  const ticker = project?.ticker;
  const companyName = project ? getProjectDisplayName(project) : undefined;

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    (async () => {
      setLoadState("loading");
      const analysis = await getAnalysis(id);
      const aid = analysis?.analysisId;
      if (!cancelled) {
        setAnalysisId(aid);
        setAgents(analysis?.agents);
      }

      const cached = await getReport(id);
      if (cached) {
        if (!cancelled) {
          setReportData(cached);
          setLoadState("ready");
        }
        return;
      }

      const remote = await fetchReport(id, aid);
      if (remote) {
        if (!cancelled) {
          setReportData(remote);
          setLoadState("ready");
          await saveReport(id, remote);
        }
        return;
      }

      if (!cancelled) {
        setReportData(null);
        setLoadState("empty");
      }
    })();

    listAnalysisHistory(id).then((list) => {
      if (!cancelled) setHistoryCount(list.length);
    });

    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleExport = async () => {
    if (!id) return;

    const cachedPdf = await getReportPdf(id);
    if (cachedPdf) {
      const date = new Date().toISOString().slice(0, 10);
      downloadBlob(cachedPdf, `IPO风险报告_${ticker ?? id}_${date}.pdf`);
      toast.success("报告已下载");
      return;
    }

    const exported = await fetchReportExport(id, analysisId);
    if (exported) {
      await saveReport(id, reportData!, exported.blob);
      downloadBlob(exported.blob, exported.filename);
      toast.success("报告已下载");
      return;
    }

    toast.info("报告 PDF 尚未生成，请等待分析完成");
  };

  if (loadState === "loading") {
    return (
      <div className="h-[calc(100vh-3rem)] flex items-center justify-center text-muted-foreground text-sm">
        加载报告中...
      </div>
    );
  }

  if (loadState === "empty" || !reportData) {
    return (
      <div className="h-[calc(100vh-3rem)] flex flex-col items-center justify-center text-muted-foreground text-sm gap-2">
        <p>暂无报告</p>
        <p className="text-xs">请先完成分析，或等待报告生成后再查看。</p>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-3rem)] flex flex-col overflow-hidden">
      {historyCount > 0 && id && (
        <div className="flex justify-end px-4 py-2 border-b border-border shrink-0">
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs gap-1.5"
            onClick={() => setHistoryOpen(true)}
          >
            <History className="w-3.5 h-3.5" />
            历史版本
          </Button>
        </div>
      )}
      <div className="flex-1 min-h-0">
        <ReportViewer
          reportData={reportData}
          agents={agents}
          companyName={companyName}
          ticker={ticker}
          onExport={handleExport}
        />
      </div>
      {id && (
        <AnalysisHistoryDialog
          projectId={id}
          open={historyOpen}
          onOpenChange={setHistoryOpen}
          defaultTab="report"
          ticker={ticker}
          companyName={companyName}
        />
      )}
    </div>
  );
}
