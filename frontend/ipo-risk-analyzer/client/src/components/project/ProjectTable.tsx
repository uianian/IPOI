/**
 * ProjectTable — Main project list table
 * Columns: File Name, Upload Time, Parse Complete Time, Status,
 *          Parse Progress, Actions
 */
import { motion } from "framer-motion";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { Checkbox } from "@/components/ui/checkbox";
import StatusBadge from "@/components/file/StatusBadge";
import ProjectActions from "./ProjectActions";
import { getProjectDisplayName } from "@/data/projects";
import type { Project } from "@/types";
import { STATUS_COLORS } from "@/types";

interface ProjectTableProps {
  projects: Project[];
  selectedProjectIds?: Set<string>;
  onToggleExportSelection?: (projectId: string) => void;
  onToggleSelectAll?: () => void;
  onView: (project: Project) => void;
  onDownload: (project: Project) => void;
  onDelete: (project: Project) => void;
  emptyMessage?: string;
}

export default function ProjectTable({
  projects,
  selectedProjectIds = new Set(),
  onToggleExportSelection,
  onToggleSelectAll,
  onView,
  onDownload,
  onDelete,
  emptyMessage = "暂无项目，点击右上角「创建新项目」开始",
}: ProjectTableProps) {
  // Empty state
  if (projects.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="panel-glass rounded-xl p-16 text-center"
      >
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-xl bg-accent mb-4">
          <svg
            className="w-8 h-8 text-muted-foreground"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </div>
        <p className="text-sm text-muted-foreground mb-1">{emptyMessage}</p>
        <p className="text-[10px] text-muted-foreground/60 font-['JetBrains_Mono',monospace]">
          NO PROJECTS FOUND
        </p>
      </motion.div>
    );
  }

  const formatDate = (isoStr?: string) => {
    if (!isoStr) return "—";
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString("zh-HK", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "—";
    }
  };

  const selectionEnabled = Boolean(onToggleExportSelection && onToggleSelectAll);
  const allSelected =
    selectionEnabled &&
    projects.length > 0 &&
    selectedProjectIds.size === projects.length;
  const someSelected =
    selectionEnabled &&
    selectedProjectIds.size > 0 &&
    selectedProjectIds.size < projects.length;

  const exportCheckboxClass =
    "size-4 border-2 border-[oklch(0.75_0.18_195/0.9)] bg-background/90 shadow-sm data-[state=checked]:bg-[oklch(0.75_0.18_195)] data-[state=checked]:border-[oklch(0.75_0.18_195)] data-[state=indeterminate]:bg-[oklch(0.75_0.18_195)] data-[state=indeterminate]:border-[oklch(0.75_0.18_195)]";

  return (
    <div className="panel-glass rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              {selectionEnabled && (
                <TableHead className="whitespace-nowrap w-12 text-center">
                  <div
                    className="flex justify-center"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Checkbox
                      className={exportCheckboxClass}
                      checked={
                        allSelected
                          ? true
                          : someSelected
                            ? "indeterminate"
                            : false
                      }
                      onCheckedChange={() => onToggleSelectAll?.()}
                      aria-label="全选导出项目"
                    />
                  </div>
                </TableHead>
              )}
              <TableHead className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider whitespace-nowrap">
                文件名
              </TableHead>
              <TableHead className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider whitespace-nowrap">
                上传时间
              </TableHead>
              <TableHead className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider whitespace-nowrap">
                解析完成时间
              </TableHead>
              <TableHead className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider whitespace-nowrap">
                状态
              </TableHead>
              <TableHead className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider whitespace-nowrap w-32">
                解析进度
              </TableHead>
              <TableHead className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider whitespace-nowrap text-right">
                操作
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {projects.map((project, i) => (
              <motion.tr
                key={project.id}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: i * 0.06 }}
                className="border-border hover:bg-secondary/40 transition-colors cursor-pointer"
                onClick={() => onView(project)}
              >
                {selectionEnabled && (
                  <TableCell
                    className="py-3 text-center"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Checkbox
                      className={exportCheckboxClass}
                      checked={selectedProjectIds.has(project.id)}
                      onCheckedChange={() =>
                        onToggleExportSelection?.(project.id)
                      }
                      aria-label={`选择 ${getProjectDisplayName(project)}`}
                    />
                  </TableCell>
                )}
                <TableCell className="py-3">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{
                        background: `${STATUS_COLORS[project.status]}15`,
                        border: `1px solid ${STATUS_COLORS[project.status]}30`,
                      }}
                    >
                      <span
                        className="text-[10px] font-bold font-['JetBrains_Mono',monospace]"
                        style={{ color: STATUS_COLORS[project.status] }}
                      >
                        {project.ticker.split(".")[0]}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground truncate max-w-48">
                        {getProjectDisplayName(project)}
                      </p>
                      <p className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] truncate max-w-48">
                        {project.projectName?.trim()
                          ? `${project.fileName} · ${project.ticker}`
                          : project.ticker}
                      </p>
                    </div>
                  </div>
                </TableCell>

                <TableCell className="py-3 text-xs text-muted-foreground font-['JetBrains_Mono',monospace] whitespace-nowrap">
                  {formatDate(project.uploadTime)}
                </TableCell>

                <TableCell className="py-3 text-xs text-muted-foreground font-['JetBrains_Mono',monospace] whitespace-nowrap">
                  {formatDate(project.parseCompleteTime)}
                </TableCell>

                <TableCell className="py-3">
                  <StatusBadge status={project.status} />
                </TableCell>

                <TableCell className="py-3">
                  <div className="flex items-center gap-2">
                    <Progress
                      value={project.parseProgress}
                      className="h-1.5 w-16 flex-shrink-0"
                    />
                    <span className="text-[10px] font-['JetBrains_Mono',monospace] text-muted-foreground flex-shrink-0">
                      {project.parseProgress}%
                    </span>
                  </div>
                </TableCell>

                <TableCell className="py-3 text-right">
                  <div
                    onClick={(e) => e.stopPropagation()}
                    className="inline-flex"
                  >
                    <ProjectActions
                      onView={() => onView(project)}
                      onDownload={() => onDownload(project)}
                      onDelete={() => onDelete(project)}
                      canDownload={
                        project.status === "completed" ||
                        project.status === "analyzing"
                      }
                    />
                  </div>
                </TableCell>
              </motion.tr>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
