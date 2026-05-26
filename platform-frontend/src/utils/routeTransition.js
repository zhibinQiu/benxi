/** 登录成功飞行动画结束后，跳过一次根路由与主布局内页过渡 */
let skipAfterLoginMotion = false;

export function markSkipMotionAfterLogin() {
  skipAfterLoginMotion = true;
}

export function shouldSkipAppRouteMotion(fromRouteName) {
  if (fromRouteName !== "login" || !skipAfterLoginMotion) return false;
  return true;
}

export function consumeSkipInnerRouteMotion() {
  if (!skipAfterLoginMotion) return false;
  skipAfterLoginMotion = false;
  return true;
}
