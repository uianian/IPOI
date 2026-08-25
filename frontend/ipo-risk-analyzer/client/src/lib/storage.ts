/**
 * storage.ts — localStorage 持久化小工具
 * ─────────────────────────────────────────────────────────────
 * 在没有真实后端前，用 localStorage 充当「数据库」，让项目与解析/分析
 * 状态跨刷新、跨会话保持。将来接后端时，只需把 projects / projectState
 * 里的读写换成网络请求，页面逻辑不变。
 *
 * 所有读写都做异常兜底：localStorage 不可用（隐私模式、配额满）时
 * 退化为「读到空 / 写入静默失败」，不影响页面运行。
 */

/** 安全读取并反序列化；失败返回 fallback */
export function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/** 安全序列化并写入；失败静默忽略 */
export function writeJSON(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage 不可用或配额满：忽略，不阻塞页面
  }
}
