/**
 * projectState.ts — 项目运行时状态（解析/分析是否完成）
 * ─────────────────────────────────────────────────────────────
 * 用于避免重复解析：ParseResultPage 据此决定「直接显示完成结果」还是
 * 「播放解析进度动画」。
 *
 * 持久化：状态写入 localStorage，跨刷新、跨会话保持。一旦某项目解析/
 * 分析完成，其结果即「定型」，下次打开直接展示完成态，不再重跑。
 * 仅当某项目从未被记录过时，才从项目 status 推导初始状态。
 *
 * 将来接后端：把这里的 localStorage 读写换成对服务端状态的读取/订阅，
 * 语义完全一致（服务端为真相源，本地为缓存）。
 */
import { getProjectById } from "./projects";
import { readJSON, writeJSON } from "@/lib/storage";

const STORAGE_KEY = "ipo:projectState";

export interface ProjectRuntimeState {
  parseDone: boolean;
  analysisDone: boolean;
}

type StateMap = Record<string, ProjectRuntimeState>;

/** 从 localStorage 读全量状态表 */
function loadAll(): StateMap {
  return readJSON<StateMap>(STORAGE_KEY, {});
}

/** 写回全量状态表 */
function saveAll(map: StateMap): void {
  writeJSON(STORAGE_KEY, map);
}

/** 从项目列表里的 status/进度推导初始状态（仅首次、无持久化记录时使用） */
function deriveFromStatus(id: string): ProjectRuntimeState {
  const p = getProjectById(id);
  if (!p) return { parseDone: false, analysisDone: false };
  return {
    // 解析进度到 100 视为已解析（completed / analyzing 都属于此列）
    parseDone: p.parseProgress >= 100,
    // 仅 completed 视为已完成分析
    analysisDone: p.status === "completed",
  };
}

export function getProjectState(id: string): ProjectRuntimeState {
  const map = loadAll();
  if (map[id]) return map[id];
  // 首次访问：推导初始状态并落盘，之后即以持久化记录为准
  const initial = deriveFromStatus(id);
  map[id] = initial;
  saveAll(map);
  return initial;
}

export function markParseDone(id: string): void {
  const map = loadAll();
  map[id] = { ...(map[id] ?? deriveFromStatus(id)), parseDone: true };
  saveAll(map);
}

export function markAnalysisDone(id: string): void {
  const map = loadAll();
  map[id] = { ...(map[id] ?? deriveFromStatus(id)), analysisDone: true };
  saveAll(map);
}

/** 删除项目时清理其状态记录 */
export function clearProjectState(id: string): void {
  const map = loadAll();
  if (map[id]) {
    delete map[id];
    saveAll(map);
  }
}
