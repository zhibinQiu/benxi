/** 平台对话场景：scope、展示名、返回路由 */
export const CHAT_SCOPES = {
  "ai-home": {
    title: "AI 助理",
    routeName: "ai-home",
  },
  "carbon-qa": {
    title: "双碳问答",
    routeName: "carbon-qa",
  },
  "smart-data-query": {
    title: "智能问数",
    routeName: "smart-data-query",
  },
  "report-generation": {
    title: "报告生成",
    routeName: "report-generation",
  },
  assistant: {
    title: "智能助手",
    routeName: null,
  },
};

export function chatScopeTitle(scope) {
  return CHAT_SCOPES[scope]?.title || scope;
}

export function chatScopeRouteName(scope) {
  return CHAT_SCOPES[scope]?.routeName || null;
}
