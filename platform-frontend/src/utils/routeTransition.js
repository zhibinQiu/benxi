/** 从功能入口进入的子功能页（翻译、问数、问答等） */
export const SUBSYSTEM_PAGE_ROUTES = new Set([
  "ai-tools",
  "translate",
  "smart-data-query",
  "data-analysis",
  "carbon-qa",
  "carbon-assets",
  "smart-forecast",
  "speech",
  "ocr",
  "kg-palantir",
  "compare",
  "assist-writing",
  "report-generation",
  "knowledge-search",
  "knowledge-graph",
  "subscription-item",
  "wechat-mp",
  "wechat-mp-article",
  "feed-subscriptions",
  "feed-entry",
  "document-detail",
  "chat-history",
  "carbon-assets-history",
]);

/** App 壳层 key：主布局内切换功能时不销毁 MainLayout，避免整页闪白 */
export function shellRouteKey(route) {
  if (route.meta?.public || route.name === "login") return route.fullPath;
  return "main-shell";
}
