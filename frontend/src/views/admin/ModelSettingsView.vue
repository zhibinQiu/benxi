<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
import { computed, onMounted, reactive, ref } from "vue";
import {
  NAlert,
  NButton,
  NColorPicker,
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
  NSwitch,
  NText } from "naive-ui";
import {
  GlobeOutline,
  ColorPaletteOutline,
  ChatbubblesOutline,
  HardwareChipOutline,
  StatsChartOutline,
  ScanOutline,
  EyeOutline,
  MicOutline,
  VolumeHighOutline,
  LanguageOutline,
  SearchOutline,
  ServerOutline,
  LibraryOutline,
} from "@vicons/ionicons5";
import {
  fetchModelSettings,
  fetchResourceHealth,
  testResourceHealth,
  updateModelSettings } from "../../api/client";
import { setApiBase } from "../../api/http";
import { applyClientBranding } from "../../composables/usePlatformBranding";
import { initAppFromServerConfig } from "../../composables/useAppPreferences";
import { COLOR_SCHEME_CUSTOM, DEFAULT_COLOR_SCHEME, normalizeColorScheme } from "../../constants/colorSchemes.js";
import { adminResourceGroupAccentStyle } from "../../constants/categoryAccents.js";
import { DEFAULT_CUSTOM_PRIMARY, normalizePrimaryColor } from "../../utils/customColorTokens.js";
import { useI18n } from "../../composables/useI18n";
import ListRefreshButton from "../../components/ListRefreshButton.vue";

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
const providerTestResults = ref({});

const PROVIDER_RESOURCE_IDS = new Set(["llm", "multimodal", "embedding", "rerank", "paddleocr", "tts"]);

let providerIdCounter = Date.now();
function generateProviderId() {
  return `prov_${providerIdCounter++}`;
}

function createEmptyProvider() {
  return {
    id: generateProviderId(),
    label: "",
    base_url: "",
    model_name: "",
    api_key: "",
  };
}

const form = reactive({
  platform_api_base_url: "",
  frontend_app_title: "",
  frontend_default_theme: "system",
  frontend_color_scheme: DEFAULT_COLOR_SCHEME,
  frontend_primary_color: DEFAULT_CUSTOM_PRIMARY,
  llm_base_url: "",
  llm_model: "",
  llm_api_key: "",
  llm_providers: [],
  llm_active_provider: "",
  multimodal_base_url: "",
  multimodal_model: "",
  multimodal_api_key: "",
  multimodal_providers: [],
  multimodal_active_provider: "",
  embedding_base_url: "",
  embedding_model: "",
  embedding_factory: "",
  embedding_api_key: "",
  embedding_providers: [],
  embedding_active_provider: "",
  rerank_base_url: "",
  rerank_model: "",
  rerank_api_key: "",
  rerank_providers: [],
  rerank_active_provider: "",
  paddleocr_base_url: "",
  paddleocr_model: "",
  paddleocr_api_key: "",
  paddleocr_url: "",
  paddleocr_providers: [],
  paddleocr_active_provider: "",
  tts_base_url: "",
  tts_model: "",
  tts_api_key: "",
  tts_providers: [],
  tts_active_provider: "",
  speech_service_url: "",
  pdf2zh_api_url: "",
  searxng_url: "",
  searxng_timeout_seconds: 15,
  firecrawl_api_key: "",
  firecrawl_api_url: "",
  firecrawl_read_full_max_urls: 3,
  agent_browser_enabled: false,
  agent_browser_headless: true,
  agent_browser_allowed_domains: "",
  agent_browser_max_steps_per_session: 50,
  agent_browser_auto_task_enabled: true,
  agent_browser_auto_task_max_steps: 15,
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
  multimodal: EyeOutline,
  embedding: HardwareChipOutline,
  rerank: StatsChartOutline,
  paddleocr: ScanOutline,
  speech: MicOutline,
  tts: VolumeHighOutline,
  pdf2zh: LanguageOutline,
  searxng: SearchOutline,
  browser_rpa: GlobeOutline,
  ragflow_api: LibraryOutline,
  knowflow_backend: ServerOutline,
  ragflow_mysql: ServerOutline,
};

const RESOURCE_CATEGORY_MAP = {
  platform_api: "platform",
  frontend: "platform",
  llm: "model",
  multimodal: "model",
  embedding: "model",
  rerank: "model",
  paddleocr: "service",
  speech: "service",
  tts: "service",
  pdf2zh: "service",
  searxng: "service",
  browser_rpa: "service",
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

const colorSchemeOptions = computed(() => [
  { label: t("admin.modelSettings.colorScheme.blue"), value: "blue" },
  { label: t("admin.modelSettings.colorScheme.custom"), value: "custom" },
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

function activeProviderSummary(id, endpointName) {
  const data = settings.value;
  if (!data) return t("common.loading");
  const ep = data[endpointName];
  if (!ep) return t("admin.modelSettings.summary.notConfigured");
  const providers = ep.providers;
  const activeId = ep.active_provider;
  if (Array.isArray(providers) && providers.length > 0) {
    const active = providers.find((p) => p.id === activeId) || providers[0];
    if (!active || (!active.base_url && !active.model_name)) {
      return t("admin.modelSettings.summary.notConfigured");
    }
    const label = active.label || active.model_name || t("admin.modelSettings.summary.noLabel");
    const url = truncate(active.base_url);
    if (providers.length > 1) {
      return `${label} · ${url} · ${t("admin.modelSettings.summary.providersCount", { count: providers.length })}`;
    }
    return `${label} · ${url}`;
  }
  // Backward compat: no providers array
  return data[endpointName]?.model_name
    ? `${data[endpointName].model_name} · ${truncate(data[endpointName].base_url)}`
    : t("admin.modelSettings.summary.notConfigured");
}

function fillForm(data) {
  settings.value = data;
  form.platform_api_base_url = data?.platform_api_base_url || "";
  form.frontend_app_title = data?.frontend_app_title || "";
  form.frontend_default_theme = data?.frontend_default_theme || "system";
  form.frontend_color_scheme = normalizeColorScheme(data?.frontend_color_scheme);
  form.frontend_primary_color = normalizePrimaryColor(data?.frontend_primary_color);
  form.llm_base_url = data?.llm?.base_url || "";
  form.llm_model = data?.llm?.model_name || "";
  form.llm_api_key = data?.llm?.api_key_masked || "";
  const llmProvs = extractProviders(data?.llm);
  form.llm_providers = llmProvs;
  form.llm_active_provider = ensureActiveProvider(llmProvs, data?.llm?.active_provider, form.llm_active_provider);
  form.multimodal_base_url = data?.multimodal?.base_url || "";
  form.multimodal_model = data?.multimodal?.model_name || "";
  form.multimodal_api_key = data?.multimodal?.api_key_masked || "";
  const mmProvs = extractProviders(data?.multimodal);
  form.multimodal_providers = mmProvs;
  form.multimodal_active_provider = ensureActiveProvider(mmProvs, data?.multimodal?.active_provider, form.multimodal_active_provider);
  form.embedding_base_url = data?.embedding?.base_url || "";
  form.embedding_model = data?.embedding?.model_name || "";
  form.embedding_factory = data?.embedding_factory || "";
  form.embedding_api_key = data?.embedding?.api_key_masked || "";
  const embProvs = extractProviders(data?.embedding);
  form.embedding_providers = embProvs;
  form.embedding_active_provider = ensureActiveProvider(embProvs, data?.embedding?.active_provider, form.embedding_active_provider);
  form.rerank_base_url = data?.rerank?.base_url || "";
  form.rerank_model = data?.rerank?.model_name || "";
  form.rerank_api_key = data?.rerank?.api_key_masked || "";
  const rerankProvs = extractProviders(data?.rerank);
  form.rerank_providers = rerankProvs;
  form.rerank_active_provider = ensureActiveProvider(rerankProvs, data?.rerank?.active_provider, form.rerank_active_provider);
  form.paddleocr_base_url = data?.paddleocr?.base_url || data?.paddleocr_url || "";
  form.paddleocr_model = data?.paddleocr?.model_name || "";
  form.paddleocr_api_key = data?.paddleocr?.api_key_masked || "";
  form.paddleocr_url = data?.paddleocr_url || "";
  const ocrProvs = extractProviders(data?.paddleocr);
  form.paddleocr_providers = ocrProvs;
  form.paddleocr_active_provider = ensureActiveProvider(ocrProvs, data?.paddleocr?.active_provider, form.paddleocr_active_provider);
  form.tts_base_url = data?.tts?.base_url || "";
  form.tts_model = data?.tts?.model_name || "";
  form.tts_api_key = data?.tts?.api_key_masked || "";
  const ttsProvs = extractProviders(data?.tts);
  form.tts_providers = ttsProvs;
  form.tts_active_provider = ensureActiveProvider(ttsProvs, data?.tts?.active_provider, form.tts_active_provider);
  form.speech_service_url = data?.speech_service_url || "";
  form.pdf2zh_api_url = data?.pdf2zh_api_url || "";
  form.searxng_url = data?.searxng_url || "";
  form.searxng_timeout_seconds = data?.searxng_timeout_seconds || 15;
  form.firecrawl_api_key = data?.firecrawl_api_key || "";
  form.firecrawl_api_url = data?.firecrawl_api_url || "https://api.firecrawl.dev";
  form.firecrawl_read_full_max_urls = data?.firecrawl_read_full_max_urls || 3;
  form.agent_browser_enabled = Boolean(data?.agent_browser_enabled);
  form.agent_browser_headless = data?.agent_browser_headless !== false;
  form.agent_browser_allowed_domains = data?.agent_browser_allowed_domains || "";
  form.agent_browser_max_steps_per_session = data?.agent_browser_max_steps_per_session || 50;
  form.agent_browser_auto_task_enabled = data?.agent_browser_auto_task_enabled !== false;
  form.agent_browser_auto_task_max_steps = data?.agent_browser_auto_task_max_steps || 15;
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
      const scheme = normalizeColorScheme(data.frontend_color_scheme);
      const schemeLabel =
        scheme === COLOR_SCHEME_CUSTOM
          ? t("admin.modelSettings.colorScheme.customShort", {
              color: normalizePrimaryColor(data.frontend_primary_color),
            })
          : colorSchemeOptions.value.find((item) => item.value === scheme)
              ?.label || t("admin.modelSettings.colorScheme.blueShort");
      const title = data.frontend_app_title || t("admin.modelSettings.summary.systemName");
      return `${title} · ${schemeLabel} · ${themeLabel}`;
    }
    case "llm":
      return activeProviderSummary(id, "llm");
    case "multimodal":
      return activeProviderSummary(id, "multimodal");
    case "embedding":
      return activeProviderSummary(id, "embedding");
    case "rerank":
      return activeProviderSummary(id, "rerank") || t("admin.modelSettings.summary.optionalNotConfigured");
    case "paddleocr": {
      const sum = activeProviderSummary(id, "paddleocr");
      if (sum !== t("admin.modelSettings.summary.notConfigured")) return sum;
      return data.paddleocr_url
        ? truncate(data.paddleocr_url)
        : t("admin.modelSettings.summary.notConfigured");
    }
    case "speech":
      return data.speech_service_url
        ? truncate(data.speech_service_url)
        : t("admin.modelSettings.summary.notConfigured");
    case "tts":
      return activeProviderSummary(id, "tts");
    case "pdf2zh":
      return data.pdf2zh_api_url
        ? truncate(data.pdf2zh_api_url)
        : t("admin.modelSettings.summary.notConfigured");
    case "searxng":
      return data.searxng_url
        ? t("admin.modelSettings.summary.seconds", {
            url: truncate(data.searxng_url),
            seconds: data.searxng_timeout_seconds || 15,
          }) + (data.firecrawl_api_key ? " · FC" : " · 无全文")
        : t("admin.modelSettings.summary.notConfigured");
    case "browser_rpa":
      return data.agent_browser_enabled
        ? t("admin.modelSettings.summary.browserRpaEnabled", {
            headless: data.agent_browser_headless ? "headless" : "headed",
            domains: data.agent_browser_allowed_domains || t("admin.modelSettings.summary.browserRpaAllDomains"),
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
      const host = kb.ragflow_mysql_host || "localhost";
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

function extractProviders(endpointData) {
  if (!endpointData) return [];
  const raw = endpointData.providers;
  if (Array.isArray(raw) && raw.length > 0) {
    return raw.map((p) => ({
      id: p.id || generateProviderId(),
      label: p.label || "",
      base_url: p.base_url || "",
      model_name: p.model_name || "",
      api_key: p.api_key_masked || "",
    }));
  }
  return [];
}

function ensureActiveProvider(providers, activeId, existingActive) {
  if (providers.length === 0) return "";
  if (activeId && providers.find((p) => p.id === activeId)) return activeId;
  if (existingActive && providers.find((p) => p.id === existingActive)) return existingActive;
  return providers[0].id;
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

const activeProviderOptions = computed(() => {
  if (!activeId.value || !PROVIDER_RESOURCE_IDS.has(activeId.value)) return [];
  const providers = form[`${activeId.value}_providers`] || [];
  return providers.map((p) => ({
    label: p.label || p.model_name || `服务源 ${providers.indexOf(p) + 1}`,
    value: p.id,
  }));
});

function addProviderTo(id) {
  const key = `${id}_providers`;
  const provs = form[key] || [];
  if (provs.length >= 3) return;
  provs.push(createEmptyProvider());
  // Setting array via index to trigger reactivity
  form[key] = [...provs];
  // Auto-select new provider if first
  if (provs.length === 1) {
    form[`${id}_active_provider`] = provs[0].id;
  }
}

function removeProviderFrom(id, index) {
  const key = `${id}_providers`;
  const provs = form[key] || [];
  if (provs.length <= 1) return;
  const removedId = provs[index].id;
  provs.splice(index, 1);
  form[key] = [...provs];
  if (form[`${id}_active_provider`] === removedId) {
    form[`${id}_active_provider`] = provs[0]?.id || "";
  }
}

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

async function refreshAll() {
  await Promise.all([loadSettings(), loadHealth()]);
}

function openResource(id) {
  activeId.value = id;
  drawerTestResult.value = null;
  providerTestResults.value = {};
  drawerOpen.value = true;
}

function providerTestResult(providerId) {
  const item = providerTestResults.value[providerId];
  if (!item) return null;
  return item;
}

function buildModelProviderPayload(prefix) {
  const providers = form[`${prefix}_providers`] || [];
  const activeProvider = form[`${prefix}_active_provider`] || (providers[0]?.id || "");
  const mapped = providers.map((p) => ({
    id: p.id,
    label: p.label || "",
    base_url: p.base_url || "",
    model_name: p.model_name || "",
    api_key: p.api_key && !p.api_key.includes("••••") ? p.api_key : "",
  }));
  return {
    [`${prefix}_providers`]: mapped,
    [`${prefix}_active_provider`]: activeProvider,
  };
}

function buildPayloadFor(id) {
  switch (id) {
    case "platform_api":
      return {
        platform_api_base_url: form.platform_api_base_url.trim()};
    case "frontend":
      return {
        frontend_app_title: form.frontend_app_title.trim(),
        frontend_default_theme: form.frontend_default_theme || "system",
        frontend_color_scheme: form.frontend_color_scheme || DEFAULT_COLOR_SCHEME,
        frontend_primary_color:
          form.frontend_color_scheme === COLOR_SCHEME_CUSTOM
            ? normalizePrimaryColor(form.frontend_primary_color)
            : "",
      };
    case "llm":
      return buildModelProviderPayload("llm");
    case "multimodal":
      return buildModelProviderPayload("multimodal");
    case "embedding":
      return {
        ...buildModelProviderPayload("embedding"),
        embedding_factory: form.embedding_factory.trim(),
      };
    case "rerank":
      return buildModelProviderPayload("rerank");
    case "paddleocr":
      return {
        ...buildModelProviderPayload("paddleocr"),
        paddleocr_url: form.paddleocr_url.trim(),
      };
    case "speech":
      return { speech_service_url: form.speech_service_url.trim() };
    case "tts":
      return buildModelProviderPayload("tts");
    case "pdf2zh":
      return { pdf2zh_api_url: form.pdf2zh_api_url.trim() };
    case "searxng":
      return {
        searxng_url: form.searxng_url.trim(),
        searxng_timeout_seconds: Number(form.searxng_timeout_seconds) || 15,
        ...(form.firecrawl_api_key && !form.firecrawl_api_key.includes("••••")
          ? { firecrawl_api_key: form.firecrawl_api_key.trim() }
          : {}),
        firecrawl_api_url: form.firecrawl_api_url.trim() || "https://api.firecrawl.dev",
        firecrawl_read_full_max_urls: Number(form.firecrawl_read_full_max_urls) || 3,
      };
    case "browser_rpa":
      return {
        agent_browser_enabled: Boolean(form.agent_browser_enabled),
        agent_browser_headless: Boolean(form.agent_browser_headless),
        agent_browser_allowed_domains: form.agent_browser_allowed_domains.trim(),
        agent_browser_max_steps_per_session:
          Number(form.agent_browser_max_steps_per_session) || 50,
        agent_browser_auto_task_enabled: Boolean(form.agent_browser_auto_task_enabled),
        agent_browser_auto_task_max_steps:
          Number(form.agent_browser_auto_task_max_steps) || 15,
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
  providerTestResults.value = {};
  try {
    const probeTimeoutMs = ["multimodal", "llm", "embedding", "tts"].includes(activeId.value)
      ? 60000
      : undefined;
    const result = await testResourceHealth(
      activeId.value,
      buildPayloadFor(activeId.value),
      probeTimeoutMs
    );
    drawerTestResult.value = result;
    // 填充逐服务源（provider）连通性结果
    if (result?.providers?.length) {
      const map = {};
      for (const p of result.providers) {
        map[p.provider_id] = {
          healthy: p.healthy,
          message: p.message,
          label: p.provider_label,
        };
      }
      providerTestResults.value = map;
    }
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
        default_theme: form.frontend_default_theme,
        color_scheme: form.frontend_color_scheme,
        primary_color:
          form.frontend_color_scheme === COLOR_SCHEME_CUSTOM
            ? normalizePrimaryColor(form.frontend_primary_color)
            : "",
      });
      initAppFromServerConfig({
        default_theme: form.frontend_default_theme,
        color_scheme: form.frontend_color_scheme,
        primary_color:
          form.frontend_color_scheme === COLOR_SCHEME_CUSTOM
            ? normalizePrimaryColor(form.frontend_primary_color)
            : "",
      });
      ui.success(t("admin.modelSettings.messages.savedFrontend"));
    } else {
      ui.success(t("admin.modelSettings.messages.savedDefault"));
    }
    drawerOpen.value = false;
    drawerTestResult.value = null;
    // 后台静默刷新健康状态（不阻塞保存成功的提示）
    loadHealth().catch(() => {});
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
      <ListRefreshButton
        :label="t('admin.modelSettings.refreshStatus')"
        :loading="healthLoading"
        @click="loadHealth"
      />
    </div>

    <section
      v-for="group in groupedResources"
      :key="group.id"
      class="category-block"
      :style="adminResourceGroupAccentStyle(group.id)"
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
                <n-icon :size="20">
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

    <n-drawer v-model:show="drawerOpen" :width="624" placement="right">
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
            <n-form-item :label="t('admin.modelSettings.labels.colorScheme')">
              <n-select
                v-model:value="form.frontend_color_scheme"
                :options="colorSchemeOptions"
              />
            </n-form-item>
            <n-form-item
              v-if="form.frontend_color_scheme === 'custom'"
              :label="t('admin.modelSettings.labels.primaryColor')"
            >
              <n-color-picker
                v-model:value="form.frontend_primary_color"
                :modes="['hex']"
                :show-alpha="false"
              />
            </n-form-item>
            <div
              class="drawer-hint"
              v-html="t('admin.modelSettings.hints.frontend')"
            />
          </template>

          <template v-else-if="activeId === 'llm'">
            <n-form-item :label="t('admin.modelSettings.labels.activeProvider')">
              <n-select
                v-model:value="form.llm_active_provider"
                :options="activeProviderOptions"
              />
            </n-form-item>
            <n-space vertical size="large">
              <div
                v-for="(prov, idx) in form.llm_providers"
                :key="prov.id"
                class="provider-card"
              >
                <div class="provider-card__head">
                  <n-text depth="3">{{ t('admin.modelSettings.summary.providersCount', { count: idx + 1 }) }}</n-text>
                  <span
                    v-if="providerTestResult(prov.id)"
                    class="provider-test-badge"
                    :class="providerTestResult(prov.id).healthy === true ? 'ok' : providerTestResult(prov.id).healthy === false ? 'bad' : 'skip'"
                    :title="providerTestResult(prov.id).message"
                  >
                    {{ providerTestResult(prov.id).healthy === true ? '✓ 通' : providerTestResult(prov.id).healthy === false ? '✗ 不通' : '— 配置不完整' }}
                  </span>
                  <n-button
                    v-if="form.llm_providers.length > 1"
                    text
                    type="warning"
                    size="small"
                    @click="removeProviderFrom('llm', idx)"
                  >
                    {{ t("admin.modelSettings.labels.removeProvider") }}
                  </n-button>
                </div>
                <n-form-item :label="t('admin.modelSettings.labels.providerLabel')">
                  <n-input v-model:value="prov.label" placeholder="如：硅基流动" />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
                  <n-input
                    v-model:value="prov.base_url"
                    :placeholder="t('admin.modelSettings.placeholders.llmApiUrl')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.modelName')">
                  <n-input
                    v-model:value="prov.model_name"
                    :placeholder="t('admin.modelSettings.placeholders.modelName')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
                  <n-input
                    v-model:value="prov.api_key"
                    type="password"
                    show-password-on="click"
                    :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
                  />
                </n-form-item>
              </div>
            </n-space>
            <n-button
              v-if="form.llm_providers.length < 3"
              block
              dashed
              style="margin-top: 12px"
              @click="addProviderTo('llm')"
            >
              {{ t("admin.modelSettings.labels.addProvider") }}
            </n-button>
            <div
              v-if="form.llm_providers.length < 3"
              class="drawer-hint"
              style="margin-top: 6px"
              v-html="t('admin.modelSettings.labels.maxProviders')"
            />
          </template>

          <template v-else-if="activeId === 'multimodal'">
            <n-form-item :label="t('admin.modelSettings.labels.activeProvider')">
              <n-select
                v-model:value="form.multimodal_active_provider"
                :options="activeProviderOptions"
              />
            </n-form-item>
            <n-space vertical size="large">
              <div
                v-for="(prov, idx) in form.multimodal_providers"
                :key="prov.id"
                class="provider-card"
              >
                <div class="provider-card__head">
                  <n-text depth="3">{{ t('admin.modelSettings.summary.providersCount', { count: idx + 1 }) }}</n-text>
                  <span
                    v-if="providerTestResult(prov.id)"
                    class="provider-test-badge"
                    :class="providerTestResult(prov.id).healthy === true ? 'ok' : providerTestResult(prov.id).healthy === false ? 'bad' : 'skip'"
                    :title="providerTestResult(prov.id).message"
                  >
                    {{ providerTestResult(prov.id).healthy === true ? '✓ 通' : providerTestResult(prov.id).healthy === false ? '✗ 不通' : '— 配置不完整' }}
                  </span>
                  <n-button
                    v-if="form.multimodal_providers.length > 1"
                    text
                    type="warning"
                    size="small"
                    @click="removeProviderFrom('multimodal', idx)"
                  >
                    {{ t("admin.modelSettings.labels.removeProvider") }}
                  </n-button>
                </div>
                <n-form-item :label="t('admin.modelSettings.labels.providerLabel')">
                  <n-input v-model:value="prov.label" placeholder="如：硅基流动" />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
                  <n-input
                    v-model:value="prov.base_url"
                    :placeholder="t('admin.modelSettings.placeholders.multimodalApiUrl')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.modelName')">
                  <n-input
                    v-model:value="prov.model_name"
                    :placeholder="t('admin.modelSettings.placeholders.multimodalModel')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
                  <n-input
                    v-model:value="prov.api_key"
                    type="password"
                    show-password-on="click"
                    :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
                  />
                </n-form-item>
              </div>
            </n-space>
            <n-button
              v-if="form.multimodal_providers.length < 3"
              block
              dashed
              style="margin-top: 12px"
              @click="addProviderTo('multimodal')"
            >
              {{ t("admin.modelSettings.labels.addProvider") }}
            </n-button>
            <div
              v-if="form.multimodal_providers.length < 3"
              class="drawer-hint"
              style="margin-top: 6px"
              v-html="t('admin.modelSettings.labels.maxProviders')"
            />
            <div class="drawer-hint" v-html="t('admin.modelSettings.hints.multimodal')" />
          </template>

          <template v-else-if="activeId === 'embedding'">
            <n-form-item :label="t('admin.modelSettings.labels.activeProvider')">
              <n-select
                v-model:value="form.embedding_active_provider"
                :options="activeProviderOptions"
              />
            </n-form-item>
            <n-space vertical size="large">
              <div
                v-for="(prov, idx) in form.embedding_providers"
                :key="prov.id"
                class="provider-card"
              >
                <div class="provider-card__head">
                  <n-text depth="3">{{ t('admin.modelSettings.summary.providersCount', { count: idx + 1 }) }}</n-text>
                  <span
                    v-if="providerTestResult(prov.id)"
                    class="provider-test-badge"
                    :class="providerTestResult(prov.id).healthy === true ? 'ok' : providerTestResult(prov.id).healthy === false ? 'bad' : 'skip'"
                    :title="providerTestResult(prov.id).message"
                  >
                    {{ providerTestResult(prov.id).healthy === true ? '✓ 通' : providerTestResult(prov.id).healthy === false ? '✗ 不通' : '— 配置不完整' }}
                  </span>
                  <n-button
                    v-if="form.embedding_providers.length > 1"
                    text
                    type="warning"
                    size="small"
                    @click="removeProviderFrom('embedding', idx)"
                  >
                    {{ t("admin.modelSettings.labels.removeProvider") }}
                  </n-button>
                </div>
                <n-form-item :label="t('admin.modelSettings.labels.providerLabel')">
                  <n-input v-model:value="prov.label" placeholder="如：硅基流动" />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
                  <n-input
                    v-model:value="prov.base_url"
                    :placeholder="t('admin.modelSettings.placeholders.embeddingApiUrl')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.modelName')">
                  <n-input
                    v-model:value="prov.model_name"
                    :placeholder="t('admin.modelSettings.placeholders.embeddingModel')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
                  <n-input
                    v-model:value="prov.api_key"
                    type="password"
                    show-password-on="click"
                    :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.provider')">
                  <n-input
                    v-model:value="form.embedding_factory"
                    :placeholder="t('admin.modelSettings.placeholders.embeddingFactory')"
                  />
                </n-form-item>
              </div>
            </n-space>
            <n-button
              v-if="form.embedding_providers.length < 3"
              block
              dashed
              style="margin-top: 12px"
              @click="addProviderTo('embedding')"
            >
              {{ t("admin.modelSettings.labels.addProvider") }}
            </n-button>
            <div
              v-if="form.embedding_providers.length < 3"
              class="drawer-hint"
              style="margin-top: 6px"
              v-html="t('admin.modelSettings.labels.maxProviders')"
            />
          </template>

          <template v-else-if="activeId === 'rerank'">
            <n-form-item :label="t('admin.modelSettings.labels.activeProvider')">
              <n-select
                v-model:value="form.rerank_active_provider"
                :options="activeProviderOptions"
              />
            </n-form-item>
            <n-space vertical size="large">
              <div
                v-for="(prov, idx) in form.rerank_providers"
                :key="prov.id"
                class="provider-card"
              >
                <div class="provider-card__head">
                  <n-text depth="3">{{ t('admin.modelSettings.summary.providersCount', { count: idx + 1 }) }}</n-text>
                  <span
                    v-if="providerTestResult(prov.id)"
                    class="provider-test-badge"
                    :class="providerTestResult(prov.id).healthy === true ? 'ok' : providerTestResult(prov.id).healthy === false ? 'bad' : 'skip'"
                    :title="providerTestResult(prov.id).message"
                  >
                    {{ providerTestResult(prov.id).healthy === true ? '✓ 通' : providerTestResult(prov.id).healthy === false ? '✗ 不通' : '— 配置不完整' }}
                  </span>
                  <n-button
                    v-if="form.rerank_providers.length > 1"
                    text
                    type="warning"
                    size="small"
                    @click="removeProviderFrom('rerank', idx)"
                  >
                    {{ t("admin.modelSettings.labels.removeProvider") }}
                  </n-button>
                </div>
                <n-form-item :label="t('admin.modelSettings.labels.providerLabel')">
                  <n-input v-model:value="prov.label" placeholder="如：硅基流动" />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
                  <n-input
                    v-model:value="prov.base_url"
                    :placeholder="t('admin.modelSettings.placeholders.rerankApiUrl')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.modelName')">
                  <n-input
                    v-model:value="prov.model_name"
                    :placeholder="t('admin.modelSettings.placeholders.rerankModel')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
                  <n-input
                    v-model:value="prov.api_key"
                    type="password"
                    show-password-on="click"
                    :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
                  />
                </n-form-item>
              </div>
            </n-space>
            <n-button
              v-if="form.rerank_providers.length < 3"
              block
              dashed
              style="margin-top: 12px"
              @click="addProviderTo('rerank')"
            >
              {{ t("admin.modelSettings.labels.addProvider") }}
            </n-button>
            <div
              v-if="form.rerank_providers.length < 3"
              class="drawer-hint"
              style="margin-top: 6px"
              v-html="t('admin.modelSettings.labels.maxProviders')"
            />
          </template>

          <template v-else-if="activeId === 'paddleocr'">
            <n-form-item :label="t('admin.modelSettings.labels.activeProvider')">
              <n-select
                v-model:value="form.paddleocr_active_provider"
                :options="activeProviderOptions"
              />
            </n-form-item>
            <n-space vertical size="large">
              <div
                v-for="(prov, idx) in form.paddleocr_providers"
                :key="prov.id"
                class="provider-card"
              >
                <div class="provider-card__head">
                  <n-text depth="3">{{ t('admin.modelSettings.summary.providersCount', { count: idx + 1 }) }}</n-text>
                  <span
                    v-if="providerTestResult(prov.id)"
                    class="provider-test-badge"
                    :class="providerTestResult(prov.id).healthy === true ? 'ok' : providerTestResult(prov.id).healthy === false ? 'bad' : 'skip'"
                    :title="providerTestResult(prov.id).message"
                  >
                    {{ providerTestResult(prov.id).healthy === true ? '✓ 通' : providerTestResult(prov.id).healthy === false ? '✗ 不通' : '— 配置不完整' }}
                  </span>
                  <n-button
                    v-if="form.paddleocr_providers.length > 1"
                    text
                    type="warning"
                    size="small"
                    @click="removeProviderFrom('paddleocr', idx)"
                  >
                    {{ t("admin.modelSettings.labels.removeProvider") }}
                  </n-button>
                </div>
                <n-form-item :label="t('admin.modelSettings.labels.providerLabel')">
                  <n-input v-model:value="prov.label" placeholder="如：硅基流动" />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
                  <n-input
                    v-model:value="prov.base_url"
                    :placeholder="t('admin.modelSettings.placeholders.paddleocrApiUrl')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.modelName')">
                  <n-input
                    v-model:value="prov.model_name"
                    :placeholder="t('admin.modelSettings.placeholders.paddleocrModel')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
                  <n-input
                    v-model:value="prov.api_key"
                    type="password"
                    show-password-on="click"
                    :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
                  />
                </n-form-item>
              </div>
            </n-space>
            <n-button
              v-if="form.paddleocr_providers.length < 3"
              block
              dashed
              style="margin-top: 12px"
              @click="addProviderTo('paddleocr')"
            >
              {{ t("admin.modelSettings.labels.addProvider") }}
            </n-button>
            <div
              v-if="form.paddleocr_providers.length < 3"
              class="drawer-hint"
              style="margin-top: 6px"
              v-html="t('admin.modelSettings.labels.maxProviders')"
            />
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
            <n-form-item :label="t('admin.modelSettings.labels.activeProvider')">
              <n-select
                v-model:value="form.tts_active_provider"
                :options="activeProviderOptions"
              />
            </n-form-item>
            <n-space vertical size="large">
              <div
                v-for="(prov, idx) in form.tts_providers"
                :key="prov.id"
                class="provider-card"
              >
                <div class="provider-card__head">
                  <n-text depth="3">{{ t('admin.modelSettings.summary.providersCount', { count: idx + 1 }) }}</n-text>
                  <span
                    v-if="providerTestResult(prov.id)"
                    class="provider-test-badge"
                    :class="providerTestResult(prov.id).healthy === true ? 'ok' : providerTestResult(prov.id).healthy === false ? 'bad' : 'skip'"
                    :title="providerTestResult(prov.id).message"
                  >
                    {{ providerTestResult(prov.id).healthy === true ? '✓ 通' : providerTestResult(prov.id).healthy === false ? '✗ 不通' : '— 配置不完整' }}
                  </span>
                  <n-button
                    v-if="form.tts_providers.length > 1"
                    text
                    type="warning"
                    size="small"
                    @click="removeProviderFrom('tts', idx)"
                  >
                    {{ t("admin.modelSettings.labels.removeProvider") }}
                  </n-button>
                </div>
                <n-form-item :label="t('admin.modelSettings.labels.providerLabel')">
                  <n-input v-model:value="prov.label" placeholder="如：硅基流动" />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiUrl')">
                  <n-input
                    v-model:value="prov.base_url"
                    :placeholder="t('admin.modelSettings.placeholders.ttsApiUrl')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.modelName')">
                  <n-input
                    v-model:value="prov.model_name"
                    :placeholder="t('admin.modelSettings.placeholders.ttsModel')"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.modelSettings.labels.apiKey')">
                  <n-input
                    v-model:value="prov.api_key"
                    type="password"
                    show-password-on="click"
                    :placeholder="t('admin.modelSettings.placeholders.apiKeyMasked')"
                  />
                </n-form-item>
              </div>
            </n-space>
            <n-button
              v-if="form.tts_providers.length < 3"
              block
              dashed
              style="margin-top: 12px"
              @click="addProviderTo('tts')"
            >
              {{ t("admin.modelSettings.labels.addProvider") }}
            </n-button>
            <div
              v-if="form.tts_providers.length < 3"
              class="drawer-hint"
              style="margin-top: 6px"
              v-html="t('admin.modelSettings.labels.maxProviders')"
            />
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
            <hr style="border:none;border-top:1px solid var(--platform-border);margin:16px 0" />
            <div class="drawer-hint" style="margin-bottom:12px;font-weight:600">
              FireCrawl 全文提取
            </div>
            <n-form-item :label="t('admin.modelSettings.labels.firecrawlApiUrl')">
              <n-input
                v-model:value="form.firecrawl_api_url"
                :placeholder="t('admin.modelSettings.placeholders.firecrawlApiUrl')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.firecrawlApiKey')">
              <n-input
                v-model:value="form.firecrawl_api_key"
                type="password"
                show-password-on="click"
                :placeholder="t('admin.modelSettings.placeholders.firecrawlApiKeyHint')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.firecrawlReadFullMaxUrls')">
              <n-input-number
                v-model:value="form.firecrawl_read_full_max_urls"
                :min="0"
                :max="10"
                style="width: 100%"
              />
            </n-form-item>
            <div class="drawer-hint" v-html="t('admin.modelSettings.hints.searxng')" />
          </template>

          <template v-else-if="activeId === 'browser_rpa'">
            <n-form-item :label="t('admin.modelSettings.labels.browserRpaEnabled')">
              <n-switch v-model:value="form.agent_browser_enabled" />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.browserRpaHeadless')">
              <n-switch v-model:value="form.agent_browser_headless" />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.browserRpaAllowedDomains')">
              <n-input
                v-model:value="form.agent_browser_allowed_domains"
                :placeholder="t('admin.modelSettings.placeholders.browserRpaDomains')"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.browserRpaMaxSteps')">
              <n-input-number
                v-model:value="form.agent_browser_max_steps_per_session"
                :min="5"
                :max="200"
                style="width: 100%"
              />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.browserRpaAutoTask')">
              <n-switch v-model:value="form.agent_browser_auto_task_enabled" />
            </n-form-item>
            <n-form-item :label="t('admin.modelSettings.labels.browserRpaAutoTaskMaxSteps')">
              <n-input-number
                v-model:value="form.agent_browser_auto_task_max_steps"
                :min="3"
                :max="40"
                style="width: 100%"
              />
            </n-form-item>
            <div class="drawer-hint" v-html="t('admin.modelSettings.hints.browserRpa')" />
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
          style="margin-top: 14px"
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
  max-width: 1536px;
}

.page-toolbar {
  display: flex;
  justify-content: flex-end;
}

.category-block {
  margin-top: 22px;
}

.category-block__head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  padding: 0 0 10px 12px;
  border-left: 4px solid var(--cat-accent, var(--platform-accent));
}

.category-block__text {
  min-width: 0;
  flex: 1;
}

.category-block__row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.category-block__title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
}

.category-block__hint {
  display: block;
  margin-top: 2px;
  font-size: 14px;
}

.category-grid :deep(> *) {
  display: flex;
}

.resource-card-wrap {
  position: relative;
  display: flex;
  width: 100%;
  padding-top: 5px;
  padding-right: 5px;
}

.resource-status-dot {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 2;
  width: 13px;
  height: 13px;
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
  padding: 13px 14px;
  border-radius: var(--platform-radius-sm, 12px);
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
    0 0 0 5px var(--cat-accent);
}

.feature-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 7px;
  margin-bottom: 7px;
}

.feature-card__icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--cat-accent, var(--platform-accent));
  background: var(--cat-accent-soft, var(--platform-accent-soft));
  transition: transform 0.2s ease;
}

.feature-card:hover .feature-card__icon {
  transform: scale(1.04);
}

.feature-card__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
}

.feature-card__desc {
  margin: 5px 0 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--platform-text-tertiary);
}

.resource-card__summary {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.4;
  color: var(--platform-text-secondary);
  word-break: break-all;
}

.drawer-hint {
  display: block;
  font-size: 14px;
  line-height: 1.55;
}

.provider-card {
  padding: 14px;
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius-sm, 10px);
  background: var(--platform-bg);
}

.provider-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  gap: 6px;
}

.provider-test-badge {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: help;
  flex-shrink: 0;
}

.provider-test-badge.ok {
  background: color-mix(in srgb, var(--platform-accent) 14%, transparent);
  color: var(--platform-accent);
}

.provider-test-badge.bad {
  background: color-mix(in srgb, #ef4444 14%, transparent);
  color: #ef4444;
}

.provider-test-badge.skip {
  background: color-mix(in srgb, #94a3b8 14%, transparent);
  color: #94a3b8;
}

@keyframes feature-card-in {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
