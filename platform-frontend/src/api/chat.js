/** 助手、对话历史与辅助写作 REST API */
import { api } from "./http.js";

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
