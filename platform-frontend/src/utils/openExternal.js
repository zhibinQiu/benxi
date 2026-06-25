const EXTERNAL_WINDOW_FEATURES = "noopener,noreferrer";

/** 新标签打开外链（统一安全参数，禁止裸 window.open） */
export function openExternal(url) {
  const target = String(url || "").trim();
  if (!target) return;
  window.open(target, "_blank", EXTERNAL_WINDOW_FEATURES);
}
