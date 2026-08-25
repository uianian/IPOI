/**
 * localCache.ts — 浏览器内「项目缓存目录」（IndexedDB 实现）
 */
import { openDB, type DBSchema, type IDBPDatabase } from "idb";

const DB_NAME = "ipo-cache";
const DB_VERSION = 1;
const STORE = "files";

interface CacheFileRecord {
  key: string;
  projectId: string;
  fileName: string;
  kind: "text" | "json" | "blob";
  text?: string;
  json?: unknown;
  blob?: Blob;
  updatedAt: string;
}

interface IpoCacheDB extends DBSchema {
  files: {
    key: string;
    value: CacheFileRecord;
    indexes: { "by-project": string };
  };
}

let dbPromise: Promise<IDBPDatabase<IpoCacheDB>> | null = null;

function cacheKey(projectId: string, fileName: string): string {
  return `${projectId}/${fileName}`;
}

function getDb(): Promise<IDBPDatabase<IpoCacheDB>> {
  if (!dbPromise) {
    dbPromise = openDB<IpoCacheDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        const store = db.createObjectStore(STORE, { keyPath: "key" });
        store.createIndex("by-project", "projectId");
      },
    });
  }
  return dbPromise;
}

export async function writeCacheText(
  projectId: string,
  fileName: string,
  text: string
): Promise<void> {
  const db = await getDb();
  await db.put(STORE, {
    key: cacheKey(projectId, fileName),
    projectId,
    fileName,
    kind: "text",
    text,
    updatedAt: new Date().toISOString(),
  });
}

export async function readCacheText(
  projectId: string,
  fileName: string
): Promise<string | null> {
  const db = await getDb();
  const rec = await db.get(STORE, cacheKey(projectId, fileName));
  return rec?.kind === "text" ? (rec.text ?? null) : null;
}

export async function writeCacheJSON(
  projectId: string,
  fileName: string,
  value: unknown
): Promise<void> {
  const db = await getDb();
  await db.put(STORE, {
    key: cacheKey(projectId, fileName),
    projectId,
    fileName,
    kind: "json",
    json: value,
    updatedAt: new Date().toISOString(),
  });
}

export async function readCacheJSON<T>(
  projectId: string,
  fileName: string
): Promise<T | null> {
  const db = await getDb();
  const rec = await db.get(STORE, cacheKey(projectId, fileName));
  if (!rec || rec.kind !== "json") return null;
  return rec.json as T;
}

export async function writeCacheBlob(
  projectId: string,
  fileName: string,
  blob: Blob
): Promise<void> {
  const db = await getDb();
  await db.put(STORE, {
    key: cacheKey(projectId, fileName),
    projectId,
    fileName,
    kind: "blob",
    blob,
    updatedAt: new Date().toISOString(),
  });
}

export async function readCacheBlob(
  projectId: string,
  fileName: string
): Promise<Blob | null> {
  const db = await getDb();
  const rec = await db.get(STORE, cacheKey(projectId, fileName));
  return rec?.kind === "blob" ? (rec.blob ?? null) : null;
}

export async function listProjectFiles(projectId: string): Promise<string[]> {
  const db = await getDb();
  const all = await db.getAllFromIndex(STORE, "by-project", projectId);
  return all.map((r) => r.fileName);
}

export async function deleteProjectCache(projectId: string): Promise<void> {
  const db = await getDb();
  const all = await db.getAllFromIndex(STORE, "by-project", projectId);
  const tx = db.transaction(STORE, "readwrite");
  await Promise.all([...all.map((r) => tx.store.delete(r.key)), tx.done]);
}

export async function exportProjectCacheEntries(
  projectId: string
): Promise<CacheFileRecord[]> {
  const db = await getDb();
  return db.getAllFromIndex(STORE, "by-project", projectId);
}

export async function importCacheEntry(
  projectId: string,
  fileName: string,
  data:
    | { kind: "text"; text: string }
    | { kind: "json"; json: unknown }
    | { kind: "blob"; blob: Blob }
): Promise<void> {
  if (data.kind === "text") {
    await writeCacheText(projectId, fileName, data.text);
  } else if (data.kind === "json") {
    await writeCacheJSON(projectId, fileName, data.json);
  } else {
    await writeCacheBlob(projectId, fileName, data.blob);
  }
}

export type { CacheFileRecord };
