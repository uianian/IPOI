/**
 * api.ts — Axios HTTP 客户端
 * ─────────────────────────────────────────────────────────────
 * 所有后端 API 调用都通过这个实例发起。
 *
 * 使用方法：
 *   import { apiClient } from "@/lib/api";
 *   const { data } = await apiClient.get("/projects");
 *   const { data } = await apiClient.post("/projects", formData);
 *
 * 对接后端时：
 *   在前端包根目录（与 vite.config.ts 同级）的 .env 中设置 VITE_API_BASE_URL，
 *   例如 VITE_API_BASE_URL=http://localhost:9100/api/v1
 *   如果不设置，默认走 /api/v1（同域部署或由网关转发）。
 */
import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 2分钟超时，大文件上传需要足够时间
  headers: {
    "Content-Type": "application/json",
  },
});

// ============================================================
// 请求拦截器：自动附带认证 token（未来多用户时启用）
// ============================================================
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth:token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ============================================================
// 响应拦截器：统一错误处理
// ============================================================
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 401 → token 过期，清除登录状态（未来启用）
    if (error.response?.status === 401) {
      localStorage.removeItem("auth:token");
    }
    return Promise.reject(error);
  }
);

export { apiClient };
export default apiClient;

export { getLlmConfigPayload } from "@/data/settings";
