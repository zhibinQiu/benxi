/** 文档对比页：sessionStorage 状态恢复（切换功能后回到对比页可继续） */

const STORAGE_KEY = "platform:compare-view-session:v1";

export function loadCompareViewSession() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : null;
  } catch {
    return null;
  }
}

export function saveCompareViewSession(data) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...data, savedAt: Date.now() }));
  } catch {
    /* quota exceeded */
  }
}

export function clearCompareViewSession() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
