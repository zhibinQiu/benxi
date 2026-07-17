<script setup>
import { useI18n } from "../composables/useI18n.js";
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NIcon,
  NInput,
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
import TranslateToolbar from "../components/translate/TranslateToolbar.vue";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import ListTableFooter from "../components/ListTableFooter.vue";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
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
const { t } = useI18n();
const { headerExtensionActive } = usePageHeaderExtension();
const headerTeleportReady = ref(false);

const LANG_KEY_MAP = {
  en: "en",
  "zh-CN": "zhCN",
  "zh-TW": "zhTW",
  ja: "ja",
  ko: "ko",
  de: "de",
  fr: "fr",
  es: "es",
  ru: "ru",
  auto: "auto",
};

function langLabel(code) {
  const key = LANG_KEY_MAP[code];
  if (key) return t(`translate.languages.${key}`);
  return code;
}

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
const langOptions = computed(() =>
  (meta.value?.languages || []).map((l) => ({
    label: langLabel(l.code) || l.label,
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
    return t("translate.displayFileName", {
      title: libraryDoc.value.title,
      fileName: libraryDoc.value.file_name,
    });
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
const statusLabel = computed(
  () => t(`translate.status.${status.value}`) || status.value
);
const showProgressPanel = computed(() => status.value !== "idle");
const resultsReady = computed(() => status.value === "done");

const langPairLabel = computed(() => {
  const inL = langLabel(langIn.value) || langIn.value;
  const outL = langLabel(langOut.value) || langOut.value;
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
        error.value = ev.error || t("translate.translateFailed");
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
  nextTick(() => {
    headerTeleportReady.value = true;
  });
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
      if (closeEvents) closeEvents();
      stopPoll();
      platformJobId.value = id;
      await refreshJob();
      if (status.value === "running") {
        subscribeLive(id);
      }
    }
  }
);

onBeforeUnmount(() => {
  if (closeEvents) closeEvents();
  stopPoll();
  if (status.value === "running") {
    ui.info(t("translate.backgroundContinue"), { duration: 5000 });
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

const libraryColumns = computed(() => [
  { title: t("translate.libraryColTitle"), key: "title", ellipsis: { tooltip: true } },
  {
    title: t("translate.libraryColFileName"),
    key: "file_name",
    width: 216,
    ellipsis: { tooltip: true },
  },
  {
    title: t("translate.libraryColSize"),
    key: "file_size",
    width: 108,
    render: (row) => {
      const mb = row.file_size / (1024 * 1024);
      return mb >= 1
        ? t("translate.sizeMb", { size: mb.toFixed(1) })
        : t("translate.sizeKb", { size: (row.file_size / 1024).toFixed(0) });
    },
  },
  {
    title: t("translate.libraryColAction"),
    key: "actions",
    width: 96,
    render: (row) =>
      h(
        NButton,
        {
          size: "small",
          type: "primary",
          onClick: () => selectLibraryDoc(row),
        },
        () => t("translate.select")
      ),
  },
]);

async function loadLibraryDocs() {
  libraryLoading.value = true;
  try {
    const data = await fetchTranslateDocuments({
      page: libraryPage.value,
      page_size: LIST_PAGE_SIZE,
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
    error.value = t("translate.glossaryNotSupported");
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
    ui.success(job.message || t("translate.submitted"));
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
    ui.success(res.message || t("translate.importedToLibrary"));
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
  previewKind.value === "dual" ? t("translate.previewDual") : t("translate.previewMono")
);

const previewFileName = computed(() =>
  previewKind.value === "dual" ? "dual.pdf" : "mono.pdf"
);

function openPreview(kind) {
  if (!platformJobId.value || status.value !== "done") return;
  previewKind.value = kind;
  previewShow.value = true;
}

const glossaryFileLabel = computed(() =>
  glossaryFiles.value.length
    ? t("translate.glossaryFilesSelected", { count: glossaryFiles.value.length })
    : ""
);

function loadPreviewBlob() {
  if (!platformJobId.value) {
    return Promise.reject(new Error(t("translate.jobNotFound")));
  }
  return fetchTranslateFileBlob(platformJobId.value, previewKind.value);
}
</script>

<template>
  <FeatureSubsystemShell fill>
    <Teleport
      v-if="headerTeleportReady && headerExtensionActive"
      to="#page-header-extension"
    >
      <TranslateToolbar
        :show-progress="showProgressPanel"
        :status="status"
        :status-label="statusLabel"
        :status-type="statusType"
        :progress="progress"
        :stage="stage"
        :platform-job-id="platformJobId"
      />
    </Teleport>

    <div class="translate-page">
    <header class="translate-steps-bar feature-local-nav">
      <n-steps :current="currentStep" size="small" class="translate-steps">
        <n-step :title="t('translate.steps.document.title')" :description="t('translate.steps.document.description')" />
        <n-step :title="t('translate.steps.config.title')" :description="t('translate.steps.config.description')" />
        <n-step :title="t('translate.steps.result.title')" :description="t('translate.steps.result.description')" />
      </n-steps>
    </header>

    <div v-if="status === 'running' || error" class="page-alerts">
      <n-alert
        v-if="status === 'running'"
        type="info"
        class="page-alert"
        closable
      >
        {{ t("translate.runningAlert") }}
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
                  <span class="wf-section-title">{{ t("translate.selectDocument") }}</span>
                  <span class="wf-section-desc">{{ t("translate.selectDocumentDesc") }}</span>
                </div>
              </div>

              <n-radio-group
                v-model:value="sourceMode"
                size="small"
                class="source-toggle"
                :disabled="status === 'running'"
                @update:value="onSourceModeChange"
              >
                <n-radio-button value="upload">{{ t("translate.sourceUpload") }}</n-radio-button>
                <n-radio-button value="library">{{ t("translate.sourceLibrary") }}</n-radio-button>
              </n-radio-group>

              <div v-if="sourceMode === 'upload'" class="upload-fill">
                <file-drop-zone
                  accept=".pdf"
                  compact
                  hide-button
                  :title="t('translate.dropPdfTitle')"
                  :hint="t('translate.dropPdfHint')"
                  :file-name="displayFileName"
                  icon="doc"
                  :disabled="status === 'running'"
                  @change="onPdfChange"
                />
              </div>

              <div
                v-else
                class="library-pick"
                :class="{ 'library-pick--disabled': status === 'running' }"
                role="button"
                tabindex="0"
                :aria-label="libraryDoc ? t('translate.replace') : t('translate.pickFromLibrary')"
                @click="status !== 'running' && openLibraryPicker()"
                @keydown.enter.prevent="status !== 'running' && openLibraryPicker()"
                @keydown.space.prevent="status !== 'running' && openLibraryPicker()"
              >
                <div v-if="libraryDoc" class="library-selected">
                  <n-icon :size="22" class="library-selected-icon">
                    <checkmark-circle-outline />
                  </n-icon>
                  <div class="library-selected-body">
                    <n-text strong>{{ libraryDoc.title }}</n-text>
                    <n-text depth="3" class="library-file-name">{{ libraryDoc.file_name }}</n-text>
                  </div>
                  <button
                    type="button"
                    class="library-clear-btn"
                    :aria-label="t('translate.clear')"
                    :disabled="status === 'running'"
                    @click.stop="libraryDoc = null"
                  >
                    {{ t("translate.clear") }}
                  </button>
                </div>
                <div v-else class="library-empty">
                  <n-icon :size="26" :depth="3" :component="FolderOpenOutline" />
                  <div class="library-empty-text">
                    <n-text strong>{{ t("translate.pickFromLibrary") }}</n-text>
                    <n-text depth="3">{{ t("translate.pickFromLibraryHint") }}</n-text>
                  </div>
                </div>
              </div>
            </div>

            <div class="wf-divider" />

            <div class="wf-section">
              <div class="wf-section-head">
                <span class="wf-step-badge">2</span>
                <div class="wf-section-titles">
                  <span class="wf-section-title">{{ t("translate.translateConfig") }}</span>
                  <span class="wf-section-desc">{{ t("translate.translateConfigDesc") }}</span>
                </div>
              </div>

              <div class="config-grid">
                <section class="config-block">
                  <n-text class="block-label">{{ t("translate.langDirection") }}</n-text>
                  <div class="lang-row">
                    <div class="lang-field">
                      <n-text depth="3" class="field-label">{{ t("translate.langSource") }}</n-text>
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
                      :aria-label="t('translate.swapLangAria')"
                      :disabled="status === 'running'"
                      @click="swapLanguages"
                    >
                      <n-icon :size="19"><swap-horizontal-outline /></n-icon>
                    </button>
                    <div class="lang-field">
                      <n-text depth="3" class="field-label">{{ t("translate.langTarget") }}</n-text>
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
                  <n-text class="block-label">{{ t("translate.translateModel") }}</n-text>
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
                  <n-text class="block-label">{{ t("translate.glossaryOptional") }}</n-text>
                  <n-tag
                    size="tiny"
                    round
                    :type="glossarySupported ? 'success' : 'warning'"
                    :bordered="false"
                  >
                    {{ glossarySupported ? t("translate.glossarySupported") : t("translate.glossaryNeedModel") }}
                  </n-tag>
                </div>
                <file-drop-zone
                  accept=".csv"
                  multiple
                  compact
                  hide-button
                  :disabled="!glossarySupported || status === 'running'"
                  :title="t('translate.dropGlossaryTitle')"
                  :hint="t('translate.dropGlossaryHint')"
                  :file-name="glossaryFileLabel"
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
                {{ status === "running" || status === "submitting" ? t("translate.translating") : t("translate.startTranslate") }}
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
                  :size="19"
                  :component="status === 'done' ? CheckmarkCircleOutline : CloudDownloadOutline"
                />
                <span>{{ t("translate.progressAndResult") }}</span>
              </div>
            </template>

            <div class="result-body">
              <div v-if="!showProgressPanel" class="result-idle">
                <n-icon :size="29" :depth="3"><time-outline /></n-icon>
                <n-text depth="2">{{ t("translate.idleHint") }}</n-text>
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

              </template>

              <div class="dl-group">
                <n-text class="dl-group-label">{{ t("translate.translation") }}</n-text>
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
                      <n-icon :size="19" :component="DownloadOutline" />
                      <span class="dl-item-text">
                        <strong>{{ t("translate.dualPdf") }}</strong>
                        <small>{{ t("translate.dualPdfDesc") }}</small>
                      </span>
                    </button>
                    <n-button text size="tiny" :disabled="!resultsReady" @click="openPreview('dual')">
                      <template #icon>
                        <n-icon :component="EyeOutline" />
                      </template>
                      {{ t("translate.preview") }}
                    </n-button>
                  </div>
                  <div class="dl-item" :class="{ 'dl-item--disabled': !resultsReady }">
                    <button
                      type="button"
                      class="dl-item-main"
                      :disabled="!resultsReady"
                      @click="dl('mono', 'mono.pdf')"
                    >
                      <n-icon :size="19" :component="DownloadOutline" />
                      <span class="dl-item-text">
                        <strong>{{ t("translate.monoPdf") }}</strong>
                        <small>{{ t("translate.monoPdfDesc") }}</small>
                      </span>
                    </button>
                    <n-button text size="tiny" :disabled="!resultsReady" @click="openPreview('mono')">
                      <template #icon>
                        <n-icon :component="EyeOutline" />
                      </template>
                      {{ t("translate.preview") }}
                    </n-button>
                  </div>
                </div>
              </div>

              <div class="dl-group">
                <n-text class="dl-group-label">{{ t("translate.moreExports") }}</n-text>
                <n-space :size="7" wrap class="dl-chips">
                  <n-button
                    size="small"
                    secondary
                    :disabled="!resultsReady"
                    @click="dl('glossary', 'glossary.csv')"
                  >
                    {{ t("translate.glossary") }}
                  </n-button>
                  <n-button
                    size="small"
                    secondary
                    :disabled="!resultsReady"
                    @click="dl('extracted-json', 'extracted.json')"
                  >
                    JSON
                  </n-button>
                  <n-button
                    size="small"
                    secondary
                    :disabled="!resultsReady"
                    @click="dl('extracted-md', 'extracted.md')"
                  >
                    Markdown
                  </n-button>
                </n-space>
              </div>

              <div class="dl-group">
                <n-text class="dl-group-label">{{ t("translate.knowledgeBase") }}</n-text>
                <n-space :size="7" wrap align="center">
                  <template v-if="importedDocumentId">
                    <n-tag type="success" :bordered="false" size="small">{{ t("translate.imported") }}</n-tag>
                    <n-button size="small" type="primary" @click="openImportedDocument">
                      {{ t("translate.viewDocument") }}
                    </n-button>
                  </template>
                  <template v-else>
                    <n-button
                      size="small"
                      secondary
                      :disabled="!resultsReady"
                      :loading="importLoading"
                      @click="importToLibrary('mono')"
                    >
                      {{ t("translate.importMono") }}
                    </n-button>
                    <n-button
                      size="small"
                      secondary
                      :disabled="!resultsReady"
                      :loading="importLoading"
                      @click="importToLibrary('dual')"
                    >
                      {{ t("translate.importDual") }}
                    </n-button>
                  </template>
                </n-space>
                <n-text
                  v-if="showProgressPanel && !resultsReady"
                  depth="3"
                  class="dl-group-hint"
                >
                  {{ t("translate.resultHint") }}
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
      :title="t('translate.libraryModalTitle')"
      :subtitle="t('translate.libraryModalSubtitle')"
      width="min(560px, 92vw)"
    >
      <n-space align="center" :size="10" class="library-search">
        <n-input
          v-model:value="libraryKeyword"
          size="small"
          :placeholder="t('translate.searchTitlePlaceholder')"
          clearable
          @keyup.enter="libraryPage = 1; loadLibraryDocs()"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" />
          </template>
        </n-input>
        <n-button size="small" type="primary" @click="libraryPage = 1; loadLibraryDocs()">
          {{ t("common.search") }}
        </n-button>
        <ListRefreshButton :loading="libraryLoading" size="small" @click="loadLibraryDocs" />
      </n-space>
      <div class="admin-list-table">
        <n-data-table
          :columns="libraryColumns"
          :data="libraryItems"
          :loading="libraryLoading"
          :max-height="384"
          :pagination="false"
          size="small"
        />
        <ListTableFooter
          :page="libraryPage"
          :page-size="LIST_PAGE_SIZE"
          :item-count="libraryTotal"
          @update:page="onLibraryPageChange"
        />
      </div>
    </AdminFormModal>

    <DocumentVersionPreviewModal
      v-model:show="previewShow"
      :blob-loader="loadPreviewBlob"
      :preview-title="previewTitle"
      :preview-subtitle="displayFileName"
      :preview-file-name="previewFileName"
      :show-download-action="false"
      width="min(760px, 94vw)"
      viewport-height="min(45vh, 480px)"
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
  max-width: 1344px;
  margin: 0 auto;
  padding: 5px 0 29px;
  box-sizing: border-box;
}

.translate-steps-bar {
  flex-shrink: 0;
  margin-bottom: 19px;
  padding: 14px 19px;
  border-radius: var(--platform-radius-md, 14px);
  background: var(--platform-bg-elevated);
  border: 1px solid var(--platform-border);
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.translate-steps {
  max-width: 576px;
}

.page-alerts {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-bottom: 10px;
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
  gap: 19px;
  align-items: start;
}

@media (min-width: 880px) {
  .translate-layout {
    grid-template-columns: minmax(0, 1.15fr) minmax(336px, 0.85fr);
    gap: 24px;
  }

  .translate-aside {
    position: sticky;
    top: 10px;
  }
}

.workflow-card,
.result-card {
  border-radius: var(--platform-card-radius);
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
  padding: 17px 19px 19px;
}

.workflow-card :deep(.n-card-header) {
  padding: 12px 19px 0;
  min-height: 0;
}

.wf-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  max-width: 100%;
}

.wf-section-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.wf-step-badge {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--platform-font-size-base);
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
  font-size: var(--platform-font-size-lg);
  font-weight: var(--platform-font-weight-strong);
  color: var(--n-text-color);
  line-height: 1.3;
}

.wf-section-desc {
  font-size: var(--platform-font-size-base);
  color: var(--platform-muted);
  line-height: 1.35;
}

.wf-divider {
  height: 1px;
  margin: 17px 0;
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
  padding: 10px 12px;
  box-sizing: border-box;
  border-radius: var(--platform-radius-sm, 10px);
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto auto;
  align-items: center;
  gap: 1px 10px;
  text-align: left;
  overflow: hidden;
}

.upload-fill :deep(.drop-zone .drop-icon-wrap) {
  grid-row: 1 / 3;
  width: 29px;
  height: 29px;
  margin-bottom: 0;
}

.upload-fill :deep(.drop-zone .drop-icon-wrap .n-icon) {
  font-size: var(--platform-font-size-lg) !important;
}

.upload-fill :deep(.drop-zone .drop-title) {
  grid-column: 2;
  grid-row: 1;
  font-size: var(--platform-font-size-base);
  margin-bottom: 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-fill :deep(.drop-zone .drop-hint) {
  grid-column: 2;
  grid-row: 2;
  font-size: var(--platform-font-size-sm);
  line-height: 1.35;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.config-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

@media (min-width: 520px) {
  .config-grid {
    grid-template-columns: 1fr 1fr;
  }
}

.config-block {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.config-block--glossary {
  margin-top: 2px;
}

.config-block--glossary :deep(.drop-zone) {
  min-height: 86px;
  padding: 0.55rem 0.7rem;
}

.block-label {
  font-size: var(--platform-font-size-lg);
  font-weight: var(--platform-font-weight-medium);
  color: var(--n-text-color-2, var(--platform-text-secondary));
}

.block-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.lang-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.lang-field {
  flex: 1;
  min-width: 0;
}

.lang-swap-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  margin-bottom: 1px;
  border: 1px solid var(--platform-border);
  border-radius: 50%;
  background: var(--platform-bg);
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
  font-size: var(--platform-font-size-sm);
  margin-bottom: 5px;
}

.wf-actions {
  margin-top: 17px;
  padding-top: 14px;
  border-top: 1px solid var(--platform-divider, var(--platform-border));
}

.start-btn {
  width: 100%;
  font-weight: var(--platform-font-weight-strong);
  height: 43px;
}

.library-pick {
  width: 100%;
  min-width: 0;
  border-radius: var(--platform-radius-sm, 10px);
  border: 2px dashed var(--n-border-color);
  background: color-mix(in srgb, var(--platform-text) 2%, transparent);
  cursor: pointer;
  transition:
    border-color 0.2s,
    background 0.2s,
    box-shadow 0.2s;
}

.library-pick:hover:not(.library-pick--disabled) {
  border-color: var(--n-text-color-3);
  background: var(--n-action-color);
}

.library-pick--disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.library-empty {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  padding: 12px 14px;
  min-height: 0;
  text-align: left;
}

.library-empty-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.library-empty-text :deep(.n-text) {
  font-size: var(--platform-font-size-base);
  line-height: 1.35;
}

.library-pick:has(.library-selected) {
  border-style: solid;
  border-color: var(--platform-accent-border-soft);
  background: var(--platform-accent-soft);
}

.library-pick:has(.library-selected):not(.library-pick--disabled):hover {
  border-color: var(--platform-accent);
  background: color-mix(in srgb, var(--platform-accent) 12%, transparent);
}

.library-selected {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  min-width: 0;
}

.library-clear-btn {
  flex-shrink: 0;
  margin-left: auto;
  padding: 2px 10px;
  border: none;
  border-radius: var(--platform-radius-sm, 7px);
  background: transparent;
  color: var(--platform-muted);
  font: inherit;
  font-size: var(--platform-font-size-sm);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.library-clear-btn:hover:not(:disabled) {
  background: var(--platform-bg-tertiary);
  color: var(--platform-text);
}

.library-clear-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
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
  font-size: var(--platform-font-size-sm);
  margin-top: 2px;
}

.result-card :deep(.n-card-header) {
  padding: 12px 17px 7px;
  min-height: 0;
}

.result-card :deep(.n-card__content) {
  padding: 10px 17px 17px;
}

.result-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: var(--platform-font-size-lg);
  font-weight: var(--platform-font-weight-medium);
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
  gap: 7px;
  padding: 10px 5px 5px;
  text-align: center;
  font-size: var(--platform-font-size-base);
}

.result-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.status-strip {
  padding: 12px 14px;
  border-radius: var(--platform-radius-sm, 10px);
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
  gap: 10px;
  flex-wrap: wrap;
}

.status-pulse {
  width: 8px;
  height: 8px;
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
  font-size: var(--platform-font-size-base);
  margin-top: 7px;
  word-break: break-all;
  line-height: 1.4;
}

.status-meta {
  display: block;
  font-size: var(--platform-font-size-sm);
  margin-top: 4px;
}

.dl-group {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.dl-group-label {
  font-size: var(--platform-font-size-sm);
  font-weight: var(--platform-font-weight-normal);
  color: var(--platform-muted);
}

.dl-group-hint {
  font-size: var(--platform-font-size-sm);
  line-height: 1.4;
}

.dl-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.dl-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px 7px 12px;
  border-radius: var(--platform-radius-sm, 10px);
  border: 1px solid var(--platform-border);
  background: var(--platform-bg);
  transition:
    border-color 0.2s var(--platform-ease-smooth),
    background 0.2s var(--platform-ease-smooth),
    box-shadow 0.2s var(--platform-ease-smooth);
}

.dl-item:hover:not(.dl-item--disabled) {
  border-color: color-mix(in srgb, var(--platform-accent) 35%, transparent);
  background: color-mix(in srgb, var(--platform-accent) 8%, transparent);
  box-shadow: 0 2px 12px color-mix(in srgb, var(--platform-accent) 10%, transparent);
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
  gap: 10px;
  padding: 5px 2px;
  border: none;
  background: transparent;
  color: var(--platform-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 7px;
  transition: color 0.2s ease;
}

.dl-item-main:hover:not(:disabled) {
  color: var(--platform-accent);
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
  font-size: var(--platform-font-size-base);
  font-weight: var(--platform-font-weight-strong);
  line-height: 1.3;
}

.dl-item-text small {
  font-size: var(--platform-font-size-sm);
  color: var(--platform-muted);
  line-height: 1.3;
}

.library-search {
  display: flex;
  width: 100%;
  margin-bottom: 12px;
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
