/** 使用全屏曲线动画背景的页面（登录 / 智能体问答 / 知识检索等对话场景） */
export function routeUsesVideoBackground(route) {
  if (!route) return false;
  if (route.name === "login") return true;
  return Boolean(route.meta?.videoBg);
}
