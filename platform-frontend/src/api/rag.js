/** 知识问答 / KnowFlow 嵌入 API */
import { API_BASE, api, formatApiDetail, getToken } from "./http.js";

let ragMetaCache = null;
let ragMetaCacheAt = 0;
const RAG_META_TTL_MS = 15000;

export async function fetchRagMeta({ force = false } = {}) {
  const now = Date.now();
  if (!force && ragMetaCache && now - ragMetaCacheAt < RAG_META_TTL_MS) {
    return ragMetaCache;
  }
  const data = await api("/api/v1/rag/meta");
  ragMetaCache = data;
  ragMetaCacheAt = now;
  return data;
}

export function invalidateRagMetaCache() {
  ragMetaCache = null;
  ragMetaCacheAt = 0;
}

export async function searchKnowledge({ query, scope, limit = 20 } = {}) {
  const body = { query, limit };
  if (scope) body.scope = scope;
  return api("/api/v1/rag/search", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchRagEmbedSession({ sync = false } = {}) {
  const q = sync ? "?sync=true" : "?sync=false";
  return api(`/api/v1/rag/embed-session${q}`);
}

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
