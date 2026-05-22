<script setup>
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDivider,
  NGi,
  NGrid,
  NIcon,
  NInput,
  NModal,
  NProgress,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NStep,
  NSteps,
  NTag,
  NText,
  useMessage,
} from "naive-ui";
import {
  BookOutline,
  DownloadOutline,
  FolderOpenOutline,
  RocketOutline,
  ArrowBackOutline,
  SearchOutline,
  LanguageOutline,
  SwapHorizontalOutline,
  CheckmarkCircleOutline,
  TimeOutline,
} from "@vicons/ionicons5";
import FileDropZone from "../components/FileDropZone.vue";
import {
  createTranslateJob,
  downloadTranslateFile,
  fetchTranslateDocuments,
  fetchTranslateJob,
  fetchTranslateMeta,
  subscribeTranslateEvents,
} from "../api/client";

const route = useRoute();
const router = useRouter();
const message = useMessage();

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
  extracted_md: null,
});
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
    label: `${l.label} (${l.code})`,
    value: l.code,
  }))
);
const engineOptions = computed(() =>
  (meta.value?.engines || []).map((e) => ({
    label: e.supports_glossary ? `${e.id} · 支持术语表` : e.id,
    value: e.id,
  }))
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
    error: "失败",
  };
  return map[status.value] || status.value;
});
const showProgressPanel = computed(() => status.value !== "idle");

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
          glossary: r.auto_extracted_glossary_path ?? files.value.glossary,
        };
      }
      if (ev.type === "error") {
        error.value = ev.error || "翻译失败";
        status.value = "error";
        stopPoll();
      }
    },
    onError() {
      /* 离开页面或网络中断时依赖轮询 */
    },
    async onComplete(data) {
      status.value = data.status === "done" ? "done" : data.status;
      if (data.error) error.value = data.error;
      if (data.files) files.value = { ...files.value, ...data.files };
      progress.value = 100;
      await refreshJob();
      stopPoll();
    },
  });
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
      startPoll();
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
    message.info("翻译将在后台继续，可在任务中心或消息中查看结果", { duration: 5000 });
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
    },
  },
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
          onClick: () => selectLibraryDoc(row),
        },
        () => "选择"
      ),
  },
];

async function loadLibraryDocs() {
  libraryLoading.value = true;
  try {
    const data = await fetchTranslateDocuments({
      page: libraryPage.value,
      keyword: libraryKeyword.value || undefined,
    });
    libraryItems.value = data.items;
    libraryTotal.value = data.total;
  } catch (e) {
    message.error(e.message);
  } finally {
    libraryLoading.value = false;
  }
}

function openLibraryPicker() {
  showLibraryModal.value = true;
  libraryPage.value = 1;
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

async function startTranslation() {
  if (!hasPdfSource.value) return;
  if (glossaryFiles.value.length && !glossarySupported.value) {
    error.value = "当前引擎不支持术语表";
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
    extracted_md: null,
  };
  if (closeEvents) closeEvents();

  try {
    const job = await createTranslateJob({
      pdf: sourceMode.value === "upload" ? pdfFile.value : null,
      documentId: sourceMode.value === "library" ? libraryDoc.value?.id : null,
      langIn: langIn.value,
      langOut: langOut.value,
      service: service.value,
      glossaries: glossaryFiles.value,
    });
    applyJob(job);
    message.success(job.message || "已提交，后台翻译中");
    status.value = "running";
    router.replace({ query: { job: job.platform_job_id } });
    subscribeLive(job.platform_job_id);
    startPoll();
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
</script>

<template>
  <div class="translate-page">
    <header class="page-header">
      <n-space align="center" :size="12" class="header-main">
        <n-button quaternary @click="router.push({ name: 'system-functions' })">
          <template #icon>
            <n-icon :component="ArrowBackOutline" />
          </template>
          返回
        </n-button>
        <div class="title-icon">
          <n-icon :size="20" :component="LanguageOutline" />
        </div>
        <n-text strong class="page-title">PDF 翻译</n-text>
        <n-tag v-if="platformJobId" size="small" round>
          任务 {{ platformJobId.slice(0, 8) }}…
        </n-tag>
      </n-space>
      <n-steps :current="currentStep" size="small" class="header-steps">
        <n-step title="文档" />
        <n-step title="配置" />
        <n-step title="结果" />
      </n-steps>
    </header>

    <n-alert
      v-if="status === 'running'"
      type="info"
      class="page-alert"
      closable
    >
      翻译在后台进行，可切换其他页面；完成后在消息或任务中心查看。
    </n-alert>

    <n-alert
      v-if="error"
      type="error"
      :title="error"
      closable
      class="page-alert"
      @close="error = ''"
    />

    <n-grid
      cols="1 m:2 xl:3"
      responsive="screen"
      item-responsive
      :x-gap="20"
      :y-gap="20"
      class="translate-grid"
    >
      <n-gi span="1 m:1 xl:1">
        <n-card class="panel panel-fill" size="small" title="选择文档">
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

          <file-drop-zone
            v-if="sourceMode === 'upload'"
            accept=".pdf"
            title="拖拽 PDF 到此处"
            hint="或点击选择文件"
            :file-name="displayFileName"
            icon="doc"
            compact
            :disabled="status === 'running'"
            @change="onPdfChange"
          />

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
            <n-space :size="8">
              <n-button
                type="primary"
                secondary
                :disabled="status === 'running'"
                @click="openLibraryPicker"
              >
                <template #icon>
                  <n-icon :component="FolderOpenOutline" />
                </template>
                {{ libraryDoc ? "更换文档" : "从文档库选择" }}
              </n-button>
              <n-button
                v-if="libraryDoc"
                quaternary
                :disabled="status === 'running'"
                @click="libraryDoc = null"
              >
                清除
              </n-button>
            </n-space>
          </div>
        </n-card>
      </n-gi>

      <n-gi span="1 m:1 xl:1">
        <n-card class="panel panel-fill" size="small" title="翻译配置">
          <div class="lang-row">
            <div class="lang-field">
              <n-text depth="3" class="field-label">源语言</n-text>
              <n-select
                v-model:value="langIn"
                :options="langOptions"
                filterable
                :disabled="status === 'running'"
              />
            </div>
            <div class="lang-swap" aria-hidden="true">
              <n-icon :size="16" :depth="3"><swap-horizontal-outline /></n-icon>
            </div>
            <div class="lang-field">
              <n-text depth="3" class="field-label">目标语言</n-text>
              <n-select
                v-model:value="langOut"
                :options="langOptions"
                filterable
                :disabled="status === 'running'"
              />
            </div>
          </div>

          <n-text depth="3" class="field-label">翻译引擎</n-text>
          <n-select
            v-model:value="service"
            :options="engineOptions"
            :disabled="status === 'running'"
          />

          <n-divider class="section-divider" />

          <n-text depth="3" class="field-label">
            术语表
            <n-text v-if="glossarySupported" depth="3" tag="span" class="glossary-badge">
              · 当前引擎可用
            </n-text>
            <n-text v-else depth="3" tag="span" class="glossary-badge warn">
              · 需 LLM 引擎
            </n-text>
          </n-text>
          <file-drop-zone
            accept=".csv"
            multiple
            compact
            :disabled="!glossarySupported || status === 'running'"
            title="上传 CSV（可选）"
            hint="表头 source,target,tgt_lng"
            :file-name="
              glossaryFiles.length
                ? `已选 ${glossaryFiles.length} 个文件`
                : ''
            "
            @change="onGlossaryChange"
          />

          <n-button
            type="primary"
            size="large"
            block
            class="start-btn"
            :disabled="!canStart"
            :loading="status === 'running' || status === 'submitting'"
            :render-icon="renderIcon(RocketOutline)"
            @click="startTranslation"
          >
            {{ status === "running" || status === "submitting" ? "翻译进行中…" : "开始翻译" }}
          </n-button>
          <n-text v-if="!hasPdfSource" depth="3" class="start-hint">
            请先选择 PDF
          </n-text>
        </n-card>
      </n-gi>

      <n-gi span="1 m:2 xl:1">
        <n-card
          class="panel panel-fill panel-side"
          size="small"
          title="进度与下载"
          :class="{ 'panel-side-active': showProgressPanel }"
        >
          <div v-if="!showProgressPanel" class="side-idle">
            <n-icon :size="32" :depth="3"><time-outline /></n-icon>
            <n-text depth="2">提交翻译后在此查看进度与下载</n-text>
          </div>

          <n-space v-else vertical :size="14" class="side-body">
            <div class="status-row">
              <n-tag :type="statusType" round>{{ statusLabel }}</n-tag>
              <n-text v-if="displayFileName" depth="3" class="status-file">
                {{ displayFileName }}
              </n-text>
            </div>

            <n-progress
              v-if="status === 'running' || status === 'done'"
              type="line"
              :percentage="Math.round(progress)"
              indicator-placement="inside"
              :processing="status === 'running'"
              :status="status === 'done' ? 'success' : 'default'"
              :height="22"
            />
            <n-text v-if="stage" depth="2" class="stage-text">{{ stage }}</n-text>

            <template v-if="status === 'done'">
              <n-divider class="section-divider" />
              <div class="download-row">
                <n-button
                  type="primary"
                  :render-icon="renderIcon(DownloadOutline)"
                  @click="dl('mono', 'mono.pdf')"
                >
                  单语 PDF
                </n-button>
                <n-button
                  secondary
                  :render-icon="renderIcon(DownloadOutline)"
                  @click="dl('dual', 'dual.pdf')"
                >
                  双语 PDF
                </n-button>
                <n-button
                  quaternary
                  :render-icon="renderIcon(BookOutline)"
                  @click="dl('glossary', 'glossary.csv')"
                >
                  术语表
                </n-button>
              </div>
              <div class="download-row download-row-secondary">
                <n-button
                  ghost
                  :render-icon="renderIcon(DownloadOutline)"
                  @click="dl('extracted-json', 'extracted.json')"
                >
                  JSON
                </n-button>
                <n-button
                  ghost
                  :render-icon="renderIcon(DownloadOutline)"
                  @click="dl('extracted-md', 'extracted.md')"
                >
                  Markdown
                </n-button>
              </div>
            </template>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>

    <n-modal
      v-model:show="showLibraryModal"
      preset="card"
      title="选择文档库 PDF"
      style="width: min(720px, 92vw)"
    >
      <n-space align="center" :size="10" style="margin-bottom: 12px">
        <n-input
          v-model:value="libraryKeyword"
          placeholder="搜索文档标题"
          clearable
          style="flex: 1"
          @keyup.enter="libraryPage = 1; loadLibraryDocs()"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" />
          </template>
        </n-input>
        <n-button type="primary" @click="libraryPage = 1; loadLibraryDocs()">搜索</n-button>
      </n-space>
      <n-data-table
        :columns="libraryColumns"
        :data="libraryItems"
        :loading="libraryLoading"
        :pagination="{
          page: libraryPage,
          pageSize: 20,
          itemCount: libraryTotal,
          onUpdatePage: onLibraryPageChange,
        }"
        size="small"
      />
    </n-modal>
  </div>
</template>

<style scoped>
.translate-page {
  width: 100%;
  max-width: none;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--n-divider-color);
}
.header-main {
  flex-shrink: 0;
}
.header-steps {
  flex: 1;
  min-width: 280px;
  max-width: 480px;
}
.title-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #eef2ff 0%, #e8f4f8 100%);
  color: #4a5fc1;
}
.page-title {
  font-size: 1.125rem;
}
.page-alert {
  margin-bottom: 16px;
}
.translate-grid {
  width: 100%;
}
.panel {
  border-radius: 10px;
  height: 100%;
}
.panel-fill :deep(.n-card__content) {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.panel-side {
  position: sticky;
  top: 16px;
}
.panel-side-active {
  border-color: rgba(91, 141, 239, 0.22);
}
.source-toggle {
  margin-bottom: 4px;
}
.section-divider {
  margin: 4px 0 !important;
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
.lang-swap {
  flex-shrink: 0;
  padding-bottom: 8px;
}
.field-label {
  display: block;
  font-size: 12px;
  margin-bottom: 6px;
}
.glossary-badge {
  font-weight: normal;
  margin-left: 4px;
}
.glossary-badge.warn {
  color: var(--n-warning-color);
}
.start-btn {
  margin-top: 4px;
  font-weight: 600;
}
.start-hint {
  display: block;
  text-align: center;
  font-size: 12px;
}
.library-pick {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}
.library-selected {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(24, 160, 88, 0.28);
  background: rgba(24, 160, 88, 0.04);
}
.library-selected-icon {
  color: #18a058;
  flex-shrink: 0;
}
.library-selected-body {
  min-width: 0;
  flex: 1;
}
.library-file-name {
  display: block;
  font-size: 12px;
  margin-top: 2px;
}
.side-idle {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 160px;
  text-align: center;
  font-size: 13px;
}
.side-body {
  width: 100%;
}
.status-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.status-file {
  font-size: 12px;
  word-break: break-all;
}
.stage-text {
  font-size: 13px;
}
.download-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.download-row-secondary {
  opacity: 0.95;
}
@media (max-width: 1279px) {
  .panel-side {
    position: static;
  }
  .header-steps {
    width: 100%;
    max-width: none;
  }
}
</style>
