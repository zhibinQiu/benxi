/** 使用全屏曲线动画背景的页面（登录、对话场景、文档中心、功能列表、网站收藏、本体图谱、问题登记、系统设置等） */
export function routeUsesVideoBackground(route) {
  if (!route) return false;
  if (route.name === "login") return true;
  return Boolean(route.meta?.videoBg);
}
