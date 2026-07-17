/** 从功能入口进入的子功能页（翻译、问数、问答等） */
export const SUBSYSTEM_PAGE_ROUTES = new Set([
  "ai-tools",
  "translate",
  "smart-data-query",
  "data-analysis",
  "carbon-qa",
  "smart-forecast",
  "speech",
  "text-to-speech",
  "ocr",
  "compare",
  "agent-skills",
  "report-generation",
  "knowledge-search",
  "subscription-item",
  "document-detail",
  "chat-history",
]);

/** App 壳层 key：主布局内切换功能时不销毁 MainLayout，避免整页闪白 */
export function shellRouteKey(route) {
  if (route.meta?.public || route.name === "login") return route.fullPath;
  return "main-shell";
}
