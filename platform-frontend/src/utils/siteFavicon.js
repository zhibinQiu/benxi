/** 从 URL 提取站点 hostname（去掉 www.） */
export function siteHostFromUrl(url) {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./i, "");
  } catch {
    return "";
  }
}

/**
 * 站点 favicon 地址：直接从目标站点 origin 拉取，避免依赖 Google s2（国内易超时）。
 * 加载失败时由组件展示字母回退。
 */
export function siteFaviconUrl(urlOrHost) {
  if (!urlOrHost) return "";
  try {
    const origin = String(urlOrHost).includes("://")
      ? new URL(urlOrHost).origin
      : `https://${String(urlOrHost).replace(/^www\./i, "")}`;
    return `${origin}/favicon.ico`;
  } catch {
    return "";
  }
}

/** 站点首字母，用于 favicon 不可用时的占位 */
export function siteInitialFromHost(host) {
  const label = (host || "").trim();
  return label.charAt(0).toUpperCase() || "?";
}
