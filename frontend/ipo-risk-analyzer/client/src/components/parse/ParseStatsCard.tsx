import {
  FileCheck,
  Image,
  Table2,
  FileText,
} from "lucide-react";
import type { ParseStats } from "@/types";

interface ParseStatsCardProps {
  stats: ParseStats;
}

export default function ParseStatsCard({ stats }: ParseStatsCardProps) {
  const successItems = [
    {
      icon: FileText,
      label: "总页数",
      value: `${stats.parsedPages} / ${stats.totalPages}`,
    },
    {
      icon: Image,
      label: "图表数量",
      value: `${stats.chartCount}`,
    },
    {
      icon: Table2,
      label: "表格数量",
      value: `${stats.tableCount}`,
    },
    {
      icon: FileCheck,
      label: "文本块",
      value: `${stats.textChunkCount}`,
    },
  ];

  return (
    <div className="panel-glass rounded-xl p-5 space-y-4 h-full">
      <div>
        <div className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-widest mb-3">
          PARSE STATISTICS
        </div>
        <div className="grid grid-cols-2 gap-2">
          {successItems.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.label}
                className="flex items-center gap-2 p-2 rounded-lg bg-[oklch(0.72_0.15_145)/0.06] border border-[oklch(0.72_0.15_145)/0.15]"
              >
                <Icon className="w-3 h-3 text-[oklch(0.72_0.15_145)] flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-[10px] text-muted-foreground">{item.label}</p>
                  <p className="text-xs font-bold font-['JetBrains_Mono',monospace] text-foreground">
                    {item.value}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
