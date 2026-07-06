/** 助手、数字机器人与对话历史 REST API */
import { api } from "./http.js";

export async function assistantChat({
  message,
  history = [],
  page_hint = null,
  conversationId = null,
  signal = null,
}) {
  const body = { message, history, page_hint };
  if (conversationId) body.conversation_id = conversationId;
  return api("/api/v1/assistant/chat", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

/** 数字机器人对话 — 描述 RPA 任务，AI 生成执行计划 */
export async function digitalRobotChat({
  message,
  history = [],
  conversationId = null,
  signal = null,
}) {
  const body = { message, history };
  if (conversationId) body.conversation_id = conversationId;
  return api("/api/v1/digital-robot/chat", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

/** 数字机器人确认执行 RPA 计划 */
export async function digitalRobotConfirm({
  conversationId,
  plan,
  taskId = null,
}) {
  const body = { conversation_id: conversationId, plan };
  if (taskId) body.task_id = taskId;
  return api("/api/v1/digital-robot/confirm", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** ── RPA 任务管理 ───────────────────────────────── */

/** 列出当前用户的 RPA 任务 */
export async function fetchDigitalRobotTasks({ status = "all", limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ status, limit: String(limit), offset: String(offset) });
  return api(`/api/v1/digital-robot/tasks?${params.toString()}`);
}

/** 获取单个 RPA 任务详情 */
export async function fetchDigitalRobotTask(taskId) {
  return api(`/api/v1/digital-robot/tasks/${encodeURIComponent(taskId)}`);
}

/** 创建 RPA 任务 */
export async function createDigitalRobotTask(data) {
  return api("/api/v1/digital-robot/tasks", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/** 更新 RPA 任务 */
export async function updateDigitalRobotTask(taskId, data) {
  return api(`/api/v1/digital-robot/tasks/${encodeURIComponent(taskId)}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/** 删除 RPA 任务 */
export async function deleteDigitalRobotTask(taskId) {
  return api(`/api/v1/digital-robot/tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });
}

/** 立即执行 RPA 任务 */
export async function executeDigitalRobotTaskNow(taskId) {
  return api(`/api/v1/digital-robot/tasks/${encodeURIComponent(taskId)}/execute`, {
    method: "POST",
  });
}

const AI_CHAT_ATTACHMENT_ACCEPT =
  ".pdf,.doc,.docx,.txt,.md,.markdown,.csv,.html,.htm,.xlsx,.xls,.xlsm,.pptx,.rtf,.json,.xml,.yaml,.yml,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tif,.tiff";

export { AI_CHAT_ATTACHMENT_ACCEPT };

export async function uploadAiChatAttachments(files, { attachmentSessionId = null } = {}) {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  if (attachmentSessionId) {
    form.append("attachment_session_id", attachmentSessionId);
  }
  return api("/api/v1/ai-chat/attachments/upload", {
    method: "POST",
    body: form,
    timeoutMs: 180000,
  });
}

export async function fetchAiChatAttachments(attachmentSessionId) {
  return api(`/api/v1/ai-chat/attachments/${encodeURIComponent(attachmentSessionId)}`);
}

export async function removeAiChatAttachmentFile(attachmentSessionId, fileId) {
  return api(
    `/api/v1/ai-chat/attachments/${encodeURIComponent(attachmentSessionId)}/files/${encodeURIComponent(fileId)}`,
    { method: "DELETE" }
  );
}

export async function clearAiChatAttachments(attachmentSessionId) {
  return api(`/api/v1/ai-chat/attachments/${encodeURIComponent(attachmentSessionId)}`, {
    method: "DELETE",
  });
}

export async function fetchAiChatSkillCatalog() {
  return api("/api/v1/ai-chat/skills/catalog");
}

export async function fetchAiChatAgentCatalog() {
  return api("/api/v1/ai-chat/agents/catalog");
}

export async function fetchChatConversations(scope, { limit = 30 } = {}) {
  const q = limit ? `?limit=${encodeURIComponent(limit)}` : "";
  return api(`/api/v1/chat-history/${encodeURIComponent(scope)}/conversations${q}`);
}

export async function fetchChatConversationMessages(
  scope,
  conversationId,
  { limit = 48, beforeId = null } = {}
) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (beforeId) params.set("before_id", beforeId);
  return api(
    `/api/v1/chat-history/${encodeURIComponent(scope)}/conversations/${encodeURIComponent(conversationId)}/messages?${params.toString()}`
  );
}

export async function deleteChatConversation(scope, conversationId) {
  return api(
    `/api/v1/chat-history/${encodeURIComponent(scope)}/conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" }
  );
}

/** Human-in-the-Loop: 用户确认或拒绝 AI 工具执行 */
export async function confirmToolExecution(confirmationId, accepted) {
  return api(`/api/v1/ai-chat/chat/tools/${encodeURIComponent(confirmationId)}/confirm`, {
    method: "POST",
    body: JSON.stringify({ accepted }),
  });
}

/** Human-in-the-Loop: 用户在 AI 提供的多个方案中选择一个 */
export async function chooseToolOption(choiceId, choice) {
  return api(`/api/v1/ai-chat/chat/tools/${encodeURIComponent(choiceId)}/choose`, {
    method: "POST",
    body: JSON.stringify({ choice }),
  });
}
