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

function formatApiDetail(detail) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && detail.message) return detail.message;
  if (!Array.isArray(detail)) return null;
  const fieldLabels = {
    username: "用户名",
    password: "密码",
    display_name: "显示名",
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

async function parseResponse(res) {
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = formatApiDetail(json?.detail) || json?.message || res.statusText;
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

export async function registerUser(username, password) {
  return api("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function fetchMe() {
  return api("/api/v1/auth/me");
}

export async function fetchDocumentLibrary() {
  return api("/api/v1/documents/library");
}

export async function fetchDocuments({ page = 1, page_size = 20, keyword, scope } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  if (scope) q.set("scope", scope);
  return api(`/api/v1/documents?${q}`);
}

export async function fetchRecycleDocuments({ page = 1, page_size = 20, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/documents/trash?${q}`);
}

export async function fetchMySharedDocuments({ page = 1, page_size = 20, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/documents/my-shares?${q}`);
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

export async function deleteDocumentVersion(documentId, versionId) {
  return api(`/api/v1/documents/${documentId}/versions/${versionId}`, {
    method: "DELETE",
  });
}

export async function patchDocumentStatus(documentId, status) {
  return api(`/api/v1/documents/${documentId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function updateDocument(documentId, payload) {
  return api(`/api/v1/documents/${documentId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function restoreDocument(documentId) {
  return api(`/api/v1/documents/${documentId}/restore`, { method: "POST" });
}

export async function permanentlyDeleteDocument(documentId) {
  return api(`/api/v1/documents/${documentId}/permanent`, { method: "DELETE" });
}

export async function emptyRecycleBin() {
  return api("/api/v1/documents/trash/empty", { method: "POST" });
}

export async function fetchDocumentAccessControl(documentId) {
  return api(`/api/v1/documents/${documentId}/access-control`);
}

export async function fetchDocumentAclCandidates(documentId) {
  return api(`/api/v1/documents/${documentId}/acl-candidates`);
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

export async function fetchDocumentDenials(documentId) {
  return api(`/api/v1/documents/${documentId}/denials`);
}

export async function denyDocumentAccess(documentId, body) {
  return api(`/api/v1/documents/${documentId}/denials`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function liftDocumentDenial(documentId, userId) {
  return api(`/api/v1/documents/${documentId}/denials/${userId}`, {
    method: "DELETE",
  });
}

export async function fetchJobs({ page = 1, page_size = 20, job_type } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (job_type) q.set("job_type", job_type);
  return api(`/api/v1/jobs?${q}`);
}

export async function clearJobs(scope = "finished") {
  const q = new URLSearchParams({ scope });
  return api(`/api/v1/jobs/clear?${q}`, { method: "DELETE" });
}

export async function cancelJob(jobId) {
  return api(`/api/v1/jobs/${jobId}/cancel`, { method: "POST" });
}

export async function fetchNotifications({ page = 1, page_size = 20, unread_only = false } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (unread_only) q.set("unread_only", "true");
  return api(`/api/v1/notifications?${q}`);
}

export async function markNotificationRead(id) {
  return api(`/api/v1/notifications/${id}/read`, { method: "PATCH" });
}

export async function markAllNotificationsRead() {
  return api("/api/v1/notifications/read-all", { method: "PATCH" });
}

export async function clearNotifications(scope = "read") {
  const q = new URLSearchParams({ scope });
  return api(`/api/v1/notifications/clear?${q}`, { method: "DELETE" });
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

export async function updateDepartment(deptId, body) {
  return api(`/api/v1/departments/${deptId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteDepartment(deptId) {
  return api(`/api/v1/departments/${deptId}`, { method: "DELETE" });
}

export async function fetchAuditLogs(limit = 100) {
  const q = new URLSearchParams({ limit: String(limit) });
  return api(`/api/v1/monitor/audit-logs?${q}`);
}

export async function fetchSystemMetrics() {
  return api("/api/v1/monitor/metrics");
}

export async function fetchTodos(status) {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return api(`/api/v1/todos${q}`);
}

export async function createTodo(body) {
  return api("/api/v1/todos", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateTodo(todoId, body) {
  return api(`/api/v1/todos/${todoId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteTodo(todoId) {
  return api(`/api/v1/todos/${todoId}`, { method: "DELETE" });
}

export async function reorderTodos(status, orderedIds) {
  return api("/api/v1/todos/reorder", {
    method: "POST",
    body: JSON.stringify({ status, ordered_ids: orderedIds }),
  });
}

export async function todoLlmPreview(text, mode) {
  return api("/api/v1/todos/llm", {
    method: "POST",
    body: JSON.stringify({ text, mode }),
  });
}

export async function batchCreateTodos(items) {
  return api("/api/v1/todos/batch", {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export async function replacePendingTodos(items) {
  return api("/api/v1/todos/pending/replace", {
    method: "PUT",
    body: JSON.stringify({ items }),
  });
}

export async function fetchModelSettings() {
  return api("/api/v1/admin/model-settings");
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

export async function updateUser(userId, body) {
  return api(`/api/v1/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteUser(userId) {
  return api(`/api/v1/users/${userId}`, { method: "DELETE" });
}

export async function fetchRoles() {
  return api("/api/v1/roles");
}

// —— 文档对比 ——

export async function fetchCompareDocuments({ page = 1, page_size = 20, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/compare/documents?${q}`);
}

export async function createCompareJob({ leftDocumentId, rightDocumentId, syncKnowflow = true }) {
  return api("/api/v1/compare/jobs", {
    method: "POST",
    body: JSON.stringify({
      left_document_id: leftDocumentId,
      right_document_id: rightDocumentId,
      sync_knowflow: syncKnowflow,
    }),
  });
}

export async function fetchCompareJob(jobId) {
  return api(`/api/v1/compare/jobs/${jobId}`);
}

/** 轮询对比任务直至完成或失败 */
export async function waitCompareJob(jobId, { intervalMs = 1500, timeoutMs = 120000 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const job = await fetchCompareJob(jobId);
    if (job?.status === "done" || job?.status === "failed") {
      return job;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("文档对比超时，请稍后重试");
}

export async function searchCompareJob(jobId, { query, scope = "right", fieldMatch = true }) {
  return api(`/api/v1/compare/jobs/${jobId}/search`, {
    method: "POST",
    body: JSON.stringify({
      query,
      scope,
      field_match: fieldMatch,
    }),
  });
}

/** 右侧目标文档内检索（KnowFlow / 本地），无需先段落比对 */
export async function searchCompareDocuments({
  rightDocumentId,
  query,
  syncKnowflow = true,
  fieldMatch = true,
}) {
  return api("/api/v1/compare/search", {
    method: "POST",
    body: JSON.stringify({
      right_document_id: rightDocumentId,
      query,
      sync_knowflow: syncKnowflow,
      field_match: fieldMatch,
    }),
  });
}

export async function getCompareDocumentDownload(documentId) {
  return api(`/api/v1/compare/documents/${documentId}/download`);
}

export async function fetchCompareDocumentContent(documentId) {
  return api(`/api/v1/compare/documents/${documentId}/content`);
}

/** 带鉴权拉取原文，用于对比页 iframe（blob URL） */
export async function fetchCompareDocumentFileBlob(documentId) {
  const token = getToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/v1/compare/documents/${documentId}/file`, {
    headers,
  });
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    throw new Error(json?.message || res.statusText || "加载文档失败");
  }
  return res.blob();
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

// —— 录音转文字（Whisper API）——

export async function fetchSpeechMeta() {
  return api("/api/v1/speech/meta");
}

export async function transcribeSpeech({ file, language, diarize = true } = {}) {
  const form = new FormData();
  form.append("file", file);
  if (language) form.append("language", language);
  form.append("diarize", diarize ? "true" : "false");
  return api("/api/v1/speech/transcribe", { method: "POST", body: form });
}

export async function summarizeSpeech({ text, style = "minutes", segments = [] } = {}) {
  return api("/api/v1/speech/summarize", {
    method: "POST",
    body: JSON.stringify({ text, style, segments }),
  });
}

export async function saveMeetingRecord(payload) {
  return api("/api/v1/speech/records", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listMeetingRecords({ page = 1, pageSize = 20 } = {}) {
  const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return api(`/api/v1/speech/records?${q}`);
}

export async function fetchMeetingRecord(id) {
  return api(`/api/v1/speech/records/${id}`);
}

export async function deleteMeetingRecord(id) {
  return api(`/api/v1/speech/records/${id}`, { method: "DELETE" });
}

// —— 知识问答（嵌入 KnowFlow / RAGFlow 自带 UI）——

export async function fetchRagMeta() {
  return api("/api/v1/rag/meta");
}

export async function fetchFeatureEmbedMeta(featureId) {
  return api(`/api/v1/system/features/${encodeURIComponent(featureId)}/embed-meta`);
}

export async function fetchRagEmbedSession() {
  return api("/api/v1/rag/embed-session");
}

export async function assistantChat({
  message,
  history = [],
  page_hint = null,
  conversationId = null,
}) {
  const body = { message, history, page_hint };
  if (conversationId) body.conversation_id = conversationId;
  return api("/api/v1/assistant/chat", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function aiHomeChat({ message, history = [] }) {
  return api("/api/v1/ai-chat/chat", {
    method: "POST",
    body: JSON.stringify({ message, history }),
  });
}

/**
 * 平台流式对话（SSE）。onDelta 增量；onDone 结束（可含 conversation_id）；onError 失败。
 */
export function createPlatformChatStream(path) {
  return async function platformChatStream(
    { message, history = [], conversationId = null },
    { onDelta, onReplace, onWorkflow, onDone, onError, signal } = {}
  ) {
    const headers = { "Content-Type": "application/json" };
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const body = { message, history };
    if (conversationId) body.conversation_id = conversationId;

    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal,
    });

    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      const msg = formatApiDetail(json?.detail) || json?.message || res.statusText;
      throw new Error(msg);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("浏览器不支持流式响应");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const block of parts) {
        const line = block
          .split("\n")
          .map((l) => l.trim())
          .find((l) => l.startsWith("data:"));
        if (!line) continue;
        let payload;
        try {
          payload = JSON.parse(line.slice(5).trim());
        } catch {
          continue;
        }
        if (payload.error) {
          onError?.(new Error(payload.error));
          return;
        }
        if (payload.workflow) onWorkflow?.(payload.workflow);
        if (payload.replace != null) onReplace?.(payload.replace);
        if (payload.delta) onDelta?.(payload.delta);
        if (payload.done) {
          onDone?.(payload);
          return;
        }
      }
    }
    onDone?.({});
  };
}

export const aiHomeChatStream = createPlatformChatStream("/api/v1/ai-chat/chat/stream");

export const smartDataQueryChatStream = createPlatformChatStream(
  "/api/v1/smart-data-query/chat/stream"
);

export const carbonQaChatStream = createPlatformChatStream(
  "/api/v1/carbon-qa/chat/stream"
);

export async function fetchChatConversations(scope, { limit = 30 } = {}) {
  const q = limit ? `?limit=${encodeURIComponent(limit)}` : "";
  return api(`/api/v1/chat-history/${encodeURIComponent(scope)}/conversations${q}`);
}

export async function fetchChatConversationMessages(scope, conversationId) {
  return api(
    `/api/v1/chat-history/${encodeURIComponent(scope)}/conversations/${encodeURIComponent(conversationId)}/messages`
  );
}

/** @deprecated 使用 smartDataQueryChatStream */
export const smartDataQueryV2ChatStream = smartDataQueryChatStream;

/** @deprecated 使用 carbonQaChatStream */
export const carbonQaV2ChatStream = carbonQaChatStream;

export async function fetchAssistWritingPresets() {
  return api("/api/v1/assist-writing/presets");
}

export async function assistWritingCompose(body) {
  return api("/api/v1/assist-writing/compose", {
    method: "POST",
    body: JSON.stringify(body),
  });
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
