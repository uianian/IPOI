import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Route, Switch, useLocation } from "wouter";
import { AnimatePresence, motion } from "framer-motion";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider, useTheme } from "./contexts/ThemeContext";
import { ActiveProjectProvider } from "./contexts/ActiveProjectContext";
import { AnalysisSessionProvider } from "./contexts/AnalysisSessionContext";
import AppLayout from "./components/AppLayout";
import FileManagementPage from "./pages/FileManagementPage";
import ParseResultPage from "./pages/ParseResultPage";
import ProjectAnalysisPage from "./pages/ProjectAnalysisPage";
import ReportPage from "./pages/ReportPage";

/** Theme-aware Toaster */
function ThemedToaster() {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  return (
    <Toaster
      theme={theme}
      toastOptions={{
        style: {
          background: isDark ? "oklch(0.14 0.015 240)" : "oklch(1 0 0)",
          border: isDark ? "1px solid oklch(0.25 0.04 210)" : "1px solid oklch(0.88 0.02 240)",
          color: isDark ? "oklch(0.92 0.005 240)" : "oklch(0.15 0.01 250)",
        },
      }}
    />
  );
}

/** Fade-in page transition wrapper */
function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="h-full"
    >
      {children}
    </motion.div>
  );
}

function Router() {
  const [location] = useLocation();

  // ── Standalone pages — minimal layout, no sidebar ──
  if (location === "/") {
    return (
      <AppLayout variant="minimal">
        <AnimatePresence mode="wait">
          <Switch>
            <Route path="/">
              <PageTransition><FileManagementPage /></PageTransition>
            </Route>
            <Route>
              <PageTransition><NotFound /></PageTransition>
            </Route>
          </Switch>
        </AnimatePresence>
      </AppLayout>
    );
  }

  // ── Detail pages — full layout with sidebar ──
  return (
    <AppLayout variant="full">
      <AnimatePresence mode="wait">
        <Switch>
          <Route path="/project/:id/report">
            <PageTransition><ReportPage /></PageTransition>
          </Route>
          <Route path="/project/:id/analysis">
            <PageTransition><ProjectAnalysisPage /></PageTransition>
          </Route>
          <Route path="/project/:id">
            <PageTransition><ParseResultPage /></PageTransition>
          </Route>
          <Route path="/report">
            <PageTransition><ReportPage /></PageTransition>
          </Route>
          <Route path="/404">
            <PageTransition><NotFound /></PageTransition>
          </Route>
          <Route>
            <PageTransition><NotFound /></PageTransition>
          </Route>
        </Switch>
      </AnimatePresence>
    </AppLayout>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="dark">
        <TooltipProvider>
          <ThemedToaster />
          <ActiveProjectProvider>
            <AnalysisSessionProvider>
              <Router />
            </AnalysisSessionProvider>
          </ActiveProjectProvider>
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
