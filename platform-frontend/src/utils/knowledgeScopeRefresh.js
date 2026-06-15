import { clearKnowledgeScopeTreeCache } from "./knowledgeScopeTreeCache.js";

/** 文档库变更后通知知识检索/报告生成左侧树刷新（清 session 缓存 + 广播） */
export function notifyKnowledgeScopeTreeStale() {
  clearKnowledgeScopeTreeCache();
  window.dispatchEvent(new CustomEvent("platform:knowledge-index-updated"));
}
