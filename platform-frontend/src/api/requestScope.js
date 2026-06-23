/** 路由级请求作用域：切换页面时取消在途 API，避免后台慢请求拖住 UI。 */

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
