/** 知识检索左侧树：sessionStorage 缓存，进入页面时先展示缓存再后台刷新 */

const CACHE_KEY = "platform:knowledge-scope-tree:v3";
const CACHE_TTL_MS = 120 * 1000;

function readRaw() {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.savedAt || !parsed?.data) return null;
    if (Date.now() - parsed.savedAt > CACHE_TTL_MS) {
      sessionStorage.removeItem(CACHE_KEY);
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}

export function readKnowledgeScopeTreeCache() {
  return readRaw();
}

export function writeKnowledgeScopeTreeCache(data) {
  if (!data) return;
  try {
    sessionStorage.setItem(
      CACHE_KEY,
      JSON.stringify({ savedAt: Date.now(), data })
    );
  } catch {
    /* quota exceeded — ignore */
  }
}

export function clearKnowledgeScopeTreeCache() {
  try {
    sessionStorage.removeItem(CACHE_KEY);
  } catch {
    /* ignore */
  }
}
