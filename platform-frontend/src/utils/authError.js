/** 退出登录后抑制无意义的鉴权错误提示 */

import { loggingOut } from "./sessionEpoch.js";

const TOKEN_KEY = "platform_access_token";

function hasAccessToken() {
  try {
    return !!localStorage.getItem(TOKEN_KEY);
  } catch {
    return false;
  }
}

export const AUTH_SILENT = Symbol("auth-silent");

const AUTH_MESSAGE_RE =
  /^(Unauthorized|Forbidden|Invalid access token|User disabled or not found|Not authenticated|登录已失效)/i;

export function isAuthRelatedMessage(msg) {
  const text = String(msg || "").trim();
  if (!text) return false;
  if (AUTH_MESSAGE_RE.test(text)) return true;
  return /未授权/i.test(text);
}

export function shouldSuppressAuthFeedback(msg) {
  if (!isAuthRelatedMessage(msg)) return false;
  return loggingOut.value || !hasAccessToken();
}

export function isAuthSilentError(err) {
  return err?.[AUTH_SILENT] === true;
}

export function createAuthSilentError(message = "Unauthorized") {
  const err = new Error(message);
  err[AUTH_SILENT] = true;
  return err;
}
