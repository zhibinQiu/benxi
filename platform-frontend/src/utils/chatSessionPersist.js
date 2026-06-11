/** 智能体 / 问答页：sessionStorage 会话恢复（切换功能或刷新标签页后仍可继续） */

const PREFIX = "platform:chat-session:";

/** 后端 chat-history 已持久化消息的 scope */
export const SERVER_HISTORY_SCOPES = new Set([
  "ai-home",
  "assistant",
  "carbon-qa",
  "smart-data-query",
]);

function storageKey(scope) {
  return `${PREFIX}${scope}`;
}

export function loadChatSession(scope) {
  if (!scope) return null;
  try {
    const raw = sessionStorage.getItem(storageKey(scope));
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function saveChatSession(scope, data) {
  if (!scope) return;
  try {
    sessionStorage.setItem(
      storageKey(scope),
      JSON.stringify({ ...data, savedAt: Date.now() })
    );
  } catch {
    /* quota exceeded */
  }
}

export function clearChatSession(scope) {
  if (!scope) return;
  try {
    sessionStorage.removeItem(storageKey(scope));
  } catch {
    /* ignore */
  }
}

/** 持久化前去掉流式 / 工作流等临时字段 */
export function serializeChatMessages(messages) {
  return (messages || [])
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({
      role: m.role,
      content: (m.content || "").trim() ? m.content : m.streaming ? "（生成中断）" : "",
      citations: m.citations,
      error: m.error,
    }))
    .filter((m) => m.content || m.role === "user");
}
