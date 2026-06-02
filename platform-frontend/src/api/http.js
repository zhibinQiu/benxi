/** HTTP 核心：Token、统一 fetch、错误解析 */

function resolveApiBase() {
  const raw = import.meta.env.VITE_API_BASE;
  if (raw !== undefined && raw !== null && String(raw).trim() !== "") {
    return String(raw).replace(/\/$/, "");
  }
  return import.meta.env.PROD ? "/ai" : "";
}

export const API_BASE = resolveApiBase();
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

/** 文档库「我的」分级（与后端 scope=personal 一致） */
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

async function parseResponse(res) {
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = formatApiDetail(json?.detail) || json?.message || res.statusText;
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
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  return parseResponse(res);
}
