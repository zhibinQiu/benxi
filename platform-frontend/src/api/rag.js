/** 知识问答 / KnowFlow 嵌入 API */
import { api, getApiBase, getToken, rejectHttpFailure } from "./http.js";

let ragMetaCache = null;
let ragMetaCacheAt = 0;
const RAG_META_TTL_MS = 15000;

let embedSessionCache = null;
let embedSessionCacheAt = 0;
const EMBED_SESSION_TTL_MS = 30 * 60 * 1000;

let prefetchInflight = null;

export async function fetchRagMeta({ force = false } = {}) {
  const now = Date.now();
  if (!force && ragMetaCache && now - ragMetaCacheAt < RAG_META_TTL_MS) {
    return ragMetaCache;
  }
  const data = await api("/api/v1/knowledge/meta");
  ragMetaCache = data;
  ragMetaCacheAt = now;
  return data;
}

export function getCachedRagMeta() {
  const now = Date.now();
  if (ragMetaCache && now - ragMetaCacheAt < RAG_META_TTL_MS) {
    return ragMetaCache;
  }
  return null;
}

export function invalidateRagMetaCache() {
  ragMetaCache = null;
  ragMetaCacheAt = 0;
}

export function getCachedRagEmbedSession() {
  const now = Date.now();
  if (embedSessionCache && now - embedSessionCacheAt < EMBED_SESSION_TTL_MS) {
    return embedSessionCache;
  }
  return null;
}

export function invalidateKnowflowSessionCache() {
  embedSessionCache = null;
  embedSessionCacheAt = 0;
  prefetchInflight = null;
}

export function invalidateRagCaches() {
  invalidateRagMetaCache();
  invalidateKnowflowSessionCache();
}

/** 登录后后台预热 KnowFlow SSO + 分级库（不阻塞界面）。 */
export function prefetchKnowflowSession() {
  if (!getToken()) {
    return Promise.resolve(null);
  }
  const cached = getCachedRagEmbedSession();
  if (cached?.sso?.ready) {
    return Promise.resolve(cached);
  }
  if (prefetchInflight) {
    return prefetchInflight;
  }
  prefetchInflight = (async () => {
    try {
      const meta = await fetchRagMeta();
      if (!meta?.knowflow_enabled && !meta?.ui_available) {
        return null;
      }
      return await fetchRagEmbedSession({ sync: false, force: true });
    } catch {
      return null;
    } finally {
      prefetchInflight = null;
    }
  })();
  return prefetchInflight;
}

export async function fetchRagEmbedSession({ sync = false, force = false } = {}) {
  const now = Date.now();
  if (
    !sync &&
    !force &&
    embedSessionCache &&
    now - embedSessionCacheAt < EMBED_SESSION_TTL_MS
  ) {
    return embedSessionCache;
  }
  if (prefetchInflight && !sync && !force) {
    const prefetched = await prefetchInflight;
    if (prefetched?.sso?.ready) {
      return prefetched;
    }
  }
  const q = sync ? "?sync=true" : "?sync=false";
  const data = await api(`/api/v1/knowledge/embed-session${q}`);
  if (!sync) {
    embedSessionCache = data;
    embedSessionCacheAt = Date.now();
  }
  return data;
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

    const res = await fetch(`${getApiBase()}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal,
    });

    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      rejectHttpFailure(res, json);
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
        if (payload.citations) onCitations?.(payload.citations);
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
