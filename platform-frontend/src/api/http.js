/** HTTP 核心：Token、统一 fetch、错误解析 */

let runtimeApiBase = null;

function normalizeApiBase(raw) {
  const trimmed = raw !== undefined && raw !== null ? String(raw).trim().replace(/\/$/, "") : "";
  return trimmed || "/ai";
}

function resolveApiBase() {
  const raw = import.meta.env.VITE_API_BASE;
  const trimmed =
    raw !== undefined && raw !== null ? String(raw).trim().replace(/\/$/, "") : "";

  if (import.meta.env.PROD) {
    return trimmed || "/ai";
  }

  // 浏览器开发态：走同源 /ai/api 反代，避免直连 127.0.0.1:18000
  // （局域网 IP、远程桌面、IDE 内置浏览器访问 40005 时 127.0.0.1 不可达）
  if (typeof window !== "undefined") {
    return "/ai";
  }

  if (trimmed) return trimmed;
  return "http://127.0.0.1:18000";
}

export function setApiBase(value) {
  runtimeApiBase = normalizeApiBase(value);
}

export function getApiBase() {
  if (runtimeApiBase) return runtimeApiBase;
  return resolveApiBase();
}

/** @deprecated 请使用 getApiBase()，运行时可被服务端配置覆盖 */
export function getApiBaseSnapshot() {
  return getApiBase();
}

/** 应用启动时从平台拉取公开配置（无需登录） */
export async function bootstrapClientConfig() {
  const initial = resolveApiBase();
  try {
    const res = await fetch(`${initial}/api/v1/system/client-config`);
    if (!res.ok) return null;
    const json = await res.json().catch(() => ({}));
    const data = json?.data || {};
    const base = normalizeApiBase(data?.api_base);
    if (base) setApiBase(base);
    return data;
  } catch {
    return null;
  }
}

const TOKEN_KEY = "platform_access_token";
const REFRESH_KEY = "platform_refresh_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access, refresh) {
  localStorage.setItem(TOKEN_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

/** 文档库「个人级」分级（与后端 scope=personal 一致） */
export const DOCUMENT_SCOPE_PERSONAL = "personal";

/** 公众号 / RSS / 网站资讯导入文档库的默认请求体 */
export function buildImportToPersonalLibraryBody(overrides = {}) {
  return {
    scope: DOCUMENT_SCOPE_PERSONAL,
    sync_knowflow: true,
    ...overrides,
  };
}

export function formatApiDetail(detail) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && detail.message) return detail.message;
  if (!Array.isArray(detail)) return null;
  const fieldLabels = {
    phone: "手机号",
    username: "姓名",
    password: "密码",
    display_name: "姓名",
    email: "邮箱",
  };
  return detail
    .map((item) => {
      const loc = Array.isArray(item.loc) ? item.loc : [];
      const field = loc.filter((x) => x !== "body").pop();
      const label = fieldLabels[field] || field || "参数";
      const raw = item.msg || "";
      if (raw.includes("at least 6 characters")) return `${label}至少 6 个字符`;
      if (raw.includes("at least 2 characters")) return `${label}至少 2 个字符`;
      return `${label}：${raw}`;
    })
    .join("；");
}

import { sanitizeUserFacingMessage } from "../utils/uiMessage.js";
import { dispatchSessionReplaced, isSessionReplacedError } from "../utils/sessionGuard.js";

async function parseResponse(res) {
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = formatApiDetail(json?.detail) || json?.message || res.statusText;
    if (res.status === 401 && isSessionReplacedError(json, msg)) {
      dispatchSessionReplaced(msg);
    }
    if (res.status === 503) {
      throw new Error(sanitizeUserFacingMessage(msg, "系统繁忙，请稍后重试"));
    }
    throw new Error(sanitizeUserFacingMessage(msg, "请求失败"));
  }
  if (json.code !== undefined && json.code !== 0) {
    throw new Error(
      sanitizeUserFacingMessage(json.message || "请求失败", "请求失败")
    );
  }
  return json.data;
}

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  let res;
  const base = getApiBase();
  try {
    res = await fetch(`${base}${path}`, { ...options, headers });
  } catch (err) {
    const msg = String(err?.message || "");
    if (/failed to fetch|networkerror|load failed/i.test(msg)) {
      if (base === "/ai" || base.endsWith("/ai")) {
        throw new Error(
          "无法连接 API。请确认已执行 bash scripts/stack.sh dev-up，并通过 http://127.0.0.1:40005/ai/ 访问前端（勿混用其它端口或旧标签页）"
        );
      }
      if (/127\.0\.0\.1:18000|localhost:18000/.test(base)) {
        throw new Error(
          "无法连接开发 API（127.0.0.1:18000）。请执行 bash scripts/stack.sh dev-up 启动完整开发栈，或确认 api 容器已映射 18000 端口"
        );
      }
      throw new Error("无法连接服务器，请确认 API 服务已启动并可访问");
    }
    throw err;
  }
  return parseResponse(res);
}
