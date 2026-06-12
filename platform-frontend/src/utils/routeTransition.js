/** 登录成功飞行动画结束后，跳过一次根路由与主布局内页过渡 */
let skipAfterLoginMotion = false;

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
  "compare",
  "assist-writing",
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

const FEATURE_HUB_ROUTES = new Set(["system-functions", "ai-tools", "ai-home"]);

export function markSkipMotionAfterLogin() {
  skipAfterLoginMotion = true;
}

/** 只读：App 壳层是否跳过 login→主界面 过渡 */
export function shouldSkipAppRouteMotion(fromRouteName) {
  return fromRouteName === "login" && skipAfterLoginMotion;
}

/** 只读：主布局内页是否跳过 login 后的首屏过渡 */
export function shouldSkipInnerRouteMotion() {
  return skipAfterLoginMotion;
}

/** 导航完成后调用，清除 skip 标记（避免多处 consume 互相抢标志） */
export function consumeSkipAfterLoginMotion() {
  if (!skipAfterLoginMotion) return false;
  skipAfterLoginMotion = false;
  return true;
}

/** @deprecated 请用 shouldSkipInnerRouteMotion + consumeSkipAfterLoginMotion */
export function consumeSkipInnerRouteMotion() {
  return consumeSkipAfterLoginMotion();
}

/** 侧栏一级菜单路由 — 切换时不做过场，避免与指示条动画叠加发「卡」 */
export const SIDEBAR_PRIMARY_ROUTES = new Set([
  "ai-home",
  "system-functions",
  "documents",
  "knowledge-subscriptions",
  "admin-users",
  "admin-departments",
  "admin-monitor",
  "admin-model-settings",
  "admin-docs",
]);

/** 主布局内页过渡：功能页 PPT 推入，侧栏一级菜单切换无过场 */
export function resolveInnerRouteTransition(from, to) {
  if (!from?.name) return "route-push";
  if (from.name === "login") return "route-instant";

  const toName = String(to.name || "");
  const fromName = String(from.name || "");
  const toSub = SUBSYSTEM_PAGE_ROUTES.has(toName);
  const fromSub = SUBSYSTEM_PAGE_ROUTES.has(fromName);
  const fromHub = FEATURE_HUB_ROUTES.has(fromName);

  if (
    SIDEBAR_PRIMARY_ROUTES.has(fromName) &&
    SIDEBAR_PRIMARY_ROUTES.has(toName)
  ) {
    return "route-instant";
  }

  if (toSub && (fromHub || fromSub)) return "route-push";
  if (fromSub && !toSub) return "route-push";

  return "route-crossfade";
}

/** App 壳层 key：主布局内切换功能时不销毁 MainLayout，避免整页闪白 */
export function shellRouteKey(route) {
  if (route.meta?.public || route.name === "login") return route.fullPath;
  return "main-shell";
}
