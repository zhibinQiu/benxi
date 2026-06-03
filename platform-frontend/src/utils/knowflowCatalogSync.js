/**
 * 通知 KnowFlow iframe 目录已更新（不再重复请求 embed-session）。
 * @param {object} [options]
 * @param {string} [options.iframeElementId]
 * @param {number} [options.syncedDocuments]
 */
export function notifyKnowflowCatalogSynced({
  iframeElementId,
  syncedDocuments = 0,
} = {}) {
  if (!iframeElementId) return;
  const iframe = document.getElementById(iframeElementId);
  const win = iframe?.contentWindow;
  if (!win) return;
  try {
    win.postMessage(
      {
        type: "zt-platform-catalog-synced",
        synced_documents: syncedDocuments,
      },
      "*",
    );
  } catch {
    /* ignore */
  }
}

/** @deprecated 登录后已 prefetch SSO，进入功能页不再额外拉 embed-session */
export function scheduleKnowflowCatalogSync() {
  return Promise.resolve(null);
}
