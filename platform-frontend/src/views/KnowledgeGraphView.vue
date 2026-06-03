<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useAuth } from "../composables/useAuth";
import { useRoute } from "vue-router";
import { NAlert, NButton } from "naive-ui";
import { fetchRagEmbedSession } from "../api/client";
import {
  KNOWLEDGE_UNAVAILABLE,
  knowflowUnavailableHint,
  sanitizeUserFacingMessage,
} from "../utils/uiMessage";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeServiceStartup from "../components/KnowledgeServiceStartup.vue";
import {
  loadKnowflowEmbedResources,
  tryApplyCachedKnowflowEmbed,
} from "../utils/knowflowEmbedBootstrap";

const route = useRoute();
const { user, isSystemAdmin } = useAuth();

const STARTUP_HINT = "正在启动知识服务系统";

const bootstrapping = ref(true);
const iframeReady = ref(false);
const meta = ref({
  ui_direct_url: "http://127.0.0.1:9380",
  ui_available: false,
  ui_hint: "",
  ui_embed_mode: "iframe",
  knowflow_enabled: false,
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
  const auth = session?.sso?.authorization;
  const q = new URLSearchParams({ zt_hide_file: "1", zt_embed: "knowledge" });
  if (session?.sso?.ready && auth) {
    q.set("auth", stripBearer(auth));
  }
  return `${base}/knowledge?${q.toString()}`;
}

function buildKnowflowThemePayload(session, user, { isSystemAdmin } = {}) {
  const base = session?.theme || {};
  const name = (
    user?.display_name ||
    user?.username ||
    ""
  ).trim();
  const kbLabels =
    session?.knowflow_kb_labels ||
    base.knowflow_kb_labels ||
    [];
  const deptSuffixLabels =
    session?.dept_suffix_labels ||
    base.dept_suffix_labels ||
    {};
  return {
    ...base,
    display_name: name || base.display_name,
    username: user?.username || base.username,
    knowflow_kb_labels: kbLabels,
    dept_suffix_labels: deptSuffixLabels,
    is_system_admin:
      isSystemAdmin === true ||
      base.is_system_admin === true ||
      user?.is_system_admin === true,
  };
}

function themePayload() {
  return buildKnowflowThemePayload(embedSession.value, user.value, {
    isSystemAdmin: isSystemAdmin.value,
  });
}

function postToIframe(payload) {
  const iframe = document.getElementById("knowflow-kg-embed");
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
  if (!serviceReady.value) {
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

/** Web 探活或 KnowFlow API 健康即视为可嵌入 */
const serviceReady = computed(
  () => Boolean(meta.value.ui_available || meta.value.knowflow_enabled)
);

async function loadMeta() {
  iframeReady.value = false;
  const cachedApplied = tryApplyCachedKnowflowEmbed({
    metaRef: meta,
    sessionRef: embedSession,
    applySession: applyIframeSession,
  });
  bootstrapping.value = !cachedApplied;
  if (!cachedApplied) {
    iframeSrc.value = "";
  }

  try {
    const { meta: m, session } = await loadKnowflowEmbedResources({
      sync: false,
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

function onIframeLoad() {
  iframeReady.value = true;
  postSsoToIframe();
  postThemeToIframe();
  postToIframe({ type: "zt-platform-embed", mode: "knowledge" });
}

watch(
  () => route.name,
  (name) => {
    if (name === "knowledge-graph") loadMeta();
  }
);

watch(
  () => user.value?.id,
  (id, prev) => {
    if (id && id !== prev && route.name === "knowledge-graph" && !bootstrapping.value) {
      loadMeta();
    }
  }
);

onMounted(loadMeta);
</script>

<template>
  <FeatureSubsystemShell fill>
    <div class="subsystem-embed-host">
      <n-alert
        v-if="!bootstrapping && !serviceReady"
        type="warning"
        title="切片管理服务未就绪"
        class="embed-alert"
      >
        <p>{{ meta.ui_hint || KNOWLEDGE_UNAVAILABLE }}</p>
        <template #action>
          <n-button size="small" @click="loadMeta">重新检测</n-button>
        </template>
      </n-alert>

      <n-alert
        v-if="!bootstrapping && serviceReady && embedSession?.sso && !embedSession.sso.ready"
        type="info"
        title="登录未完成"
        class="embed-alert"
      >
        {{
          sanitizeUserFacingMessage(
            embedSession.sso.message,
            "请刷新页面重试。"
          )
        }}
        <template #action>
          <n-button size="small" @click="loadMeta">重试</n-button>
        </template>
      </n-alert>

      <KnowledgeServiceStartup v-if="showStartupHint" :message="STARTUP_HINT" />

      <iframe
        v-if="iframeSrc"
        id="knowflow-kg-embed"
        class="subsystem-embed-frame"
        :class="{ 'subsystem-embed-frame--loading': showStartupHint }"
        :src="iframeSrc"
        title="切片管理"
        allow="fullscreen; clipboard-read; clipboard-write"
        referrerpolicy="no-referrer-when-downgrade"
        @load="onIframeLoad"
      />
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.embed-alert {
  margin: 16px;
  max-width: 640px;
}
</style>
