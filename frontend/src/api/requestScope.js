/** 路由级请求作用域：切换页面时取消在途 API，避免后台慢请求拖住 UI。 */

import { isNavigationFailure, NavigationFailureType } from "vue-router";

let routeEpoch = 0;
let routeAbortController = new AbortController();

/** 当前路由代际；请求携带 signal 时切换路由会自动 abort */
export function getRouteRequestSignal() {
  return routeAbortController.signal;
}

export function getRouteEpoch() {
  return routeEpoch;
}

/** 路由 beforeEach 调用：取消上一页未完成的 fetch */
export function beginRouteRequestScope() {
  routeEpoch += 1;
  routeAbortController.abort();
  routeAbortController = new AbortController();
  return routeEpoch;
}

export function isRouteAbortError(err) {
  return err?.name === "AbortError" || err?.code === "ROUTE_ABORT";
}

/** 路由切换或重复导航导致的可忽略错误，勿向用户弹 toast */
export function isBenignNavigationError(err) {
  if (!err) return false;
  if (isRouteAbortError(err)) return true;
  if (err?.name === "NavigationDuplicated") return true;
  const msg = String(err?.message || err || "").trim();
  if (msg === "ROUTE_ABORT") return true;
  if (/Avoided redundant navigation/i.test(msg)) return true;
  if (
    isNavigationFailure(err, NavigationFailureType.duplicated) ||
    isNavigationFailure(err, NavigationFailureType.aborted) ||
    isNavigationFailure(err, NavigationFailureType.cancelled)
  ) {
    return true;
  }
  return false;
}
