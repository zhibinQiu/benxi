/** 登录/退出时清空与用户会话相关的前端状态（不复用上一账户的缓存与 KeepAlive） */

import { clearAllChatSessions } from "./chatSessionPersist.js";
import { clearCompareViewSession } from "./compareViewPersist.js";
import { clearDocumentsViewCache } from "./documentsViewCache.js";
import { clearKgPalantirCache } from "./kgPalantirCache.js";
import { invalidateKnowledgeScopeTree } from "../composables/useKnowledgeScopeTree.js";
import { clearKnowledgeScopeTreeCache } from "./knowledgeScopeTreeCache.js";
import { clearKnowledgeScopeSelection } from "./knowledgeScopeSelectionCache.js";
import { stopNotificationAlerts } from "../composables/useNotificationAlerts.js";
import { resetChatTabs } from "../composables/useChatTabs.js";

let resetMenuSettingsFn = null;

const KNOWLEDGE_SEARCH_CHECKED_KEYS = "platform:knowledge-search-checked-keys:v2";

export function registerMenuSettingsReset(fn) {
  resetMenuSettingsFn = fn;
}

export function resetClientSessionState() {
  stopNotificationAlerts();
  clearDocumentsViewCache();
  clearKgPalantirCache();
  invalidateKnowledgeScopeTree();
  clearKnowledgeScopeTreeCache();
  clearAllChatSessions();
  clearCompareViewSession();
  resetChatTabs();
  resetMenuSettingsFn?.();
  try {
    sessionStorage.removeItem(KNOWLEDGE_SEARCH_CHECKED_KEYS);
    clearKnowledgeScopeSelection();
  } catch {
    /* ignore */
  }
}
