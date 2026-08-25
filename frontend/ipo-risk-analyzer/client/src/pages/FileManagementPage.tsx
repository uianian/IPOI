/**
 * FileManagementPage — Project list (standalone homepage)
 */
import { useState, useEffect, useCallback } from "react";
import { useLocation } from "wouter";
import { useActiveProject } from "@/contexts/ActiveProjectContext";
import { motion } from "framer-motion";
import { Plus, FolderOpen, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import ProjectTable from "@/components/project/ProjectTable";
import CreateProjectDialog from "@/components/project/CreateProjectDialog";
import SettingsDialog from "@/components/settings/SettingsDialog";
import ImportExportActions from "@/components/project/ImportExportActions";
import { getProjects, deleteProject, getProjectDisplayName } from "@/data/projects";
import { clearProjectState } from "@/data/projectState";
import { deleteProjectData, getReportPdf, downloadBlob } from "@/data/projectStore";
import type { Project } from "@/types";
import { toast } from "sonner";

export default function FileManagementPage() {
  const [, navigate] = useLocation();
  const { setActiveProjectId } = useActiveProject();
  const [projects, setProjects] = useState(() => getProjects());
  const [exportSelectedIds, setExportSelectedIds] = useState<Set<string>>(
    () => new Set()
  );
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const refreshProjects = () => setProjects(getProjects());

  useEffect(() => {
    setExportSelectedIds((prev) => {
      const valid = new Set(
        [...prev].filter((id) => projects.some((p) => p.id === id))
      );
      return valid.size === prev.size ? prev : valid;
    });
  }, [projects]);

  const toggleExportSelection = useCallback((projectId: string) => {
    setExportSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(projectId)) next.delete(projectId);
      else next.add(projectId);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setExportSelectedIds((prev) => {
      if (prev.size === projects.length) return new Set();
      return new Set(projects.map((p) => p.id));
    });
  }, [projects]);

  const handleView = (project: Project) => {
    setActiveProjectId(project.id);
    navigate(`/project/${project.id}`);
  };

  const handleDownload = async (project: Project) => {
    if (project.status === "completed" || project.status === "analyzing") {
      const pdf = await getReportPdf(project.id);
      if (pdf) {
        downloadBlob(pdf, `IPO风险报告_${project.ticker}.pdf`);
        toast.success("报告已下载");
        return;
      }
      setActiveProjectId(project.id);
      navigate(`/project/${project.id}/report`);
      toast.info("报告 PDF 尚未缓存，已跳转报告页");
    } else {
      toast.info("请等待分析完成后再下载报告");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    deleteProject(deleteTarget.id);
    clearProjectState(deleteTarget.id);
    await deleteProjectData(deleteTarget.id);
    setExportSelectedIds((prev) => {
      const next = new Set(prev);
      next.delete(deleteTarget.id);
      return next;
    });
    refreshProjects();
    toast.success(`项目 "${getProjectDisplayName(deleteTarget)}" 已删除`);
    setDeleteTarget(null);
  };

  return (
    <div className="min-h-full p-6">
      <div className="max-w-7xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex items-center justify-between mb-6"
        >
          <div>
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider mb-2">
              <span className="text-primary">PROJECTS</span>
              <span>/</span>
              <span>FILE MANAGEMENT</span>
            </div>
            <h1 className="text-2xl font-bold text-foreground">项目管理</h1>
            <p className="text-muted-foreground text-sm max-w-xl mt-1">
              勾选要导出的项目后点击「导出项目」，可选择保存文件夹并支持批量导出
            </p>
          </div>

          <div className="flex items-center gap-2">
            <ImportExportActions
              projects={projects}
              selectedProjectIds={[...exportSelectedIds]}
              onImported={refreshProjects}
            />
            <Button
              variant="outline"
              size="sm"
              className="h-10 gap-2"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings className="w-4 h-4" />
              设置
            </Button>
            <Button
              onClick={() => setCreateOpen(true)}
              className="h-10 text-sm font-semibold gap-2"
              style={{
                background: "oklch(0.75 0.18 195)",
                color: "oklch(0.10 0.012 240)",
                boxShadow: "0 0 20px oklch(0.75 0.18 195 / 0.4)",
              }}
            >
              <Plus className="w-4 h-4" />
              创建新项目
            </Button>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
        >
          <ProjectTable
            projects={projects}
            selectedProjectIds={exportSelectedIds}
            onToggleExportSelection={toggleExportSelection}
            onToggleSelectAll={toggleSelectAll}
            onView={handleView}
            onDownload={handleDownload}
            onDelete={(p) => setDeleteTarget(p)}
          />
        </motion.div>

        <div className="mt-4 flex items-center justify-between text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace]">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <FolderOpen className="w-3 h-3" />
              共 {projects.length} 个项目
            </span>
            <span>
              已完成: {projects.filter((p) => p.status === "completed").length}
            </span>
            <span>
              进行中:{" "}
              {projects.filter((p) => p.status !== "completed").length}
            </span>
          </div>
          <span>LOCAL CACHE · IndexedDB</span>
        </div>
      </div>

      <CreateProjectDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onProjectCreated={refreshProjects}
      />

      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />

      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base">确认删除</DialogTitle>
            <DialogDescription className="text-xs">
              将删除本地缓存中的项目及所有解析、分析、报告数据，无法恢复。
            </DialogDescription>
          </DialogHeader>
          {deleteTarget && (
            <div className="p-3 rounded-lg bg-secondary/50 border border-border text-sm text-foreground font-medium truncate">
              {getProjectDisplayName(deleteTarget)}
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeleteTarget(null)}
              className="h-8 text-xs"
            >
              取消
            </Button>
            <Button
              onClick={handleDeleteConfirm}
              size="sm"
              className="h-8 text-xs"
              variant="destructive"
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
