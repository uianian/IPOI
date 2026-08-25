/**
 * ToolTraceList — Agent 工具调用 trace 时间线
 */
import { cn } from "@/lib/utils";
import type { ToolTraceDisplayItem } from "@/lib/thoughtDisplay";

interface ToolTraceListProps {
  items: ToolTraceDisplayItem[];
  className?: string;
}

function statusClass(status?: string): string {
  if (status === "ok") return "text-[oklch(0.72_0.15_145)]";
  if (status === "error") return "text-[oklch(0.65_0.22_25)]";
  if (status === "running") return "text-primary";
  return "text-muted-foreground";
}

export default function ToolTraceList({ items, className }: ToolTraceListProps) {
  if (!items.length) return null;

  return (
    <ul className={cn("space-y-1.5 mt-2 pl-5", className)}>
      {items.map((item) => (
        <li
          key={item.id}
          className="text-[10px] font-['JetBrains_Mono',monospace] leading-relaxed border-l-2 border-border/60 pl-2.5 py-0.5"
        >
          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
            {item.toolName && (
              <span className="text-foreground font-semibold">
                {item.toolName}
              </span>
            )}
            <span className="text-muted-foreground/80">
              {item.kind === "tool_call" ? "call" : item.kind === "tool_result" ? "result" : item.kind}
            </span>
            {item.status && (
              <span className={cn("uppercase", statusClass(item.status))}>
                {item.status}
              </span>
            )}
            {item.durationMs != null && (
              <span className="text-muted-foreground">{item.durationMs}ms</span>
            )}
          </div>
          {item.content && (
            <p className="text-[10px] text-muted-foreground mt-0.5 font-sans">
              {item.content}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
