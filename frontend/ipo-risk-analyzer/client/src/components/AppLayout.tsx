/**
 * AppLayout - Dark Quant Terminal layout
 * Left sidebar navigation + main content area
 * Design: Bloomberg Terminal aesthetic, deep navy, cyan accents
 */
import { Link, useLocation } from "wouter";
import { useMemo } from "react";
import { cn } from "@/lib/utils";
import {
  FolderOpen,
  BrainCircuit,
  FileBarChart2,
  Activity,
  ChevronRight,
  ArrowLeft,
  ScanSearch,
  Zap,
} from "lucide-react";
import ThemeToggle from "@/components/theme/ThemeToggle";
import { useActiveProject } from "@/contexts/ActiveProjectContext";

interface AppLayoutProps {
  children: React.ReactNode;
  variant?: "full" | "minimal";
}

export default function AppLayout({ children, variant = "full" }: AppLayoutProps) {
  const [location, navigate] = useLocation();
  const { activeProjectId } = useActiveProject();
  const minimal = variant === "minimal";

  const navItems = useMemo(() => [
    {
      path: activeProjectId ? `/project/${activeProjectId}` : "/",
      icon: FolderOpen,
      label: "PDF解析",
      sublabel: "PARSE",
      step: "01",
    },
    {
      path: activeProjectId ? `/project/${activeProjectId}/analysis` : "/",
      icon: BrainCircuit,
      label: "智能分析",
      sublabel: "ANALYSIS",
      step: "02",
    },
    {
      path: activeProjectId ? `/project/${activeProjectId}/report` : "/report",
      icon: FileBarChart2,
      label: "风险报告",
      sublabel: "REPORT",
      step: "03",
    },
  ], [activeProjectId]);

  return (
    <div className="flex min-h-screen bg-background font-['IBM_Plex_Sans',sans-serif]">
      {/* Sidebar — only in full mode */}
      {!minimal && (
      <aside className="w-64 flex-shrink-0 flex flex-col border-r border-border bg-sidebar relative">
        {/* Scanline overlay */}
        <div
          className="absolute inset-0 pointer-events-none z-0"
          style={{
            backgroundImage:
              "repeating-linear-gradient(0deg, transparent, transparent 2px, oklch(0 0 0 / 0.04) 2px, oklch(0 0 0 / 0.04) 4px)",
          }}
        />

        {/* Logo */}
        <div className="relative z-10 px-5 py-5 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg flex-shrink-0 bg-accent flex items-center justify-center glow-cyan border border-primary/30">
              <ScanSearch className="w-5 h-5 text-primary" />
            </div>
            <div>
              <div
                className="text-sm font-bold tracking-widest text-primary font-['JetBrains_Mono',monospace]"
                style={{ textShadow: "0 0 10px oklch(0.75 0.18 195 / 0.6)" }}
              >
                IPO INSIGHT
              </div>
              <div className="text-[10px] text-muted-foreground tracking-wider font-['JetBrains_Mono',monospace]">
                HK · IPO ANALYZER
              </div>
            </div>
          </div>
        </div>

        {/* System status */}
        <div className="relative z-10 px-5 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-[oklch(0.72_0.15_145)] agent-active" />
            <span className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-wider">
              SYSTEM ONLINE
            </span>
            <Activity className="w-3 h-3 text-muted-foreground ml-auto" />
          </div>
        </div>

        {/* Navigation */}
        <nav className="relative z-10 flex-1 px-3 py-4 space-y-1">
          <div className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-widest px-2 mb-3">
            WORKFLOW
          </div>
          {navItems.map((item) => {
            const isActive = location === item.path;
            const Icon = item.icon;
            return (
              <Link key={item.path} href={item.path}>
                <div
                  className={cn(
                    "group flex items-center gap-3 px-3 py-3 rounded-md transition-all duration-200 cursor-pointer relative",
                    isActive
                      ? "bg-accent text-primary border border-primary/30"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary border border-transparent"
                  )}
                  style={
                    isActive
                      ? {
                          boxShadow:
                            "0 0 12px oklch(0.75 0.18 195 / 0.2), inset 0 0 12px oklch(0.75 0.18 195 / 0.05)",
                        }
                      : {}
                  }
                >
                  {/* Step number */}
                  <span
                    className={cn(
                      "text-[10px] font-['JetBrains_Mono',monospace] font-bold w-5 flex-shrink-0",
                      isActive ? "text-primary" : "text-muted-foreground"
                    )}
                  >
                    {item.step}
                  </span>

                  <Icon
                    className={cn(
                      "w-4 h-4 flex-shrink-0 transition-colors",
                      isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                    )}
                  />

                  <div className="flex-1 min-w-0">
                    <div
                      className={cn(
                        "text-sm font-medium truncate",
                        isActive ? "text-foreground" : ""
                      )}
                    >
                      {item.label}
                    </div>
                    <div className="text-[10px] font-['JetBrains_Mono',monospace] tracking-wider opacity-50">
                      {item.sublabel}
                    </div>
                  </div>

                  {isActive && (
                    <ChevronRight className="w-3 h-3 text-primary flex-shrink-0" />
                  )}
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Bottom info */}
        <div className="relative z-10 px-5 py-4 border-t border-border">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-3 h-3 text-primary" />
            <span className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace]">
              POWERED BY MULTI-AGENT RAG
            </span>
          </div>
          <div className="text-[10px] text-muted-foreground/50 font-['JetBrains_Mono',monospace]">
            v2.4.1 · HK MARKET EDITION
          </div>
        </div>
      </aside>
      )}

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <header className="h-12 border-b border-border flex items-center px-6 gap-4 flex-shrink-0 bg-background/80 backdrop-blur-sm">
          {!minimal && (
            <button
              onClick={() => navigate("/")}
              className="flex items-center justify-center w-7 h-7 rounded-md border border-border text-muted-foreground hover:text-primary hover:border-primary/40 transition-colors flex-shrink-0"
              title="返回项目管理"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
          )}
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-['JetBrains_Mono',monospace]">
            <span className="text-primary">IPO INSIGHT</span>
            <span>/</span>
            {navItems.find((n) => n.path === location)?.sublabel || "HOME"}
          </div>
          <div className="ml-auto flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-[oklch(0.72_0.15_145)]" />
              <span className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace]">
                4 AGENTS READY
              </span>
            </div>
            <div className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace]">
              HKEx · {new Date().toLocaleDateString("zh-HK")}
            </div>
            <ThemeToggle />
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1 overflow-auto">{children}</div>
      </main>
    </div>
  );
}
