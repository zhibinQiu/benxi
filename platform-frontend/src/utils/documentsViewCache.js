/** 文档中心：sessionStorage 缓存，进入时先展示缓存，手动刷新或变更后再拉取 */

import { trimBoundedMap } from "./boundedMap.js";

const LIBRARY_KEY = "platform:documents-library:v1";
const KB_FOLDERS_PREFIX = "platform:documents-kb-folders:v1:";
const DOC_LIST_PREFIX = "platform:documents-list:v1:";

const LIBRARY_TTL_MS = 120 * 1000;
const KB_FOLDERS_TTL_MS = 45 * 1000;
const DOC_LIST_TTL_MS = 60 * 1000;
const DOC_LIST_MEM_TTL_MS = 5 * 60 * 1000;
const DOC_LIST_MEM_MAX_ENTRIES = 24;

/** 同会话内存缓存，避免 sessionStorage 读写与 TTL 导致的二次打开延迟 */
const memListCache = new Map();

function readEntry(key, ttlMs) {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.savedAt || parsed.data === undefined) return null;
    if (Date.now() - parsed.savedAt > ttlMs) {
      sessionStorage.removeItem(key);
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}

function writeEntry(key, data) {
  if (data === undefined) return;
  try {
    sessionStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), data }));
  } catch {
    /* quota exceeded */
  }
}

export function kbFoldersCacheKey(scope, deptId, ownerId) {
  return `${scope}:${deptId || ""}:${ownerId || ""}`;
}

export function readDocumentsLibraryCache() {
  return readEntry(LIBRARY_KEY, LIBRARY_TTL_MS);
}

export function writeDocumentsLibraryCache(data) {
  writeEntry(LIBRARY_KEY, data);
}

export function readDocumentsKbFoldersCache(scope, deptId, ownerId) {
  return readEntry(
    `${KB_FOLDERS_PREFIX}${kbFoldersCacheKey(scope, deptId, ownerId)}`,
    KB_FOLDERS_TTL_MS
  );
}

export function writeDocumentsKbFoldersCache(scope, deptId, ownerId, data) {
  writeEntry(
    `${KB_FOLDERS_PREFIX}${kbFoldersCacheKey(scope, deptId, ownerId)}`,
    data
  );
}

export function readDocumentsListCache(cacheKey) {
  const mem = memListCache.get(cacheKey);
  if (mem?.data !== undefined && Date.now() - mem.savedAt <= DOC_LIST_MEM_TTL_MS) {
    return mem.data;
  }
  const data = readEntry(`${DOC_LIST_PREFIX}${cacheKey}`, DOC_LIST_TTL_MS);
  if (data !== null) {
    memListCache.set(cacheKey, { savedAt: Date.now(), data });
  }
  return data;
}

export function writeDocumentsListCache(cacheKey, data) {
  memListCache.set(cacheKey, { savedAt: Date.now(), data });
  trimBoundedMap(memListCache, DOC_LIST_MEM_MAX_ENTRIES);
  writeEntry(`${DOC_LIST_PREFIX}${cacheKey}`, data);
}

export function clearDocumentsViewCache() {
  memListCache.clear();
  try {
    const keys = [];
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i);
      if (
        key &&
        (key === LIBRARY_KEY ||
          key.startsWith(KB_FOLDERS_PREFIX) ||
          key.startsWith(DOC_LIST_PREFIX))
      ) {
        keys.push(key);
      }
    }
    keys.forEach((key) => sessionStorage.removeItem(key));
  } catch {
    /* ignore */
  }
}
