<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute } from "vue-router";
import { NAlert, NButton, NText } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeServiceStartup from "../components/KnowledgeServiceStartup.vue";
import { fetchFeatureEmbedMeta, getToken } from "../api/client";
import { useI18n } from "../composables/useI18n.js";
import { FEATURE_UNAVAILABLE, sanitizeUserFacingMessage } from "../utils/uiMessage";

const route = useRoute();
const { t, routeTitle } = useI18n();

const featureId = computed(() => route.meta.embedFeatureId || "");
const pageTitle = computed(() =>
  routeTitle(String(route.name || ""), String(route.meta.title || "").trim() || t("featureEmbed.defaultTitle"))
);

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

const startupMessage = computed(() =>
  loadSlow.value ? t("featureEmbed.loadSlow") : t("featureEmbed.loading")
);

const loadErrorTitle = computed(() => t("featureEmbed.loadFailed", { title: pageTitle.value }));

function onIframeLoad() {
  iframeReady.value = true;
  loadSlow.value = false;
  clearSlowTimer();
}

function onIframeError() {
  iframeReady.value = false;
  error.value = error.value || FEATURE_UNAVAILABLE;
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
    error.value = t("featureEmbed.noFeature");
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
      error.value = FEATURE_UNAVAILABLE;
      return;
    }
    startSlowTimer();
  } catch (e) {
    error.value = sanitizeUserFacingMessage(e.message, FEATURE_UNAVAILABLE);
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
      <n-alert v-if="error" type="error" :title="loadErrorTitle" class="embed-alert">
        {{ error }}
        <template #action>
          <n-button size="small" @click="loadEmbed">{{ t("chat.retry") }}</n-button>
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
        <n-text depth="3">{{ t("featureEmbed.slowHint") }}</n-text>
      </p>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.embed-alert {
  margin: 19px;
  max-width: 768px;
}
.embed-slow-hint {
  position: absolute;
  bottom: 19px;
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
  font-size: 14px;
}
</style>
