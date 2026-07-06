/** 浏览器 matchMedia 封装，避免散落 window.matchMedia */

export function matchMediaQuery(query) {
  if (typeof window === "undefined" || !window.matchMedia) return null;
  return window.matchMedia(query);
}

export function prefersReducedMotion() {
  return matchMediaQuery("(prefers-reduced-motion: reduce)")?.matches ?? false;
}

export function prefersDarkColorScheme() {
  return matchMediaQuery("(prefers-color-scheme: dark)")?.matches ?? false;
}

/** @returns {() => void} unsubscribe */
export function subscribeMediaQuery(query, listener) {
  const mq = matchMediaQuery(query);
  if (!mq) return () => {};
  mq.addEventListener("change", listener);
  return () => mq.removeEventListener("change", listener);
}
