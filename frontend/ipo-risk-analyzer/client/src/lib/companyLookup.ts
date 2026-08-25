/**
 * companyLookup.ts — 按 Wind 代码 / 股票代码查询公司基础信息
 * ─────────────────────────────────────────────────────────────
 * 数据来自 public/company-lookup.json（由 scripts/build-company-data.mjs 生成，
 * 源文件 data/companyinfo.xlsx）。懒加载 + 内存缓存。
 */
import type { CompanyRecord, CompanyLookupData } from "@/types";

let cache: CompanyLookupData | null = null;
let inflight: Promise<CompanyLookupData> | null = null;

/** 加载查询数据（缓存 + 去重并发） */
export async function loadLookup(): Promise<CompanyLookupData> {
  if (cache) return cache;
  if (inflight) return inflight;
  inflight = fetch("/company-lookup.json")
    .then((res) => {
      if (!res.ok) throw new Error(`加载数据失败：HTTP ${res.status}`);
      return res.json() as Promise<CompanyLookupData>;
    })
    .then((data) => {
      cache = data;
      inflight = null;
      return data;
    })
    .catch((err) => {
      inflight = null;
      throw err;
    });
  return inflight;
}

/**
 * 规范化 Wind 代码：去空格转大写；已含 `.` 则原样保留。
 * 纯数字：1–4 位左补零至 4 位 + `.HK`；5 位不截断，直接 + `.HK`。
 */
export function normalizeWindCode(input: string): string {
  const s = input.trim().toUpperCase();
  if (!s) return "";
  if (s.includes(".")) return s;
  if (/^\d+$/.test(s)) {
    if (s.length === 5) return `${s}.HK`;
    if (s.length <= 4) return `${s.padStart(4, "0")}.HK`;
  }
  return s;
}

/** 股票代码 canonical：4 位及以下左补零，5 位保留。 */
export function normalizeStockCode(input: string): string {
  const s = input.trim().toUpperCase();
  if (!s) return "";
  const numeric = s.replace(/\.HK$/i, "");
  if (!/^\d+$/.test(numeric)) return s;
  if (numeric.length === 5) return numeric;
  if (numeric.length <= 4) return numeric.padStart(4, "0");
  return numeric;
}

/** 创建项目前的 ticker 格式校验（纯数字 1–5 位或 Wind 代码）。 */
export function isValidTickerInput(input: string): boolean {
  const s = input.trim().toUpperCase();
  if (!s) return false;
  if (s.includes(".")) return /^[A-Z0-9]+\.[A-Z]+$/.test(s);
  if (/^\d+$/.test(s)) return s.length >= 1 && s.length <= 5;
  return false;
}

/** 按 Wind 代码或股票 alias 查询公司记录，未找到返回 null */
export async function lookupCompany(
  input: string
): Promise<CompanyRecord | null> {
  const data = await loadLookup();
  const wind = normalizeWindCode(input);
  if (wind && data.records[wind]) return data.records[wind];

  const stock = normalizeStockCode(input);
  if (stock && data.aliases?.[stock]) {
    const aliasWind = data.aliases[stock];
    return data.records[aliasWind] ?? null;
  }
  return null;
}

/**
 * 解析用户输入为后端 ticker：lookup 命中时用 record.windCode，
 * 否则按 normalizeWindCode 规则出站。
 */
export async function resolveTickerForBackend(input: string): Promise<string> {
  const trimmed = input.trim();
  if (!isValidTickerInput(trimmed)) {
    throw new Error("INVALID_TICKER");
  }
  const record = await lookupCompany(trimmed);
  if (record) return record.windCode;
  return normalizeWindCode(trimmed);
}
