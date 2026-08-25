/**
 * AgentReportDialog — 展示单 Agent Markdown 专项报告
 */
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import ParseMarkdownContent from "@/components/parse/ParseMarkdownContent";
import { AGENTS } from "@/data/agentDefinitions";
import type { AgentId } from "@/types";

interface AgentReportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId: AgentId | null;
  reportMarkdown?: string;
}

export default function AgentReportDialog({
  open,
  onOpenChange,
  agentId,
  reportMarkdown,
}: AgentReportDialogProps) {
  const agent = agentId ? AGENTS.find((a) => a.id === agentId) : undefined;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex h-[min(92vh,920px)] w-[min(96vw,72rem)] max-w-[min(96vw,72rem)] sm:max-w-[min(96vw,72rem)] flex-col gap-0 p-0"
      >
        <DialogHeader className="shrink-0 border-b border-border px-6 py-4">
          <DialogTitle className="text-base">
            {agent?.name ?? "Agent"} · 专项报告
          </DialogTitle>
          <p className="text-[11px] text-muted-foreground font-normal mt-1">
            宽表格与代码块可横向滚动查看
          </p>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-auto px-6 py-4">
          {reportMarkdown ? (
            <ParseMarkdownContent
              content={reportMarkdown}
              className="agent-report-markdown text-sm"
            />
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">
              暂无报告内容
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
