/**
 * ThoughtEvidenceList — finding 按页分组的 PDF 证据摘录
 */
import { BookOpen, FileText } from "lucide-react";
import type { Thought } from "@/types";
import {
  collectEvidence,
  getFieldCodeLabel,
  groupEvidenceByPage,
} from "@/lib/thoughtDisplay";

interface ThoughtEvidenceListProps {
  thought: Thought;
  className?: string;
}

export default function ThoughtEvidenceList({
  thought,
  className,
}: ThoughtEvidenceListProps) {
  const groups = groupEvidenceByPage(collectEvidence(thought));

  if (!groups.length) {
    if (thought.ref) {
      return (
        <div className={className}>
          <div className="flex items-center gap-1 mt-1">
            <FileText className="w-2.5 h-2.5 text-primary/60" />
            <span className="text-[10px] text-primary/70 font-['JetBrains_Mono',monospace]">
              {thought.ref}
            </span>
          </div>
        </div>
      );
    }
    return null;
  }

  return (
    <div className={className}>
      <div className="flex items-center gap-2 mt-2 mb-2">
        <BookOpen className="w-3 h-3 text-primary" />
        <span className="text-[10px] font-semibold text-foreground">
          PDF 证据溯源
        </span>
      </div>
      <div className="space-y-2">
        {groups.map((group) => (
          <div
            key={group.page}
            className="rounded-lg border border-border/50 bg-secondary/50 p-2.5"
          >
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <div className="flex items-center gap-1">
                <FileText className="w-3 h-3 text-primary" />
                <span className="text-[10px] font-bold font-['JetBrains_Mono',monospace] text-primary">
                  P.{group.page}
                </span>
              </div>
              {group.sourceTypes.map((st) => (
                <span
                  key={st}
                  className="text-[9px] px-1 py-0.5 rounded bg-muted text-muted-foreground font-['JetBrains_Mono',monospace]"
                >
                  {st}
                </span>
              ))}
              {group.fieldCodes.map((fc) => (
                <span
                  key={fc}
                  className="text-[9px] px-1 py-0.5 rounded bg-primary/10 text-primary/80"
                >
                  {getFieldCodeLabel(fc) ?? fc}
                </span>
              ))}
            </div>
            <ul className="space-y-1.5">
              {group.excerpts.map((excerpt) => (
                <li
                  key={excerpt}
                  className="text-[11px] text-muted-foreground leading-relaxed"
                >
                  「{excerpt}」
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
