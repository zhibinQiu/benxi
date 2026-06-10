import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { fetchRagEmbedSession } from "../api/client";
import { knowflowUnavailableHint } from "../utils/uiMessage";
import { useAuth } from "./useAuth";
import {
  installKnowflowEmbedSsoListener,
  loadKnowflowEmbedResources,
} from "../utils/knowflowEmbedBootstrap";

/**
 * 内嵌 KnowFlow / RAGFlow Web UI（SSO + 主题同步）。
 * @param {object} options
 * @param {string} options.knowflowPath - KnowFlow 前端路径，如 `/search`、`/knowledge`、`/`
 * @param {string} options.watchRouteName - 当前 Vue 路由名，用于切换 Tab 时重载
 * @param {string} [options.iframeElementId] - iframe DOM id
 * @param {'search'|'knowledge'|'1'} [options.embedMode] - zt_embed：search 保留知识库选择侧栏
 */
export function useKnowflowEmbed({
  knowflowPath = "/",
  watchRouteName,
  iframeElementId = "knowflow-embed",
  embedMode = "1",
}) {
  const route = useRoute();
  const { user } = useAuth();

  const bootstrapping = ref(true);
  const iframeReady = ref(false);
  const meta = ref({
    ui_direct_url: "http://127.0.0.1:9380",
    ui_available: false,
    ui_hint: "",
    ui_embed_mode: "iframe",
  });
  const embedSession = ref(null);
  const iframeSrc = ref("");

  function resolveEmbedBase(url) {
    let base = url || meta.value.ui_direct_url || "http://127.0.0.1:9380";
    if (base.startsWith("/")) {
      base = `${window.location.origin}${base}`;
    }
    return base.replace(/\/$/, "");
  }

  const iframeBase = computed(() =>
    resolveEmbedBase(meta.value.ui_direct_url || "http://127.0.0.1:9380")
  );

  function stripBearer(token) {
    return (token || "").replace(/^Bearer\s+/i, "").trim();
  }

  function buildKnowflowUrl(session) {
    const base = iframeBase.value;
    const path = knowflowPath === "/" ? "" : knowflowPath.replace(/\/$/, "");
    const auth = session?.sso?.authorization;
    const embed =
      embedMode === "search" || embedMode === "knowledge" ? embedMode : "1";
    const q = new URLSearchParams({ zt_hide_file: "1", zt_embed: embed });
    if (session?.sso?.ready && auth) {
      q.set("auth", stripBearer(auth));
    }
    return `${base}${path}?${q.toString()}`;
  }

  function themePayload() {
    const base = embedSession.value?.theme || {};
    const name = (
      user.value?.display_name ||
      user.value?.username ||
      ""
    ).trim();
    const kbLabels =
      embedSession.value?.knowflow_kb_labels ||
      base.knowflow_kb_labels ||
      [];
    const deptSuffixLabels =
      embedSession.value?.dept_suffix_labels ||
      base.dept_suffix_labels ||
      {};
    return {
      ...base,
      display_name: name || base.display_name,
      username: user.value?.username || base.username,
      knowflow_kb_labels: kbLabels,
      dept_suffix_labels: deptSuffixLabels,
    };
  }

  function postToIframe(payload) {
    const iframe = document.getElementById(iframeElementId);
    if (!iframe?.contentWindow) return;
    iframe.contentWindow.postMessage(payload, "*");
  }

  function postThemeToIframe() {
    postToIframe({ type: "zt-platform-theme", theme: themePayload() });
  }

  function postSsoToIframe() {
    const sso = embedSession.value?.sso;
    if (!sso?.ready || !sso.authorization) return;
    postToIframe({ type: "zt-platform-sso", sso });
  }

  function applyIframeSession(session) {
    if (!meta.value.ui_available) {
      iframeSrc.value = "";
      return;
    }
    if (!session?.sso?.ready || !session.sso.authorization) {
      iframeSrc.value = "";
      return;
    }
    iframeReady.value = false;
    iframeSrc.value = buildKnowflowUrl(session);
  }

  const showStartupHint = computed(
    () => bootstrapping.value || (Boolean(iframeSrc.value) && !iframeReady.value)
  );

  let removeSsoListener = () => {};

  async function loadMeta() {
    iframeReady.value = false;
    bootstrapping.value = true;
    iframeSrc.value = "";

    try {
      const { meta: m, session } = await loadKnowflowEmbedResources({
        sync: false,
        freshSession: true,
      });
      meta.value = m;
      embedSession.value = session;
      applyIframeSession(session);
    } catch (e) {
      meta.value = {
        ...meta.value,
        ui_available: false,
        knowflow_enabled: false,
        ui_hint: knowflowUnavailableHint(e),
      };
    } finally {
      bootstrapping.value = false;
    }
  }

  function postEmbedChromeToIframe() {
    const mode =
      embedMode === "search" || embedMode === "knowledge" ? embedMode : "1";
    postToIframe({ type: "zt-platform-embed", mode });
  }

  function onIframeLoad() {
    iframeReady.value = true;
    postSsoToIframe();
    postThemeToIframe();
    postEmbedChromeToIframe();
    window.setTimeout(postSsoToIframe, 300);
    window.setTimeout(postEmbedChromeToIframe, 400);
    window.setTimeout(postSsoToIframe, 1200);
    window.setTimeout(postEmbedChromeToIframe, 1500);
  }

  async function reloadForUser() {
    if (route.name !== watchRouteName) return;
    iframeReady.value = false;
    iframeSrc.value = "";
    embedSession.value = await fetchRagEmbedSession({ sync: false, force: true }).catch(
      () => null
    );
    applyIframeSession(embedSession.value);
  }

  watch(
    () => route.name,
    (name) => {
      if (name === watchRouteName) loadMeta();
    }
  );

  watch(
    () => user.value?.id,
    (id, prev) => {
      if (id && id !== prev && route.name === watchRouteName && !bootstrapping.value) {
        reloadForUser();
      }
    }
  );

  onMounted(() => {
    removeSsoListener = installKnowflowEmbedSsoListener(reloadForUser);
    loadMeta();
  });

  onUnmounted(() => {
    removeSsoListener();
  });

  return {
    bootstrapping,
    iframeReady,
    meta,
    embedSession,
    iframeSrc,
    showStartupHint,
    loadMeta,
    onIframeLoad,
  };
}
