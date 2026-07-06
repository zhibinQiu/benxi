/** 仅登录宣传页使用全屏曲线动画背景 */
export function routeUsesVideoBackground(route) {
  if (!route) return false;
  return route.name === "login";
}
