/** 登录/退出时清空与用户会话相关的前端状态（不复用上一账户的缓存与 KeepAlive） */

import { invalidateRagCaches } from "../api/rag.js";
import { clearAllChatSessions } from "./chatSessionPersist.js";
import { clearDocumentsViewCache } from "./documentsViewCache.js";
import { clearKnowledgeScopeTreeCache } from "./knowledgeScopeTreeCache.js";

const KNOWLEDGE_SEARCH_CHECKED_KEYS = "platform:knowledge-search-checked-keys:v2";

export function resetClientSessionState() {
  invalidateRagCaches();
  clearDocumentsViewCache();
  clearKnowledgeScopeTreeCache();
  clearAllChatSessions();
  try {
    sessionStorage.removeItem(KNOWLEDGE_SEARCH_CHECKED_KEYS);
  } catch {
    /* ignore */
  }
}
