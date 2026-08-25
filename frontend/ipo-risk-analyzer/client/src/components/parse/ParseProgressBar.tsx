import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface ParseProgressBarProps {
  progress: number; // 0-100
  stage: string; // UPLOADING | PARSING | ANALYZING | READY
  className?: string;
}

const STAGE_LABELS: Record<string, string> = {
  UPLOADING: "正在上传PDF...",
  PARSING: "正在解析文档...",
  ANALYZING: "正在初始化Agent...",
  READY: "就绪",
};

export default function ParseProgressBar({
  progress,
  stage,
  className,
}: ParseProgressBarProps) {
  const label = STAGE_LABELS[stage] || stage;
  const isComplete = progress >= 100;

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {!isComplete && (
            <div className="w-2 h-2 rounded-full bg-primary agent-active" />
          )}
          <span className="text-sm font-medium text-foreground">
            {isComplete ? "解析完成" : label}
          </span>
        </div>
        <span className="text-[10px] text-primary font-['JetBrains_Mono',monospace]">
          {Math.round(progress)}%
        </span>
      </div>
      <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{
            background: isComplete
              ? "oklch(0.72 0.15 145)"
              : "linear-gradient(90deg, oklch(0.75 0.18 195), oklch(0.65 0.15 270))",
            boxShadow: isComplete
              ? "0 0 8px oklch(0.72 0.15 145 / 0.6)"
              : "0 0 8px oklch(0.75 0.18 195 / 0.6)",
          }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.3 }}
        />
      </div>
    </div>
  );
}
