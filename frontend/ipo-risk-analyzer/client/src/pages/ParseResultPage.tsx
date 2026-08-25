/**
 * ParseResultPage — PDF 解析结果展示
 */
import { useState, useEffect } from "react";
import { useParams, useLocation } from "wouter";
import { motion } from "framer-motion";
import { ChevronRight, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useActiveProject } from "@/contexts/ActiveProjectContext";
import ParseProgressBar from "@/components/parse/ParseProgressBar";
import BasicInfoCard from "@/components/parse/BasicInfoCard";
import ParseStatsCard from "@/components/parse/ParseStatsCard";
import DocumentViewer from "@/components/parse/DocumentViewer";
import { getProjectById, updateProject } from "@/data/projects";
import { getProjectState, markParseDone } from "@/data/projectState";
import {
  getParseResult,
  saveParseResult,
  getSourcePdf,
} from "@/data/projectStore";
import { runParsePipeline } from "@/services/parseService";
import type { ParseResult, CompanyRecord } from "@/types";
import { lookupCompany } from "@/lib/companyLookup";
import { toast } from "sonner";

export default function ParseResultPage() {
  const { id } = useParams();
  const [, navigate] = useLocation();
  const { setActiveProjectId } = useActiveProject();

  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [companyRecord, setCompanyRecord] = useState<CompanyRecord | null>(null);
  const [lookupTicker, setLookupTicker] = useState("");
  const [parseProgress, setParseProgress] = useState(0);
  const [parseStage, setParseStage] = useState("INIT");

  const project = id ? getProjectById(id) : undefined;

  useEffect(() => {
    if (id) setActiveProjectId(id);
  }, [id, setActiveProjectId]);

  useEffect(() => {
    if (!id) return;
    const project = getProjectById(id);
    if (!project) return;

    let cancelled = false;

    async function loadOrParse() {
      const state = getProjectState(id!);
      const cached = await getParseResult(id!);

      if (state.parseDone && cached) {
        setParseProgress(100);
        setParseStage("READY");
        setParseResult(cached);
        return;
      }

      setParseResult(null);
      setParseProgress(0);
      setParseStage("PARSING");

      try {
        const pdf = await getSourcePdf(id!);
        if (!pdf) {
          toast.error("未找到本地 PDF，请重新上传");
          return;
        }

        const file = new File([pdf], project!.fileName, {
          type: "application/pdf",
        });

        const result = await runParsePipeline(
          file,
          {
            clientProjectId: id!,
            ticker: project!.ticker,
            fileName: project!.fileName,
            isBiotech: project!.isBiotech,
            enableEmbellishment: project!.enableEmbellishment ?? false,
          },
          (progress, stage) => {
            if (!cancelled) {
              setParseProgress(progress);
              setParseStage(stage);
              updateProject(id!, { parseProgress: progress, status: "parsing" });
            }
          }
        );

        if (cancelled) return;

        await saveParseResult(id!, result);
        markParseDone(id!);
        updateProject(id!, {
          status: "parsing",
          parseProgress: 100,
          parseCompleteTime: result.completedAt ?? new Date().toISOString(),
          parseTaskId: result.taskId,
          parseDone: true,
        });
        setParseResult(result);
        setParseProgress(100);
        setParseStage("READY");
      } catch (err) {
        if (!cancelled) {
          console.error("[ParseResultPage]", err);
          toast.error("解析失败，请稍后重试");
          setParseStage("INIT");
        }
      }
    }

    loadOrParse();
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (!id) return;
    const ticker = getProjectById(id)?.ticker ?? "";
    setLookupTicker(ticker);
    if (!ticker) {
      setCompanyRecord(null);
      return;
    }
    let active = true;
    lookupCompany(ticker)
      .then((rec) => active && setCompanyRecord(rec))
      .catch(() => active && setCompanyRecord(null));
    return () => {
      active = false;
    };
  }, [id]);

  const isParsed = parseProgress >= 100 && parseResult;

  return (
    <div className="h-[calc(100vh-3rem)] overflow-hidden">
      <ScrollArea className="h-full">
        <div className="p-6 max-w-5xl mx-auto space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-foreground">解析结果</h1>
              {parseResult && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {companyRecord?.companyName ||
                    parseResult.companyInfo?.companyName ||
                    lookupTicker}
                  {lookupTicker ? ` · ${lookupTicker}` : ""}
                </p>
              )}
            </div>

            {isParsed && (
              <Button
                onClick={() => navigate(`/project/${id}/analysis`)}
                className="h-9 text-sm font-semibold gap-2"
                style={{
                  background: "oklch(0.75 0.18 195)",
                  color: "oklch(0.10 0.012 240)",
                  boxShadow: "0 0 20px oklch(0.75 0.18 195 / 0.4)",
                }}
              >
                <Cpu className="w-4 h-4" />
                进入智能分析
                <ChevronRight className="w-4 h-4" />
              </Button>
            )}
          </div>

          {!isParsed && (
            <motion.div initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}>
              <ParseProgressBar progress={parseProgress} stage={parseStage} />
            </motion.div>
          )}

          {isParsed && parseResult && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
                <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}>
                  <BasicInfoCard record={companyRecord} ticker={lookupTicker} />
                </motion.div>
                <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}>
                  <ParseStatsCard stats={parseResult.stats} />
                </motion.div>
              </div>

              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
              >
                <DocumentViewer markdown={parseResult.markdown} />
              </motion.div>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
