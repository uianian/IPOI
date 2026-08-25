import type { ParseResult } from "@/types";
import { apiClient } from "@/lib/api";
import { lookupCompany, normalizeWindCode } from "@/lib/companyLookup";

const PARSE_BASE = "/parse/expert";

export interface StartParseMeta {
  clientProjectId: string;
  ticker: string;
  fileName: string;
  isBiotech: boolean;
  /** 专业模式：纳入文本粉饰度评分；上传时选择，默认 false */
  enableEmbellishment: boolean;
  /** 公司中文名称（lookup 命中时填入） */
  companyName?: string;
  /** 上市日期（lookup 命中时填入） */
  listDate?: string;
}

export interface ParseProgressData {
  progress: number;
  stage: string;
}

export interface StartParseResponse {
  taskId: string;
  status: string;
}

export async function startParse(
  file: File,
  meta: StartParseMeta,
  onUploadProgress?: (percent: number) => void
): Promise<StartParseResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("ticker", normalizeWindCode(meta.ticker));
  form.append("clientProjectId", meta.clientProjectId);
  form.append("fileName", meta.fileName);
  form.append("isBiotech", String(meta.isBiotech));
  form.append("enableEmbellishment", String(meta.enableEmbellishment));
  form.append("companyName", meta.companyName ?? "");
  form.append("listDate", meta.listDate ?? "");

  const { data } = await apiClient.post<{ success: boolean; data: StartParseResponse }>(
    `${PARSE_BASE}/start`,
    form,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => {
        if (e.total && onUploadProgress) {
          onUploadProgress(Math.round((e.loaded / e.total) * 100));
        }
      },
    }
  );
  return data.data;
}

export async function pollParseProgress(
  taskId: string
): Promise<ParseProgressData> {
  const { data } = await apiClient.get<{
    success: boolean;
    data: ParseProgressData;
  }>(`${PARSE_BASE}/tasks/${taskId}/progress`);
  return data.data;
}

export async function fetchParseResult(taskId: string): Promise<ParseResult> {
  const { data } = await apiClient.get<{ success: boolean; data: ParseResult }>(
    `${PARSE_BASE}/tasks/${taskId}/result`
  );
  return data.data;
}

export async function runParsePipeline(
  file: File,
  meta: StartParseMeta,
  onProgress: (progress: number, stage: string) => void
): Promise<ParseResult> {
  const record = await lookupCompany(meta.ticker);
  const enriched: StartParseMeta = {
    ...meta,
    companyName: record?.companyName ?? "",
    listDate: record?.listDate ?? "",
  };

  const { taskId } = await startParse(file, enriched);
  onProgress(0, "PARSING");

  for (;;) {
    await delay(500);
    const { progress, stage } = await pollParseProgress(taskId);
    onProgress(progress, stage);
    if (progress >= 100 && stage === "READY") break;
  }

  return fetchParseResult(taskId);
}

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
