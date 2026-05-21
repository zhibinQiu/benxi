const API_BASE = import.meta.env.VITE_API_BASE || "";
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

async function parseResponse(res) {
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = json?.message || res.statusText;
    const d = json?.detail;
    if (d && typeof d === "object" && d.message) msg = d.message;
    else if (typeof d === "string") msg = d;
    throw new Error(msg);
  }
  if (json.code !== undefined && json.code !== 0) {
    throw new Error(json.message || "请求失败");
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

export async function login(username, password) {
  return api("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function fetchMe() {
  return api("/api/v1/auth/me");
}

export async function fetchDocuments({ page = 1, page_size = 20, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/documents?${q}`);
}

export async function createDocument(payload) {
  return api("/api/v1/documents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchDocument(id) {
  return api(`/api/v1/documents/${id}`);
}

export async function prepareUpload(documentId, fileName, mimeType) {
  const q = new URLSearchParams({ file_name: fileName, mime_type: mimeType });
  return api(`/api/v1/documents/${documentId}/upload/prepare?${q}`, {
    method: "POST",
  });
}

export async function completeUpload(documentId, body) {
  return api(`/api/v1/documents/${documentId}/upload/complete`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getDownloadUrl(documentId) {
  return api(`/api/v1/documents/${documentId}/download`);
}

export async function deleteDocument(documentId) {
  return api(`/api/v1/documents/${documentId}`, { method: "DELETE" });
}

export async function fetchDocumentPermissions(documentId) {
  return api(`/api/v1/documents/${documentId}/permissions`);
}

export async function grantPermission(documentId, body) {
  return api(`/api/v1/documents/${documentId}/permissions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function revokePermission(documentId, permId) {
  return api(`/api/v1/documents/${documentId}/permissions/${permId}`, {
    method: "DELETE",
  });
}

export async function fetchJobs({ page = 1, page_size = 20, job_type } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (job_type) q.set("job_type", job_type);
  return api(`/api/v1/jobs?${q}`);
}

export async function fetchNotifications({ page = 1, unread_only = false } = {}) {
  const q = new URLSearchParams({ page, page_size: 20 });
  if (unread_only) q.set("unread_only", "true");
  return api(`/api/v1/notifications?${q}`);
}

export async function markNotificationRead(id) {
  return api(`/api/v1/notifications/${id}/read`, { method: "PATCH" });
}

export async function fetchDepartments() {
  return api("/api/v1/departments");
}

export async function createDepartment(body) {
  return api("/api/v1/departments", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchUsers() {
  return api("/api/v1/users");
}

export async function createUser(body) {
  return api("/api/v1/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchRoles() {
  return api("/api/v1/roles");
}

// —— PDF 翻译（经平台代理 pdf2zh）——

export async function fetchTranslateMeta() {
  return api("/api/v1/translate/meta");
}

export async function fetchSystemFeatures() {
  return api("/api/v1/system/features");
}

export async function fetchTranslateJobs({ page = 1, page_size = 20 } = {}) {
  const q = new URLSearchParams({ page, page_size });
  return api(`/api/v1/translate/jobs?${q}`);
}

export async function fetchTranslateDocuments({ page = 1, page_size = 20, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/translate/documents?${q}`);
}

export async function createTranslateJob({
  pdf,
  documentId,
  langIn,
  langOut,
  service,
  glossaries,
}) {
  const form = new FormData();
  if (pdf) form.append("file", pdf);
  if (documentId) form.append("document_id", documentId);
  form.append("lang_in", langIn);
  form.append("lang_out", langOut);
  form.append("service", service);
  for (const g of glossaries || []) {
    form.append("glossary_files", g);
  }
  return api("/api/v1/translate/jobs", { method: "POST", body: form });
}

/** @param {string} platformJobId 平台任务 UUID */
export async function fetchTranslateJob(platformJobId) {
  return api(`/api/v1/translate/jobs/${platformJobId}`);
}

export function subscribeTranslateEvents(platformJobId, { onEvent, onError, onComplete }) {
  const token = getToken();
  const url = `${API_BASE}/api/v1/translate/jobs/${platformJobId}/events${
    token ? `?token=${encodeURIComponent(token)}` : ""
  }`;
  const es = new EventSource(url);
  const types = [
    "progress_update",
    "progress_start",
    "progress_end",
    "finish",
    "error",
    "job_finished",
    "complete",
    "snapshot",
    "files_updated",
  ];
  for (const type of types) {
    es.addEventListener(type, (e) => {
      try {
        const data = JSON.parse(e.data);
        if (type === "complete") onComplete?.(data);
        else onEvent?.({ type, ...data });
      } catch {
        /* ignore */
      }
    });
  }
  es.onerror = () => {
    onError?.(new Error("SSE 连接中断"));
    es.close();
  };
  return () => es.close();
}

export async function downloadTranslateFile(jobId, kind, fallbackName = "download") {
  const res = await fetch(`${API_BASE}/api/v1/translate/jobs/${jobId}/download/${kind}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const match = disp.match(/filename="?([^";]+)"?/);
  const name = match ? match[1] : fallbackName;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
