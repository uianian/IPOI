/**
 * AgentDebatePanel — 专家模式只读四 Agent 辩论面板
 */
import { useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Scale,
  TrendingUp,
  Globe,
  ShieldAlert,
  MessageSquare,
  Loader2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { AGENTS } from "@/data/agentDefinitions";
import { DEBATE_TYPE_LABELS } from "@/lib/analysisHelpers";
import ParseMarkdownContent from "@/components/parse/ParseMarkdownContent";
import type { AgentId, AnalysisPhase, DebateMessage } from "@/types";

const ICON_MAP: Record<string, LucideIcon> = {
  Scale,
  TrendingUp,
  Globe,
  ShieldAlert,
};

interface AgentDebatePanelProps {
  messages: DebateMessage[];
  phase?: AnalysisPhase;
  isLive?: boolean;
  phaseMessage?: string;
}

export default function AgentDebatePanel({
  messages,
  phase,
  isLive = false,
  phaseMessage,
}: AgentDebatePanelProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const agentMap = Object.fromEntries(AGENTS.map((a) => [a.id, a]));

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLive, phase]);

  const showWaiting =
    isLive && phase !== "debate" && phase !== "report" && messages.length === 0;
  const showDebateLoading = isLive && phase === "debate" && messages.length === 0;
  const showNoDebate =
    messages.length === 0 &&
    !showWaiting &&
    !showDebateLoading &&
    (phase === "report" || (!isLive && phase != null));

  return (
    <div className="flex h-full min-h-0 flex-col bg-background/50">
      <div className="px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">
            专家辩论
          </span>
          {phase === "debate" && isLive && (
            <span className="text-[10px] font-['JetBrains_Mono',monospace] text-[oklch(0.72_0.18_55)] animate-pulse">
              LIVE
            </span>
          )}
        </div>
        <p className="text-[10px] text-muted-foreground mt-0.5">
          {phaseMessage ??
            (phase === "debate"
              ? "四位 Agent 正在就风险分歧进行辩论（只读）"
              : phase === "report"
              ? showNoDebate
                ? "总控已判定无需辩论"
                : "辩论已结束，正在生成综合报告"
              : "完成三 Agent 初评后将进入辩论环节")}
        </p>
      </div>

      <ScrollArea className="min-h-0 flex-1 p-4">
        <div className="space-y-3">
          {showWaiting && (
            <div className="py-8 text-center text-[11px] text-muted-foreground">
              等待 Agent 初评完成…
            </div>
          )}

          {showDebateLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-[11px] text-muted-foreground">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              辩论即将开始…
            </div>
          )}

          {showNoDebate && (
            <div className="py-8 text-center text-[11px] text-muted-foreground">
              总控Agent认为无需辩论
            </div>
          )}

          <AnimatePresence>
            {messages.map((msg) => {
              const agent = agentMap[msg.agentId as AgentId];
              const Icon = agent ? ICON_MAP[agent.icon] : MessageSquare;
              const targetAgent =
                msg.targetAgentId != null
                  ? agentMap[msg.targetAgentId]
                  : undefined;

              return (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex gap-2.5"
                >
                  <div
                    className={cn(
                      "w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 border",
                      agent?.bgClass,
                      agent?.borderClass
                    )}
                  >
                    {Icon && (
                      <Icon className={cn("w-3.5 h-3.5", agent?.colorClass)} />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5 mb-1">
                      <span className="text-[11px] font-semibold text-foreground">
                        {agent?.name ?? msg.agentId}
                      </span>
                      <span className="text-[9px] text-muted-foreground font-['JetBrains_Mono',monospace]">
                        第 {msg.round} 轮 · {DEBATE_TYPE_LABELS[msg.type]}
                      </span>
                      {targetAgent && (
                        <span className="text-[9px] text-muted-foreground">
                          → {targetAgent.name}
                        </span>
                      )}
                    </div>
                    <div
                      className={cn(
                        "rounded-lg px-3 py-2 border panel-glass",
                        agent?.borderClass
                      )}
                    >
                      <ParseMarkdownContent
                        content={msg.content}
                        className="text-[11px] [&_.prose]:text-[11px]"
                      />
                      <p className="text-[9px] text-muted-foreground font-['JetBrains_Mono',monospace] mt-2">
                        {new Date(msg.timestamp).toLocaleTimeString("zh-HK")}
                      </p>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>

          {isLive && phase === "debate" && messages.length > 0 && (
            <div className="flex gap-2.5 py-1">
              <div className="w-7 h-7 rounded-md bg-muted/50 border border-border flex items-center justify-center">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
              </div>
              <div className="panel-glass rounded-lg px-3 py-2 text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace]">
                辩论进行中…
              </div>
            </div>
          )}

          <div ref={endRef} />
        </div>
      </ScrollArea>
    </div>
  );
}
