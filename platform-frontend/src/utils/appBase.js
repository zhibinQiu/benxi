/** Vite `base`（生产默认 /ai/） */
export const APP_BASE = import.meta.env.BASE_URL;

/** public 目录资源（logo、favicon 等） */
export function publicAsset(path) {
  const clean = String(path || "").replace(/^\//, "");
  return `${APP_BASE}${clean}`;
}
