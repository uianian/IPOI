import { Eye, Download, Trash2 } from "lucide-react";

interface ProjectActionsProps {
  onView: () => void;
  onDownload: () => void;
  onDelete: () => void;
  canDownload?: boolean;
}

export default function ProjectActions({
  onView,
  onDownload,
  onDelete,
  canDownload = false,
}: ProjectActionsProps) {
  return (
    <div className="flex items-center gap-1">
      {/* View */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onView();
        }}
        className="p-1.5 rounded hover:bg-accent hover:text-primary transition-colors"
        title="查看详情"
      >
        <Eye className="w-3.5 h-3.5" />
      </button>

      {/* Download report */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDownload();
        }}
        disabled={!canDownload}
        className={`p-1.5 rounded transition-colors ${
          canDownload
            ? "hover:bg-accent hover:text-primary"
            : "opacity-30 cursor-not-allowed"
        }`}
        title={canDownload ? "下载报告" : "分析尚未完成"}
      >
        <Download className="w-3.5 h-3.5" />
      </button>

      {/* Delete */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="p-1.5 rounded hover:bg-red-500/10 hover:text-destructive transition-colors"
        title="删除项目"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
