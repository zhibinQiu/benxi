/** 知识检索文档勾选结果：与树 checkedKeys 配套，供主面板立即恢复可检索状态 */

export const KNOWLEDGE_SCOPE_SELECTION_KEY = Symbol("knowledgeScopeSelection");

const SELECTION_KEY = "platform:knowledge-search-selection:v1";

export function readKnowledgeScopeSelection() {
  try {
    const raw = sessionStorage.getItem(SELECTION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") return null;
    return data;
  } catch {
    return null;
  }
}

export function writeKnowledgeScopeSelection(payload) {
  try {
    if (!payload) {
      sessionStorage.removeItem(SELECTION_KEY);
      return;
    }
    sessionStorage.setItem(SELECTION_KEY, JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}

export function clearKnowledgeScopeSelection() {
  try {
    sessionStorage.removeItem(SELECTION_KEY);
  } catch {
    /* ignore */
  }
}
