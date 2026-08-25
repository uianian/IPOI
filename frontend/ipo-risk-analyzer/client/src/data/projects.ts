import type { Project } from "@/types";
import { normalizeWindCode } from "@/lib/companyLookup";
import { readJSON, writeJSON } from "@/lib/storage";

const STORAGE_KEY = "ipo:projects";

let projects: Project[] = (() => {
  const stored = readJSON<Project[] | null>(STORAGE_KEY, null);
  if (stored && Array.isArray(stored)) {
    return stored.map(normalizeProject);
  }
  return [];
})();

function normalizeProject(p: Project): Project {
  return {
    ...p,
    parseMode: "expert",
    parseProgress: p.parseProgress ?? 0,
    isBiotech: p.isBiotech ?? false,
    enableEmbellishment: p.enableEmbellishment ?? false,
  };
}

function persist(): void {
  writeJSON(STORAGE_KEY, projects);
}

export function getProjects(): Project[] {
  return [...projects];
}

export function getProjectById(id: string): Project | undefined {
  return projects.find((p) => p.id === id);
}

/** 列表/对话框展示用：有 projectName 用自定义名，否则 PDF 文件名 */
export function getProjectDisplayName(project: Project): string {
  return project.projectName?.trim() || project.fileName;
}

export function createProject(
  fileName: string,
  ticker: string,
  isBiotech: boolean = false,
  projectName?: string,
  enableEmbellishment: boolean = false
): Project {
  const trimmedName = projectName?.trim();
  const project: Project = {
    id: `proj-${Date.now().toString(16)}`,
    fileName,
    ...(trimmedName ? { projectName: trimmedName } : {}),
    ticker: normalizeWindCode(ticker),
    uploadTime: new Date().toISOString(),
    parseCompleteTime: undefined,
    status: "uploading",
    parseProgress: 0,
    parseMode: "expert",
    isBiotech,
    enableEmbellishment,
    parseDone: false,
    analysisDone: false,
  };
  projects = [project, ...projects];
  persist();
  return project;
}

export function upsertProject(project: Project): void {
  const idx = projects.findIndex((p) => p.id === project.id);
  const normalized = normalizeProject(project);
  if (idx >= 0) {
    projects[idx] = normalized;
  } else {
    projects = [normalized, ...projects];
  }
  persist();
}

export function updateProject(
  id: string,
  patch: Partial<Project>
): Project | undefined {
  const p = projects.find((x) => x.id === id);
  if (!p) return undefined;
  Object.assign(p, patch);
  persist();
  return p;
}

export function deleteProject(id: string): boolean {
  const before = projects.length;
  projects = projects.filter((p) => p.id !== id);
  if (projects.length === before) return false;
  persist();
  return true;
}
