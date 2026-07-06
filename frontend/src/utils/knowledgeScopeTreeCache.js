/** 知识检索 / 报告生成左侧树：内存 + sessionStorage 缓存，进入页面优先展示缓存 */

const CACHE_KEY = "platform:knowledge-scope-tree:v5";
/** 与后端 scope_tree_cache_ttl_sec 默认 300s 对齐 */
const CACHE_TTL_MS = 300 * 1000;

/** 同会话内存缓存：避免 session TTL / 文档变更清 session 后二次打开空白 */
let memCache = null;

export function hasKnowledgeScopeTreeItems(payload) {
  return Array.isArray(payload?.items) && payload.items.length > 0;
}

function isFresh(savedAt) {
  return savedAt && Date.now() - savedAt <= CACHE_TTL_MS;
}

function readSessionRaw() {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.savedAt || !parsed?.data) return null;
    if (!isFresh(parsed.savedAt)) {
      sessionStorage.removeItem(CACHE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/** session / 内存缓存仍在 TTL 内（无需后台强刷） */
export function isKnowledgeScopeTreeCacheFresh() {
  if (memCache?.data && isFresh(memCache.savedAt) && hasKnowledgeScopeTreeItems(memCache.data)) {
    return true;
  }
  const session = readSessionRaw();
  return Boolean(session?.data && hasKnowledgeScopeTreeItems(session.data));
}

/**
 * @param {{ allowStale?: boolean }} [opts]
 * allowStale：文档变更等场景仍展示上次树，后台再刷新
 */
export function readKnowledgeScopeTreeCache({ allowStale = false } = {}) {
  if (memCache?.data) {
    if (allowStale || isFresh(memCache.savedAt)) {
      if (hasKnowledgeScopeTreeItems(memCache.data)) return memCache.data;
    }
  }
  const session = readSessionRaw();
  if (session?.data) {
    if (hasKnowledgeScopeTreeItems(session.data)) {
      memCache = { savedAt: session.savedAt, data: session.data };
      return session.data;
    }
    try {
      sessionStorage.removeItem(CACHE_KEY);
    } catch {
      /* ignore */
    }
  }
  if (allowStale && memCache?.data && hasKnowledgeScopeTreeItems(memCache.data)) {
    return memCache.data;
  }
  return null;
}

export function writeKnowledgeScopeTreeCache(data) {
  if (!hasKnowledgeScopeTreeItems(data)) return;
  const savedAt = Date.now();
  memCache = { savedAt, data };
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ savedAt, data }));
  } catch {
    /* quota exceeded — ignore */
  }
}

/**
 * @param {{ memory?: boolean, session?: boolean }} [opts]
 * 文档变更通知默认只清 session，保留内存供 stale-while-revalidate
 */
export function clearKnowledgeScopeTreeCache({ memory = true, session = true } = {}) {
  if (memory) memCache = null;
  if (!session) return;
  try {
    sessionStorage.removeItem(CACHE_KEY);
  } catch {
    /* ignore */
  }
}
