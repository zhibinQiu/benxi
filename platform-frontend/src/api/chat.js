/** 助手、对话历史与辅助写作 REST API */
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

export async function aiHomeChat({ message, history = [], attachmentSessionId = null }) {
  const body = { message, history };
  if (attachmentSessionId) body.attachment_session_id = attachmentSessionId;
  return api("/api/v1/ai-chat/chat", {
    method: "POST",
    body: JSON.stringify(body),
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
