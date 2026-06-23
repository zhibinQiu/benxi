/** 本体图谱：sessionStorage 缓存，进入页面或切换实体时先展示缓存再后台刷新 */

const META_CACHE_KEY = "platform:kg-meta:v1";
const GRAPH_CACHE_KEY = "platform:kg-graph:v1";
const CACHE_TTL_MS = 120 * 1000;
const GRAPH_CACHE_MAX_ENTRIES = 16;

function readEntry(key) {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.savedAt) return null;
    if (Date.now() - parsed.savedAt > CACHE_TTL_MS) {
      sessionStorage.removeItem(key);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeEntry(key, payload) {
  try {
    sessionStorage.setItem(
      key,
      JSON.stringify({ savedAt: Date.now(), ...payload })
    );
  } catch {
    /* quota exceeded — ignore */
  }
}

export function readKgMetaCache() {
  return readEntry(META_CACHE_KEY)?.data ?? null;
}

export function writeKgMetaCache(data) {
  if (!data) return;
  writeEntry(META_CACHE_KEY, { data });
}

function graphEntryKey(focusEntityId, depth) {
  return `${focusEntityId}:${depth}`;
}

export function readKgGraphCache(focusEntityId, depth) {
  if (!focusEntityId) return null;
  const entry = readEntry(GRAPH_CACHE_KEY);
  const hit = entry?.entries?.[graphEntryKey(focusEntityId, depth)];
  return hit ?? null;
}

export function writeKgGraphCache(focusEntityId, depth, data) {
  if (!focusEntityId || !data) return;
  const entry = readEntry(GRAPH_CACHE_KEY) || { entries: {} };
  const entries = { ...(entry.entries || {}) };
  entries[graphEntryKey(focusEntityId, depth)] = data;
  const keys = Object.keys(entries);
  if (keys.length > GRAPH_CACHE_MAX_ENTRIES) {
    for (const stale of keys.slice(0, keys.length - GRAPH_CACHE_MAX_ENTRIES)) {
      delete entries[stale];
    }
  }
  writeEntry(GRAPH_CACHE_KEY, { entries });
}

export function clearKgPalantirCache() {
  try {
    sessionStorage.removeItem(META_CACHE_KEY);
    sessionStorage.removeItem(GRAPH_CACHE_KEY);
  } catch {
    /* ignore */
  }
}
