<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NAlert, NButton, NFloatButton, NIcon, NSpin, NText } from "naive-ui";
import FeaturePageToolbar from "../components/FeaturePageToolbar.vue";
import { ArrowBackOutline } from "@vicons/ionicons5";
import { fetchFeatureEmbedMeta, getToken } from "../api/client";

const route = useRoute();
const router = useRouter();

const featureId = computed(() => route.meta.embedFeatureId || "");
const pageTitle = computed(() => route.meta.title || "功能");
const fullscreen = computed(() => Boolean(route.meta.knowflowNative));

const loading = ref(true);
const iframeLoading = ref(true);
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

function goBack() {
  router.push({ name: "system-functions" });
}

function onIframeLoad() {
  iframeLoading.value = false;
  loadSlow.value = false;
  if (slowTimer) {
    clearTimeout(slowTimer);
    slowTimer = null;
  }
}

function onIframeError() {
  iframeLoading.value = false;
  error.value =
    error.value ||
    "内嵌页面加载失败，请确认上游服务可访问且已配置反向代理（/api/v1/embed-proxy 或 /design-system-ui）";
}

function clearSlowTimer() {
  if (slowTimer) {
    clearTimeout(slowTimer);
    slowTimer = null;
  }
}

onMounted(async () => {
  if (!featureId.value) {
    error.value = "未指定功能";
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    meta.value = await fetchFeatureEmbedMeta(featureId.value);
    if (!meta.value?.available) {
      error.value = "未配置内嵌地址";
      iframeLoading.value = false;
      return;
    }
    slowTimer = setTimeout(() => {
      if (iframeLoading.value) loadSlow.value = true;
    }, 12000);
  } catch (e) {
    error.value = e.message || "加载失败";
    iframeLoading.value = false;
  } finally {
    loading.value = false;
  }
});

onBeforeUnmount(clearSlowTimer);
</script>

<template>
  <div v-if="fullscreen" class="embed-native">
    <n-spin :show="loading" class="embed-spin">
      <n-alert v-if="error" type="error" :title="`无法加载${pageTitle}`" class="embed-alert">
        {{ error }}
        <template #action>
          <n-button size="small" @click="goBack">返回</n-button>
        </template>
      </n-alert>
      <iframe
        v-else-if="iframeSrc"
        class="embed-frame embed-frame--fullscreen"
        :class="{ 'embed-frame--loading': iframeLoading }"
        :src="iframeSrc"
        :title="pageTitle"
        allow="fullscreen"
        referrerpolicy="no-referrer-when-downgrade"
        @load="onIframeLoad"
        @error="onIframeError"
      />
      <div v-if="iframeSrc && iframeLoading" class="embed-hint">
        {{ loadSlow ? "加载较慢，请检查上游服务或网络…" : `正在加载 ${pageTitle}…` }}
      </div>
    </n-spin>
    <n-float-button
      class="embed-back-float"
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

  <div v-else class="embed-panel-page feature-page feature-page--fill">
    <FeaturePageToolbar />

    <n-alert v-if="error" type="error" :title="`无法加载${pageTitle}`" class="embed-alert" />

    <div v-else-if="iframeSrc" class="embed-panel-frame-wrap">
      <n-spin :show="loading" class="embed-panel-spin">
        <div class="embed-panel-iframe-host">
          <iframe
            class="embed-frame embed-frame--panel"
            :class="{ 'embed-frame--loading': iframeLoading }"
            :src="iframeSrc"
            :title="pageTitle"
            allow="fullscreen"
            referrerpolicy="no-referrer-when-downgrade"
            @load="onIframeLoad"
            @error="onIframeError"
          />
          <div v-if="iframeLoading" class="embed-panel-overlay">
            <n-text depth="3">
              {{ loadSlow ? "加载较慢，请检查上游服务是否启动…" : `正在加载 ${pageTitle}…` }}
            </n-text>
          </div>
        </div>
      </n-spin>
    </div>
  </div>
</template>

<style scoped>
.embed-native {
  position: relative;
  width: 100%;
  height: 100vh;
  min-height: 480px;
  background: #f5f5f5;
}
.embed-panel-page {
  box-sizing: border-box;
}
.embed-spin {
  width: 100%;
  height: 100%;
}
.embed-spin :deep(.n-spin-container) {
  width: 100%;
  height: 100%;
}
.embed-panel-frame-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.embed-panel-spin {
  flex: 1;
  min-height: 0;
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
}
.embed-panel-spin :deep(.n-spin-container) {
  flex: 1;
  min-height: 0;
  height: 100% !important;
  display: flex;
  flex-direction: column;
}
.embed-panel-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.embed-panel-iframe-host {
  position: relative;
  flex: 1;
  min-height: 0;
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
}
.embed-panel-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.75);
  z-index: 2;
  pointer-events: none;
}
.embed-alert {
  margin: 0 0 12px;
  max-width: 720px;
}
.embed-frame {
  display: block;
  border: none;
  background: #fff;
  width: 100%;
}
.embed-frame--fullscreen {
  height: 100vh;
}
.embed-frame--panel {
  flex: 1;
  width: 100%;
  height: 100%;
  min-height: 0;
  border-radius: var(--platform-radius-sm, 8px);
  border: 1px solid var(--platform-border, var(--n-border-color));
  box-shadow: var(--platform-shadow);
}
.embed-frame--loading {
  opacity: 0.45;
}
.embed-hint {
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
.embed-back-float :deep(.n-float-button__body) {
  padding-inline: 10px;
}
</style>
