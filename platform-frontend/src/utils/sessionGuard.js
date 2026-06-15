/** 单点登录：旧会话被顶下线时的全局处理 */

import { clearTokens } from "../api/http.js";
import { resetClientSessionState } from "./resetClientSessionState.js";
import { bumpSessionEpoch } from "./sessionEpoch.js";

const listeners = new Set();
let handling = false;
let authRedirecting = false;

export function onSessionReplaced(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function dispatchSessionReplaced(message = "账号已在其他设备登录，请重新登录") {
  if (handling) return;
  handling = true;
  clearTokens();
  resetClientSessionState();
  bumpSessionEpoch();
  for (const listener of listeners) {
    try {
      listener(message);
    } catch {
      /* ignore */
    }
  }
  setTimeout(() => {
    handling = false;
  }, 1500);
}

export function isSessionReplacedError(payload, message = "") {
  const reason = payload?.reason || payload?.detail?.reason;
  if (reason === "session_replaced") return true;
  const text = String(message || payload?.message || "");
  return /其他设备登录|session_replaced/i.test(text);
}

function navigateToLoginPage({ saveRedirect = false } = {}) {
  return import("../router/index.js").then(({ default: router }) => {
    if (router.currentRoute.value.name === "login") return;
    const query = saveRedirect
      ? { redirect: router.currentRoute.value.fullPath }
      : undefined;
    return router.replace({ name: "login", query });
  });
}

function finishAuthRedirect() {
  setTimeout(() => {
    authRedirecting = false;
  }, 800);
}

/** 未登录或 access token 失效：清会话并跳转登录页（不弹未授权提示） */
export function redirectToLoginAfterAuthFailure() {
  if (authRedirecting) return;
  authRedirecting = true;
  clearTokens();
  resetClientSessionState();
  bumpSessionEpoch();
  navigateToLoginPage({ saveRedirect: true }).finally(finishAuthRedirect);
}

/** 主动退出：会话已在 logout 中清理，直接跳转登录页 */
export function redirectToLoginAfterLogout() {
  navigateToLoginPage({ saveRedirect: false });
}
