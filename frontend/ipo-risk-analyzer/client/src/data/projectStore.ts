/**
 * projectStore.ts — 项目缓存目录业务封装
 */
import JSZip from "jszip";
import type {
  AnalysisHistoryManifest,
  AnalysisHistoryMeta,
  AnalysisRecord,
  ParseResult,
  ParseStats,
  Project,
} from "@/types";
import type { ReportData } from "@/data/reportData";
import { writeBlobToDirectory } from "@/lib/exportToFolder";
import {
  deleteProjectCache,
  exportProjectCacheEntries,
  importCacheEntry,
  readCacheBlob,
  readCacheJSON,
  readCacheText,
  writeCacheBlob,
  writeCacheJSON,
  writeCacheText,
  type CacheFileRecord,
} from "@/lib/localCache";

const PARSE_CONTENT = "parse-content.md";
const PARSE_STATS = "parse-stats.json";
const PARSE_META = "parse-meta.json";
const SOURCE_PDF = "source.pdf";
const ANALYSIS_FILE = "analysis.json";
const REPORT_JSON = "report.json";
const REPORT_PDF = "report.pdf";
const HISTORY_MANIFEST = "analysis-history/manifest.json";

export interface AnalysisHistorySnapshot {
  meta: AnalysisHistoryMeta;
  analysis: AnalysisRecord;
  report: ReportData;
}

function historyAnalysisPath(versionId: string): string {
  return `analysis-history/${versionId}/analysis.json`;
}

function historyReportJsonPath(versionId: string): string {
  return `analysis-history/${versionId}/report.json`;
}

function historyReportPdfPath(versionId: string): string {
  return `analysis-history/${versionId}/report.pdf`;
}

function formatHistoryLabel(index: number, completedAt: string): string {
  const d = new Date(completedAt);
  const time = d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `第 ${index} 次分析 · ${time}`;
}

async function readHistoryManifest(
  projectId: string
): Promise<AnalysisHistoryManifest> {
  const manifest = await readCacheJSON<AnalysisHistoryManifest>(
    projectId,
    HISTORY_MANIFEST
  );
  return manifest ?? { versions: [] };
}

async function writeHistoryManifest(
  projectId: string,
  manifest: AnalysisHistoryManifest
): Promise<void> {
  await writeCacheJSON(projectId, HISTORY_MANIFEST, manifest);
}

/** 将当前 analysis/report 快照归档到 history（无当前结果则跳过） */
export async function archiveCurrentAnalysis(
  projectId: string
): Promise<AnalysisHistoryMeta | null> {
  const analysis = await getAnalysis(projectId);
  if (!analysis?.thoughts.length) return null;

  const cachedReport = await getReport(projectId);
  const report = cachedReport ?? null;
  if (!report) return null;
  const pdf = await getReportPdf(projectId);

  const manifest = await readHistoryManifest(projectId);
  const versionIndex = manifest.versions.length + 1;
  const completedAt = analysis.completedAt ?? new Date().toISOString();
  const meta: AnalysisHistoryMeta = {
    id: `analysis-${Date.now().toString(16)}`,
    completedAt,
    overallScore: analysis.overallScore,
    riskLevel: analysis.riskLevel,
    label: formatHistoryLabel(versionIndex, completedAt),
  };

  await writeCacheJSON(projectId, historyAnalysisPath(meta.id), analysis);
  await writeCacheJSON(projectId, historyReportJsonPath(meta.id), report);
  if (pdf) {
    await writeCacheBlob(projectId, historyReportPdfPath(meta.id), pdf);
  }

  manifest.versions.push(meta);
  await writeHistoryManifest(projectId, manifest);
  return meta;
}

export async function listAnalysisHistory(
  projectId: string
): Promise<AnalysisHistoryMeta[]> {
  const manifest = await readHistoryManifest(projectId);
  return [...manifest.versions].reverse();
}

export async function getAnalysisHistorySnapshot(
  projectId: string,
  versionId: string
): Promise<AnalysisHistorySnapshot | null> {
  const manifest = await readHistoryManifest(projectId);
  const meta = manifest.versions.find((v) => v.id === versionId);
  if (!meta) return null;

  const analysis = await readCacheJSON<AnalysisRecord>(
    projectId,
    historyAnalysisPath(versionId)
  );
  const report = await readCacheJSON<ReportData>(
    projectId,
    historyReportJsonPath(versionId)
  );
  if (!analysis || !report) return null;

  return { meta, analysis, report };
}

export async function getAnalysisHistoryReportPdf(
  projectId: string,
  versionId: string
): Promise<Blob | null> {
  return readCacheBlob(projectId, historyReportPdfPath(versionId));
}

export interface ParseMeta {
  taskId: string;
  mode: ParseResult["mode"];
  companyInfo?: ParseResult["companyInfo"];
  completedAt?: string;
}

export async function saveSourcePdf(
  projectId: string,
  file: File | Blob
): Promise<void> {
  await writeCacheBlob(projectId, SOURCE_PDF, file);
}

export async function getSourcePdf(projectId: string): Promise<Blob | null> {
  return readCacheBlob(projectId, SOURCE_PDF);
}

export async function saveParseResult(
  projectId: string,
  result: ParseResult
): Promise<void> {
  await writeCacheText(projectId, PARSE_CONTENT, result.markdown);
  await writeCacheJSON(projectId, PARSE_STATS, result.stats);
  await writeCacheJSON(projectId, PARSE_META, {
    taskId: result.taskId,
    mode: result.mode,
    ...(result.companyInfo ? { companyInfo: result.companyInfo } : {}),
    completedAt: result.completedAt,
  } satisfies ParseMeta);
}

export async function getParseResult(
  projectId: string
): Promise<ParseResult | null> {
  const markdown = await readCacheText(projectId, PARSE_CONTENT);
  const stats = await readCacheJSON<ParseStats>(projectId, PARSE_STATS);
  const meta = await readCacheJSON<ParseMeta>(projectId, PARSE_META);
  if (!markdown || !stats || !meta) return null;

  return {
    taskId: meta.taskId,
    projectId,
    mode: meta.mode,
    status: "completed",
    ...(meta.companyInfo ? { companyInfo: meta.companyInfo } : {}),
    stats,
    markdown,
    completedAt: meta.completedAt,
  };
}

export async function getParseContent(projectId: string): Promise<string | null> {
  return readCacheText(projectId, PARSE_CONTENT);
}

export async function getParseStats(
  projectId: string
): Promise<ParseStats | null> {
  return readCacheJSON<ParseStats>(projectId, PARSE_STATS);
}

export async function saveAnalysis(
  projectId: string,
  data: AnalysisRecord
): Promise<void> {
  await writeCacheJSON(projectId, ANALYSIS_FILE, data);
}

export async function getAnalysis(
  projectId: string
): Promise<AnalysisRecord | null> {
  return readCacheJSON<AnalysisRecord>(projectId, ANALYSIS_FILE);
}

/** 分析进行中增量落库（无 completedAt，刷新后可恢复 thoughts / agents / debate） */
export async function saveAnalysisProgress(
  projectId: string,
  data: Pick<AnalysisRecord, "thoughts"> &
    Partial<Omit<AnalysisRecord, "thoughts">>
): Promise<void> {
  const existing = (await getAnalysis(projectId)) ?? { thoughts: [] };
  await saveAnalysis(projectId, {
    ...existing,
    ...data,
    thoughts: data.thoughts,
  });
}

export interface AnalysisLogExport {
  projectId: string;
  ticker?: string;
  fileName?: string;
  exportedAt: string;
  analysis: AnalysisRecord;
}

/** 导出 IndexedDB 中的 analysis.json 为可下载 JSON 日志 */
export async function exportAnalysisLog(
  projectId: string,
  meta?: Pick<Project, "ticker" | "fileName">
): Promise<boolean> {
  const analysis = await getAnalysis(projectId);
  if (!analysis?.thoughts.length) return false;

  const payload: AnalysisLogExport = {
    projectId,
    ticker: meta?.ticker,
    fileName: meta?.fileName,
    exportedAt: new Date().toISOString(),
    analysis,
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  downloadBlob(
    blob,
    `analysis-log-${projectId}-${Date.now().toString(16)}.json`
  );
  return true;
}

export async function saveReport(
  projectId: string,
  report: ReportData,
  pdfBlob?: Blob
): Promise<void> {
  await writeCacheJSON(projectId, REPORT_JSON, report);
  if (pdfBlob) {
    await writeCacheBlob(projectId, REPORT_PDF, pdfBlob);
  }
}

export async function getReport(
  projectId: string
): Promise<ReportData | null> {
  return readCacheJSON<ReportData>(projectId, REPORT_JSON);
}

export async function getReportPdf(projectId: string): Promise<Blob | null> {
  return readCacheBlob(projectId, REPORT_PDF);
}

export async function deleteProjectData(projectId: string): Promise<void> {
  await deleteProjectCache(projectId);
}

export async function exportProjectBundle(
  project: Project
): Promise<Blob> {
  const zip = new JSZip();
  zip.file("project.json", JSON.stringify(project, null, 2));

  const entries = await exportProjectCacheEntries(project.id);
  for (const entry of entries) {
    const path = `cache/${entry.fileName}`;
    if (entry.kind === "text" && entry.text != null) {
      zip.file(path, entry.text);
    } else if (entry.kind === "json" && entry.json != null) {
      zip.file(path, JSON.stringify(entry.json, null, 2));
    } else if (entry.kind === "blob" && entry.blob) {
      zip.file(path, entry.blob);
    }
  }

  return zip.generateAsync({ type: "blob" });
}

export function getProjectExportFilename(project: Project): string {
  return `${project.fileName.replace(/\.pdf$/i, "")}.ipo-project.zip`;
}

export async function exportProjectsToDestination(
  projects: Project[],
  dirHandle: FileSystemDirectoryHandle | null
): Promise<{ count: number; mode: "directory" | "download" }> {
  const mode = dirHandle ? "directory" : "download";

  for (const project of projects) {
    const blob = await exportProjectBundle(project);
    const filename = getProjectExportFilename(project);
    if (dirHandle) {
      await writeBlobToDirectory(dirHandle, filename, blob);
    } else {
      downloadBlob(blob, filename);
    }
  }

  return { count: projects.length, mode };
}

export async function importProjectBundle(
  file: File,
  onConflict?: (project: Project) => "overwrite" | "rename" | "cancel"
): Promise<Project | null> {
  const zip = await JSZip.loadAsync(file);
  const projectFile = zip.file("project.json");
  if (!projectFile) throw new Error("无效的项目包：缺少 project.json");

  const project = JSON.parse(await projectFile.async("string")) as Project;
  if (!project.id || !project.fileName) {
    throw new Error("无效的项目包：project.json 格式错误");
  }

  if (onConflict) {
    const { getProjectById } = await import("@/data/projects");
    if (getProjectById(project.id)) {
      const action = onConflict(project);
      if (action === "cancel") return null;
      if (action === "rename") {
        project.id = `${project.id}-import-${Date.now().toString(16)}`;
      }
    }
  }

  const cacheFolder = zip.folder("cache");
  if (cacheFolder) {
    await deleteProjectCache(project.id);
    const tasks: Promise<void>[] = [];
    cacheFolder.forEach((relativePath, zipEntry) => {
      if (zipEntry.dir) return;
      tasks.push(
        (async () => {
          if (relativePath.endsWith(".md")) {
            const text = await zipEntry.async("string");
            await importCacheEntry(project.id, relativePath, {
              kind: "text",
              text,
            });
          } else if (relativePath.endsWith(".json")) {
            const json = JSON.parse(await zipEntry.async("string"));
            await importCacheEntry(project.id, relativePath, {
              kind: "json",
              json,
            });
          } else {
            const blob = await zipEntry.async("blob");
            await importCacheEntry(project.id, relativePath, {
              kind: "blob",
              blob,
            });
          }
        })()
      );
    });
    await Promise.all(tasks);
  }

  const { upsertProject } = await import("@/data/projects");
  upsertProject(project);
  return project;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function cacheEntryToImport(
  entry: CacheFileRecord
): Promise<void> {
  if (entry.kind === "text" && entry.text != null) {
    await importCacheEntry(entry.projectId, entry.fileName, {
      kind: "text",
      text: entry.text,
    });
  } else if (entry.kind === "json" && entry.json != null) {
    await importCacheEntry(entry.projectId, entry.fileName, {
      kind: "json",
      json: entry.json,
    });
  } else if (entry.kind === "blob" && entry.blob) {
    await importCacheEntry(entry.projectId, entry.fileName, {
      kind: "blob",
      blob: entry.blob,
    });
  }
}
