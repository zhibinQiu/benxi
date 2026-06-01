import { fetchRagEmbedSession } from "../api/client";

let syncInflight = null;

/**
 * 后台全量同步文档到 KnowFlow，完成后刷新 iframe 以更新知识库树。
 * @param {object} [options]
 * @param {string} [options.iframeElementId]
 */
export function scheduleKnowflowCatalogSync({ iframeElementId } = {}) {
  if (syncInflight) return syncInflight;
  syncInflight = fetchRagEmbedSession({ sync: true })
    .then((session) => {
      if (iframeElementId) {
        const iframe = document.getElementById(iframeElementId);
        const win = iframe?.contentWindow;
        if (win) {
          try {
            win.postMessage(
              {
                type: "zt-platform-catalog-synced",
                synced_documents: session?.synced_documents ?? 0,
              },
              "*",
            );
          } catch {
            /* ignore */
          }
          try {
            win.location.reload();
          } catch {
            /* ignore */
          }
        }
      }
      return session;
    })
    .catch((err) => {
      console.warn("[knowflow] catalog sync failed:", err?.message || err);
    })
    .finally(() => {
      syncInflight = null;
    });
  return syncInflight;
}
