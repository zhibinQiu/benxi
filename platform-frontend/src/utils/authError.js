/** 未登录 / 会话失效：静默跳转登录页，不弹未授权类提示 */

import { loggingOut } from "./sessionEpoch.js";

export const AUTH_SILENT = Symbol("auth-silent");

const SESSION_AUTH_MESSAGE_RE =
  /^(Unauthorized|Invalid access token|User disabled or not found|Not authenticated|登录已失效)/i;

const LOGIN_FAILURE_RE =
  /手机号|姓名或密码|账号已禁用|refresh_token|Invalid refresh token/i;

export function isAuthRelatedMessage(msg) {
  const text = String(msg || "").trim();
  if (!text) return false;
  if (SESSION_AUTH_MESSAGE_RE.test(text)) return true;
  return /未授权/i.test(text);
}

/** 登录接口返回的 401（密码错误等），不应触发全局跳转 */
export function isLoginFailureMessage(msg) {
  return LOGIN_FAILURE_RE.test(String(msg || ""));
}

/** 受保护接口的 401：视为未登录或会话失效 */
export function isSessionUnauthorized(status, msg) {
  if (status !== 401) return false;
  return !isLoginFailureMessage(msg);
}

export function shouldSuppressAuthFeedback(msg) {
  if (loggingOut.value && isAuthRelatedMessage(msg)) return true;
  return isAuthRelatedMessage(msg);
}

export function isAuthSilentError(err) {
  return err?.[AUTH_SILENT] === true;
}

export function createAuthSilentError(message = "Unauthorized") {
  const err = new Error(message);
  err[AUTH_SILENT] = true;
  return err;
}
