/**
 * FileDropZone — Drag-and-drop PDF upload zone
 * Extracted from UploadPage.tsx
 */
import { useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, FileText, X, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface FileDropZoneProps {
  file: File | null;
  onFileSelect: (file: File) => void;
  onFileRemove: () => void;
  disabled?: boolean;
}

export default function FileDropZone({
  file,
  onFileSelect,
  onFileRemove,
  disabled = false,
}: FileDropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (f: File) => {
      if (f.type !== "application/pdf") {
        toast.error("仅支持PDF格式的招股书文件");
        return;
      }
      if (f.size > 500 * 1024 * 1024) {
        toast.error("文件大小不能超过500MB");
        return;
      }
      onFileSelect(f);
    },
    [onFileSelect]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={() => !file && !disabled && inputRef.current?.click()}
      className={cn(
        "relative rounded-lg border-2 border-dashed transition-all duration-300 overflow-hidden min-w-0",
        !file && !disabled && "cursor-pointer",
        isDragging
          ? "border-primary bg-accent/50"
          : file
          ? "border-[oklch(0.72_0.15_145)] bg-[oklch(0.72_0.15_145)/0.05]"
          : "border-border hover:border-primary/50 hover:bg-accent/20"
      )}
      style={
        isDragging
          ? { boxShadow: "0 0 30px oklch(0.75 0.18 195 / 0.3)" }
          : file
          ? { boxShadow: "0 0 20px oklch(0.72 0.15 145 / 0.2)" }
          : {}
      }
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={handleInputChange}
        disabled={disabled}
      />

      <AnimatePresence mode="wait">
        {!file ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center justify-center py-12 px-6 text-center"
          >
            <div
              className="w-14 h-14 rounded-xl bg-accent flex items-center justify-center mb-4"
              style={{
                boxShadow: isDragging
                  ? "0 0 30px oklch(0.75 0.18 195 / 0.5)"
                  : "0 0 15px oklch(0.75 0.18 195 / 0.2)",
              }}
            >
              <Upload
                className={cn(
                  "w-6 h-6 transition-colors",
                  isDragging ? "text-primary" : "text-muted-foreground"
                )}
              />
            </div>
            <p className="text-sm font-medium text-foreground mb-1">
              {isDragging ? "释放以上传文件" : "拖拽招股书PDF至此处"}
            </p>
            <p className="text-xs text-muted-foreground mb-3">
              或点击选择文件 · 支持PDF格式 · 最大500MB
            </p>
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace]">
              <span className="px-2 py-0.5 rounded bg-secondary border border-border">
                PDF
              </span>
              <span>招股书 / Prospectus</span>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="file"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-4 p-4 overflow-hidden w-full"
          >
            <div className="w-11 h-11 rounded-lg bg-[oklch(0.72_0.15_145)/0.15] border border-[oklch(0.72_0.15_145)/0.4] flex items-center justify-center flex-shrink-0">
              <FileText className="w-5 h-5 text-[oklch(0.72_0.15_145)]" />
            </div>
            <div className="flex-1 min-w-0 overflow-hidden">
              <p className="text-sm font-medium text-foreground truncate">
                {file.name}
              </p>
              <p className="text-xs text-muted-foreground font-['JetBrains_Mono',monospace]">
                {formatFileSize(file.size)} · PDF · 已就绪
              </p>
              <div className="flex items-center gap-1.5 mt-1">
                <CheckCircle2 className="w-3 h-3 text-[oklch(0.72_0.15_145)]" />
                <span className="text-[10px] text-[oklch(0.72_0.15_145)] font-['JetBrains_Mono',monospace]">
                  FILE VALIDATED
                </span>
              </div>
            </div>
            {!disabled && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (inputRef.current) inputRef.current.value = "";
                  onFileRemove();
                }}
                className="p-1.5 rounded-md hover:bg-secondary transition-colors flex-shrink-0"
              >
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
