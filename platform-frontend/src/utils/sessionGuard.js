/** 单点登录：旧会话被顶下线时的全局处理 */

import { clearTokens } from "../api/http.js";

const listeners = new Set();
let handling = false;

export function onSessionReplaced(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function dispatchSessionReplaced(message = "账号已在其他设备登录，请重新登录") {
  if (handling) return;
  handling = true;
  clearTokens();
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
