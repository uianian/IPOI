/**
 * BiotechSelector — 是否生物科技公司（必填二选一）
 */
import { Dna, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface BiotechSelectorProps {
  value: boolean | null;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}

const OPTIONS: {
  value: boolean;
  title: string;
  desc: string;
  icon: typeof Dna;
}[] = [
  {
    value: true,
    title: "是",
    desc: "生物科技类 IPO，Agent 分析将启用专项策略",
    icon: Dna,
  },
  {
    value: false,
    title: "否",
    desc: "非生物科技类企业",
    icon: Building2,
  },
];

export default function BiotechSelector({
  value,
  onChange,
  disabled,
}: BiotechSelectorProps) {
  return (
    <div className="space-y-2">
      <div className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-widest">
        BIOTECH COMPANY <span className="text-primary">*</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {OPTIONS.map(({ value: optValue, title, desc, icon: Icon }) => (
          <button
            key={String(optValue)}
            type="button"
            disabled={disabled}
            onClick={() => onChange(optValue)}
            className={cn(
              "text-left p-3 rounded-lg border transition-all",
              value === optValue
                ? "border-primary bg-primary/10 ring-1 ring-primary/30"
                : "border-border bg-secondary/30 hover:border-primary/40",
              disabled && "opacity-50 cursor-not-allowed"
            )}
          >
            <div className="flex items-center gap-2 mb-1">
              <Icon
                className={cn(
                  "w-4 h-4",
                  value === optValue ? "text-primary" : "text-muted-foreground"
                )}
              />
              <span className="text-sm font-medium text-foreground">{title}</span>
            </div>
            <p className="text-[10px] text-muted-foreground leading-relaxed">
              {desc}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}
