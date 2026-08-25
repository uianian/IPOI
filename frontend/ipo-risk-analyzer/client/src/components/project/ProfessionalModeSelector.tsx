/**
 * ProfessionalModeSelector — 是否启用专业模式（文本粉饰度纳入评分）
 */
import { Sparkles, Gauge } from "lucide-react";
import { cn } from "@/lib/utils";

interface ProfessionalModeSelectorProps {
  value: boolean;
  onChange: (enableEmbellishment: boolean) => void;
  disabled?: boolean;
}

const OPTIONS: {
  value: boolean;
  title: string;
  desc: string;
  icon: typeof Sparkles;
}[] = [
  {
    value: false,
    title: "标准模式",
    desc: "不纳入文本粉饰度评分，Token 消耗较低",
    icon: Gauge,
  },
  {
    value: true,
    title: "专业模式",
    desc: "评分将纳入文本粉饰度分析；会消耗更多 Token，产生更高费用",
    icon: Sparkles,
  },
];

export default function ProfessionalModeSelector({
  value,
  onChange,
  disabled,
}: ProfessionalModeSelectorProps) {
  return (
    <div className="space-y-2">
      <div className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-widest">
        ANALYSIS MODE
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
