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

const THEME_OPTIONS = [
  { label: "跟随系统（自动切换日/夜）", value: "system" },
  { label: "默认日间模式", value: "light" },
  { label: "默认夜间模式", value: "dark" },
];

const ui = usePlatformUi();
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

const RESOURCE_DEFS = [
  {
    id: "platform_api",
    title: "系统后台地址（前端）",
    hint: "浏览器请求智碳平台后端的 API 根路径",
    icon: GlobeOutline,
    category: "platform"},
  {
    id: "frontend",
    title: "前台配置",
    hint: "系统大标题与默认日/夜主题",
    icon: ColorPaletteOutline,
    category: "platform"},
  {
    id: "llm",
    title: "语言模型（LLM）",
    hint: "知识问答、会议摘要等",
    icon: ChatbubblesOutline,
    category: "model"},
  {
    id: "embedding",
    title: "Embedding 模型",
    hint: "文档向量与知识检索",
    icon: HardwareChipOutline,
    category: "model"},
  {
    id: "vl",
    title: "VL 模型",
    hint: "PDF 图表增强（IMAGE2TEXT）",
    icon: ImageOutline,
    category: "model"},
  {
    id: "rerank",
    title: "Reranker 模型",
    hint: "检索重排序（可选）",
    icon: StatsChartOutline,
    category: "model"},
  {
    id: "paddleocr",
    title: "PaddleOCR-VL",
    hint: "硅基流动 API 或自建 OCR 服务",
    icon: ScanOutline,
    category: "service"},
  {
    id: "speech",
    title: "语音识别服务",
    hint: "会议助手语音转写",
    icon: MicOutline,
    category: "service"},
  {
    id: "pdf2zh",
    title: "PDF 翻译服务",
    hint: "pdf2zh 文档翻译 API",
    icon: LanguageOutline,
    category: "service"},
  {
    id: "searxng",
    title: "SearXNG 联网搜索",
    hint: "网站收藏在线搜索",
    icon: SearchOutline,
    category: "service"},
  {
    id: "ragflow_api",
    title: "RAGFlow API",
    hint: "知识库检索、文档同步 HTTP API",
    icon: LibraryOutline,
    category: "knowledge"},
  {
    id: "knowflow_backend",
    title: "KnowFlow 知识库后台",
    hint: "KnowFlow API、Web UI 与 iframe 基址",
    icon: ServerOutline,
    category: "knowledge"},
  {
    id: "ragflow_mysql",
    title: "RAGFlow MySQL",
    hint: "知识库元数据与用户模型配置库",
    icon: ServerSharp,
    category: "knowledge"},
];

const CATEGORY_META = {
  platform: { title: "平台", hint: "前端访问地址与展示配置" },
  model: { title: "AI 模型", hint: "语言、嵌入、VL 与重排序；改 URL/模型名可切换本地或在线" },
  service: { title: "外部服务", hint: "OCR-VL、语音、翻译等；OCR 支持在线 API 或本地 layout-parsing" },
  knowledge: { title: "知识库基础设施", hint: "RAGFlow / KnowFlow 后台与 MySQL 数据库" }};

const activeResource = computed(() =>
  RESOURCE_DEFS.find((item) => item.id === activeId.value) || null
);

const groupedResources = computed(() =>
  ["platform", "model", "knowledge", "service"].map((id) => ({
    id,
    ...CATEGORY_META[id],
    items: RESOURCE_DEFS.filter((item) => item.category === id)}))
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
  if (!data) return "加载中…";
  switch (id) {
    case "platform_api":
      return data.platform_api_base_url
        ? truncate(data.platform_api_base_url)
        : "默认（/ai）";
    case "frontend": {
      const themeLabel =
        THEME_OPTIONS.find((item) => item.value === data.frontend_default_theme)?.label ||
        "跟随系统";
      const title = data.frontend_app_title || "使用系统名称";
      return `${title} · ${themeLabel}`;
    }
    case "llm":
      return data.llm?.model_name
        ? `${data.llm.model_name} · ${truncate(data.llm.base_url)}`
        : "未配置";
    case "embedding":
      return data.embedding?.model_name
        ? `${data.embedding.model_name} · ${truncate(data.embedding.base_url)}`
        : "未配置";
    case "vl": {
      const vl = modelEndpoint(data, "vl", "vision");
      if (!vl?.model_name) return "未配置";
      if (!vl.base_url) return `${vl.model_name}（未填 API 地址）`;
      if (!vl.api_key_configured) return `${vl.model_name}（未配置 Key）`;
      return `${vl.model_name} · ${truncate(vl.base_url)}`;
    }
    case "rerank":
      return data.rerank?.model_name
        ? `${data.rerank.model_name} · ${truncate(data.rerank.base_url)}`
        : "可选，未配置";
    case "paddleocr":
      return data.paddleocr?.model_name
        ? `${data.paddleocr.model_name} · ${truncate(data.paddleocr.base_url)}`
        : data.paddleocr_url
          ? truncate(data.paddleocr_url)
          : "未配置";
    case "speech":
      return data.speech_service_url ? truncate(data.speech_service_url) : "未配置";
    case "pdf2zh":
      return data.pdf2zh_api_url ? truncate(data.pdf2zh_api_url) : "未配置";
    case "searxng":
      return data.searxng_url
        ? `${truncate(data.searxng_url)} · ${data.searxng_timeout_seconds || 15}s`
        : "未配置";
    case "ragflow_api":
      return data.knowledge?.ragflow_api_url
        ? truncate(data.knowledge.ragflow_api_url)
        : "未配置";
    case "knowflow_backend": {
      const kb = data.knowledge;
      const parts = [];
      if (kb?.knowflow_backend_url) parts.push(`API ${truncate(kb.knowflow_backend_url)}`);
      if (kb?.knowflow_ui_url) parts.push(`UI ${truncate(kb.knowflow_ui_url)}`);
      return parts.length ? parts.join(" · ") : "未配置";
    }
    case "ragflow_mysql": {
      const kb = data.knowledge;
      if (!kb?.ragflow_mysql_host && !kb?.ragflow_mysql_password_configured) {
        return kb?.knowflow_enabled ? "Docker 默认（knowflow-mysql）" : "未配置";
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
  if (healthLoading.value && !item) return "检测中";
  if (!item) return "未检测";
  if (item.healthy === true) return item.message || "服务正常";
  if (item.healthy === false) return item.message || "服务异常";
  return item.message || "未配置";
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
    const prefix = drawerTestResult.value.healthy ? "测试通过：" : "测试未通过：";
    return `${prefix}${item.message || (item.healthy ? "连接正常" : "连接失败")}`;
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
    const probeTimeoutMs = ["vl", "llm", "embedding"].includes(activeId.value) ? 60000 : undefined;
    const result = await testResourceHealth(
      activeId.value,
      buildPayloadFor(activeId.value),
      probeTimeoutMs
    );
    drawerTestResult.value = result;
    if (result?.healthy) {
      ui.success(result.message || "连接正常");
    } else if (result?.healthy === false) {
      ui.warning(result.message || "连接失败");
    } else {
      ui.info(result?.message || "当前配置无需测试或未填写完整");
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
      ui.success("资源配置已保存；若 API 地址与当前访问方式不一致，请刷新页面");
    } else if (activeId.value === "frontend") {
      applyClientBranding({
        app_title: form.frontend_app_title.trim(),
        default_theme: form.frontend_default_theme});
      initAppFromServerConfig({ default_theme: form.frontend_default_theme });
      ui.success("前台配置已保存；标题已更新，主题策略在用户未手动切换时生效");
    } else {
      ui.success("资源配置已保存并同步");
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
        <n-button :loading="loading || healthLoading" @click="loadAll">刷新状态</n-button>
        <n-tag v-if="settings?.editable" type="success" :bordered="false">在线配置已启用</n-tag>
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
            <n-form-item label="API 根地址">
              <n-input
                v-model:value="form.platform_api_base_url"
                placeholder="/ai 或 http://172.19.134.45:40005/ai"
              />
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              浏览器请求智碳平台后端的根路径（不含 <code>/api/v1</code>）。
              同源部署填 <code>/ai</code>；跨域或远程开发填完整 URL。
              对应 .env 中 <code>PLATFORM_API_BASE_URL</code>，留空时使用
              <code>API_PUBLIC_PATH_PREFIX</code>（默认 <code>/ai</code>）。
              保存后前端立即生效；若与当前页面访问方式不一致，请刷新页面。
            </n-text>
          </template>

          <template v-else-if="activeId === 'frontend'">
            <n-form-item label="系统大标题">
              <n-input
                v-model:value="form.frontend_app_title"
                placeholder="留空时使用 APP_NAME（环境变量）"
              />
            </n-form-item>
            <n-form-item label="默认主题">
              <n-select
                v-model:value="form.frontend_default_theme"
                :options="THEME_OPTIONS"
              />
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              「跟随系统」时，前台根据操作系统日/夜模式自动切换；用户手动切换主题后将以本地偏好为准。
              对应 .env 中 <code>FRONTEND_APP_TITLE</code>、<code>FRONTEND_DEFAULT_THEME</code>。
            </n-text>
          </template>

          <template v-else-if="activeId === 'llm'">
            <n-form-item label="API URL">
              <n-input v-model:value="form.llm_base_url" placeholder="https://host/v1 或本地 vLLM 地址" />
            </n-form-item>
            <n-form-item label="模型名称">
              <n-input v-model:value="form.llm_model" placeholder="模型名称" />
            </n-form-item>
            <n-form-item label="SK / API Key">
              <n-input
                v-model:value="form.llm_api_key"
                type="password"
                show-password-on="click"
                placeholder="留空或掩码表示不修改"
              />
            </n-form-item>
          </template>

          <template v-else-if="activeId === 'embedding'">
            <n-form-item label="API URL">
              <n-input v-model:value="form.embedding_base_url" placeholder="嵌入模型 API 地址" />
            </n-form-item>
            <n-form-item label="模型名称">
              <n-input v-model:value="form.embedding_model" placeholder="如 BAAI/bge-large-zh-v1.5" />
            </n-form-item>
            <n-form-item label="供应商">
              <n-input
                v-model:value="form.embedding_factory"
                placeholder="如 SILICONFLOW、OpenAI-API-Compatible"
              />
            </n-form-item>
            <n-form-item label="SK / API Key">
              <n-input
                v-model:value="form.embedding_api_key"
                type="password"
                show-password-on="click"
                placeholder="留空或掩码表示不修改"
              />
            </n-form-item>
          </template>

          <template v-else-if="activeId === 'vl'">
            <n-form-item label="API URL">
              <n-input
                v-model:value="form.vl_base_url"
                placeholder="https://host/v1 或本地推理服务"
              />
            </n-form-item>
            <n-form-item label="模型名称">
              <n-input
                v-model:value="form.vl_model"
                placeholder="VL 模型名称"
              />
            </n-form-item>
            <n-form-item label="SK / API Key">
              <n-input
                v-model:value="form.vl_api_key"
                type="password"
                show-password-on="click"
                placeholder="留空或掩码表示不修改"
              />
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              KnowFlow PDF 图表增强（IMAGE2TEXT）。保存后立即生效并写入 RAGFlow；
              切换本地模型时仅改 API URL 与模型名即可。
            </n-text>
          </template>

          <template v-else-if="activeId === 'rerank'">
            <n-form-item label="API URL">
              <n-input v-model:value="form.rerank_base_url" placeholder="可选" />
            </n-form-item>
            <n-form-item label="模型名称">
              <n-input v-model:value="form.rerank_model" placeholder="可选" />
            </n-form-item>
            <n-form-item label="SK / API Key">
              <n-input
                v-model:value="form.rerank_api_key"
                type="password"
                show-password-on="click"
                placeholder="留空或掩码表示不修改"
              />
            </n-form-item>
          </template>

          <template v-else-if="activeId === 'paddleocr'">
            <n-form-item label="API URL">
              <n-input
                v-model:value="form.paddleocr_base_url"
                placeholder="https://host/v1 或自建 OCR 根地址"
              />
            </n-form-item>
            <n-form-item label="模型名称">
              <n-input
                v-model:value="form.paddleocr_model"
                placeholder="OCR-VL 模型名称"
              />
            </n-form-item>
            <n-form-item label="SK / API Key">
              <n-input
                v-model:value="form.paddleocr_api_key"
                type="password"
                show-password-on="click"
                placeholder="留空或掩码表示不修改"
              />
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              OpenAI 兼容 API（<code>/v1</code>）或自建 layout-parsing 根地址。
              保存后立即写入 KnowFlow <code>settings.yaml</code>；本地部署时改 URL 与模型名即可。
            </n-text>
          </template>

          <template v-else-if="activeId === 'speech'">
            <n-form-item label="服务地址">
              <n-input
                v-model:value="form.speech_service_url"
                placeholder="http://127.0.0.1:8765"
              />
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              平台语音转写功能调用此地址（对应 .env 中的
              <code>SPEECH_SERVICE_URL</code>）。保存后立即生效。
            </n-text>
          </template>

          <template v-else-if="activeId === 'pdf2zh'">
            <n-form-item label="服务地址">
              <n-input v-model:value="form.pdf2zh_api_url" placeholder="http://127.0.0.1:7861" />
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              文档翻译任务调用 pdf2zh API（对应 .env 中的
              <code>PDF2ZH_API_URL</code>）。保存后立即生效。
            </n-text>
          </template>

          <template v-else-if="activeId === 'searxng'">
            <n-form-item label="服务地址">
              <n-input
                v-model:value="form.searxng_url"
                placeholder="http://172.19.134.45:40000"
              />
            </n-form-item>
            <n-form-item label="请求超时">
              <n-input-number
                v-model:value="form.searxng_timeout_seconds"
                :min="3"
                :max="120"
                style="width: 100%"
              >
                <template #suffix>秒</template>
              </n-input-number>
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              网站收藏「联网搜索」通过此 SearXNG 实例的 JSON API（<code>/search?format=json</code>）检索。
              对应 .env 中 <code>SEARXNG_URL</code>、<code>SEARXNG_TIMEOUT_SECONDS</code>。保存后立即生效。
            </n-text>
          </template>

          <template v-else-if="activeId === 'ragflow_api'">
            <n-form-item label="API 地址">
              <n-input
                v-model:value="form.ragflow_api_url"
                placeholder="http://127.0.0.1:9380"
              />
            </n-form-item>
            <n-form-item label="API Key">
              <n-input
                v-model:value="form.ragflow_api_key"
                type="password"
                show-password-on="click"
                placeholder="留空或掩码表示不修改；mapped 模式可留空走用户会话"
              />
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              对应 .env 中 <code>RAGFLOW_API_URL</code>、<code>RAGFLOW_API_KEY</code>。
              Docker 栈内服务名 <code>ragflow</code> 会自动映射到 nginx :80。
            </n-text>
          </template>

          <template v-else-if="activeId === 'knowflow_backend'">
            <n-form-item label="API 后台">
              <n-input
                v-model:value="form.knowflow_backend_url"
                placeholder="http://127.0.0.1:5001"
              />
            </n-form-item>
            <n-form-item label="Web UI 后台">
              <n-input
                v-model:value="form.knowflow_ui_url"
                placeholder="http://127.0.0.1:9380"
              />
            </n-form-item>
            <n-form-item label="iframe 基址">
              <n-input
                v-model:value="form.knowflow_ui_public_url"
                placeholder="可选，如 http://127.0.0.1:40005/ragflow-ui"
              />
            </n-form-item>
            <n-form-item label="同源代理前缀">
              <n-input
                v-model:value="form.knowflow_ui_proxy_prefix"
                placeholder="可选，如 /ragflow-ui"
              />
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              对应 <code>KNOWFLOW_BACKEND_URL</code>、<code>KNOWFLOW_UI_URL</code>、
              <code>KNOWFLOW_UI_PUBLIC_URL</code>、<code>KNOWFLOW_UI_PROXY_PREFIX</code>。
              API 后台用于 RBAC 与知识库授权；Web UI 为 RAGFlow 管理界面；iframe 基址用于知识问答嵌入。
              保存后立即生效。
            </n-text>
          </template>

          <template v-else-if="activeId === 'ragflow_mysql'">
            <n-form-item label="主机">
              <n-input
                v-model:value="form.ragflow_mysql_host"
                placeholder="留空且启用 KnowFlow 时使用 knowflow-mysql"
              />
            </n-form-item>
            <n-form-item label="端口">
              <n-input-number
                v-model:value="form.ragflow_mysql_port"
                :min="1"
                :max="65535"
                style="width: 100%"
              />
            </n-form-item>
            <n-form-item label="数据库">
              <n-input v-model:value="form.ragflow_mysql_db" placeholder="rag_flow" />
            </n-form-item>
            <n-form-item label="root 密码">
              <n-input
                v-model:value="form.ragflow_mysql_password"
                type="password"
                show-password-on="click"
                placeholder="留空或掩码表示不修改"
              />
            </n-form-item>
            <n-form-item label="Docker 容器">
              <n-input
                v-model:value="form.ragflow_mysql_container"
                placeholder="ragflow-mysql（无法 TCP 连接时 fallback docker exec）"
              />
            </n-form-item>
            <n-text depth="3" class="drawer-hint">
              平台通过 MySQL 同步 RAGFlow 租户模型、清理冲突账号等。对应
              <code>RAGFLOW_MYSQL_*</code> 环境变量；远程开发可填服务器 IP。
            </n-text>
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
              测试连通性
            </n-button>
            <n-button type="primary" :loading="saving" :disabled="testing" @click="saveActive">
              保存并生效
            </n-button>
            <n-button @click="drawerOpen = false">取消</n-button>
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
