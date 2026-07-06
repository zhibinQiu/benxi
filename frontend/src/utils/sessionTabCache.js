/** 轻量 session + 内存 Tab 缓存，减少重复请求与 Tab 切换开销 */

const DEFAULT_TTL_MS = 120 * 1000;

export function createSessionTabCache(storageKey, { ttlMs = DEFAULT_TTL_MS, validate } = {}) {
  const isValid = validate || ((data) => data != null);
  let memCache = null;

  function isFresh(savedAt) {
    return savedAt && Date.now() - savedAt <= ttlMs;
  }

  function readSessionRaw() {
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed?.savedAt || !parsed?.data) return null;
      if (!isFresh(parsed.savedAt)) {
        sessionStorage.removeItem(storageKey);
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  }

  function hasData(data) {
    return isValid(data);
  }

  function isFreshCache() {
    if (memCache?.data && isFresh(memCache.savedAt) && hasData(memCache.data)) return true;
    const session = readSessionRaw();
    return Boolean(session?.data && hasData(session.data));
  }

  function read({ allowStale = false } = {}) {
    if (memCache?.data) {
      if (allowStale || isFresh(memCache.savedAt)) {
        if (hasData(memCache.data)) return memCache.data;
      }
    }
    const session = readSessionRaw();
    if (session?.data && hasData(session.data)) {
      memCache = { savedAt: session.savedAt, data: session.data };
      return session.data;
    }
    if (allowStale && memCache?.data && hasData(memCache.data)) {
      return memCache.data;
    }
    return null;
  }

  function write(data) {
    if (!hasData(data)) return;
    const savedAt = Date.now();
    memCache = { savedAt, data };
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({ savedAt, data }));
    } catch {
      /* quota exceeded */
    }
  }

  function clear() {
    memCache = null;
    try {
      sessionStorage.removeItem(storageKey);
    } catch {
      /* ignore */
    }
  }

  return { read, write, isFreshCache, hasData, clear };
}
