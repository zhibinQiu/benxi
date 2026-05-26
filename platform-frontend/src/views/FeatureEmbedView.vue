<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute } from "vue-router";
import { NAlert, NButton, NText } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeServiceStartup from "../components/KnowledgeServiceStartup.vue";
import { fetchFeatureEmbedMeta, getToken } from "../api/client";

const route = useRoute();

const featureId = computed(() => route.meta.embedFeatureId || "");
const pageTitle = computed(() => route.meta.title || "功能");

const bootstrapping = ref(true);
const iframeReady = ref(false);
const meta = ref({ embed_url: "", available: false, requires_auth: true });
const error = ref("");
const loadSlow = ref(false);

let slowTimer = null;

const iframeSrc = computed(() => {
  const raw = (meta.value?.embed_url || "").trim();
  if (!raw) return "";
  let url;
  if (/^https?:\/\//i.test(raw)) {
    url = new URL(raw);
  } else {
    const path = raw.startsWith("/") ? raw : `/${raw}`;
    url = new URL(`${window.location.origin}${path}`);
  }
  if (meta.value.requires_auth !== false) {
    const token = getToken();
    if (token) url.searchParams.set("token", token);
  }
  return url.toString();
});

const showStartupHint = computed(
  () =>
    bootstrapping.value ||
    (Boolean(iframeSrc.value) && !iframeReady.value && !error.value)
);

const startupMessage = computed(() => {
  if (loadSlow.value) return "加载较慢，请稍候…";
  return "正在加载子系统…";
});

function onIframeLoad() {
  iframeReady.value = true;
  loadSlow.value = false;
  clearSlowTimer();
}

function onIframeError() {
  iframeReady.value = false;
  error.value =
    error.value ||
    "内嵌页面加载失败，请确认上游服务可访问且已配置反向代理。";
}

function clearSlowTimer() {
  if (slowTimer) {
    clearTimeout(slowTimer);
    slowTimer = null;
  }
}

function startSlowTimer() {
  clearSlowTimer();
  slowTimer = setTimeout(() => {
    if (!iframeReady.value) loadSlow.value = true;
  }, 12000);
}

async function loadEmbed() {
  if (!featureId.value) {
    error.value = "未指定功能";
    bootstrapping.value = false;
    return;
  }
  bootstrapping.value = true;
  iframeReady.value = false;
  loadSlow.value = false;
  error.value = "";
  clearSlowTimer();
  try {
    meta.value = await fetchFeatureEmbedMeta(featureId.value);
    if (!meta.value?.available) {
      error.value = "未配置内嵌地址";
      return;
    }
    startSlowTimer();
  } catch (e) {
    error.value = e.message || "加载失败";
  } finally {
    bootstrapping.value = false;
  }
}

onMounted(loadEmbed);
onBeforeUnmount(clearSlowTimer);
</script>

<template>
  <FeatureSubsystemShell fill>
    <div class="subsystem-embed-host">
      <n-alert v-if="error" type="error" :title="`无法加载${pageTitle}`" class="embed-alert">
        {{ error }}
        <template #action>
          <n-button size="small" @click="loadEmbed">重试</n-button>
        </template>
      </n-alert>

      <KnowledgeServiceStartup v-if="showStartupHint" :message="startupMessage" />

      <iframe
        v-if="iframeSrc && !error"
        class="subsystem-embed-frame"
        :class="{ 'subsystem-embed-frame--loading': showStartupHint }"
        :src="iframeSrc"
        :title="pageTitle"
        allow="fullscreen"
        referrerpolicy="no-referrer-when-downgrade"
        @load="onIframeLoad"
        @error="onIframeError"
      />
      <p v-if="loadSlow && showStartupHint" class="embed-slow-hint">
        <n-text depth="3">若长时间无响应，请检查上游服务或网络连接。</n-text>
      </p>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.embed-alert {
  margin: 16px;
  max-width: 640px;
}
.embed-slow-hint {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
  font-size: 12px;
}
</style>
