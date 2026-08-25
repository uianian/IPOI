/**
 * ReportViewer — IPO风险穿透预警报告（可嵌入页面或历史版本弹窗）
 */
import { useState, useEffect, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Download,
  Share2,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  BookOpen,
  MessageSquare,
  Gauge,
  Layers,
  Radar as RadarIcon,
  BarChart3,
  Clock,
  TrendingUp,
  ClipboardCheck,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  CartesianGrid,
} from "recharts";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import ParseMarkdownContent from "@/components/parse/ParseMarkdownContent";
import type { ReportData, HttpRiskLevel } from "@/data/reportData";
import {
  agentLabel,
  formatReportScore,
  formatReportScoreOneDecimal,
  formatReportScoreRaw,
  getEmbellishmentDisplay,
  getAgentDimensions,
  riskLevelColor,
  riskTagColor,
  riskTagLabel,
} from "@/data/reportData";
import { getAgentReportMarkdown } from "@/lib/analysisHelpers";
import { AGENT_ICON_MAP, getAgentDef } from "@/lib/agentVisual";
import type { AgentId, AgentOutput } from "@/types";

function AgentBadge({ agentId }: { agentId: string }) {
  const agent = getAgentDef(agentId);
  const Icon: LucideIcon | null = agent
    ? AGENT_ICON_MAP[agent.icon] ?? null
    : null;
  const color = agent?.color ?? "oklch(0.75 0.18 195)";

  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] font-['JetBrains_Mono',monospace] px-1.5 py-0.5 rounded"
      style={{
        background: `${color}15`,
        color,
        border: `1px solid ${color}40`,
      }}
    >
      {Icon && <Icon className="w-3 h-3 shrink-0" />}
      {agentLabel(agentId)}
    </span>
  );
}

function SectionTitle({
  icon: Icon,
  className,
  children,
}: {
  icon: LucideIcon;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex items-center gap-2 mb-4", className)}>
      <Icon className="w-3.5 h-3.5 text-primary shrink-0" />
      <div className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-widest">
        {children}
      </div>
    </div>
  );
}

function DebateHighlightItem({
  agentId,
  content,
}: {
  agentId?: string;
  content: string;
}) {
  const agent = getAgentDef(agentId);
  const Icon: LucideIcon | null = agent
    ? AGENT_ICON_MAP[agent.icon] ?? null
    : null;
  const color = agent?.color ?? "oklch(0.75 0.18 195)";

  return (
    <div
      className="flex gap-3 rounded-lg border border-border/50 bg-secondary/20 p-3"
      style={{ borderLeftWidth: 3, borderLeftColor: color }}
    >
      {Icon && (
        <div
          className="w-7 h-7 rounded-md flex items-center justify-center shrink-0"
          style={{ background: `${color}15`, border: `1px solid ${color}40` }}
        >
          <Icon className="w-3.5 h-3.5" style={{ color }} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        {agentId && (
          <div
            className="text-[10px] font-bold font-['JetBrains_Mono',monospace] mb-1"
            style={{ color }}
          >
            {agentLabel(agentId)}
          </div>
        )}
        <p className="text-xs text-muted-foreground leading-relaxed">{content}</p>
      </div>
    </div>
  );
}

function RiskScoreGauge({
  score,
  riskLabel,
  riskLevel,
}: {
  score: number;
  riskLabel: string;
  riskLevel: HttpRiskLevel | string;
}) {
  const formattedScore = formatReportScoreRaw(score);
  const [displayScore, setDisplayScore] = useState(formattedScore);
  const hasAnimatedRef = useRef(false);

  useEffect(() => {
    if (hasAnimatedRef.current) {
      setDisplayScore(formatReportScoreRaw(score));
      return;
    }

    let current = 0;
    const step = score / 60;
    const timer = setInterval(() => {
      current += step;
      if (current >= score) {
        setDisplayScore(formatReportScoreRaw(score));
        hasAnimatedRef.current = true;
        clearInterval(timer);
      } else {
        setDisplayScore(formatReportScoreOneDecimal(current));
      }
    }, 25);
    return () => clearInterval(timer);
  }, [score]);

  const angle = (score / 100) * 180 - 90;
  const riskColor = riskLevelColor(riskLevel);

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-48 h-28 overflow-hidden">
        <svg viewBox="0 0 200 110" className="w-full h-full">
          <defs>
            <linearGradient
              id="riskGaugeGradient"
              x1="20"
              y1="100"
              x2="180"
              y2="100"
              gradientUnits="userSpaceOnUse"
            >
              <stop offset="0%" stopColor="oklch(0.72 0.15 145)" />
              <stop offset="50%" stopColor="oklch(0.72 0.18 55)" />
              <stop offset="100%" stopColor="oklch(0.65 0.22 25)" />
            </linearGradient>
          </defs>
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="hsl(var(--border))"
            strokeWidth="16"
            strokeLinecap="round"
          />
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="url(#riskGaugeGradient)"
            strokeWidth="16"
            strokeLinecap="round"
            opacity="0.9"
          />
          <g transform={`rotate(${angle}, 100, 100)`}>
            <line
              x1="100"
              y1="100"
              x2="100"
              y2="28"
              stroke={riskColor}
              strokeWidth="2.5"
              strokeLinecap="round"
              style={{ filter: `drop-shadow(0 0 4px ${riskColor})` }}
            />
            <circle cx="100" cy="100" r="5" fill={riskColor} />
          </g>
        </svg>
      </div>
      <div className="text-center -mt-2">
        <div
          className="text-5xl font-bold font-['JetBrains_Mono',monospace] leading-none"
          style={{ color: riskColor, textShadow: `0 0 20px ${riskColor}80` }}
        >
          {displayScore}
        </div>
        <div className="text-sm text-muted-foreground mt-1">/ 100</div>
        <div
          className="mt-2 px-4 py-1 rounded-full text-xs font-bold font-['JetBrains_Mono',monospace] tracking-wider"
          style={{
            background: `${riskColor}20`,
            border: `1px solid ${riskColor}60`,
            color: riskColor,
          }}
        >
          {riskLabel} · {riskLevel}
        </div>
      </div>
    </div>
  );
}

function EmptyBlock({ message }: { message: string }) {
  return (
    <div className="py-8 text-center text-sm text-muted-foreground border border-dashed border-border rounded-xl">
      {message}
    </div>
  );
}

export interface ReportViewerProps {
  reportData: ReportData;
  agents?: Partial<Record<AgentId, AgentOutput>>;
  companyName?: string;
  ticker?: string;
  embedded?: boolean;
  showActions?: boolean;
  onExport?: () => void;
}

export default function ReportViewer({
  reportData,
  agents,
  companyName,
  ticker,
  embedded = false,
  showActions = true,
  onExport,
}: ReportViewerProps) {
  const firstFactorId = reportData.riskFactors[0]?.id ?? null;
  const [expandedFactors, setExpandedFactors] = useState<Set<string>>(
    () => new Set(firstFactorId ? [firstFactorId] : [])
  );
  const [activeTab, setActiveTab] = useState("overview");
  const [debateExpanded, setDebateExpanded] = useState(false);

  useEffect(() => {
    if (firstFactorId) {
      setExpandedFactors(new Set([firstFactorId]));
    }
  }, [firstFactorId]);

  const toggleFactor = (factorId: string) => {
    setExpandedFactors((prev) => {
      const next = new Set(prev);
      if (next.has(factorId)) next.delete(factorId);
      else next.add(factorId);
      return next;
    });
  };

  const handleExport = () => {
    if (onExport) {
      onExport();
    } else {
      toast.info("报告 PDF 尚未生成，请等待分析完成");
    }
  };

  const evidenceStats = useMemo(() => {
    const total = reportData.riskFactors.length;
    const withPage = reportData.riskFactors.filter(
      (f) => f.evidencePage != null
    ).length;
    return { total, withPage };
  }, [reportData.riskFactors]);

  const agentDimensions = useMemo(
    () => getAgentDimensions(reportData),
    [reportData]
  );

  const embellishmentInfo = useMemo(
    () => getEmbellishmentDisplay(reportData),
    [reportData]
  );

  const warningReportMarkdown =
    getAgentReportMarkdown(agents, "orchestrator") ??
    reportData.executiveSummary ??
    "";

  const dimensionBarData = agentDimensions.map((d) => ({
    name: d.name,
    score: d.score,
    id: d.id,
  }));

  const scoreBarColor = (id: string, score: number) => {
    const agent = getAgentDef(id);
    if (agent) return agent.color;
    if (id === "embellishment") return "oklch(0.65 0.18 330)";
    if (score >= 70) return "oklch(0.65 0.22 25)";
    if (score >= 50) return "oklch(0.72 0.18 55)";
    return "oklch(0.72 0.15 145)";
  };

  const post = reportData.postListingValidation;
  const hasPostListing =
    post.status !== "not_available" && post.checkpoints.length > 0;
  const DEBATE_PREVIEW_COUNT = 5;
  const debateVisible = debateExpanded
    ? reportData.debateHighlights
    : reportData.debateHighlights.slice(0, DEBATE_PREVIEW_COUNT);
  const debateHasMore =
    reportData.debateHighlights.length > DEBATE_PREVIEW_COUNT;

  const headerTitle = companyName ?? ticker ?? "IPO 项目";
  const headerSub = [ticker, "港交所主板"].filter(Boolean).join(" · ");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-6 py-4 border-b border-border flex-shrink-0 bg-background/80 backdrop-blur-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className={cn("font-bold text-foreground", embedded ? "text-base" : "text-lg")}>
              IPO风险穿透预警报告
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">{headerTitle} · {headerSub}</p>
          </div>
          {showActions && (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5 border-border"
                onClick={handleExport}
              >
                <Download className="w-3.5 h-3.5" />
                导出PDF
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5 border-border"
                onClick={() => toast.info("分享功能 · API: POST /api/v1/report/share")}
              >
                <Share2 className="w-3.5 h-3.5" />
                分享
              </Button>
            </div>
          )}
        </div>
      </div>

      {(reportData.degraded || reportData.gateWarning) && (
        <div className="mx-6 mt-4 px-4 py-3 rounded-lg border border-[oklch(0.72_0.18_55/0.4)] bg-[oklch(0.72_0.18_55/0.08)] flex items-start gap-2 shrink-0">
          <AlertTriangle className="w-4 h-4 text-[oklch(0.72_0.18_55)] shrink-0 mt-0.5" />
          <div className="text-xs text-foreground leading-relaxed">
            {reportData.degraded && <p>分析已降级运行，部分结论可能不完整。</p>}
            {reportData.gateWarning && <p className="mt-1">门禁提示：{reportData.gateWarning}</p>}
          </div>
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col overflow-hidden">
        <TabsList className="flex-shrink-0 mx-6 mt-4 mb-0 bg-secondary border border-border w-fit">
          <TabsTrigger value="overview" className="text-xs">综合概览</TabsTrigger>
          <TabsTrigger value="factors" className="text-xs">风险因子</TabsTrigger>
          <TabsTrigger value="charts" className="text-xs">可视化分析</TabsTrigger>
          <TabsTrigger value="validation" className="text-xs">历史验证</TabsTrigger>
        </TabsList>

        <div className="flex-1 overflow-hidden">
          <TabsContent value="overview" className="h-full m-0">
            <ScrollArea className="h-full">
              <div className="p-6 space-y-6 max-w-6xl">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.5 }}
                    className="panel-glass rounded-xl p-6 flex flex-col items-center justify-center"
                    style={{
                      boxShadow: `0 0 30px ${riskLevelColor(reportData.riskLevel)}26`,
                    }}
                  >
                    <SectionTitle icon={Gauge}>COMPREHENSIVE RISK SCORE</SectionTitle>
                    <RiskScoreGauge
                      score={reportData.overallScore}
                      riskLabel={reportData.riskLabel}
                      riskLevel={reportData.riskLevel}
                    />
                  </motion.div>

                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.1 }}
                    className="panel-glass rounded-xl p-5 lg:col-span-2"
                  >
                    <SectionTitle icon={AlertTriangle}>RISK SOURCES · TOP 3</SectionTitle>
                    {reportData.riskFactors.length === 0 ? (
                      <EmptyBlock message="暂无识别风险因子" />
                    ) : (
                      <div className="space-y-3">
                        {reportData.riskFactors.slice(0, 3).map((rf, i) => (
                          <div key={rf.id} className="flex items-start gap-3">
                            <div
                              className="w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold font-['JetBrains_Mono',monospace] flex-shrink-0 mt-0.5"
                              style={{
                                background: "oklch(0.65 0.22 25 / 0.2)",
                                color: "oklch(0.65 0.22 25)",
                                border: "1px solid oklch(0.65 0.22 25 / 0.4)",
                              }}
                            >
                              {i + 1}
                            </div>
                            <div>
                              <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                                <span className="text-sm font-semibold text-foreground">{rf.title}</span>
                                <AgentBadge agentId={rf.sourceAgent} />
                              </div>
                              <p className="text-[11px] text-muted-foreground leading-relaxed">{rf.reason}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </motion.div>
                </div>

                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.2 }}
                  className="panel-glass rounded-xl p-5"
                >
                  <SectionTitle icon={Layers}>RISK DIMENSION BREAKDOWN</SectionTitle>
                  {agentDimensions.length === 0 && !embellishmentInfo ? (
                    <EmptyBlock message="暂无维度分数" />
                  ) : (
                    <div className="space-y-3">
                      {agentDimensions.map((dim) => {
                        const color = scoreBarColor(dim.id, dim.score);
                        return (
                          <div key={dim.id} className="flex items-center gap-4">
                            <span className="text-xs text-foreground w-24 flex-shrink-0">{dim.name}</span>
                            <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                              <motion.div
                                className="h-full rounded-full"
                                initial={{ width: 0 }}
                                animate={{ width: `${Math.min(dim.score, 100)}%` }}
                                transition={{ duration: 1, delay: 0.5, ease: "easeOut" }}
                                style={{ background: color, boxShadow: `0 0 6px ${color}80` }}
                              />
                            </div>
                            <span
                              className="text-xs font-bold font-['JetBrains_Mono',monospace] w-16 text-right flex-shrink-0 tabular-nums"
                              style={{ color }}
                            >
                              {formatReportScoreOneDecimal(dim.score)}/100
                            </span>
                          </div>
                        );
                      })}
                      {embellishmentInfo && (
                        <div className="flex items-center gap-4 pt-3 border-t border-border/50">
                          <span className="text-xs text-foreground w-24 flex-shrink-0 inline-flex items-center gap-1">
                            <Sparkles className="w-3 h-3 text-[oklch(0.65_0.18_330)] shrink-0" />
                            文本粉饰度
                          </span>
                          <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                            {embellishmentInfo.score != null && (
                              <motion.div
                                className="h-full rounded-full"
                                initial={{ width: 0 }}
                                animate={{
                                  width: `${Math.min(embellishmentInfo.score / 10, 1) * 100}%`,
                                }}
                                transition={{ duration: 1, delay: 0.65, ease: "easeOut" }}
                                style={{
                                  background: "oklch(0.65 0.18 330)",
                                  boxShadow: "0 0 6px oklch(0.65 0.18 330 / 0.5)",
                                }}
                              />
                            )}
                          </div>
                          <span className="text-xs font-bold font-['JetBrains_Mono',monospace] min-w-[4.5rem] text-right flex-shrink-0 tabular-nums text-[oklch(0.65_0.18_330)]">
                            {[
                              embellishmentInfo.score != null
                                ? `${formatReportScoreOneDecimal(embellishmentInfo.score)}/10`
                                : null,
                              embellishmentInfo.level
                                ? riskTagLabel(embellishmentInfo.level)
                                : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.25 }}
                  className="panel-glass rounded-xl p-5"
                >
                  <SectionTitle icon={FileText}>EVIDENCE SUMMARY</SectionTitle>
                  <div className="space-y-2.5">
                    <div className="flex items-center justify-between py-1.5 border-b border-border/50">
                      <span className="text-xs text-muted-foreground">识别风险因子</span>
                      <span className="text-xs font-bold font-['JetBrains_Mono',monospace] text-[oklch(0.65_0.22_25)]">
                        {evidenceStats.total}项
                      </span>
                    </div>
                    <div className="flex items-center justify-between py-1.5 border-b border-border/50">
                      <span className="text-xs text-muted-foreground">含PDF页码引用</span>
                      <span className="text-xs font-bold font-['JetBrains_Mono',monospace] text-[oklch(0.75_0.18_195)]">
                        {evidenceStats.withPage}处
                      </span>
                    </div>
                    {embellishmentInfo && (
                      <div className="flex items-center justify-between py-1.5 border-b border-border/50">
                        <span className="text-xs text-muted-foreground">文本粉饰</span>
                        <span className="text-xs font-bold font-['JetBrains_Mono',monospace] text-[oklch(0.65_0.18_330)]">
                          {[
                            embellishmentInfo.score != null
                              ? `${formatReportScoreOneDecimal(embellishmentInfo.score)}/10`
                              : null,
                            embellishmentInfo.level
                              ? riskTagLabel(embellishmentInfo.level)
                              : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </div>
                    )}
                    {reportData.referenceFundamentalScore != null && (
                      <div className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
                        <span className="text-xs text-muted-foreground">参考基本面分</span>
                        <span className="text-xs font-bold font-['JetBrains_Mono',monospace] text-foreground">
                          {formatReportScore(reportData.referenceFundamentalScore)}
                        </span>
                      </div>
                    )}
                  </div>
                </motion.div>

                {reportData.debateHighlights.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.35 }}
                    className="panel-glass rounded-xl p-5"
                  >
                    <SectionTitle icon={MessageSquare}>DEBATE HIGHLIGHTS</SectionTitle>
                    <div className="space-y-3">
                      {debateVisible.map((h, i) => (
                        <DebateHighlightItem
                          key={i}
                          agentId={h.agentId}
                          content={h.content}
                        />
                      ))}
                    </div>
                    {debateHasMore && (
                      <button
                        type="button"
                        onClick={() => setDebateExpanded((v) => !v)}
                        className="mt-3 text-[11px] text-primary font-['JetBrains_Mono',monospace] hover:underline"
                      >
                        {debateExpanded
                          ? "收起"
                          : `展开全部 ${reportData.debateHighlights.length} 条`}
                      </button>
                    )}
                  </motion.div>
                )}

                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.4 }}
                  className="panel-glass rounded-xl p-5"
                >
                  <SectionTitle icon={BookOpen}>IPO RISK WARNING REPORT</SectionTitle>
                  {warningReportMarkdown ? (
                    <ParseMarkdownContent content={warningReportMarkdown} />
                  ) : (
                    <EmptyBlock message="暂无风险预警报告" />
                  )}
                </motion.div>
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="factors" className="h-full m-0">
            <ScrollArea className="h-full">
              <div className="p-6 space-y-4 max-w-4xl">
                <SectionTitle icon={AlertTriangle} className="mb-2">
                  RISK FACTORS · {reportData.riskFactors.length} IDENTIFIED
                </SectionTitle>
                {reportData.riskFactors.length === 0 ? (
                  <EmptyBlock message="暂无风险因子" />
                ) : (
                  reportData.riskFactors.map((rf, index) => {
                    const isExpanded = expandedFactors.has(rf.id);
                    return (
                      <motion.div
                        key={rf.id}
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.3, delay: index * 0.08 }}
                        className="panel-glass rounded-xl overflow-hidden"
                      >
                        <button
                          onClick={() => toggleFactor(rf.id)}
                          className="w-full flex items-start gap-4 p-5 text-left hover:bg-secondary/30 transition-colors"
                        >
                          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold font-['JetBrains_Mono',monospace] flex-shrink-0 bg-primary/10 border border-primary/30 text-primary">
                            {index + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className="text-sm font-semibold text-foreground">{rf.title}</span>
                              <AgentBadge agentId={rf.sourceAgent} />
                              {rf.weight != null && (
                                <span className="text-[10px] font-['JetBrains_Mono',monospace] text-muted-foreground">
                                  w={rf.weight}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground leading-relaxed">{rf.reason}</p>
                          </div>
                          <div className="flex-shrink-0 mt-1">
                            {isExpanded ? (
                              <ChevronDown className="w-4 h-4 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-muted-foreground" />
                            )}
                          </div>
                        </button>
                        <AnimatePresence>
                          {isExpanded && (rf.evidencePage != null || rf.evidenceExcerpt) && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              transition={{ duration: 0.25 }}
                              className="overflow-hidden"
                            >
                              <div className="px-5 pb-5 border-t border-border/50 pt-4">
                                <div className="flex items-center gap-2 mb-3">
                                  <BookOpen className="w-3.5 h-3.5 text-primary" />
                                  <span className="text-xs font-semibold text-foreground">PDF证据溯源</span>
                                </div>
                                <div className="flex gap-3 p-3 rounded-lg bg-secondary/50 border border-border/50">
                                  {rf.evidencePage != null && (
                                    <div className="flex items-center gap-1 flex-shrink-0">
                                      <FileText className="w-3 h-3 text-primary" />
                                      <span className="text-[10px] font-bold font-['JetBrains_Mono',monospace] text-primary">
                                        P.{rf.evidencePage}
                                      </span>
                                    </div>
                                  )}
                                  {rf.evidenceExcerpt && (
                                    <p className="text-[11px] text-muted-foreground leading-relaxed flex-1">
                                      「{rf.evidenceExcerpt}」
                                    </p>
                                  )}
                                </div>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </motion.div>
                    );
                  })
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="charts" className="h-full m-0">
            <ScrollArea className="h-full">
              <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-5 max-w-5xl">
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="panel-glass rounded-xl p-5"
                >
                  <SectionTitle icon={RadarIcon}>RISK RADAR · MULTI-DIMENSION</SectionTitle>
                  {reportData.radarData.length === 0 ? (
                    <EmptyBlock message="暂无雷达数据" />
                  ) : (
                    <ResponsiveContainer width="100%" height={260}>
                      <RadarChart data={reportData.radarData}>
                        <PolarGrid stroke="oklch(0.25 0.04 210)" />
                        <PolarAngleAxis
                          dataKey="axis"
                          tick={{ fill: "oklch(0.55 0.02 240)", fontSize: 11, fontFamily: "IBM Plex Sans" }}
                        />
                        <Radar
                          name="风险分值"
                          dataKey="value"
                          stroke="oklch(0.65 0.22 25)"
                          fill="oklch(0.65 0.22 25)"
                          fillOpacity={0.25}
                          strokeWidth={2}
                        />
                      </RadarChart>
                    </ResponsiveContainer>
                  )}
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.1 }}
                  className="panel-glass rounded-xl p-5"
                >
                  <SectionTitle icon={BarChart3}>AGENT SCORES</SectionTitle>
                  {dimensionBarData.length === 0 ? (
                    <EmptyBlock message="暂无维度分数" />
                  ) : (
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={dimensionBarData} layout="vertical" margin={{ left: 60, right: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.25 0.04 210)" horizontal={false} />
                        <XAxis type="number" domain={[0, 100]} tick={{ fill: "oklch(0.55 0.02 240)", fontSize: 10, fontFamily: "JetBrains Mono" }} />
                        <YAxis type="category" dataKey="name" tick={{ fill: "oklch(0.75 0.01 240)", fontSize: 10, fontFamily: "IBM Plex Sans" }} width={70} />
                        <Tooltip
                          formatter={(value: number) => [formatReportScore(value), "风险分值"]}
                          contentStyle={{
                            background: "oklch(0.14 0.015 240)",
                            border: "1px solid oklch(0.25 0.04 210)",
                            borderRadius: "6px",
                            fontSize: "11px",
                            color: "oklch(0.92 0.005 240)",
                          }}
                        />
                        <Bar dataKey="score" radius={[0, 3, 3, 0]}>
                          {dimensionBarData.map((entry) => (
                            <Cell
                              key={entry.name}
                              fill={scoreBarColor(entry.id, entry.score)}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 }}
                  className="panel-glass rounded-xl p-5 lg:col-span-2"
                >
                  <SectionTitle icon={Clock}>RISK WINDOWS · D1 / D5 / D20 / D60</SectionTitle>
                  {reportData.riskTimeline.length === 0 ? (
                    <EmptyBlock message="暂无风险窗口数据" />
                  ) : (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {reportData.riskTimeline.map((pt) => {
                        const color = riskTagColor(pt.risk);
                        return (
                          <div
                            key={pt.window}
                            className="rounded-lg border border-border/60 p-4 text-center"
                            style={{ background: `${color}10` }}
                          >
                            <div className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] mb-1">
                              {pt.label}
                            </div>
                            <div className="text-lg font-bold font-['JetBrains_Mono',monospace]" style={{ color }}>
                              {riskTagLabel(pt.risk)}
                            </div>
                            <div className="text-[10px] text-muted-foreground mt-1">{pt.risk}</div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.25 }}
                  className="panel-glass rounded-xl p-5 lg:col-span-2"
                >
                  <SectionTitle icon={TrendingUp}>PRICE PATH FORECAST</SectionTitle>
                  {reportData.pricePathForecast.length === 0 ? (
                    <EmptyBlock message="暂无价格路径预测" />
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {reportData.pricePathForecast.map((item) => (
                        <div key={item.window} className="rounded-lg border border-border/60 p-4 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold font-['JetBrains_Mono',monospace] text-foreground">
                              {item.window}
                            </span>
                            <span
                              className="text-[10px] px-2 py-0.5 rounded font-['JetBrains_Mono',monospace]"
                              style={{
                                color: riskTagColor(item.riskLabel),
                                background: `${riskTagColor(item.riskLabel)}15`,
                                border: `1px solid ${riskTagColor(item.riskLabel)}40`,
                              }}
                            >
                              {item.riskLabel}
                            </span>
                          </div>
                          <p className="text-[11px] text-foreground">{item.expectedDirection}</p>
                          <p className="text-[10px] text-muted-foreground">{item.expectedPattern}</p>
                          <p className="text-[10px] text-muted-foreground">波动：{item.volatilityView}</p>
                          {item.keyDrivers.length > 0 && (
                            <p className="text-[10px] text-muted-foreground">
                              驱动：{item.keyDrivers.join("、")}
                            </p>
                          )}
                          <p className="text-[10px] font-['JetBrains_Mono',monospace] text-muted-foreground">
                            置信度 {item.confidence}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </motion.div>
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="validation" className="h-full m-0">
            <ScrollArea className="h-full">
              <div className="p-6 space-y-5 max-w-4xl">
                <SectionTitle icon={ClipboardCheck} className="mb-2">
                  POST-LISTING VALIDATION
                </SectionTitle>

                {!hasPostListing ? (
                  <EmptyBlock
                    message={
                      post.summary ||
                      (post.status === "not_available"
                        ? "尚未上市或暂无上市后验证数据"
                        : "暂无验证检查点")
                    }
                  />
                ) : (
                  <>
                    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="panel-glass rounded-xl p-5 space-y-3">
                      <div className="flex flex-wrap gap-4 text-xs">
                        {post.businessValueScore != null && (
                          <div>
                            <span className="text-muted-foreground">业务价值分 </span>
                            <span className="font-['JetBrains_Mono',monospace]">{post.businessValueScore}</span>
                          </div>
                        )}
                        {post.weightedHitScore != null && (
                          <div>
                            <span className="text-muted-foreground">加权命中分 </span>
                            <span className="font-['JetBrains_Mono',monospace]">{post.weightedHitScore}</span>
                          </div>
                        )}
                      </div>
                      {post.summary && (
                        <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">{post.summary}</p>
                      )}
                    </motion.div>

                    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="panel-glass rounded-xl overflow-hidden">
                      <div className="px-5 py-3 border-b border-border">
                        <span className="text-xs font-semibold text-foreground">验证检查点</span>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-border">
                              {["窗口", "预测", "实际", "命中", "对齐", "备注"].map((h) => (
                                <th key={h} className="px-4 py-3 text-left text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider font-normal">
                                  {h}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {post.checkpoints.map((cp, i) => (
                              <tr key={i} className="border-b border-border/50 hover:bg-secondary/30">
                                <td className="px-4 py-3 font-['JetBrains_Mono',monospace]">{cp.window ?? "—"}</td>
                                <td className="px-4 py-3">{cp.predictionLabel ?? cp.predictionText ?? "—"}</td>
                                <td className="px-4 py-3">{cp.actualSeverity ?? "—"}</td>
                                <td className="px-4 py-3">{cp.hit == null ? "—" : cp.hit ? "是" : "否"}</td>
                                <td className="px-4 py-3">{cp.alignment ?? "—"}</td>
                                <td className="px-4 py-3 text-muted-foreground">{cp.note || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </motion.div>
                  </>
                )}

                {post.limitations.length > 0 && (
                  <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="panel-glass rounded-xl p-5">
                    <div className="text-xs font-semibold text-foreground mb-2">局限性说明</div>
                    <ul className="list-disc list-inside text-xs text-muted-foreground space-y-1">
                      {post.limitations.map((lim, i) => (
                        <li key={i}>{lim}</li>
                      ))}
                    </ul>
                  </motion.div>
                )}
              </div>
            </ScrollArea>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
