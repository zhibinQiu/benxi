/**
 * 平台 API 聚合入口（兼容既有 `from "../api/client"`）。
 * 新代码请按域引用：`api/http.js`、`api/documents.js`、`api/rag.js`。
 */
export * from "./http.js";
export * from "./auth.js";
export * from "./documents.js";
export * from "./rag.js";
export * from "./dataAnalysis.js";

import { api, formatApiDetail, getApiBase, getToken } from "./http.js";

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

export async function updateModelSettings(payload) {
  return api("/api/v1/admin/model-settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function fetchResourceHealth() {
  return api("/api/v1/admin/model-settings/health");
}

export async function testResourceHealth(resourceId, draft = {}) {
  return api("/api/v1/admin/model-settings/health/test", {
    method: "POST",
    body: JSON.stringify({ resource_id: resourceId, draft }),
  });
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
  const res = await fetch(`${getApiBase()}/api/v1/compare/documents/${documentId}/file`, {
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

export async function fetchCarbonAssetOverview() {
  return api("/api/v1/carbon-assets/overview");
}

export async function fetchCarbonAssetHoldings() {
  return api("/api/v1/carbon-assets/holdings");
}

export async function fetchCarbonAssetMarket({ refresh = false } = {}) {
  const q = refresh ? "?refresh=true" : "";
  return api(`/api/v1/carbon-assets/market${q}`);
}

export async function fetchCarbonAssetHistory(assetCode, { days = 90 } = {}) {
  const q = new URLSearchParams({ days: String(days) });
  return api(`/api/v1/carbon-assets/market/${encodeURIComponent(assetCode)}/history?${q}`);
}

export async function fetchCarbonAssetTrades() {
  return api("/api/v1/carbon-assets/trades");
}

export async function createCarbonAssetTrade(body) {
  return api("/api/v1/carbon-assets/trades", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function resetCarbonAssetDemo() {
  return api("/api/v1/carbon-assets/demo/reset", { method: "POST" });
}

export async function parseWechatMpUrl(url) {
  return api("/api/v1/wechat-mp/parse-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function fetchWechatMpSources() {
  return api("/api/v1/wechat-mp/sources");
}

export async function createWechatMpSource({ name, sample_url, biz }) {
  return api("/api/v1/wechat-mp/sources", {
    method: "POST",
    body: JSON.stringify({ name, sample_url, biz: biz || undefined }),
  });
}

export async function deleteWechatMpSource(sourceId) {
  return api(`/api/v1/wechat-mp/sources/${sourceId}`, { method: "DELETE" });
}

export async function syncWechatMpSource(sourceId) {
  return api(`/api/v1/wechat-mp/sources/${sourceId}/sync`, { method: "POST" });
}

export async function fetchWechatMpArticles({ page = 1, page_size = 20, source_id } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (source_id) q.set("source_id", source_id);
  return api(`/api/v1/wechat-mp/articles?${q}`);
}

export async function fetchWechatMpArticle(articleId) {
  return api(`/api/v1/wechat-mp/articles/${articleId}`);
}

export async function ingestWechatMpUrl(url) {
  return api("/api/v1/wechat-mp/articles/ingest-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function importWechatMpArticle(articleId, body = {}) {
  return api(`/api/v1/wechat-mp/articles/${articleId}/import`, {
    method: "POST",
    body: JSON.stringify(buildImportToPersonalLibraryBody(body)),
  });
}

export async function fetchFeedPresets() {
  return api("/api/v1/feed-subscriptions/presets");
}

export async function fetchFeedSources({ kind } = {}) {
  const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  return api(`/api/v1/feed-subscriptions/sources${q}`);
}

export async function createFeedSubscription(body) {
  return api("/api/v1/feed-subscriptions/sources", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function subscribeFeedPreset(index) {
  return api(`/api/v1/feed-subscriptions/presets/${index}`, { method: "POST" });
}

export async function deleteFeedSubscription(sourceId) {
  return api(`/api/v1/feed-subscriptions/sources/${sourceId}`, { method: "DELETE" });
}

export async function syncFeedSubscription(sourceId) {
  return api(`/api/v1/feed-subscriptions/sources/${sourceId}/sync`, { method: "POST" });
}

export async function fetchFeedEntries({ page = 1, page_size = 20, source_id, kind } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (source_id) q.set("source_id", source_id);
  if (kind) q.set("kind", kind);
  return api(`/api/v1/feed-subscriptions/entries?${q}`);
}

export async function fetchFeedEntry(entryId) {
  return api(`/api/v1/feed-subscriptions/entries/${entryId}`);
}

export async function importFeedEntry(entryId, body = {}) {
  return api(`/api/v1/feed-subscriptions/entries/${entryId}/import`, {
    method: "POST",
    body: JSON.stringify(buildImportToPersonalLibraryBody(body)),
  });
}

/** 统一资讯订阅：粘贴链接收录 */
export async function ingestSubscriptionUrl(url) {
  return api("/api/v1/subscriptions/ingest-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function fetchSubscriptionItems({
  page = 1,
  page_size = 20,
  keyword,
  created_from,
  created_to,
} = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  if (created_from) q.set("created_from", created_from);
  if (created_to) q.set("created_to", created_to);
  return api(`/api/v1/subscriptions/items?${q}`);
}

export async function fetchSubscriptionItem(ref) {
  return api(`/api/v1/subscriptions/items/${encodeURIComponent(ref)}`);
}

export async function importSubscriptionItem(ref, body = {}) {
  return api(`/api/v1/subscriptions/items/${encodeURIComponent(ref)}/import`, {
    method: "POST",
    body: JSON.stringify({
      sync_knowflow: body.sync_knowflow !== false,
      ...body,
    }),
  });
}

export async function deleteSubscriptionItem(ref) {
  return api(`/api/v1/subscriptions/items/${encodeURIComponent(ref)}`, {
    method: "DELETE",
  });
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
  const url = `${getApiBase()}/api/v1/translate/jobs/${platformJobId}/events${
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

export async function fetchFeatureEmbedMeta(featureId) {
  return api(`/api/v1/system/features/${encodeURIComponent(featureId)}/embed-meta`);
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

export async function fetchChatConversations(scope, { limit = 30 } = {}) {
  const q = limit ? `?limit=${encodeURIComponent(limit)}` : "";
  return api(`/api/v1/chat-history/${encodeURIComponent(scope)}/conversations${q}`);
}

export async function fetchChatConversationMessages(scope, conversationId) {
  return api(
    `/api/v1/chat-history/${encodeURIComponent(scope)}/conversations/${encodeURIComponent(conversationId)}/messages`
  );
}

export async function deleteChatConversation(scope, conversationId) {
  return api(
    `/api/v1/chat-history/${encodeURIComponent(scope)}/conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" }
  );
}

export async function clearChatConversations(scope) {
  return api(`/api/v1/chat-history/${encodeURIComponent(scope)}/conversations`, {
    method: "DELETE",
  });
}

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
  const res = await fetch(`${getApiBase()}/api/v1/translate/jobs/${jobId}/download/${kind}`, {
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
