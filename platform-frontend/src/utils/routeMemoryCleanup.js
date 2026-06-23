/** 离开功能页时释放 session / 内存缓存（KeepAlive 页实例与共享勾选由登出时统一清理） */

import { clearChatSession } from "./chatSessionPersist.js";
import { clearCompareViewSession } from "./compareViewPersist.js";
import { clearDocumentsViewCache } from "./documentsViewCache.js";
import { clearKgPalantirCache } from "./kgPalantirCache.js";

const AI_HOME_ROUTE = "ai-home";

const DOCUMENT_ROUTES = new Set(["documents", "document-detail"]);

const SUBSCRIPTION_ROUTES = new Set(["knowledge-subscriptions", "subscription-item"]);

const COMPARE_ROUTES = new Set(["compare"]);

const DATA_ANALYSIS_ROUTES = new Set(["data-analysis"]);

const DATA_ANALYSIS_SESSION_KEY = "data-analysis-session";

/** 路由名 → chatSessionPersist scope；不含 ai-home / report-generation（KeepAlive 保留） */
const ROUTE_CHAT_SCOPE = {
  "carbon-qa": "carbon-qa",
  "smart-data-query": "smart-data-query",
};

function routeName(route) {
  return String(route?.name || "");
}

function leavesGroup(fromName, toName, group) {
  return group.has(fromName) && !group.has(toName);
}

export function releaseRouteMemory(fromRoute, toRoute) {
  const fromName = routeName(fromRoute);
  const toName = routeName(toRoute);
  if (!fromName || fromName === toName) return;

  if (leavesGroup(fromName, toName, DOCUMENT_ROUTES)) {
    clearDocumentsViewCache();
  }

  if (fromName === "kg-palantir" && toName !== "kg-palantir") {
    clearKgPalantirCache();
  }

  if (leavesGroup(fromName, toName, COMPARE_ROUTES)) {
    clearCompareViewSession();
  }

  if (leavesGroup(fromName, toName, DATA_ANALYSIS_ROUTES)) {
    try {
      sessionStorage.removeItem(DATA_ANALYSIS_SESSION_KEY);
    } catch {
      /* ignore */
    }
  }

  if (leavesGroup(fromName, toName, SUBSCRIPTION_ROUTES)) {
    /* 订阅列表无独立 cache 模块；依赖组件 unmount 释放 DOM */
  }

  const chatScope = ROUTE_CHAT_SCOPE[fromName];
  if (chatScope && fromName !== AI_HOME_ROUTE && toName !== fromName) {
    clearChatSession(chatScope);
  }
}
