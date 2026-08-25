/**
 * build-company-data.mjs
 * ─────────────────────────────────────────────────────────────
 * 离线预处理：读取 data/companyinfo.xlsx（中文表头），以 Wind 代码为 key
 * 生成 client/public/company-lookup.json，并建立股票代码 alias 索引。
 *
 * 数据更新后重跑：pnpm build:data
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import XLSX from "xlsx";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const DATA_DIR = path.join(ROOT, "data");
const XLSX_FILE = path.join(DATA_DIR, "companyinfo.xlsx");
const OUT_FILE = path.join(ROOT, "client", "public", "company-lookup.json");

/** xlsx 中文列名 → 内部字段 */
const COLUMN = {
  windCode: "Wind代码",
  stockCode: "股票代码",
  secCode: "证券代码",
  name: "证券简称",
  companyName: "公司中文名称",
  nameEng: "公司英文名称",
  listBoard: "上市板",
  listDate: "上市日期",
  country: "注册地所在国家或地区",
};

/** Excel 日期序列号 → YYYY-MM-DD */
function fmtDate(value) {
  if (value == null || value === "") return "";
  if (typeof value === "number" && value > 1000) {
    const epoch = new Date(Date.UTC(1899, 11, 30));
    const d = new Date(epoch.getTime() + value * 86400000);
    return d.toISOString().slice(0, 10);
  }
  const s = String(value).trim();
  if (/^\d{8}$/.test(s)) {
    return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  return s;
}

/** 股票代码 canonical：1～4 位补零，5 位保持 */
function normalizeStockCode(input) {
  const s = String(input ?? "").trim().toUpperCase();
  if (!s) return "";
  const numeric = s.replace(/\.HK$/i, "");
  if (!/^\d+$/.test(numeric)) return s;
  if (numeric.length === 5) return numeric;
  if (numeric.length <= 4) return numeric.padStart(4, "0");
  return numeric;
}

/** Wind 代码 canonical */
function normalizeWindCode(input) {
  const s = String(input ?? "").trim().toUpperCase();
  if (!s) return "";
  if (s.includes(".")) return s;
  if (/^\d+$/.test(s)) {
    if (s.length === 5) return `${s}.HK`;
    if (s.length <= 4) return `${s.padStart(4, "0")}.HK`;
  }
  return s;
}

function addAlias(aliases, alias, windCode) {
  const key = normalizeStockCode(alias);
  if (!key || key.includes(".")) return;
  if (!aliases[key]) aliases[key] = windCode;
}

function main() {
  if (!fs.existsSync(XLSX_FILE)) {
    console.error(`缺少数据文件：${XLSX_FILE}`);
    console.error("请将 companyinfo.xlsx 放入 data/ 目录后重试。");
    process.exit(1);
  }

  console.log("读取 xlsx ...");
  const wb = XLSX.readFile(XLSX_FILE);
  const sheet = wb.Sheets[wb.SheetNames[0]];
  const rows = XLSX.utils.sheet_to_json(sheet, { defval: "" });
  console.log(`  共 ${rows.length} 行`);

  const records = {};
  const aliases = {};
  let skipped = 0;

  for (const row of rows) {
    const windCode = normalizeWindCode(row[COLUMN.windCode] || row[COLUMN.secCode]);
    if (!windCode) {
      skipped++;
      continue;
    }

    const stockCode = normalizeStockCode(row[COLUMN.stockCode]);
    records[windCode] = {
      windCode,
      stockCode,
      name: String(row[COLUMN.name] ?? ""),
      fullName: String(row[COLUMN.companyName] ?? ""),
      listBoard: String(row[COLUMN.listBoard] ?? ""),
      listDate: fmtDate(row[COLUMN.listDate]),
      companyName: String(row[COLUMN.companyName] ?? ""),
      nameEng: String(row[COLUMN.nameEng] ?? ""),
      foundDate: "",
      legalRep: "",
      country: String(row[COLUMN.country] ?? ""),
    };

    if (stockCode) addAlias(aliases, stockCode, windCode);
    const windNumeric = windCode.replace(/\.HK$/i, "");
    if (windNumeric !== stockCode) addAlias(aliases, windNumeric, windCode);
  }

  const payload = {
    generatedAt: new Date().toISOString(),
    source: "data/companyinfo.xlsx",
    total: Object.keys(records).length,
    aliasCount: Object.keys(aliases).length,
    skipped,
    aliases,
    records,
  };

  fs.mkdirSync(path.dirname(OUT_FILE), { recursive: true });
  fs.writeFileSync(OUT_FILE, JSON.stringify(payload), "utf-8");
  const kb = (fs.statSync(OUT_FILE).size / 1024).toFixed(0);
  console.log(`\n✓ 写入 ${OUT_FILE}`);
  console.log(
    `  记录 ${payload.total} | alias ${payload.aliasCount} | 跳过 ${skipped} | 大小 ${kb} KB`
  );
}

main();
