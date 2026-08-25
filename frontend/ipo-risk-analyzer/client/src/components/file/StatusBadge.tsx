import { cn } from "@/lib/utils";
import type { ProjectStatus } from "@/types";
import { STATUS_LABELS, STATUS_COLORS } from "@/types";

interface StatusBadgeProps {
  status: ProjectStatus;
  className?: string;
}

export default function StatusBadge({ status, className }: StatusBadgeProps) {
  const label = STATUS_LABELS[status];
  const color = STATUS_COLORS[status];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[10px] font-bold font-['JetBrains_Mono',monospace] px-2 py-1 rounded tracking-wider flex-shrink-0",
        className
      )}
      style={{
        color,
        background: `${color}15`,
        border: `1px solid ${color}40`,
      }}
    >
      {/* Pulsing dot for active statuses */}
      {status !== "completed" && (
        <span
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{
            background: color,
            animation:
              status === "uploading" || status === "parsing"
                ? "agent-active 1.5s ease-in-out infinite"
                : "none",
          }}
        />
      )}
      {status === "completed" && (
        <span
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ background: color }}
        />
      )}
      {label}
    </span>
  );
}
