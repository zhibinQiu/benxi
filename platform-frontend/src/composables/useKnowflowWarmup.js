/** 进入知识相关页面时再预热 KnowFlow（避免登录后拖慢首屏） */
import { prefetchKnowflowSession } from "../api/rag.js";

const KNOWFLOW_ROUTE_NAMES = new Set([
  "knowledge-search",
  "documents",
  "document-detail",
]);

export function isKnowflowWarmupRoute(route) {
  if (!route) return false;
  if (KNOWFLOW_ROUTE_NAMES.has(route.name)) return true;
  const path = route.path || "";
  return path.includes("/knowledge");
}

/** 路由进入知识页时调用；内部去重，不阻塞渲染 */
export function warmupKnowflowForRoute(route) {
  if (!isKnowflowWarmupRoute(route)) return;
  prefetchKnowflowSession();
}
