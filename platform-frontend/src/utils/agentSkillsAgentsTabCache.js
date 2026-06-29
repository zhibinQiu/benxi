/** 多智能体「智能体」Tab：内存 + sessionStorage 缓存，再次进入优先展示缓存 */

const CACHE_KEY = "platform:agent-skills-agents-tab:v1";
const CACHE_TTL_MS = 120 * 1000;

let memCache = null;

export function hasAgentsTabCacheData(data) {
  return Array.isArray(data?.agents);
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

export function isAgentsTabCacheFresh() {
  if (memCache?.data && isFresh(memCache.savedAt) && hasAgentsTabCacheData(memCache.data)) {
    return true;
  }
  const session = readSessionRaw();
  return Boolean(session?.data && hasAgentsTabCacheData(session.data));
}

/**
 * @param {{ allowStale?: boolean }} [opts]
 */
export function readAgentsTabCache({ allowStale = false } = {}) {
  if (memCache?.data) {
    if (allowStale || isFresh(memCache.savedAt)) {
      if (hasAgentsTabCacheData(memCache.data)) return memCache.data;
    }
  }
  const session = readSessionRaw();
  if (session?.data) {
    if (hasAgentsTabCacheData(session.data)) {
      memCache = { savedAt: session.savedAt, data: session.data };
      return session.data;
    }
    try {
      sessionStorage.removeItem(CACHE_KEY);
    } catch {
      /* ignore */
    }
  }
  if (allowStale && memCache?.data && hasAgentsTabCacheData(memCache.data)) {
    return memCache.data;
  }
  return null;
}

export function writeAgentsTabCache(data) {
  if (!hasAgentsTabCacheData(data)) return;
  const savedAt = Date.now();
  memCache = { savedAt, data };
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ savedAt, data }));
  } catch {
    /* quota exceeded — ignore */
  }
}

export function clearAgentsTabCache() {
  memCache = null;
  try {
    sessionStorage.removeItem(CACHE_KEY);
  } catch {
    /* ignore */
  }
}
