import {
  fetchRagEmbedSession,
  fetchRagMeta,
  getCachedRagEmbedSession,
  getCachedRagMeta,
  waitForKnowflowPrefetch,
} from "../api/rag.js";

function serviceAvailable(meta) {
  return Boolean(meta?.ui_available || meta?.knowflow_enabled);
}

/**
 * 加载 KnowFlow 嵌入所需 meta + SSO session。
 * 若登录后已 prefetch，则先用缓存立即出 iframe，再后台刷新。
 */
export async function loadKnowflowEmbedResources({ sync = false } = {}) {
  await waitForKnowflowPrefetch();

  const cachedMeta = getCachedRagMeta();
  const cachedSession = getCachedRagEmbedSession();
  const canUseCache =
    cachedMeta &&
    cachedSession?.sso?.ready &&
    serviceAvailable(cachedMeta);

  if (canUseCache) {
    Promise.all([fetchRagMeta(), fetchRagEmbedSession({ sync })]).catch(() => {});
    return {
      meta: cachedMeta,
      session: cachedSession,
      fromCache: true,
    };
  }

  const [meta, session] = await Promise.all([
    fetchRagMeta(),
    fetchRagEmbedSession({ sync }),
  ]);
  return { meta, session, fromCache: false };
}

export function tryApplyCachedKnowflowEmbed({ metaRef, sessionRef, applySession }) {
  const cachedMeta = getCachedRagMeta();
  const cachedSession = getCachedRagEmbedSession();
  if (!cachedMeta || !cachedSession?.sso?.ready || !serviceAvailable(cachedMeta)) {
    return false;
  }
  metaRef.value = cachedMeta;
  sessionRef.value = cachedSession;
  applySession(cachedSession);
  return true;
}
