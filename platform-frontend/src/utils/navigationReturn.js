/**
 * 子页面返回：回到进入该功能时的入口（携带 query），避免落到其他菜单或默认 Tab。
 * 通过路由 query.return 传递 JSON 编码的 { name, query, params }。
 */

/** 允许作为 return 目标的路由名（防止任意跳转） */
export const VALID_RETURN_ROUTE_NAMES = new Set([
  "ai-home",
  "system-functions",
  "documents",
  "document-detail",
  "knowledge-subscriptions",
  "knowledge-graph",
  "knowledge-search",
  "subscription-item",
  "carbon-assets",
  "carbon-qa",
  "smart-data-query",
  "data-analysis",
  "translate",
  "speech",
  "text-to-speech",
  "ocr",
  "kg-palantir",
  "compare",
  "assist-writing",
  "report-generation",
  "ai-tools",
  "smart-forecast",
  "todos",
  "jobs",
  "notifications",
]);

export function encodeReturnLocation(route) {
  if (!route?.name) return undefined;
  const query = { ...(route.query || {}) };
  delete query.return;
  const params = { ...(route.params || {}) };
  return JSON.stringify({ name: route.name, query, params });
}

export function decodeReturnLocation(encoded) {
  if (!encoded || typeof encoded !== "string") return null;
  try {
    const parsed = JSON.parse(encoded);
    if (!parsed?.name || !VALID_RETURN_ROUTE_NAMES.has(parsed.name)) {
      return null;
    }
    const query = { ...(parsed.query || {}) };
    delete query.return;
    return {
      name: parsed.name,
      query,
      params: parsed.params || {},
    };
  } catch {
    return null;
  }
}

/**
 * @param {import('vue-router').RouteLocationNormalizedLoaded} route
 * @param {{ name: string, query?: object, params?: object } | null} [explicitFallback]
 */
export function resolveReturnTarget(route, explicitFallback = null) {
  const fromReturn = decodeReturnLocation(route.query?.return);
  if (fromReturn) return fromReturn;
  if (explicitFallback?.name) return explicitFallback;
  const backTo = route.meta?.backTo;
  if (backTo && VALID_RETURN_ROUTE_NAMES.has(String(backTo))) {
    return { name: String(backTo), query: {}, params: {} };
  }
  return null;
}

/**
 * 进入子页时附带 return，供返回按钮使用。
 */
export function navigateWithReturn(router, target, fromRoute) {
  const encoded = encodeReturnLocation(fromRoute);
  const query = { ...(target.query || {}) };
  if (encoded) query.return = encoded;
  return router.push({
    name: target.name,
    params: target.params,
    query,
  });
}

export function goBackToEntry(router, route, explicitFallback = null) {
  const target = resolveReturnTarget(route, explicitFallback);
  if (target) {
    return router.push(target);
  }
  return router.push({ name: "system-functions" });
}
