/**
 * AnalysisThoughtsPanel — Agent 思考过程面板（可复用于主分析页与历史版本只读查看）
 */
import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Scale,
  TrendingUp,
  Globe,
  ShieldAlert,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Clock,
  Loader2,
  AlertTriangle,
  Lightbulb,
  Wrench,
  FileText,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { AGENTS } from "@/data/agentDefinitions";
import {
  getAgentSummaryLabel,
  mergeReasoningText,
  splitAgentThoughtsForSummary,
  getFindingTitle,
  toToolTraceDisplayItems,
} from "@/lib/thoughtDisplay";
import ThoughtEvidenceList from "@/components/analysis/ThoughtEvidenceList";
import ToolTraceList from "@/components/analysis/ToolTraceList";
import type { AgentId, AgentOutput, AgentStatus, Thought, ThoughtType } from "@/types";
import {
  getAgentReportMarkdown,
  isSpecialistAgent,
} from "@/lib/analysisHelpers";

const ICON_MAP: Record<string, LucideIcon> = {
  Scale,
  TrendingUp,
  Globe,
  ShieldAlert,
};

const THOUGHT_TYPE_META: Record<
  ThoughtType,
  {
    label: string;
    Icon: LucideIcon;
    iconClass: string;
    badgeClass: string;
    contentClass: string;
  }
> = {
  thinking: {
    label: "思考",
    Icon: Lightbulb,
    iconClass: "text-muted-foreground/70",
    badgeClass: "bg-muted/80 text-muted-foreground border-border/60",
    contentClass: "text-muted-foreground italic",
  },
  finding: {
    label: "发现",
    Icon: AlertTriangle,
    iconClass: "text-[oklch(0.72_0.18_55)]",
    badgeClass:
      "bg-[oklch(0.72_0.18_55)/0.12] text-[oklch(0.72_0.18_55)] border-[oklch(0.72_0.18_55)/0.25]",
    contentClass: "text-foreground",
  },
  conclusion: {
    label: "结论",
    Icon: CheckCircle2,
    iconClass: "text-[oklch(0.72_0.15_145)]",
    badgeClass:
      "bg-[oklch(0.72_0.15_145)/0.12] text-[oklch(0.72_0.15_145)] border-[oklch(0.72_0.15_145)/0.25]",
    contentClass: "text-[oklch(0.72_0.15_145)] font-medium",
  },
};

function getStatusIcon(status: AgentStatus) {
  switch (status) {
    case "running":
      return <Loader2 className="w-3.5 h-3.5 animate-spin" />;
    case "done":
      return <CheckCircle2 className="w-3.5 h-3.5" />;
    case "waiting":
      return <Clock className="w-3.5 h-3.5" />;
    default:
      return (
        <div className="w-3.5 h-3.5 rounded-full border border-current opacity-30" />
      );
  }
}

export interface AnalysisThoughtsPanelProps {
  thoughts: Thought[];
  agentStatuses: Record<AgentId, AgentStatus>;
  agents?: Partial<Record<AgentId, AgentOutput>>;
  onViewReport?: (agentId: AgentId) => void;
  readOnly?: boolean;
  scrollOnUpdate?: boolean;
  footer?: React.ReactNode;
  className?: string;
}

export default function AnalysisThoughtsPanel({
  thoughts,
  agentStatuses,
  agents,
  onViewReport,
  readOnly = false,
  scrollOnUpdate = false,
  footer,
  className,
}: AnalysisThoughtsPanelProps) {
  const [expandedAgents, setExpandedAgents] = useState<Set<AgentId>>(
    new Set<AgentId>(["legal", "financial", "market", "orchestrator"])
  );
  const [expandedReasoning, setExpandedReasoning] = useState<Set<AgentId>>(
    new Set()
  );
  const [expandedToolTrace, setExpandedToolTrace] = useState<Set<AgentId>>(
    new Set()
  );
  const thoughtsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollOnUpdate) {
      thoughtsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [thoughts, scrollOnUpdate]);

  const toggleAgent = (agentId: AgentId) => {
    setExpandedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) next.delete(agentId);
      else next.add(agentId);
      return next;
    });
  };

  const toggleReasoning = (agentId: AgentId) => {
    setExpandedReasoning((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) next.delete(agentId);
      else next.add(agentId);
      return next;
    });
  };

  const toggleToolTrace = (agentId: AgentId) => {
    setExpandedToolTrace((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) next.delete(agentId);
      else next.add(agentId);
      return next;
    });
  };

  const thoughtsByAgent = thoughts.reduce<Record<string, Thought[]>>(
    (acc, t) => {
      if (!acc[t.agentId]) acc[t.agentId] = [];
      acc[t.agentId].push(t);
      return acc;
    },
    {}
  );

  return (
    <div className={cn("flex flex-col flex-1 min-h-0 min-w-0", className)}>
      <ScrollArea className="flex-1 min-h-0">
      <div className="p-3 space-y-2">
        {AGENTS.map((agent) => {
          const status = agentStatuses[agent.id];
          const agentThoughts = thoughtsByAgent[agent.id] || [];
          const { findings, conclusions, reasoning, toolTraces } =
            splitAgentThoughtsForSummary(agentThoughts);
          const summaryLabel = getAgentSummaryLabel(agentThoughts);
          const hasSummary =
            findings.length > 0 ||
            conclusions.length > 0 ||
            reasoning.length > 0 ||
            toolTraces.length > 0;
          const isExpanded = expandedAgents.has(agent.id);
          const isReasoningOpen = expandedReasoning.has(agent.id);
          const isToolTraceOpen = expandedToolTrace.has(agent.id);
          const Icon = ICON_MAP[agent.icon];
          const lastThought = agentThoughts.at(-1);
          const showProcessing =
            status === "running" && lastThought?.type !== "conclusion";
          const reasoningText = mergeReasoningText(reasoning);
          const toolTraceItems = toToolTraceDisplayItems(toolTraces);
          const reportMarkdown = getAgentReportMarkdown(agents, agent.id);
          const showReportBtn =
            isSpecialistAgent(agent.id) &&
            status === "done" &&
            !!reportMarkdown &&
            !!onViewReport;

          return (
            <motion.div
              key={agent.id}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn(
                "rounded-lg border overflow-hidden transition-all duration-300",
                status === "running"
                  ? agent.borderClass
                  : status === "done"
                  ? "border-border"
                  : "border-border/50"
              )}
              style={
                status === "running"
                  ? { boxShadow: `0 0 15px ${agent.color}30` }
                  : {}
              }
            >
              <div
                className={cn(
                  "w-full flex items-center gap-2 px-4 py-3",
                  status === "running" ? agent.bgClass : ""
                )}
              >
                <button
                  type="button"
                  onClick={() => toggleAgent(agent.id)}
                  className={cn(
                    "flex flex-1 min-w-0 items-center gap-3 text-left transition-colors",
                    status !== "running" && "hover:opacity-90",
                    readOnly && "cursor-default"
                  )}
                >
                <div
                  className={cn(
                    "w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0",
                    agent.bgClass,
                    "border",
                    agent.borderClass
                  )}
                >
                  {Icon && (
                    <Icon className={cn("w-3.5 h-3.5", agent.colorClass)} />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-foreground truncate">
                      {agent.name}
                    </span>
                    {status === "running" && (
                      <span
                        className="text-[10px] font-['JetBrains_Mono',monospace] agent-active"
                        style={{ color: agent.color }}
                      >
                        ACTIVE
                      </span>
                    )}
                    {status === "done" && (
                      <span className="text-[10px] font-['JetBrains_Mono',monospace] text-[oklch(0.72_0.15_145)]">
                        DONE
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] truncate">
                    {summaryLabel ?? agent.nameEn}
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <span style={{ color: agent.color }}>
                    {getStatusIcon(status)}
                  </span>
                  {isExpanded ? (
                    <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                  )}
                </div>
                </button>

                {showReportBtn && (
                  <button
                    type="button"
                    onClick={() => onViewReport!(agent.id)}
                    className={cn(
                      "flex-shrink-0 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-medium transition-colors",
                      agent.borderClass,
                      agent.bgClass,
                      agent.colorClass,
                      "hover:opacity-90"
                    )}
                  >
                    <FileText className="w-3 h-3" />
                    查看报告
                  </button>
                )}
              </div>

              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-3 space-y-3 border-t border-border/50">
                      {!hasSummary ? (
                        <div className="py-3 text-center text-[11px] text-muted-foreground">
                          {status === "idle" ? "等待启动..." : "分析中..."}
                        </div>
                      ) : (
                        <>
                          {findings.map((thought, i) => {
                            const meta = THOUGHT_TYPE_META.finding;
                            const TypeIcon = meta.Icon;

                            return (
                              <motion.div
                                key={thought.id}
                                initial={{ opacity: 0, x: -5 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ duration: 0.3, delay: i * 0.05 }}
                                className="flex gap-2 pt-2"
                              >
                                <div className="flex-shrink-0 mt-0.5">
                                  <TypeIcon
                                    className={cn("w-3 h-3", meta.iconClass)}
                                  />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <span
                                    className={cn(
                                      "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium mb-1",
                                      meta.badgeClass
                                    )}
                                  >
                                    {meta.label}
                                  </span>
                                  <p
                                    className={cn(
                                      "text-[11px] leading-relaxed font-medium",
                                      meta.contentClass
                                    )}
                                  >
                                    {getFindingTitle(thought)}
                                  </p>
                                  <ThoughtEvidenceList thought={thought} />
                                </div>
                              </motion.div>
                            );
                          })}

                          {conclusions.map((thought, i) => {
                            const meta = THOUGHT_TYPE_META.conclusion;
                            const TypeIcon = meta.Icon;

                            return (
                              <motion.div
                                key={thought.id}
                                initial={{ opacity: 0, x: -5 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{
                                  duration: 0.3,
                                  delay: (findings.length + i) * 0.05,
                                }}
                                className="flex gap-2 pt-2 mt-1"
                              >
                                <div className="flex-shrink-0 mt-0.5">
                                  <TypeIcon
                                    className={cn("w-3 h-3", meta.iconClass)}
                                  />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <span
                                    className={cn(
                                      "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium mb-1",
                                      meta.badgeClass
                                    )}
                                  >
                                    {meta.label}
                                  </span>
                                  <p
                                    className={cn(
                                      "text-[11px] leading-relaxed",
                                      meta.contentClass
                                    )}
                                  >
                                    {thought.content}
                                  </p>
                                  <ThoughtEvidenceList thought={thought} />
                                </div>
                              </motion.div>
                            );
                          })}

                          {reasoning.length > 0 && (
                            <div className="pt-2 border-t border-border/40">
                              <button
                                type="button"
                                onClick={() => toggleReasoning(agent.id)}
                                className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground transition-colors w-full text-left"
                              >
                                {isReasoningOpen ? (
                                  <ChevronDown className="w-3 h-3" />
                                ) : (
                                  <ChevronRight className="w-3 h-3" />
                                )}
                                <Lightbulb className="w-3 h-3" />
                                <span>推理过程（{reasoning.length} 条）</span>
                              </button>
                              <AnimatePresence>
                                {isReasoningOpen && reasoningText && (
                                  <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: "auto", opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    className="overflow-hidden"
                                  >
                                    <p className="text-[11px] text-muted-foreground italic leading-relaxed whitespace-pre-line mt-2 pl-5">
                                      {reasoningText}
                                    </p>
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                          )}

                          {toolTraces.length > 0 && (
                            <div className="pt-2 border-t border-border/40">
                              <button
                                type="button"
                                onClick={() => toggleToolTrace(agent.id)}
                                className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground transition-colors w-full text-left"
                              >
                                {isToolTraceOpen ? (
                                  <ChevronDown className="w-3 h-3" />
                                ) : (
                                  <ChevronRight className="w-3 h-3" />
                                )}
                                <Wrench className="w-3 h-3" />
                                <span>工具调用（{toolTraces.length} 条）</span>
                              </button>
                              <AnimatePresence>
                                {isToolTraceOpen && (
                                  <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: "auto", opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    className="overflow-hidden"
                                  >
                                    <ToolTraceList items={toolTraceItems} />
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                          )}
                        </>
                      )}

                      {showProcessing && (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="flex items-center gap-2 pt-2"
                        >
                          <div className="flex gap-1">
                            {[0, 1, 2].map((idx) => (
                              <motion.div
                                key={idx}
                                className="w-1 h-1 rounded-full"
                                style={{ background: agent.color }}
                                animate={{ opacity: [0.3, 1, 0.3] }}
                                transition={{
                                  duration: 1,
                                  repeat: Infinity,
                                  delay: idx * 0.2,
                                }}
                              />
                            ))}
                          </div>
                          <span className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace]">
                            PROCESSING...
                          </span>
                        </motion.div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
        <div ref={thoughtsEndRef} />
      </div>
      {footer}
      </ScrollArea>
    </div>
  );
}
