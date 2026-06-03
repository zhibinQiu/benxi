<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useAuth } from "../composables/useAuth";
import { useRoute, useRouter } from "vue-router";
import { NAlert, NButton } from "naive-ui";
import { fetchEncodingEmbedSession, fetchEncodingMeta } from "../api/rag.js";
import {
  KNOWLEDGE_UNAVAILABLE,
  knowflowUnavailableHint,
  sanitizeUserFacingMessage,
} from "../utils/uiMessage";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeServiceStartup from "../components/KnowledgeServiceStartup.vue";

const route = useRoute();
const router = useRouter();
const { user, isSystemAdmin } = useAuth();

const STARTUP_HINT = "正在启动知识服务系统";

const bootstrapping = ref(true);
const iframeReady = ref(false);
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
  return `${base}/user-setting/model?${q.toString()}`;
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
  bootstrapping.value = true;
  iframeSrc.value = "";

  try {
    const [m, session] = await Promise.all([
      fetchEncodingMeta(),
      fetchEncodingEmbedSession({ sync: true }),
    ]);
    meta.value = m;
    embedSession.value = session;

    if (meta.value.ui_embed_mode === "redirect" && meta.value.ui_available && session?.sso?.ready) {
      const ret = encodeURIComponent(
        `${window.location.origin}${router.resolve({ name: "system-functions" }).fullPath}`,
      );
      window.location.href = `${buildKnowflowUrl(session)}&platform_return=${ret}`;
      return;
    }

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
}

async function reloadKnowflowForUser() {
  if (route.name !== "rag") return;
  iframeReady.value = false;
  iframeSrc.value = "";
  embedSession.value = await fetchEncodingEmbedSession({ sync: false }).catch(
    () => null
  );
  applyIframeSession(embedSession.value);
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
    if (id && id !== prev && route.name === "rag" && !bootstrapping.value) {
      reloadKnowflowForUser();
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
        title="编码管理服务未就绪"
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
        id="knowflow-embed"
        class="subsystem-embed-frame"
        :class="{ 'subsystem-embed-frame--loading': showStartupHint }"
        :src="iframeSrc"
        title="编码管理"
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
