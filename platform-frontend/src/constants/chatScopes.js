import { messages } from "../locales";

function resolvePath(dict, key) {
  let cur = dict;
  for (const part of key.split(".")) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = cur[part];
  }
  return cur;
}

/** 平台对话场景：scope、返回路由 */
export const CHAT_SCOPES = {
  "ai-home": {
    routeName: "ai-home",
  },
  "carbon-qa": {
    routeName: "carbon-qa",
  },
  "smart-data-query": {
    routeName: "smart-data-query",
  },
  "report-generation": {
    routeName: "report-generation",
  },
  assistant: {
    routeName: null,
  },
};

export function chatScopeTitle(scope, locale = "zh") {
  if (!scope) return scope;
  const raw = resolvePath(messages[locale], `chatScopes.${scope}.title`);
  if (typeof raw === "string") return raw;
  return scope;
}

export function chatScopeRouteName(scope) {
  return CHAT_SCOPES[scope]?.routeName || null;
}
