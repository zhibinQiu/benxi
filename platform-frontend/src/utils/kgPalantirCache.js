/** 本体图谱：内存 + sessionStorage 缓存，进入页面优先展示缓存再后台刷新 */

import { trimBoundedMap } from "./boundedMap.js";

const META_CACHE_KEY = "platform:kg-meta:v2";
const ENTITY_LIST_CACHE_KEY = "platform:kg-entity-list:v1";
const GRAPH_CACHE_KEY = "platform:kg-graph:v1";

const META_TTL_MS = 300 * 1000;
const ENTITY_LIST_TTL_MS = 120 * 1000;
const GRAPH_TTL_MS = 300 * 1000;
const ENTITY_LIST_MEM_MAX_ENTRIES = 8;
const GRAPH_CACHE_MAX_ENTRIES = 16;

let memMeta = null;
const memEntityLists = new Map();
const memGraphEntries = new Map();

function isFresh(savedAt, ttlMs) {
  return savedAt && Date.now() - savedAt <= ttlMs;
}

function readSessionEntry(key, ttlMs, { allowStale = false } = {}) {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.savedAt) return null;
    if (!allowStale && !isFresh(parsed.savedAt, ttlMs)) {
      sessionStorage.removeItem(key);
      return null;
    }
    if (allowStale && !isFresh(parsed.savedAt, ttlMs)) {
      return { ...parsed, stale: true };
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeSessionEntry(key, payload, ttlMs) {
  try {
    sessionStorage.setItem(
      key,
      JSON.stringify({ savedAt: Date.now(), ttlMs, ...payload })
    );
  } catch {
    /* quota exceeded — ignore */
  }
}

export function entityListCacheKey(typeId, q) {
  return `${typeId ?? ""}:${String(q || "").trim()}`;
}

function graphEntryKey(focusEntityId, depth) {
  return `${focusEntityId}:${depth}`;
}

export function isKgPalantirMetaCacheFresh() {
  if (memMeta?.data && isFresh(memMeta.savedAt, META_TTL_MS)) return true;
  const session = readSessionEntry(META_CACHE_KEY, META_TTL_MS);
  return Boolean(session?.data);
}

export function readKgMetaCache({ allowStale = false } = {}) {
  if (memMeta?.data) {
    if (allowStale || isFresh(memMeta.savedAt, META_TTL_MS)) return memMeta.data;
  }
  const session = readSessionEntry(META_CACHE_KEY, META_TTL_MS, { allowStale });
  if (session?.data) {
    memMeta = { savedAt: session.savedAt, data: session.data };
    return session.data;
  }
  if (allowStale && memMeta?.data) return memMeta.data;
  return null;
}

export function writeKgMetaCache(data) {
  if (!data) return;
  const savedAt = Date.now();
  memMeta = { savedAt, data };
  writeSessionEntry(META_CACHE_KEY, { data }, META_TTL_MS);
}

export function isKgEntityListCacheFresh(typeId, q) {
  const key = entityListCacheKey(typeId, q);
  const mem = memEntityLists.get(key);
  if (mem?.data && isFresh(mem.savedAt, ENTITY_LIST_TTL_MS)) return true;
  const session = readSessionEntry(
    `${ENTITY_LIST_CACHE_KEY}:${key}`,
    ENTITY_LIST_TTL_MS
  );
  return session?.data !== undefined;
}

export function readKgEntityListCache(typeId, q, { allowStale = false } = {}) {
  const key = entityListCacheKey(typeId, q);
  const mem = memEntityLists.get(key);
  if (mem?.data !== undefined) {
    if (allowStale || isFresh(mem.savedAt, ENTITY_LIST_TTL_MS)) return mem.data;
  }
  const session = readSessionEntry(
    `${ENTITY_LIST_CACHE_KEY}:${key}`,
    ENTITY_LIST_TTL_MS,
    { allowStale }
  );
  if (session?.data !== undefined) {
    memEntityLists.set(key, { savedAt: session.savedAt, data: session.data });
    return session.data;
  }
  if (allowStale && mem?.data !== undefined) return mem.data;
  return null;
}

export function writeKgEntityListCache(typeId, q, data) {
  if (!Array.isArray(data)) return;
  const key = entityListCacheKey(typeId, q);
  const savedAt = Date.now();
  memEntityLists.set(key, { savedAt, data });
  trimBoundedMap(memEntityLists, ENTITY_LIST_MEM_MAX_ENTRIES);
  writeSessionEntry(`${ENTITY_LIST_CACHE_KEY}:${key}`, { data }, ENTITY_LIST_TTL_MS);
}

export function isKgGraphCacheFresh(focusEntityId, depth) {
  if (!focusEntityId) return false;
  const gKey = graphEntryKey(focusEntityId, depth);
  const mem = memGraphEntries.get(gKey);
  if (mem && isFresh(mem.savedAt, GRAPH_TTL_MS)) return true;
  const entry = readSessionEntry(GRAPH_CACHE_KEY, GRAPH_TTL_MS);
  return Boolean(entry?.entries?.[gKey]);
}

export function readKgGraphCache(focusEntityId, depth, { allowStale = false } = {}) {
  if (!focusEntityId) return null;
  const gKey = graphEntryKey(focusEntityId, depth);
  const mem = memGraphEntries.get(gKey);
  if (mem) {
    if (allowStale || isFresh(mem.savedAt, GRAPH_TTL_MS)) return mem.data;
  }
  const entry = readSessionEntry(GRAPH_CACHE_KEY, GRAPH_TTL_MS, { allowStale });
  const hit = entry?.entries?.[gKey];
  if (hit) {
    memGraphEntries.set(gKey, { savedAt: entry.savedAt, data: hit });
    return hit;
  }
  if (allowStale && mem?.data) return mem.data;
  return null;
}

export function writeKgGraphCache(focusEntityId, depth, data) {
  if (!focusEntityId || !data) return;
  const gKey = graphEntryKey(focusEntityId, depth);
  const savedAt = Date.now();
  memGraphEntries.set(gKey, { savedAt, data });
  trimBoundedMap(memGraphEntries, GRAPH_CACHE_MAX_ENTRIES);

  const entry = readSessionEntry(GRAPH_CACHE_KEY, GRAPH_TTL_MS, { allowStale: true }) || {
    entries: {},
  };
  const entries = { ...(entry.entries || {}) };
  entries[gKey] = data;
  const keys = Object.keys(entries);
  if (keys.length > GRAPH_CACHE_MAX_ENTRIES) {
    for (const stale of keys.slice(0, keys.length - GRAPH_CACHE_MAX_ENTRIES)) {
      delete entries[stale];
      memGraphEntries.delete(stale);
    }
  }
  writeSessionEntry(GRAPH_CACHE_KEY, { entries }, GRAPH_TTL_MS);
}

export function clearKgPalantirCache() {
  memMeta = null;
  memEntityLists.clear();
  memGraphEntries.clear();
  try {
    const keys = [];
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i);
      if (
        key &&
        (key === META_CACHE_KEY ||
          key === GRAPH_CACHE_KEY ||
          key.startsWith(`${ENTITY_LIST_CACHE_KEY}:`))
      ) {
        keys.push(key);
      }
    }
    keys.forEach((key) => sessionStorage.removeItem(key));
  } catch {
    /* ignore */
  }
}
