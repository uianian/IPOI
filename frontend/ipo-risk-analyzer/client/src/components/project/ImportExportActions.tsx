/**
 * ImportExportActions — 项目包导入/导出
 */
import { useRef, useState } from "react";
import { Download, Upload, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  exportProjectsToDestination,
  importProjectBundle,
} from "@/data/projectStore";
import {
  isDirectoryExportSupported,
  pickExportDirectory,
} from "@/lib/exportToFolder";
import { getProjectDisplayName } from "@/data/projects";
import type { Project } from "@/types";
import { toast } from "sonner";

interface ImportExportActionsProps {
  projects: Project[];
  selectedProjectIds: string[];
  onImported: () => void;
}

export default function ImportExportActions({
  projects,
  selectedProjectIds,
  onImported,
}: ImportExportActionsProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    if (selectedProjectIds.length === 0) {
      toast.info("请先勾选要导出的项目");
      return;
    }

    const selected = projects.filter((p) => selectedProjectIds.includes(p.id));
    if (selected.length === 0) {
      toast.info("所选项目不存在或已被删除");
      return;
    }

    setExporting(true);
    try {
      let dirHandle: FileSystemDirectoryHandle | null = null;
      let dirName: string | undefined;

      if (isDirectoryExportSupported()) {
        dirHandle = await pickExportDirectory();
        if (!dirHandle) return;
        dirName = dirHandle.name;
      }

      const { count, mode } = await exportProjectsToDestination(
        selected,
        dirHandle
      );

      if (mode === "directory" && dirName) {
        toast.success(`已导出 ${count} 个项目到文件夹「${dirName}」`);
      } else if (mode === "download") {
        toast.success(`已导出 ${count} 个项目`);
        if (!isDirectoryExportSupported()) {
          toast.info("当前浏览器不支持选择文件夹，已使用默认下载目录");
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "导出失败");
    } finally {
      setExporting(false);
    }
  };

  const handleImportClick = () => inputRef.current?.click();

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    try {
      const project = await importProjectBundle(file, () => "overwrite");
      if (project) {
        toast.success(`项目 "${getProjectDisplayName(project)}" 已导入`);
        onImported();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "导入失败");
    }
  };

  const selectedCount = selectedProjectIds.length;

  return (
    <div className="flex items-center gap-2">
      <input
        ref={inputRef}
        type="file"
        accept=".zip,.ipo-project.zip"
        className="hidden"
        onChange={handleFile}
      />
      <Button
        variant="outline"
        size="sm"
        className="h-9 text-xs gap-1.5"
        onClick={handleImportClick}
      >
        <Upload className="w-3.5 h-3.5" />
        导入项目
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="h-9 text-xs gap-1.5"
        onClick={handleExport}
        disabled={projects.length === 0 || selectedCount === 0 || exporting}
      >
        {exporting ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Download className="w-3.5 h-3.5" />
        )}
        导出项目{selectedCount > 0 ? ` (${selectedCount})` : ""}
      </Button>
    </div>
  );
}
