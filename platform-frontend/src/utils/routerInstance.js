/** 运行时注入 router，供 sessionGuard 等模块跳转而避免与 router/index 循环依赖 */

let appRouter = null;

export function setAppRouter(router) {
  appRouter = router;
}

export function getAppRouter() {
  return appRouter;
}
