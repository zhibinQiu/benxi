/** 读取子面板 defineExpose({ loading }) 的 ref/computed 值 */
export function readPanelLoading(panelRef) {
  const exposed = panelRef?.loading;
  if (exposed == null) return false;
  return typeof exposed === "object" && "value" in exposed ? exposed.value : Boolean(exposed);
}
