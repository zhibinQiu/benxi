<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useAuth } from "../composables/useAuth";
import { useRoute } from "vue-router";
import { NAlert, NButton, useMessage } from "naive-ui";
import { fetchRagEmbedSession, fetchRagMeta } from "../api/client";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeServiceStartup from "../components/KnowledgeServiceStartup.vue";

const route = useRoute();
const message = useMessage();
const { user } = useAuth();

const STARTUP_HINT = "正在启动知识服务系统";

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
  const auth = session?.sso?.authorization;
  const q = new URLSearchParams({ zt_hide_file: "1" });
  if (session?.sso?.ready && auth) {
    q.set("auth", stripBearer(auth));
  }
  return `${base}/knowledge?${q.toString()}`;
}

function themePayload() {
  const base = embedSession.value?.theme || {};
  const name = (user.value?.username || "").trim();
  return {
    ...base,
    display_name: name || base.display_name,
    username: user.value?.username || base.username,
  };
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

async function loadMeta() {
  bootstrapping.value = true;
  iframeReady.value = false;
  iframeSrc.value = "";
  try {
    const [m, session] = await Promise.all([
      fetchRagMeta(),
      fetchRagEmbedSession().catch(() => null),
    ]);
    meta.value = m;
    embedSession.value = session;
    applyIframeSession(session);
  } catch (e) {
    message.error(e.message);
  } finally {
    bootstrapping.value = false;
  }
}

function onIframeLoad() {
  iframeReady.value = true;
  postSsoToIframe();
  postThemeToIframe();
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
        v-if="!bootstrapping && !meta.ui_available"
        type="warning"
        title="知识图谱服务未就绪"
        class="embed-alert"
      >
        <p>知识服务系统暂不可用，请稍后重试或联系管理员。</p>
        <p v-if="meta.ui_hint" style="margin: 8px 0 0">{{ meta.ui_hint }}</p>
        <template #action>
          <n-button size="small" @click="loadMeta">重新检测</n-button>
        </template>
      </n-alert>

      <n-alert
        v-if="!bootstrapping && meta.ui_available && embedSession?.sso && !embedSession.sso.ready"
        type="info"
        title="登录未完成"
        class="embed-alert"
      >
        {{ embedSession.sso.message || "请刷新页面重试。" }}
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
        title="知识图谱"
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
