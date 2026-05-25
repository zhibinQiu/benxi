<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useAuth } from "../composables/useAuth";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NFloatButton,
  NIcon,
  NSpin,
  useMessage,
} from "naive-ui";
import { ArrowBackOutline } from "@vicons/ionicons5";
import { fetchRagEmbedSession, fetchRagMeta } from "../api/client";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const { user } = useAuth();

const loading = ref(true);
const iframeLoading = ref(false);
const meta = ref({
  ui_embed_url: "",
  ui_direct_url: "http://127.0.0.1:9380",
  ui_embed_mode: "iframe",
  ui_available: false,
  ui_hint: "",
  knowflow_enabled: false,
  integration_phase: 1,
});
const embedSession = ref(null);
/** 仅在拿到平台 embed-session 后设置，避免无 auth 的首屏加载触发 KnowFlow 登录页 */
const iframeSrc = ref("");

let iframeLoadTimer = null;

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
  return `${base}/?${q.toString()}`;
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
  const iframe = document.getElementById("knowflow-embed");
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

function clearIframeLoadTimer() {
  if (iframeLoadTimer) {
    clearTimeout(iframeLoadTimer);
    iframeLoadTimer = null;
  }
}

function armIframeLoadTimeout(ms = 20000) {
  clearIframeLoadTimer();
  iframeLoadTimer = setTimeout(() => {
    iframeLoading.value = false;
  }, ms);
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
  iframeLoading.value = true;
  iframeSrc.value = buildKnowflowUrl(session);
  armIframeLoadTimeout();
}

async function loadMeta() {
  loading.value = true;
  iframeSrc.value = "";
  clearIframeLoadTimer();
  try {
    const [m, session] = await Promise.all([
      fetchRagMeta(),
      fetchRagEmbedSession().catch(() => null),
    ]);
    meta.value = m;
    embedSession.value = session;

    if (meta.value.ui_embed_mode === "redirect" && meta.value.ui_available && session?.sso?.ready) {
      const ret = encodeURIComponent(window.location.origin + "/system/functions");
      window.location.href = `${buildKnowflowUrl(session)}&platform_return=${ret}`;
      return;
    }

    applyIframeSession(session);
  } catch (e) {
    message.error(e.message);
  } finally {
    loading.value = false;
  }
}

function goBack() {
  router.push({ name: "system-functions" });
}

function onIframeLoad() {
  clearIframeLoadTimer();
  iframeLoading.value = false;
  postSsoToIframe();
  postThemeToIframe();
}

async function reloadKnowflowForUser() {
  if (route.name !== "rag") return;
  loading.value = true;
  iframeSrc.value = "";
  try {
    embedSession.value = await fetchRagEmbedSession().catch(() => null);
    applyIframeSession(embedSession.value);
  } catch (e) {
    message.error(e.message);
    iframeLoading.value = false;
  } finally {
    loading.value = false;
  }
}

watch(
  () => route.name,
  (name) => {
    if (name === "rag") loadMeta();
  }
);

watch(
  () => user.value?.id,
  (id, prev) => {
    if (id && id !== prev && route.name === "rag" && !loading.value) {
      reloadKnowflowForUser();
    }
  }
);

onMounted(loadMeta);
onBeforeUnmount(clearIframeLoadTimer);
</script>

<template>
  <div class="knowflow-native">
    <n-spin :show="loading" class="knowflow-spin">
      <n-alert
        v-if="!loading && !meta.ui_available"
        type="warning"
        title="知识问答服务未就绪"
        class="knowflow-alert"
      >
        <p>KnowFlow（RAGFlow）Web 未启动或 :9380 不可访问，平台无法内嵌知识问答界面。</p>
        <p v-if="meta.ui_hint" style="margin: 8px 0 0">{{ meta.ui_hint }}</p>
        <p v-else style="margin: 8px 0 0">
          本地开发请执行：<code>bash scripts/start_platform.sh knowflow</code>，等待 RAGFlow 就绪后刷新。
          诊断：<code>bash scripts/check_knowflow.sh</code>
        </p>
        <template #action>
          <n-button size="small" @click="loadMeta">重新检测</n-button>
        </template>
      </n-alert>

      <n-alert
        v-if="!loading && meta.ui_available && embedSession?.sso && !embedSession.sso.ready"
        type="info"
        title="未自动登录 KnowFlow"
        class="knowflow-alert"
      >
        {{ embedSession.sso.message || "请刷新页面重试。" }}
        <template #action>
          <n-button size="small" @click="loadMeta">重试</n-button>
        </template>
      </n-alert>

      <iframe
        v-if="iframeSrc"
        id="knowflow-embed"
        class="knowflow-frame"
        :class="{ 'knowflow-frame--loading': iframeLoading }"
        :src="iframeSrc"
        title="知识问答"
        allow="fullscreen; clipboard-read; clipboard-write"
        referrerpolicy="no-referrer-when-downgrade"
        @load="onIframeLoad"
      />
      <div v-if="iframeSrc && iframeLoading" class="knowflow-iframe-hint">
        正在加载 KnowFlow…
      </div>
    </n-spin>

    <n-float-button
      class="knowflow-back-float"
      type="primary"
      :width="88"
      :height="54"
      :bottom="96"
      :left="24"
      @click="goBack"
    >
      <template #description>返回平台</template>
      <n-icon :component="ArrowBackOutline" />
    </n-float-button>
  </div>
</template>

<style scoped>
.knowflow-native {
  position: relative;
  width: 100%;
  height: 100vh;
  min-height: 480px;
  background: #f5f5f5;
}
.knowflow-spin {
  width: 100%;
  height: 100%;
}
.knowflow-spin :deep(.n-spin-container) {
  width: 100%;
  height: 100%;
}
.knowflow-alert {
  margin: 24px;
  max-width: 640px;
}
.knowflow-frame {
  display: block;
  width: 100%;
  height: 100vh;
  border: none;
  background: #fff;
}
.knowflow-frame--loading {
  opacity: 0.35;
}
.knowflow-iframe-hint {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 8px;
  font-size: 14px;
  color: #666;
  pointer-events: none;
  z-index: 2;
}
.knowflow-back-float :deep(.n-float-button__body) {
  padding-inline: 10px;
}
</style>
