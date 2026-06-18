<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
import { computed, onMounted, reactive, ref } from "vue";
import {
  NAlert,
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NGrid,
  NGi,
  NIcon,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NTag,
  NText } from "naive-ui";
import {
  GlobeOutline,
  ColorPaletteOutline,
  ChatbubblesOutline,
  HardwareChipOutline,
  StatsChartOutline,
  ScanOutline,
  ImageOutline,
  MicOutline,
  VolumeHighOutline,
  LanguageOutline,
  SearchOutline,
  ServerOutline,
  LibraryOutline,
  ServerSharp } from "@vicons/ionicons5";
import {
  fetchModelSettings,
  fetchResourceHealth,
  testResourceHealth,
  updateModelSettings } from "../../api/client";
import { setApiBase } from "../../api/http";
import { applyClientBranding } from "../../composables/usePlatformBranding";
import { initAppFromServerConfig } from "../../composables/useAppPreferences";
import { useI18n } from "../../composables/useI18n";

const ui = usePlatformUi();
const { t } = useI18n();
const loading = ref(false);
const healthLoading = ref(false);
const saving = ref(false);
const testing = ref(false);
const settings = ref(null);
const health = ref({});
const drawerTestResult = ref(null);
const drawerOpen = ref(false);
const activeId = ref(null);

const form = reactive({
  platform_api_base_url: "",
  frontend_app_title: "",
  frontend_default_theme: "system",
  llm_base_url: "",
  llm_model: "",
  llm_api_key: "",
  embedding_base_url: "",
  embedding_model: "",
  embedding_factory: "",
  embedding_api_key: "",
  rerank_base_url: "",
  rerank_model: "",
  rerank_api_key: "",
  vl_base_url: "",
  vl_model: "",
  vl_api_key: "",
  paddleocr_base_url: "",
  paddleocr_model: "",
  paddleocr_api_key: "",
  paddleocr_url: "",
  tts_base_url: "",
  tts_model: "",
  tts_api_key: "",
  speech_service_url: "",
  pdf2zh_api_url: "",
  searxng_url: "",
  searxng_timeout_seconds: 15,
  ragflow_api_url: "",
  ragflow_api_key: "",
  knowflow_backend_url: "",
  knowflow_ui_url: "",
  knowflow_ui_public_url: "",
  knowflow_ui_proxy_prefix: "",
  ragflow_mysql_host: "",
  ragflow_mysql_port: 3306,
  ragflow_mysql_db: "",
  ragflow_mysql_password: "",
  ragflow_mysql_container: ""});

const RESOURCE_ICON_MAP = {
  platform_api: GlobeOutline,
  frontend: ColorPaletteOutline,
  llm: ChatbubblesOutline,
  embedding: HardwareChipOutline,
  vl: ImageOutline,
  rerank: StatsChartOutline,
  paddleocr: ScanOutline,
  speech: MicOutline,
  tts: VolumeHighOutline,
  pdf2zh: LanguageOutline,
  searxng: SearchOutline,
  ragflow_api: LibraryOutline,
  knowflow_backend: ServerOutline,
  ragflow_mysql: ServerSharp,
};

const RESOURCE_CATEGORY_MAP = {
  platform_api: "platform",
  frontend: "platform",
  llm: "model",
  embedding: "model",
  vl: "model",
  rerank: "model",
  paddleocr: "service",
  speech: "service",
  tts: "service",
  pdf2zh: "service",
  searxng: "service",
  ragflow_api: "knowledge",
  knowflow_backend: "knowledge",
  ragflow_mysql: "knowledge",
};

const RESOURCE_IDS = Object.keys(RESOURCE_ICON_MAP);

const themeOptions = computed(() => [
  { label: t("admin.modelSettings.theme.system"), value: "system" },
  { label: t("admin.modelSettings.theme.light"), value: "light" },
  { label: t("admin.modelSettings.theme.dark"), value: "dark" },
]);

const resourceDefs = computed(() =>
  RESOURCE_IDS.map((id) => ({
    id,
    title: t(`admin.modelSettings.resources.${id}.title`),
    hint: t(`admin.modelSettings.resources.${id}.hint`),
    icon: RESOURCE_ICON_MAP[id],
    category: RESOURCE_CATEGORY_MAP[id],
  }))
);

function categoryMeta(id) {
  return {
    title: t(`admin.modelSettings.categories.${id}.title`),
    hint: t(`admin.modelSettings.categories.${id}.hint`),
  };
}

const activeResource = computed(() =>
  resourceDefs.value.find((item) => item.id === activeId.value) || null
);

const groupedResources = computed(() =>
  ["platform", "model", "knowledge", "service"].map((id) => ({
    id,
    ...categoryMeta(id),
    items: resourceDefs.value.filter((item) => item.category === id),
  }))
);

function modelEndpoint(data, key, legacyKey) {
  return data?.[key] || data?.[legacyKey] || null;
}

function fillForm(data) {
  settings.value = data;
  form.platform_api_base_url = data?.platform_api_base_url || "";
  form.frontend_app_title = data?.frontend_app_title || "";
  form.frontend_default_theme = data?.frontend_default_theme || "system";
  form.llm_base_url = data?.llm?.base_url || "";
  form.llm_model = data?.llm?.model_name || "";
  form.llm_api_key = data?.llm?.api_key_masked || "";
  form.embedding_base_url = data?.embedding?.base_url || "";
  form.embedding_model = data?.embedding?.model_name || "";
  form.embedding_factory = data?.embedding_factory || "";
  form.embedding_api_key = data?.embedding?.api_key_masked || "";
  form.rerank_base_url = data?.rerank?.base_url || "";
  form.rerank_model = data?.rerank?.model_name || "";
  form.rerank_api_key = data?.rerank?.api_key_masked || "";
  const vl = modelEndpoint(data, "vl", "vision");
  form.vl_base_url = vl?.base_url || "";
  form.vl_model = vl?.model_name || "";
  form.vl_api_key = vl?.api_key_masked || "";
  form.paddleocr_base_url = data?.paddleocr?.base_url || data?.paddleocr_url || "";
  form.paddleocr_model = data?.paddleocr?.model_name || "";
  form.paddleocr_api_key = data?.paddleocr?.api_key_masked || "";
  form.paddleocr_url = data?.paddleocr_url || "";
  form.tts_base_url = data?.tts?.base_url || "";
  form.tts_model = data?.tts?.model_name || "";
  form.tts_api_key = data?.tts?.api_key_masked || "";
  form.speech_service_url = data?.speech_service_url || "";
  form.pdf2zh_api_url = data?.pdf2zh_api_url || "";
  form.searxng_url = data?.searxng_url || "";
  form.searxng_timeout_seconds = data?.searxng_timeout_seconds || 15;
  const kb = data?.knowledge || {};
  form.ragflow_api_url = kb.ragflow_api_url || "";
  form.ragflow_api_key = kb.ragflow_api_key_masked || "";
  form.knowflow_backend_url = kb.knowflow_backend_url || "";
  form.knowflow_ui_url = kb.knowflow_ui_url || "";
  form.knowflow_ui_public_url = kb.knowflow_ui_public_url || "";
  form.knowflow_ui_proxy_prefix = kb.knowflow_ui_proxy_prefix || "";
  form.ragflow_mysql_host = kb.ragflow_mysql_host || "";
  form.ragflow_mysql_port = kb.ragflow_mysql_port || 3306;
  form.ragflow_mysql_db = kb.ragflow_mysql_db || "";
  form.ragflow_mysql_password = kb.ragflow_mysql_password_masked || "";
  form.ragflow_mysql_container = kb.ragflow_mysql_container || "";
}

function resourceSummary(id) {
  const data = settings.value;
  if (!data) return t("common.loading");
  switch (id) {
    case "platform_api":
      return data.platform_api_base_url
        ? truncate(data.platform_api_base_url)
        : t("admin.modelSettings.summary.defaultApi");
    case "frontend": {
      const themeLabel =
        themeOptions.value.find((item) => item.value === data.frontend_default_theme)?.label ||
        t("admin.modelSettings.theme.systemShort");
      const title = data.frontend_app_title || t("admin.modelSettings.summary.systemName");
      return `${title} · ${themeLabel}`;
    }
    case "llm":
      return data.llm?.model_name
        ? `${data.llm.model_name} · ${truncate(data.llm.base_url)}`
        : t("admin.modelSettings.summary.notConfigured");
    case "embedding":
      return data.embedding?.model_name
        ? `${data.embedding.model_name} · ${truncate(data.embedding.base_url)}`
        : t("admin.modelSettings.summary.notConfigured");
    case "vl": {
      const vl = modelEndpoint(data, "vl", "vision");
      if (!vl?.model_name) return t("admin.modelSettings.summary.notConfigured");
      if (!vl.base_url) return t("admin.modelSettings.summary.noApiUrl", { model: vl.model_name });
      if (!vl.api_key_configured) return t("admin.modelSettings.summary.noApiKey", { model: vl.model_name });
      return `${vl.model_name} · ${truncate(vl.base_url)}`;
    }
    case "rerank":
      return data.rerank?.model_name
        ? `${data.rerank.model_name} · ${truncate(data.rerank.base_url)}`
        : t("admin.modelSettings.summary.optionalNotConfigured");
    case "paddleocr":
      return data.paddleocr?.model_name
        ? `${data.paddleocr.model_name} · ${truncate(data.paddleocr.base_url)}`
        : data.paddleocr_url
          ? truncate(data.paddleocr_url)
          : t("admin.modelSettings.summary.notConfigured");
    case "speech":
      return data.speech_service_url
        ? truncate(data.speech_service_url)
        : t("admin.modelSettings.summary.notConfigured");
    case "tts":
      return data.tts?.model_name
        ? `${data.tts.model_name} · ${truncate(data.tts.base_url)}`
        : t("admin.modelSettings.summary.notConfigured");
    case "pdf2zh":
      return data.pdf2zh_api_url
        ? truncate(data.pdf2zh_api_url)
        : t("admin.modelSettings.summary.notConfigured");
    case "searxng":
      return data.searxng_url
        ? t("admin.modelSettings.summary.seconds", {
            url: truncate(data.searxng_url),
            seconds: data.searxng_timeout_seconds || 15,
          })
        : t("admin.modelSettings.summary.notConfigured");
    case "ragflow_api":
      return data.knowledge?.ragflow_api_url
        ? truncate(data.knowledge.ragflow_api_url)
        : t("admin.modelSettings.summary.notConfigured");
    case "knowflow_backend": {
      const kb = data.knowledge;
      const parts = [];
      if (kb?.knowflow_backend_url) {
        parts.push(t("admin.modelSettings.summary.apiPrefix", { url: truncate(kb.knowflow_backend_url) }));
      }
      if (kb?.knowflow_ui_url) {
        parts.push(t("admin.modelSettings.summary.uiPrefix", { url: truncate(kb.knowflow_ui_url) }));
      }
      return parts.length ? parts.join(" · ") : t("admin.modelSettings.summary.notConfigured");
    }
    case "ragflow_mysql": {
      const kb = data.knowledge;
      if (!kb?.ragflow_mysql_host && !kb?.ragflow_mysql_password_configured) {
        return kb?.knowflow_enabled
          ? t("admin.modelSettings.summary.dockerDefault")
          : t("admin.modelSettings.summary.notConfigured");
      }
      const host = kb.ragflow_mysql_host || "knowflow-mysql";
      return `${host}:${kb.ragflow_mysql_port || 3306}/${kb.ragflow_mysql_db || "rag_flow"}`;
    }
    default:
      return "";
  }
}

function truncate(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  if (text.length <= 42) return text;
  return `${text.slice(0, 39)}…`;
}

function healthState(id) {
  const item = health.value[id];
  if (!item) return healthLoading.value ? "checking" : "neutral";
  if (item.healthy === true) return "ok";
  if (item.healthy === false) return "bad";
  return "neutral";
}

function healthTitle(id) {
  const item = health.value[id];
  if (healthLoading.value && !item) return t("admin.modelSettings.health.checking");
  if (!item) return t("admin.modelSettings.health.notChecked");
  if (item.healthy === true) return item.message || t("admin.modelSettings.health.healthy");
  if (item.healthy === false) return item.message || t("admin.modelSettings.health.unhealthy");
  return item.message || t("admin.modelSettings.health.notConfigured");
}

const drawerHealthAlert = computed(() => {
  if (drawerTestResult.value) return drawerTestResult.value;
  if (activeId.value) return health.value[activeId.value] || null;
  return null;
});

const drawerHealthType = computed(() => {
  const item = drawerHealthAlert.value;
  if (!item) return "default";
  if (item.healthy === true) return "success";
  if (item.healthy === false) return "error";
  return "default";
});

const drawerHealthMessage = computed(() => {
  const item = drawerHealthAlert.value;
  if (!item) return "";
  if (drawerTestResult.value) {
    const prefix = drawerTestResult.value.healthy
      ? t("admin.modelSettings.health.testPassed")
      : t("admin.modelSettings.health.testFailed");
    return `${prefix}${item.message || (item.healthy ? t("admin.modelSettings.health.connectionOk") : t("admin.modelSettings.health.connectionFailed"))}`;
  }
  return healthTitle(activeId.value);
});

const canTestActive = computed(
  () =>
    activeId.value &&
    activeId.value !== "frontend" &&
    settings.value?.editable !== false
);

async function loadSettings() {
  loading.value = true;
  try {
    fillForm(await fetchModelSettings());
  } catch (e) {
    ui.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function loadHealth() {
  healthLoading.value = true;
  try {
    const data = await fetchResourceHealth();
    health.value = data?.items || {};
  } catch (e) {
    ui.error(e.message);
  } finally {
    healthLoading.value = false;
  }
}

async function loadAll() {
  await Promise.all([loadSettings(), loadHealth()]);
}

function openResource(id) {
  activeId.value = id;
  drawerTestResult.value = null;
  drawerOpen.value = true;
}

function buildPayloadFor(id) {
  switch (id) {
    case "platform_api":
      return {
        platform_api_base_url: form.platform_api_base_url.trim()};
    case "frontend":
      return {
        frontend_app_title: form.frontend_app_title.trim(),
        frontend_default_theme: form.frontend_default_theme || "system"};
    case "llm":
      return {
        llm_base_url: form.llm_base_url.trim(),
        llm_model: form.llm_model.trim(),
        ...(form.llm_api_key && !form.llm_api_key.includes("••••")
          ? { llm_api_key: form.llm_api_key.trim() }
          : {})};
    case "embedding":
      return {
        embedding_base_url: form.embedding_base_url.trim(),
        embedding_model: form.embedding_model.trim(),
        embedding_factory: form.embedding_factory.trim(),
        ...(form.embedding_api_key && !form.embedding_api_key.includes("••••")
          ? { embedding_api_key: form.embedding_api_key.trim() }
          : {})};
    case "rerank":
      return {
        rerank_base_url: form.rerank_base_url.trim(),
        rerank_model: form.rerank_model.trim(),
        ...(form.rerank_api_key && !form.rerank_api_key.includes("••••")
          ? { rerank_api_key: form.rerank_api_key.trim() }
          : {})};
    case "vl":
      return {
        vl_base_url: form.vl_base_url.trim(),
        vl_model: form.vl_model.trim(),
        ...(form.vl_api_key && !form.vl_api_key.includes("••••")
          ? { vl_api_key: form.vl_api_key.trim() }
          : {})};
    case "paddleocr":
      return {
        paddleocr_base_url: form.paddleocr_base_url.trim(),
        paddleocr_model: form.paddleocr_model.trim(),
        ...(form.paddleocr_api_key && !form.paddleocr_api_key.includes("••••")
          ? { paddleocr_api_key: form.paddleocr_api_key.trim() }
          : {})};
    case "speech":
      return { speech_service_url: form.speech_service_url.trim() };
    case "tts":
      return {
        tts_base_url: form.tts_base_url.trim(),
        tts_model: form.tts_model.trim(),
        ...(form.tts_api_key && !form.tts_api_key.includes("••••")
          ? { tts_api_key: form.tts_api_key.trim() }
          : {})};
    case "pdf2zh":
      return { pdf2zh_api_url: form.pdf2zh_api_url.trim() };
    case "searxng":
      return {
        searxng_url: form.searxng_url.trim(),
        searxng_timeout_seconds: Number(form.searxng_timeout_seconds) || 15,
      };
    case "ragflow_api":
      return {
        ragflow_api_url: form.ragflow_api_url.trim(),
        ...(form.ragflow_api_key && !form.ragflow_api_key.includes("••••")
          ? { ragflow_api_key: form.ragflow_api_key.trim() }
          : {})};
    case "knowflow_backend":
      return {
        knowflow_backend_url: form.knowflow_backend_url.trim(),
        knowflow_ui_url: form.knowflow_ui_url.trim(),
        knowflow_ui_public_url: form.knowflow_ui_public_url.trim(),
        knowflow_ui_proxy_prefix: form.knowflow_ui_proxy_prefix.trim()};
    case "ragflow_mysql":
      return {
        ragflow_mysql_host: form.ragflow_mysql_host.trim(),
        ragflow_mysql_port: Number(form.ragflow_mysql_port) || 3306,
        ragflow_mysql_db: form.ragflow_mysql_db.trim(),
        ragflow_mysql_container: form.ragflow_mysql_container.trim(),
        ...(form.ragflow_mysql_password && !form.ragflow_mysql_password.includes("••••")
          ? { ragflow_mysql_password: form.ragflow_mysql_password.trim() }
          : {})};
    default:
      return {};
  }
}

async function testActive() {
  if (!canTestActive.value) return;
  testing.value = true;
  drawerTestResult.value = null;
  try {
    const probeTimeoutMs = ["vl", "llm", "embedding", "tts"].includes(activeId.value)
      ? 60000
      : undefined;
    const result = await testResourceHealth(
      activeId.value,
      buildPayloadFor(activeId.value),
      probeTimeoutMs
    );
    drawerTestResult.value = result;
    if (result?.healthy) {
      ui.success(result.message || t("admin.modelSettings.messages.connectionOk"));
    } else if (result?.healthy === false) {
      ui.warning(result.message || t("admin.modelSettings.messages.connectionFailed"));
    } else {
      ui.info(result?.message || t("admin.modelSettings.messages.testNotNeeded"));
    }
  } catch (e) {
    ui.error(e.message);
  } finally {
    testing.value = false;
  }
}

async function saveActive() {
  if (!activeId.value) return;
  saving.value = true;
  try {
    fillForm(await updateModelSettings(buildPayloadFor(activeId.value)));
    if (activeId.value === "platform_api") {
      setApiBase(form.platform_api_base_url.trim() || "/ai");
      ui.success(t("admin.modelSettings.messages.savedApi"));
    } else if (activeId.value === "frontend") {
      applyClientBranding({
        app_title: form.frontend_app_title.trim(),
        default_theme: form.frontend_default_theme});
      initAppFromServerConfig({ default_theme: form.frontend_default_theme });
      ui.success(t("admin.modelSettings.messages.savedFrontend"));
    } else {
      ui.success(t("admin.modelSettings.messages.savedDefault"));
    }
    drawerOpen.value = false;
    drawerTestResult.value = null;
    await loadHealth();
  } catch (e) {
    ui.error(e.message);
  } finally {
    saving.value = false;
  }
}

onMounted(loadAll);
</script>

<template>
  <div class="resource-settings-page feature-page">
    <div class="page-toolbar feature-local-nav">
      <n-space>
        <n-button :loading="loading || healthLoading" @click="loadAll">
          {{ t("admin.modelSettings.refreshStatus") }}
        </n-button>
      </n-space>
    </div>

    <section
      v-for="group in groupedResources"
      :key="group.id"
      class="category-block"
      :style="{
        '--cat-accent':
          group.id === 'platform'
            ? '#2563eb'
            : group.id === 'model'
              ? '#6366f1'
              : group.id === 'knowledge'
                ? '#7c3aed'
                : '#5b9cf5',
        '--cat-accent-soft':
          group.id === 'platform'
            ? 'rgba(37, 99, 235, 0.1)'
            : group.id === 'model'
              ? 'rgba(99, 102, 241, 0.1)'
              : group.id === 'knowledge'
                ? 'rgba(124, 58, 237, 0.1)'
                : 'rgba(91, 156, 245, 0.1)'}"
    >
      <div class="category-block__head">
        <div class="category-block__text">
          <div class="category-block__row">
            <h2 class="category-block__title">{{ group.title }}</h2>
          </div>
          <n-text depth="3" class="category-block__hint">{{ group.hint }}</n-text>
        </div>
      </div>

      <n-grid
        cols="2 s:3 m:4 xl:5"
        :x-gap="14"
        :y-gap="14"
        responsive="screen"
        class="category-grid"
      >
        <n-gi v-for="(item, index) in group.items" :key="item.id" class="resource-card-wrap">
          <span
            class="resource-status-dot"
            :class="`resource-status-dot--${healthState(item.id)}`"
            :title="healthTitle(item.id)"
            aria-hidden="true"
          />
          <article
            class="feature-card resource-card"
            role="button"
            tabindex="0"
            :style="{ '--enter-delay': `${Math.min(index, 10) * 28}ms` }"
            @click="openResource(item.id)"
            @keydown.enter.prevent="openResource(item.id)"
            @keydown.space.prevent="openResource(item.id)"
          >
            <div class="feature-card__top">
              <div class="feature-card__icon">
                <n-icon :size="17">
                  <component :is="item.icon" />
                </n-icon>
              </div>
            </div>
            <h3 class="feature-card__title">{{ item.title }}</h3>
            <p class="feature-card__desc">{{ item.hint }}</p>
            <p class="resource-card__summary">{{ resourceSummary(item.id) }}</p>
          </article>
        </n-gi>
      </n-grid>
    </section>

    <n-drawer v-model:show="drawerOpen" :width="520" placement="right">
      <n-drawer-content
        v-if="activeResource"
        :title="activeResource.title"
        closable
      >
        <n-form label-placement="left" label-width="108">
          <template v-if="activeId === 'platform_api'">
            <n-form-item :label="t('admin.modelSettings.labels.apiRoot')">
              <n-input
                v-model:value="form.platform_api_base_url"
                :placeholder="t('admin.modelSettings.placeholders.apiRoot')"
              />
            </n-form-item>
            <div
              class="drawer-hint"
              v-html="t('admin.modelSettings.hints.platformApi')"
            />
          </template>

          <template v-else-if="activeId === 'frontend'">
            <n-form-item :label="t('admin.modelSettings.labels.appTitle')">
              <n-input
                v-model:value="form.frontend_app_title"
                :placeholder="t('admin.modelSettings.placeholders.appTitle')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.defaultTheme')">
              <n-select
                v-model:value="form.frontend_default_theme"
                :options="themeOptions"
              />
            </n-form-item>
            <div
              class="drawer-hint"
              v-html="t('admin.modelSettings.hints.frontend')"
            />
          </template>

          <template v-else-if="activeId === 'llm'">
            <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
              <n-input
                v-model:value="form.llm_base_url"
                :placeholder="t('admin.modelSettings.placeholders.llmApiUrl')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.modelName')">
              <n-input
                v-model:value="form.llm_model"
                :placeholder="t('admin.modelSettings.placeholders.modelName')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
              <n-input
                v-model:value="form.llm_api_key"
                type="password"
                show-password-on="click"
                :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
              />
            </n-form-item>
          </template>

          <template v-else-if="activeId === 'embedding'">
            <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
              <n-input
                v-model:value="form.embedding_base_url"
                :placeholder="t('admin.modelSettings.placeholders.embeddingApiUrl')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.modelName')">
              <n-input
                v-model:value="form.embedding_model"
                :placeholder="t('admin.modelSettings.placeholders.embeddingModel')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.provider')">
              <n-input
                v-model:value="form.embedding_factory"
                :placeholder="t('admin.modelSettings.placeholders.embeddingFactory')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
              <n-input
                v-model:value="form.embedding_api_key"
                type="password"
                show-password-on="click"
                :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
              />
            </n-form-item>
          </template>

          <template v-else-if="activeId === 'vl'">
            <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
              <n-input
                v-model:value="form.vl_base_url"
                :placeholder="t('admin.modelSettings.placeholders.vlApiUrl')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.modelName')">
              <n-input
                v-model:value="form.vl_model"
                :placeholder="t('admin.modelSettings.placeholders.vlModel')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
              <n-input
                v-model:value="form.vl_api_key"
                type="password"
                show-password-on="click"
                :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
              />
            </n-form-item>
            <div class="drawer-hint" v-html="t('admin.modelSettings.hints.vl')" />
          </template>

          <template v-else-if="activeId === 'rerank'">
            <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
              <n-input
                v-model:value="form.rerank_base_url"
                :placeholder="t('admin.modelSettings.placeholders.rerankOptional')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.modelName')">
              <n-input
                v-model:value="form.rerank_model"
                :placeholder="t('admin.modelSettings.placeholders.rerankOptional')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
              <n-input
                v-model:value="form.rerank_api_key"
                type="password"
                show-password-on="click"
                :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
              />
            </n-form-item>
          </template>

          <template v-else-if="activeId === 'paddleocr'">
            <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
              <n-input
                v-model:value="form.paddleocr_base_url"
                :placeholder="t('admin.modelSettings.placeholders.paddleocrApiUrl')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.modelName')">
              <n-input
                v-model:value="form.paddleocr_model"
                :placeholder="t('admin.modelSettings.placeholders.paddleocrModel')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
              <n-input
                v-model:value="form.paddleocr_api_key"
                type="password"
                show-password-on="click"
                :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
              />
            </n-form-item>
            <div
              class="drawer-hint"
              v-html="t('admin.modelSettings.hints.paddleocr')"
            />
          </template>

          <template v-else-if="activeId === 'speech'">
            <n-form-item :label="t('admin.modelSettings.labels.serviceUrl')">
              <n-input
                v-model:value="form.speech_service_url"
                :placeholder="t('admin.modelSettings.placeholders.speechUrl')"
              />
            </n-form-item>
            <div class="drawer-hint" v-html="t('admin.modelSettings.hints.speech')" />
          </template>

          <template v-else-if="activeId === 'tts'">
            <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
              <n-input
                v-model:value="form.tts_base_url"
                :placeholder="t('admin.modelSettings.placeholders.ttsApiUrl')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.modelName')">
              <n-input
                v-model:value="form.tts_model"
                :placeholder="t('admin.modelSettings.placeholders.ttsModel')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
              <n-input
                v-model:value="form.tts_api_key"
                type="password"
                show-password-on="click"
                :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
              />
            </n-form-item>
            <div class="drawer-hint" v-html="t('admin.modelSettings.hints.tts')" />
          </template>

          <template v-else-if="activeId === 'pdf2zh'">
            <n-form-item :label="t('admin.modelSettings.labels.serviceUrl')">
              <n-input
                v-model:value="form.pdf2zh_api_url"
                :placeholder="t('admin.modelSettings.placeholders.pdf2zhUrl')"
              />
            </n-form-item>
            <div class="drawer-hint" v-html="t('admin.modelSettings.hints.pdf2zh')" />
          </template>

          <template v-else-if="activeId === 'searxng'">
            <n-form-item :label="t('admin.modelSettings.labels.serviceUrl')">
              <n-input
                v-model:value="form.searxng_url"
                :placeholder="t('admin.modelSettings.placeholders.searxngUrl')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.requestTimeout')">
              <n-input-number
                v-model:value="form.searxng_timeout_seconds"
                :min="3"
                :max="120"
                style="width: 100%"
              >
                <template #suffix>{{ t("admin.modelSettings.secondsSuffix") }}</template>
              </n-input-number>
            </n-form-item>
            <div class="drawer-hint" v-html="t('admin.modelSettings.hints.searxng')" />
          </template>

          <template v-else-if="activeId === 'ragflow_api'">
            <n-form-item :label="t('admin.modelSettings.labels.apiAddress')">
              <n-input
                v-model:value="form.ragflow_api_url"
                :placeholder="t('admin.modelSettings.placeholders.ragflowApiUrl')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
              <n-input
                v-model:value="form.ragflow_api_key"
                type="password"
                show-password-on="click"
                :placeholder="t('admin.modelSettings.placeholders.ragflowApiKey')"
              />
            </n-form-item>
            <div class="drawer-hint" v-html="t('admin.modelSettings.hints.ragflowApi')" />
          </template>

          <template v-else-if="activeId === 'knowflow_backend'">
            <n-form-item :label="t('admin.modelSettings.labels.apiBackend')">
              <n-input
                v-model:value="form.knowflow_backend_url"
                :placeholder="t('admin.modelSettings.placeholders.knowflowBackend')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.webUiBackend')">
              <n-input
                v-model:value="form.knowflow_ui_url"
                :placeholder="t('admin.modelSettings.placeholders.knowflowUi')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.iframeBase')">
              <n-input
                v-model:value="form.knowflow_ui_public_url"
                :placeholder="t('admin.modelSettings.placeholders.knowflowPublic')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.proxyPrefix')">
              <n-input
                v-model:value="form.knowflow_ui_proxy_prefix"
                :placeholder="t('admin.modelSettings.placeholders.knowflowProxy')"
              />
            </n-form-item>
            <div
              class="drawer-hint"
              v-html="t('admin.modelSettings.hints.knowflowBackend')"
            />
          </template>

          <template v-else-if="activeId === 'ragflow_mysql'">
            <n-form-item :label="t('admin.modelSettings.labels.host')">
              <n-input
                v-model:value="form.ragflow_mysql_host"
                :placeholder="t('admin.modelSettings.placeholders.mysqlHost')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.port')">
              <n-input-number
                v-model:value="form.ragflow_mysql_port"
                :min="1"
                :max="65535"
                style="width: 100%"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.database')">
              <n-input
                v-model:value="form.ragflow_mysql_db"
                :placeholder="t('admin.modelSettings.placeholders.mysqlDb')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.rootPassword')">
              <n-input
                v-model:value="form.ragflow_mysql_password"
                type="password"
                show-password-on="click"
                :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.dockerContainer')">
              <n-input
                v-model:value="form.ragflow_mysql_container"
                :placeholder="t('admin.modelSettings.placeholders.mysqlContainer')"
              />
            </n-form-item>
            <div
              class="drawer-hint"
              v-html="t('admin.modelSettings.hints.ragflowMysql')"
            />
          </template>
        </n-form>

        <n-alert
          v-if="drawerHealthAlert"
          :type="drawerHealthType"
          :bordered="false"
          style="margin-top: 12px"
        >
          {{ drawerHealthMessage }}
        </n-alert>

        <template #footer>
          <n-space>
            <n-button
              v-if="canTestActive"
              :loading="testing"
              :disabled="saving"
              @click="testActive"
            >
              {{ t("admin.modelSettings.testConnectivity") }}
            </n-button>
            <n-button type="primary" :loading="saving" :disabled="testing" @click="saveActive">
              {{ t("admin.modelSettings.saveAndApply") }}
            </n-button>
            <n-button @click="drawerOpen = false">{{ t("common.cancel") }}</n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style scoped>
.resource-settings-page {
  width: 100%;
  max-width: 1280px;
}

.page-toolbar {
  display: flex;
  justify-content: flex-end;
}

.category-block {
  margin-top: 18px;
}

.category-block__head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
  padding: 0 0 8px 10px;
  border-left: 3px solid var(--cat-accent, var(--platform-accent));
}

.category-block__text {
  min-width: 0;
  flex: 1;
}

.category-block__row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.category-block__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
}

.category-block__hint {
  display: block;
  margin-top: 2px;
  font-size: 12px;
}

.category-grid :deep(> *) {
  display: flex;
}

.resource-card-wrap {
  position: relative;
  display: flex;
  width: 100%;
  padding-top: 4px;
  padding-right: 4px;
}

.resource-status-dot {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 2;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 2px solid var(--platform-bg-elevated, #fff);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--platform-border) 80%, transparent);
}

.resource-status-dot--ok {
  background: var(--platform-accent);
}

.resource-status-dot--bad {
  background: #ef4444;
}

.resource-status-dot--neutral {
  background: #94a3b8;
}

.resource-status-dot--checking {
  background: #94a3b8;
  animation: status-pulse 1.2s ease-in-out infinite;
}

@keyframes status-pulse {
  0%,
  100% {
    opacity: 0.45;
  }
  50% {
    opacity: 1;
  }
}

.feature-card {
  flex: 1;
  width: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  padding: 11px 12px;
  border-radius: var(--platform-radius-sm, 10px);
  background: var(--platform-bg-elevated);
  border: 1px solid var(--platform-border);
  box-shadow: var(--platform-shadow-sm);
  cursor: pointer;
  outline: none;
  animation: feature-card-in 0.34s cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: var(--enter-delay, 0ms);
  transition:
    transform 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.feature-card:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--cat-accent) 35%, transparent);
  box-shadow:
    var(--platform-shadow),
    0 0 0 1px color-mix(in srgb, var(--cat-accent) 10%, transparent);
}

.resource-card--readonly {
  cursor: default;
}

.resource-card--readonly:hover {
  transform: none;
  border-color: var(--platform-border);
  box-shadow: var(--platform-shadow-sm);
}

.feature-card:focus-visible {
  box-shadow:
    0 0 0 2px var(--platform-bg-elevated),
    0 0 0 4px var(--cat-accent);
}

.feature-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 6px;
}

.feature-card__icon {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--cat-accent, var(--platform-accent));
  background: var(--cat-accent-soft, var(--platform-accent-soft));
  transition: transform 0.2s ease;
}

.feature-card:hover .feature-card__icon {
  transform: scale(1.04);
}

.feature-card__title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
}

.feature-card__desc {
  margin: 4px 0 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--platform-text-tertiary);
}

.resource-card__summary {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.4;
  color: var(--platform-text-secondary);
  word-break: break-all;
}

.drawer-hint {
  display: block;
  font-size: 12px;
  line-height: 1.55;
}

@keyframes feature-card-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
