<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NIcon,
  NInput,
  NProgress,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NStep,
  NSteps,
  NTag,
  NText } from "naive-ui";
import {
  DownloadOutline,
  FolderOpenOutline,
  RocketOutline,
  SearchOutline,
  SwapHorizontalOutline,
  CheckmarkCircleOutline,
  TimeOutline,
  CloudDownloadOutline,
  EyeOutline } from "@vicons/ionicons5";
import AdminFormModal from "../components/AdminFormModal.vue";
import FileDropZone from "../components/FileDropZone.vue";
import DocumentVersionPreviewModal from "../components/DocumentVersionPreviewModal.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  createTranslateJob,
  downloadTranslateFile,
  fetchTranslateDocuments,
  fetchTranslateFileBlob,
  fetchTranslateJob,
  fetchTranslateMeta,
  importTranslateToLibrary,
  subscribeTranslateEvents } from "../api/client";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();

const meta = ref(null);
const sourceMode = ref("upload");
const pdfFile = ref(null);
const libraryDoc = ref(null);
const showLibraryModal = ref(false);
const libraryLoading = ref(false);
const libraryKeyword = ref("");
const libraryItems = ref([]);
const libraryPage = ref(1);
const libraryTotal = ref(0);
const glossaryFiles = ref([]);
const langIn = ref("en");
const langOut = ref("zh-CN");
const service = ref("");
const platformJobId = ref(null);
const status = ref("idle");
const progress = ref(0);
const stage = ref("");
const error = ref("");
const fileName = ref("");
const files = ref({
  mono: null,
  dual: null,
  glossary: null,
  extracted_json: null,
  extracted_md: null});
const importedDocumentId = ref(null);
const importLoading = ref(false);
const previewShow = ref(false);
const previewKind = ref("dual");
let closeEvents = null;
let pollTimer = null;

const selectedEngine = computed(() =>
  meta.value?.engines?.find((e) => e.id === service.value)
);
const glossarySupported = computed(
  () => selectedEngine.value?.supports_glossary ?? false
);
const LANG_LABEL_ZH = {
  en: "英语",
  "zh-CN": "简体中文",
  "zh-TW": "繁体中文（台湾）",
  ja: "日语",
  ko: "韩语",
  de: "德语",
  fr: "法语",
  es: "西班牙语",
  ru: "俄语",
  auto: "自动检测"};

const langOptions = computed(() =>
  (meta.value?.languages || []).map((l) => ({
    label: LANG_LABEL_ZH[l.code] || l.label,
    value: l.code}))
);
const engineOptions = computed(() =>
  (meta.value?.engines || []).map((e) => ({
    label: e.label || e.model || e.id,
    value: e.id}))
);
const hasPdfSource = computed(
  () =>
    (sourceMode.value === "upload" && pdfFile.value) ||
    (sourceMode.value === "library" && libraryDoc.value)
);
const canStart = computed(
  () => hasPdfSource.value && !["running", "submitting"].includes(status.value)
);
const displayFileName = computed(() => {
  if (sourceMode.value === "library" && libraryDoc.value) {
    return `${libraryDoc.value.title}（${libraryDoc.value.file_name}）`;
  }
  return pdfFile.value?.name || fileName.value;
});
const statusType = computed(() => {
  if (status.value === "error") return "error";
  if (status.value === "done") return "success";
  if (status.value === "running") return "info";
  return "default";
});
const currentStep = computed(() => {
  if (status.value === "done" || ["running", "submitting"].includes(status.value)) return 3;
  if (hasPdfSource.value) return 2;
  return 1;
});
const statusLabel = computed(() => {
  const map = {
    idle: "待开始",
    submitting: "提交中",
    running: "翻译中",
    done: "已完成",
    error: "失败"};
  return map[status.value] || status.value;
});
const showProgressPanel = computed(() => status.value !== "idle");
const resultsReady = computed(() => status.value === "done");

const langPairLabel = computed(() => {
  const inL = LANG_LABEL_ZH[langIn.value] || langIn.value;
  const outL = LANG_LABEL_ZH[langOut.value] || langOut.value;
  return `${inL} → ${outL}`;
});

const engineLabel = computed(
  () => engineOptions.value.find((o) => o.value === service.value)?.label || ""
);

function applyJob(job) {
  platformJobId.value = job.platform_job_id;
  status.value = job.status;
  progress.value = job.progress ?? 0;
  stage.value = job.stage || "";
  error.value = job.error_message || "";
  fileName.value = job.file_name || "";
  if (job.files) files.value = { ...files.value, ...job.files };
  if (job.lang_in) langIn.value = job.lang_in;
  if (job.lang_out) langOut.value = job.lang_out;
  if (job.service) service.value = job.service;
  importedDocumentId.value = job.imported_document_id || null;
}

async function refreshJob() {
  if (!platformJobId.value) return;
  try {
    const job = await fetchTranslateJob(platformJobId.value);
    applyJob(job);
  } catch (e) {
    if (status.value === "running") error.value = e.message;
  }
}

function startPoll() {
  stopPoll();
  pollTimer = setInterval(refreshJob, 4000);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function subscribeLive(jobId) {
  if (closeEvents) closeEvents();
  closeEvents = subscribeTranslateEvents(jobId, {
    onEvent(ev) {
      if (ev.overall_progress != null) progress.value = ev.overall_progress;
      if (ev.stage) stage.value = ev.stage;
      if (ev.type === "files_updated" && ev.files) {
        files.value = { ...files.value, ...ev.files };
      }
      if (ev.type === "finish" && ev.translate_result) {
        const r = ev.translate_result;
        files.value = {
          ...files.value,
          mono: r.mono_pdf_path ?? files.value.mono,
          dual: r.dual_pdf_path ?? files.value.dual,
          glossary: r.auto_extracted_glossary_path ?? files.value.glossary};
      }
      if (ev.type === "error") {
        error.value = ev.error || "翻译失败";
        status.value = "error";
        stopPoll();
      }
    },
    onError() {
      startPoll();
    },
    async onComplete(data) {
      status.value = data.status === "done" ? "done" : data.status;
      if (data.error) error.value = data.error;
      if (data.files) files.value = { ...files.value, ...data.files };
      progress.value = 100;
      await refreshJob();
      stopPoll();
    }});
}

onMounted(async () => {
  try {
    meta.value = await fetchTranslateMeta();
    if (meta.value.engines?.length) {
      const withGlossary = meta.value.engines.find((e) => e.supports_glossary);
      service.value = (withGlossary || meta.value.engines[0]).id;
    }
  } catch (e) {
    error.value = e.message;
  }
  const qid = route.query.job;
  if (qid) {
    platformJobId.value = qid;
    await refreshJob();
    if (status.value === "running") {
      subscribeLive(qid);
    }
  }
});

watch(
  () => route.query.job,
  async (id) => {
    if (id && id !== platformJobId.value) {
      platformJobId.value = id;
      await refreshJob();
    }
  }
);

onBeforeUnmount(() => {
  if (closeEvents) closeEvents();
  stopPoll();
  if (status.value === "running") {
    ui.info("翻译将在后台继续，可在后台任务或消息中查看结果", { duration: 5000 });
  }
});

function onSourceModeChange(mode) {
  if (mode === "upload") libraryDoc.value = null;
  else pdfFile.value = null;
}

function onPdfChange(e) {
  pdfFile.value = e.target.files?.[0] || null;
  if (pdfFile.value) libraryDoc.value = null;
}

const libraryColumns = [
  { title: "标题", key: "title", ellipsis: { tooltip: true } },
  { title: "文件名", key: "file_name", width: 180, ellipsis: { tooltip: true } },
  {
    title: "大小",
    key: "file_size",
    width: 90,
    render: (row) => {
      const mb = row.file_size / (1024 * 1024);
      return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(row.file_size / 1024).toFixed(0)} KB`;
    }},
  {
    title: "操作",
    key: "actions",
    width: 80,
    render: (row) =>
      h(
        NButton,
        {
          text: true,
          type: "primary",
          size: "small",
          onClick: () => selectLibraryDoc(row)},
        () => "选择"
      )},
];

async function loadLibraryDocs() {
  libraryLoading.value = true;
  try {
    const data = await fetchTranslateDocuments({
      page: libraryPage.value,
      keyword: libraryKeyword.value || undefined});
    libraryItems.value = data.items;
    libraryTotal.value = data.total;
  } catch (e) {
    ui.error(e.message);
  } finally {
    libraryLoading.value = false;
  }
}

function openLibraryPicker() {
  showLibraryModal.value = true;
  libraryPage.value = 1;
  libraryKeyword.value = "";
  libraryItems.value = [];
  libraryTotal.value = 0;
  loadLibraryDocs();
}

function selectLibraryDoc(row) {
  libraryDoc.value = row;
  pdfFile.value = null;
  sourceMode.value = "library";
  showLibraryModal.value = false;
}

function onLibraryPageChange(p) {
  libraryPage.value = p;
  loadLibraryDocs();
}

function onGlossaryChange(e) {
  glossaryFiles.value = Array.from(e.target.files || []);
}

function swapLanguages() {
  if (status.value === "running") return;
  const from = langIn.value;
  langIn.value = langOut.value;
  langOut.value = from;
}

async function startTranslation() {
  if (!hasPdfSource.value) return;
  if (glossaryFiles.value.length && !glossarySupported.value) {
    error.value = "当前翻译方式不支持术语表";
    return;
  }
  error.value = "";
  status.value = "submitting";
  progress.value = 0;
  files.value = {
    mono: null,
    dual: null,
    glossary: null,
    extracted_json: null,
    extracted_md: null};
  if (closeEvents) closeEvents();

  try {
    const job = await createTranslateJob({
      pdf: sourceMode.value === "upload" ? pdfFile.value : null,
      documentId: sourceMode.value === "library" ? libraryDoc.value?.id : null,
      langIn: langIn.value,
      langOut: langOut.value,
      service: service.value,
      glossaries: glossaryFiles.value});
    applyJob(job);
    ui.success(job.message || "已提交，后台翻译中");
    status.value = "running";
    router.replace({ query: { job: job.platform_job_id } });
    subscribeLive(job.platform_job_id);
  } catch (e) {
    error.value = e.message;
    status.value = "error";
  }
}

const renderIcon = (icon) => () => h(NIcon, null, { default: () => h(icon) });

async function dl(kind, name) {
  if (!platformJobId.value) return;
  try {
    await downloadTranslateFile(platformJobId.value, kind, name);
  } catch (e) {
    error.value = e.message;
  }
}

async function importToLibrary(variant = "mono") {
  if (!platformJobId.value || importLoading.value || status.value !== "done") return;
  importLoading.value = true;
  try {
    const res = await importTranslateToLibrary(platformJobId.value, { variant });
    importedDocumentId.value = res.document_id;
    ui.success(res.message || "已添加到知识库");
    await refreshJob();
  } catch (e) {
    ui.error(e.message);
  } finally {
    importLoading.value = false;
  }
}

function openImportedDocument() {
  if (!importedDocumentId.value) return;
  router.push({ name: "document-detail", params: { id: importedDocumentId.value } });
}

const previewTitle = computed(() =>
  previewKind.value === "dual" ? "预览双语 PDF" : "预览单语 PDF"
);

const previewFileName = computed(() =>
  previewKind.value === "dual" ? "dual.pdf" : "mono.pdf"
);

function openPreview(kind) {
  if (!platformJobId.value || status.value !== "done") return;
  previewKind.value = kind;
  previewShow.value = true;
}

function loadPreviewBlob() {
  if (!platformJobId.value) {
    return Promise.reject(new Error("任务不存在"));
  }
  return fetchTranslateFileBlob(platformJobId.value, previewKind.value);
}
</script>

<template>
  <FeatureSubsystemShell fill>
    <template #extra>
      <n-tag v-if="platformJobId" size="small" round type="info" :bordered="false">
        任务 {{ platformJobId.slice(0, 8) }}…
      </n-tag>
    </template>

    <div class="translate-page">
    <header class="translate-steps-bar feature-local-nav">
      <n-steps :current="currentStep" size="small" class="translate-steps">
        <n-step title="文档" description="上传或选取" />
        <n-step title="配置" description="语言与模型" />
        <n-step title="结果" description="下载译文" />
      </n-steps>
    </header>

    <div v-if="status === 'running' || error" class="page-alerts">
      <n-alert
        v-if="status === 'running'"
        type="info"
        class="page-alert"
        closable
      >
        翻译在后台进行，可切换其他页面；完成后在消息或后台任务查看。
      </n-alert>
      <n-alert
        v-if="error"
        type="error"
        :title="error"
        closable
        class="page-alert"
        @close="error = ''"
      />
    </div>

    <div class="translate-workspace">
      <div class="translate-layout">
        <section class="translate-main">
          <n-card class="workflow-card" size="small">
            <div class="wf-section">
              <div class="wf-section-head">
                <span class="wf-step-badge">1</span>
                <div class="wf-section-titles">
                  <span class="wf-section-title">选择文档</span>
                  <span class="wf-section-desc">本地上传或从文档库选取</span>
                </div>
              </div>

              <n-radio-group
                v-model:value="sourceMode"
                size="small"
                class="source-toggle"
                :disabled="status === 'running'"
                @update:value="onSourceModeChange"
              >
                <n-radio-button value="upload">本地上传</n-radio-button>
                <n-radio-button value="library">文档库</n-radio-button>
              </n-radio-group>

              <div v-if="sourceMode === 'upload'" class="upload-fill">
                <file-drop-zone
                  accept=".pdf"
                  compact
                  title="拖拽 PDF 到此处"
                  hint="支持标准 PDF"
                  :file-name="displayFileName"
                  icon="doc"
                  :disabled="status === 'running'"
                  @change="onPdfChange"
                />
              </div>

              <div v-else class="library-pick">
                <div v-if="libraryDoc" class="library-selected">
                  <n-icon :size="18" class="library-selected-icon">
                    <checkmark-circle-outline />
                  </n-icon>
                  <div class="library-selected-body">
                    <n-text strong>{{ libraryDoc.title }}</n-text>
                    <n-text depth="3" class="library-file-name">{{ libraryDoc.file_name }}</n-text>
                  </div>
                </div>
                <div v-else class="library-empty">
                  <n-icon :size="22" :depth="3" :component="FolderOpenOutline" />
                  <n-text depth="2">从文档库选择 PDF</n-text>
                </div>
                <n-space :size="8" class="library-actions">
                  <n-button
                    size="small"
                    type="primary"
                    :disabled="status === 'running'"
                    @click="openLibraryPicker"
                  >
                    <template #icon>
                      <n-icon :component="FolderOpenOutline" />
                    </template>
                    {{ libraryDoc ? "更换" : "浏览文档库" }}
                  </n-button>
                  <n-button
                    v-if="libraryDoc"
                    size="small"
                    quaternary
                    :disabled="status === 'running'"
                    @click="libraryDoc = null"
                  >
                    清除
                  </n-button>
                </n-space>
              </div>
            </div>

            <div class="wf-divider" />

            <div class="wf-section">
              <div class="wf-section-head">
                <span class="wf-step-badge">2</span>
                <div class="wf-section-titles">
                  <span class="wf-section-title">翻译配置</span>
                  <span class="wf-section-desc">语言、模型与术语表</span>
                </div>
              </div>

              <div class="config-grid">
                <section class="config-block">
                  <n-text class="block-label">语言方向</n-text>
                  <div class="lang-row">
                    <div class="lang-field">
                      <n-text depth="3" class="field-label">源</n-text>
                      <n-select
                        v-model:value="langIn"
                        size="small"
                        :options="langOptions"
                        filterable
                        :disabled="status === 'running'"
                      />
                    </div>
                    <button
                      type="button"
                      class="lang-swap-btn"
                      aria-label="交换语言方向"
                      :disabled="status === 'running'"
                      @click="swapLanguages"
                    >
                      <n-icon :size="16"><swap-horizontal-outline /></n-icon>
                    </button>
                    <div class="lang-field">
                      <n-text depth="3" class="field-label">目标</n-text>
                      <n-select
                        v-model:value="langOut"
                        size="small"
                        :options="langOptions"
                        filterable
                        :disabled="status === 'running'"
                      />
                    </div>
                  </div>
                  <n-tag size="tiny" :bordered="false" class="lang-pair-tag">
                    {{ langPairLabel }}
                  </n-tag>
                </section>

                <section class="config-block">
                  <n-text class="block-label">翻译模型</n-text>
                  <n-select
                    v-model:value="service"
                    size="small"
                    :options="engineOptions"
                    :disabled="status === 'running'"
                  />
                </section>
              </div>

              <section class="config-block config-block--glossary">
                <div class="block-label-row">
                  <n-text class="block-label">术语表（可选）</n-text>
                  <n-tag
                    size="tiny"
                    round
                    :type="glossarySupported ? 'success' : 'warning'"
                    :bordered="false"
                  >
                    {{ glossarySupported ? "支持" : "需换模型" }}
                  </n-tag>
                </div>
                <file-drop-zone
                  accept=".csv"
                  multiple
                  compact
                  :disabled="!glossarySupported || status === 'running'"
                  title="上传 CSV 术语表"
                  hint="source, target, tgt_lng"
                  :file-name="
                    glossaryFiles.length
                      ? `已选 ${glossaryFiles.length} 个文件`
                      : ''
                  "
                  @change="onGlossaryChange"
                />
              </section>
            </div>

            <div class="wf-actions">
              <n-button
                type="primary"
                size="medium"
                class="start-btn"
                :disabled="!canStart"
                :loading="status === 'running' || status === 'submitting'"
                :render-icon="renderIcon(RocketOutline)"
                @click="startTranslation"
              >
                {{ status === "running" || status === "submitting" ? "翻译进行中…" : "开始翻译" }}
              </n-button>
            </div>
          </n-card>
        </section>

        <aside
          class="translate-aside"
          :class="{
            'translate-aside--active': showProgressPanel,
            'translate-aside--done': status === 'done',
          }"
        >
          <n-card class="result-card" size="small">
            <template #header>
              <div class="result-head">
                <n-icon
                  :size="16"
                  :component="status === 'done' ? CheckmarkCircleOutline : CloudDownloadOutline"
                />
                <span>进度与结果</span>
              </div>
            </template>

            <div class="result-body">
              <div v-if="!showProgressPanel" class="result-idle">
                <n-icon :size="24" :depth="3"><time-outline /></n-icon>
                <n-text depth="2">配置完成后点击「开始翻译」</n-text>
              </div>

              <template v-else>
              <div class="status-strip" :class="`status-strip--${status}`">
                <div class="status-row">
                  <n-tag :type="statusType" round size="small">{{ statusLabel }}</n-tag>
                  <span
                    v-if="status === 'running'"
                    class="status-pulse"
                    aria-hidden="true"
                  />
                </div>
                <n-text v-if="displayFileName" depth="2" class="status-file">
                  {{ displayFileName }}
                </n-text>
                <n-text v-if="status !== 'idle'" depth="3" class="status-meta">
                  {{ langPairLabel }}
                  <template v-if="engineLabel"> · {{ engineLabel }}</template>
                </n-text>
              </div>

              <div
                v-if="status === 'running' || status === 'done'"
                class="progress-block"
              >
                <div class="progress-head">
                  <n-text depth="3">进度</n-text>
                  <n-text strong class="progress-pct">{{ Math.round(progress) }}%</n-text>
                </div>
                <n-progress
                  type="line"
                  :percentage="Math.round(progress)"
                  indicator-placement="inside"
                  :processing="status === 'running'"
                  :status="status === 'done' ? 'success' : 'default'"
                  :height="8"
                  :border-radius="4"
                />
                <n-text v-if="stage" depth="2" class="stage-text">{{ stage }}</n-text>
              </div>

              </template>

              <div class="dl-group">
                <n-text class="dl-group-label">译文</n-text>
                <div class="dl-list">
                  <div
                    class="dl-item dl-item--primary"
                    :class="{ 'dl-item--disabled': !resultsReady }"
                  >
                    <button
                      type="button"
                      class="dl-item-main"
                      :disabled="!resultsReady"
                      @click="dl('dual', 'dual.pdf')"
                    >
                      <n-icon :size="16" :component="DownloadOutline" />
                      <span class="dl-item-text">
                        <strong>双语 PDF</strong>
                        <small>对照版</small>
                      </span>
                    </button>
                    <n-button text size="tiny" :disabled="!resultsReady" @click="openPreview('dual')">
                      <template #icon>
                        <n-icon :component="EyeOutline" />
                      </template>
                      预览
                    </n-button>
                  </div>
                  <div class="dl-item" :class="{ 'dl-item--disabled': !resultsReady }">
                    <button
                      type="button"
                      class="dl-item-main"
                      :disabled="!resultsReady"
                      @click="dl('mono', 'mono.pdf')"
                    >
                      <n-icon :size="16" :component="DownloadOutline" />
                      <span class="dl-item-text">
                        <strong>单语 PDF</strong>
                        <small>仅译文</small>
                      </span>
                    </button>
                    <n-button text size="tiny" :disabled="!resultsReady" @click="openPreview('mono')">
                      <template #icon>
                        <n-icon :component="EyeOutline" />
                      </template>
                      预览
                    </n-button>
                  </div>
                </div>
              </div>

              <div class="dl-group">
                <n-text class="dl-group-label">更多导出</n-text>
                <n-space :size="6" wrap class="dl-chips">
                  <n-button
                    size="tiny"
                    secondary
                    :disabled="!resultsReady"
                    @click="dl('glossary', 'glossary.csv')"
                  >
                    术语表
                  </n-button>
                  <n-button
                    size="tiny"
                    secondary
                    :disabled="!resultsReady"
                    @click="dl('extracted-json', 'extracted.json')"
                  >
                    JSON
                  </n-button>
                  <n-button
                    size="tiny"
                    secondary
                    :disabled="!resultsReady"
                    @click="dl('extracted-md', 'extracted.md')"
                  >
                    Markdown
                  </n-button>
                </n-space>
              </div>

              <div class="dl-group">
                <n-text class="dl-group-label">知识库</n-text>
                <n-space :size="6" wrap align="center">
                  <template v-if="importedDocumentId">
                    <n-tag type="success" :bordered="false" size="small">已入库</n-tag>
                    <n-button size="tiny" type="primary" @click="openImportedDocument">
                      查看文档
                    </n-button>
                  </template>
                  <template v-else>
                    <n-button
                      size="tiny"
                      type="primary"
                      :disabled="!resultsReady"
                      :loading="importLoading"
                      @click="importToLibrary('mono')"
                    >
                      单语入库
                    </n-button>
                    <n-button
                      size="tiny"
                      secondary
                      :disabled="!resultsReady"
                      :loading="importLoading"
                      @click="importToLibrary('dual')"
                    >
                      双语入库
                    </n-button>
                  </template>
                </n-space>
                <n-text
                  v-if="showProgressPanel && !resultsReady"
                  depth="3"
                  class="dl-group-hint"
                >
                  翻译完成后可下载或导入文档库
                </n-text>
              </div>
            </div>
          </n-card>
        </aside>
      </div>
    </div>
    </div>

    <AdminFormModal
      v-model:show="showLibraryModal"
      title="选择文档库 PDF"
      subtitle="从已上传的 PDF 中选取"
      width="min(560px, 92vw)"
    >
      <n-space align="center" :size="8" class="library-search">
        <n-input
          v-model:value="libraryKeyword"
          size="small"
          placeholder="搜索标题"
          clearable
          @keyup.enter="libraryPage = 1; loadLibraryDocs()"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" />
          </template>
        </n-input>
        <n-button size="small" type="primary" @click="libraryPage = 1; loadLibraryDocs()">
          搜索
        </n-button>
      </n-space>
      <n-data-table
        :columns="libraryColumns"
        :data="libraryItems"
        :loading="libraryLoading"
        :max-height="320"
        :pagination="{
          page: libraryPage,
          pageSize: 10,
          itemCount: libraryTotal,
          onUpdatePage: onLibraryPageChange}"
        size="small"
      />
    </AdminFormModal>

    <DocumentVersionPreviewModal
      v-model:show="previewShow"
      :blob-loader="loadPreviewBlob"
      :preview-title="previewTitle"
      :preview-subtitle="displayFileName"
      :preview-file-name="previewFileName"
      :show-download-action="false"
      width="min(760px, 94vw)"
      viewport-height="min(58vh, 560px)"
    />
  </FeatureSubsystemShell>
</template>

<style scoped>
.translate-page {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 1040px;
  margin: 0 auto;
  box-sizing: border-box;
}

.translate-steps-bar {
  flex-shrink: 0;
}

.translate-steps {
  max-width: 420px;
}

.page-alerts {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.page-alert {
  margin: 0;
}

.translate-workspace {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.translate-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  align-items: start;
}

@media (min-width: 880px) {
  .translate-layout {
    grid-template-columns: minmax(0, 1.2fr) minmax(260px, 0.8fr);
    gap: 14px;
  }

  .translate-aside {
    position: sticky;
    top: 6px;
  }
}

.translate-main,
.translate-aside,
.workflow-card {
  min-width: 0;
  max-width: 100%;
}

.workflow-card :deep(.n-card__content) {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 14px 16px 16px;
}

.workflow-card :deep(.n-card-header) {
  padding: 10px 16px 0;
  min-height: 0;
}

.wf-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  max-width: 100%;
}

.wf-section-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.wf-step-badge {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}

.wf-section-titles {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.wf-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color);
  line-height: 1.3;
}

.wf-section-desc {
  font-size: 12px;
  color: var(--platform-muted);
  line-height: 1.35;
}

.wf-divider {
  height: 1px;
  margin: 14px 0;
  background: var(--platform-divider, var(--platform-border));
}

.source-toggle {
  width: 100%;
}

.source-toggle :deep(.n-radio-group) {
  display: flex;
  width: 100%;
}

.source-toggle :deep(.n-radio-button) {
  flex: 1;
  text-align: center;
}

.upload-fill {
  width: 100%;
  min-width: 0;
  max-width: 100%;
}

.upload-fill :deep(.drop-zone) {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  min-height: 0;
  padding: 8px 10px;
  box-sizing: border-box;
  border-radius: var(--platform-radius-sm, 8px);
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto auto auto;
  align-items: center;
  gap: 1px 8px;
  text-align: left;
  overflow: hidden;
}

.upload-fill :deep(.drop-zone .drop-icon-wrap) {
  grid-row: 1 / 3;
  width: 24px;
  height: 24px;
  margin-bottom: 0;
}

.upload-fill :deep(.drop-zone .drop-icon-wrap .n-icon) {
  font-size: 16px !important;
}

.upload-fill :deep(.drop-zone .drop-title) {
  grid-column: 2;
  grid-row: 1;
  font-size: 12px;
  margin-bottom: 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-fill :deep(.drop-zone .drop-hint) {
  grid-column: 2;
  grid-row: 2;
  font-size: 11px;
  line-height: 1.35;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-fill :deep(.drop-zone .drop-btn) {
  grid-column: 1 / -1;
  grid-row: 3;
  margin-top: 4px;
  justify-self: start;
  max-width: 100%;
}

.upload-fill :deep(.drop-zone .drop-btn.n-button) {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}

.config-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

@media (min-width: 520px) {
  .config-grid {
    grid-template-columns: 1fr 1fr;
  }
}

.config-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-block--glossary {
  margin-top: 2px;
}

.config-block--glossary :deep(.drop-zone) {
  min-height: 72px;
  padding: 0.55rem 0.7rem;
}

.block-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--n-text-color);
}

.block-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.lang-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.lang-field {
  flex: 1;
  min-width: 0;
}

.lang-swap-btn {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  margin-bottom: 1px;
  border: 1px solid var(--platform-border);
  border-radius: 50%;
  background: var(--platform-bg-glass-subtle, var(--n-color));
  color: var(--platform-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.lang-swap-btn:hover:not(:disabled) {
  color: var(--platform-accent);
  border-color: var(--platform-accent-border-soft);
  background: var(--platform-accent-soft);
}

.lang-swap-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.lang-pair-tag {
  align-self: flex-start;
  background: var(--platform-accent-soft) !important;
  color: var(--platform-accent) !important;
}

.field-label {
  display: block;
  font-size: 11px;
  margin-bottom: 4px;
}

.wf-actions {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--platform-divider, var(--platform-border));
}

.start-btn {
  width: 100%;
  font-weight: 600;
  height: 36px;
}

.library-pick {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.library-empty {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  padding: 8px 12px;
  min-height: 0;
  border-radius: var(--platform-radius-sm, 8px);
  border: 1.5px dashed var(--n-border-color);
  background: color-mix(in srgb, var(--platform-text) 2%, transparent);
  text-align: left;
  font-size: 12px;
}

.library-selected {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--platform-radius-sm, 8px);
  border: 1px solid var(--platform-accent-border-soft);
  background: var(--platform-accent-soft);
}

.library-selected-icon {
  color: var(--platform-accent);
  flex-shrink: 0;
  margin-top: 1px;
}

.library-selected-body {
  min-width: 0;
  flex: 1;
}

.library-file-name {
  display: block;
  font-size: 11px;
  margin-top: 2px;
}

.result-card :deep(.n-card-header) {
  padding: 10px 14px 6px;
  min-height: 0;
}

.result-card :deep(.n-card__content) {
  padding: 8px 14px 14px;
}

.result-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color);
}

.result-head .n-icon {
  color: var(--platform-accent);
}

.translate-aside--active .result-card {
  border-color: color-mix(in srgb, var(--platform-accent) 22%, transparent);
}

.translate-aside--done .result-card {
  border-color: var(--platform-accent-border-soft);
}

.result-idle {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 4px 4px;
  text-align: center;
  font-size: 12px;
}

.result-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.status-strip {
  padding: 10px 12px;
  border-radius: var(--platform-radius-sm, 8px);
  background: color-mix(in srgb, var(--platform-text) 3%, transparent);
  border: 1px solid var(--platform-border);
}

.status-strip--done {
  background: var(--platform-accent-soft);
  border-color: var(--platform-accent-border-soft);
}

.status-strip--running {
  background: color-mix(in srgb, var(--platform-accent) 6%, transparent);
  border-color: var(--platform-accent-border-soft);
}

.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.status-pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--platform-accent);
  animation: translate-pulse 1.4s ease-in-out infinite;
}

@keyframes translate-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.45;
    transform: scale(0.85);
  }
}

.status-file {
  display: block;
  font-size: 12px;
  margin-top: 6px;
  word-break: break-all;
  line-height: 1.4;
}

.status-meta {
  display: block;
  font-size: 11px;
  margin-top: 3px;
}

.progress-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
}

.progress-pct {
  font-size: 13px;
  color: var(--platform-accent);
}

.stage-text {
  font-size: 12px;
  line-height: 1.45;
}

.dl-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dl-group-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--platform-muted);
}

.dl-group-hint {
  font-size: 11px;
  line-height: 1.4;
}

.dl-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dl-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px 4px 8px;
  border-radius: var(--platform-radius-sm, 8px);
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-glass-subtle, transparent);
  transition: border-color 0.15s, background 0.15s;
}

.dl-item:hover:not(.dl-item--disabled) {
  border-color: var(--platform-accent-border-soft);
  background: var(--platform-accent-soft);
}

.dl-item--disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.dl-item--disabled .dl-item-main {
  cursor: not-allowed;
}

.dl-item--disabled .dl-item-main:disabled {
  opacity: 1;
}

.dl-item--primary {
  border-color: var(--platform-accent-border-soft);
  background: color-mix(in srgb, var(--platform-accent) 5%, transparent);
}

.dl-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  color: inherit;
}

.dl-item-main .n-icon {
  flex-shrink: 0;
  color: var(--platform-accent);
}

.dl-item-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.dl-item-text strong {
  font-size: 12px;
  font-weight: 600;
  line-height: 1.3;
}

.dl-item-text small {
  font-size: 11px;
  color: var(--platform-muted);
  line-height: 1.3;
}

.library-search {
  display: flex;
  width: 100%;
  margin-bottom: 10px;
}

.library-search :deep(.n-input) {
  flex: 1;
  min-width: 0;
}

@media (max-width: 639px) {
  .lang-swap-btn {
    display: none;
  }

  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
