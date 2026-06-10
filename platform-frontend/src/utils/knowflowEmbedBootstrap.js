import {
  fetchRagEmbedSession,
  fetchRagMeta,
  getCachedRagEmbedSession,
  getCachedRagMeta,
} from "../api/rag.js";

function serviceAvailable(meta) {
  return Boolean(meta?.ui_available || meta?.knowflow_enabled);
}

/**
 * 加载 KnowFlow 嵌入所需 meta + SSO session。
 * 若登录后已 prefetch，则先用缓存立即出 iframe，再后台刷新。
 * 不等待登录 prefetch，避免阻塞切片管理跳转。
 */
export async function loadKnowflowEmbedResources({
  sync = false,
  freshSession = false,
} = {}) {
  if (freshSession) {
    const [meta, session] = await Promise.all([
      fetchRagMeta({ force: true }),
      fetchRagEmbedSession({ sync, force: true }),
    ]);
    return { meta, session, fromCache: false };
  }

  const cachedMeta = getCachedRagMeta();
  const cachedSession = getCachedRagEmbedSession();
  const canUseCache =
    cachedMeta &&
    cachedSession?.sso?.ready &&
    serviceAvailable(cachedMeta);

  if (canUseCache) {
    Promise.all([
      fetchRagMeta({ force: true }),
      fetchRagEmbedSession({ sync, force: true }),
    ]).catch(() => {});
    return {
      meta: cachedMeta,
      session: cachedSession,
      fromCache: true,
    };
  }

  const [meta, session] = await Promise.all([
    fetchRagMeta({ force: true }),
    fetchRagEmbedSession({ sync, force: true }),
  ]);
  return { meta, session, fromCache: false };
}

/** iframe 内 KnowFlow 会话失效时，由 platform-branding 请求父页刷新 SSO。 */
export function installKnowflowEmbedSsoListener(onRefresh) {
  if (typeof window === "undefined") return () => {};
  const handler = (ev) => {
    if (ev?.data?.type !== "zt-request-embed-sso") return;
    onRefresh?.();
  };
  window.addEventListener("message", handler);
  return () => window.removeEventListener("message", handler);
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
