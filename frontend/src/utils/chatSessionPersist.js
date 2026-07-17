/** 智能体 / 问答页：sessionStorage 会话恢复（切换功能或刷新标签页后仍可继续） */

import {
  MAX_CHAT_MESSAGES,
  MAX_PERSISTED_MESSAGE_CHARS,
  MAX_VISIBLE_CHAT_MESSAGES,
  trimChatMessages,
} from "./chatMessageLimits.js";

const PREFIX = "platform:chat-session:";

/** 后端 chat-history 已持久化消息的 scope */
export const SERVER_HISTORY_SCOPES = new Set([
  "ai-home",
  "assistant",
  "carbon-qa",
  "smart-data-query",
  "report-generation",
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

export function clearAllChatSessions() {
  try {
    const keys = [];
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i);
      if (key && key.startsWith(PREFIX)) keys.push(key);
    }
    keys.forEach((key) => sessionStorage.removeItem(key));
  } catch {
    /* ignore */
  }
}

/** 首屏同步恢复会话，避免 welcome → 对话区切换造成 CLS */
export function readChatSessionBootstrap(scope, { conversationId: routeConversationId } = {}) {
  const empty = {
    started: false,
    loadingHistory: false,
    messages: [],
    messageWindowStart: 0,
    conversationId: null,
    input: "",
    attachmentSessionId: null,
    attachmentFiles: [],
  };
  if (!scope) return empty;

  const routeCid = String(routeConversationId || "").trim();
  if (routeCid) {
    return {
      ...empty,
      started: true,
      loadingHistory: true,
      conversationId: routeCid,
    };
  }

  const saved = loadChatSession(scope);
  if (!saved) return empty;

  const input = String(saved.input || "");
  const conversationId = saved.conversationId || null;
  const attachmentSessionId = saved.attachmentSessionId || null;
  const attachmentFiles = Array.isArray(saved.attachmentFiles) ? saved.attachmentFiles : [];

  if (SERVER_HISTORY_SCOPES.has(scope) && conversationId) {
    return {
      started: true,
      loadingHistory: true,
      messages: [],
      messageWindowStart: 0,
      conversationId,
      input,
      attachmentSessionId,
      attachmentFiles,
    };
  }

  const rows = Array.isArray(saved.messages) ? saved.messages : [];
  const started = Boolean(saved.started ?? rows.length > 0);
  if (!started || !rows.length) {
    return {
      ...empty,
      input,
      attachmentSessionId,
      attachmentFiles,
    };
  }

  const messages = trimChatMessages(
    rows.map((m) => ({
      role: m.role,
      content: m.content || "",
      streaming: false,
      citations: m.citations,
      error: m.error,
    }))
  );

  return {
    started: true,
    loadingHistory: false,
    messages,
    messageWindowStart: Math.max(0, messages.length - MAX_VISIBLE_CHAT_MESSAGES),
    conversationId,
    input,
    attachmentSessionId,
    attachmentFiles,
  };
}

export function serializeChatMessages(messages) {
  return trimChatMessages(
    (messages || [])
      .filter((m) => m.role === "user" || m.role === "assistant" || m.role === "robot")
      .map((m) => {
        // 流式消息无内容时不写"（生成中断）"占位，避免 tab 切换后恢复显示错误文案
        let content = (m.content || "").trim() ? m.content : "";
        if (content.length > MAX_PERSISTED_MESSAGE_CHARS) {
          content = `${content.slice(0, MAX_PERSISTED_MESSAGE_CHARS)}\n\n…（内容过长，已截断存储）`;
        }
        return {
          role: m.role,
          content,
          citations: Array.isArray(m.citations) ? m.citations.slice(0, 40) : undefined,
          error: m.error,
        };
      })
      .filter((m) => m.content || m.role === "user"),
    MAX_CHAT_MESSAGES
  );
}
