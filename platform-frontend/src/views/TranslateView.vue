<script setup>
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
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
  SearchOutline,
  LanguageOutline,
  SwapHorizontalOutline,
  CheckmarkCircleOutline,
  TimeOutline,
  DocumentTextOutline,
  SettingsOutline,
  CloudDownloadOutline,
} from "@vicons/ionicons5";
import FileDropZone from "../components/FileDropZone.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
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
  auto: "自动检测",
};

const langOptions = computed(() =>
  (meta.value?.languages || []).map((l) => ({
    label: LANG_LABEL_ZH[l.code] || l.label,
    value: l.code,
  }))
);
const engineOptions = computed(() =>
  (meta.value?.engines || []).map((e) => ({
    label: e.label || e.model || e.id,
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
    message.info("翻译将在后台继续，可在后台任务或消息中查看结果", { duration: 5000 });
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
  <FeatureSubsystemShell fill>
    <template #extra>
      <n-tag v-if="platformJobId" size="small" round type="info" :bordered="false">
        任务 {{ platformJobId.slice(0, 8) }}…
      </n-tag>
    </template>

    <header class="translate-steps-bar">
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
      <n-grid
        cols="1 m:2 xl:3"
        responsive="screen"
        item-responsive
        :x-gap="20"
        :y-gap="20"
        class="translate-grid"
      >
        <n-gi span="1 m:1 xl:1">
          <n-card class="panel panel-fill" size="small" :bordered="false">
            <template #header>
              <div class="panel-header">
                <span class="panel-header-icon panel-header-icon--doc">
                  <n-icon :size="18" :component="DocumentTextOutline" />
                </span>
                <div class="panel-header-text">
                  <span class="panel-header-title">选择文档</span>
                  <span class="panel-header-desc">本地上传或从文档库选取 PDF</span>
                </div>
              </div>
            </template>

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
                title="拖拽 PDF 到此处"
                hint="支持标准 PDF，建议单文件不超过平台限制"
                :file-name="displayFileName"
                icon="doc"
                :disabled="status === 'running'"
                @change="onPdfChange"
              />
            </div>

            <div v-else class="library-pick">
              <div v-if="libraryDoc" class="library-selected">
                <n-icon :size="20" class="library-selected-icon">
                  <checkmark-circle-outline />
                </n-icon>
                <div class="library-selected-body">
                  <n-text strong>{{ libraryDoc.title }}</n-text>
                  <n-text depth="3" class="library-file-name">{{ libraryDoc.file_name }}</n-text>
                </div>
              </div>
              <div v-else class="library-empty">
                <n-icon :size="28" :depth="3" :component="FolderOpenOutline" />
                <n-text depth="2">从文档库选择已上传的 PDF</n-text>
              </div>
              <n-space :size="8" class="library-actions">
                <n-button
                  type="primary"
                  :disabled="status === 'running'"
                  @click="openLibraryPicker"
                >
                  <template #icon>
                    <n-icon :component="FolderOpenOutline" />
                  </template>
                  {{ libraryDoc ? "更换文档" : "浏览文档库" }}
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
          <n-card class="panel panel-fill panel-config" size="small" :bordered="false">
            <template #header>
              <div class="panel-header">
                <span class="panel-header-icon panel-header-icon--config">
                  <n-icon :size="18" :component="SettingsOutline" />
                </span>
                <div class="panel-header-text">
                  <span class="panel-header-title">翻译配置</span>
                  <span class="panel-header-desc">语言方向、模型与可选术语表</span>
                </div>
              </div>
            </template>

            <section class="config-block">
              <n-text class="block-label">语言方向</n-text>
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
                <button
                  type="button"
                  class="lang-swap-btn"
                  aria-label="语言方向"
                  :disabled="status === 'running'"
                >
                  <n-icon :size="18"><swap-horizontal-outline /></n-icon>
                </button>
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
              <n-tag size="small" :bordered="false" class="lang-pair-tag">
                {{ langPairLabel }}
              </n-tag>
            </section>

            <section class="config-block">
              <n-text class="block-label">翻译模型</n-text>
              <n-select
                v-model:value="service"
                :options="engineOptions"
                :disabled="status === 'running'"
              />
              <n-text v-if="engineLabel" depth="3" class="engine-hint">{{ engineLabel }}</n-text>
            </section>

            <section class="config-block config-block--glossary">
              <div class="block-label-row">
                <n-text class="block-label">术语表（可选）</n-text>
                <n-tag
                  size="tiny"
                  round
                  :type="glossarySupported ? 'success' : 'warning'"
                  :bordered="false"
                >
                  {{ glossarySupported ? "当前模型支持" : "需支持术语表的模型" }}
                </n-tag>
              </div>
              <file-drop-zone
                accept=".csv"
                multiple
                compact
                :disabled="!glossarySupported || status === 'running'"
                title="上传 CSV 术语表"
                hint="表头：source, target, tgt_lng"
                :file-name="
                  glossaryFiles.length
                    ? `已选 ${glossaryFiles.length} 个文件`
                    : ''
                "
                @change="onGlossaryChange"
              />
            </section>

            <div class="start-wrap">
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
                请先在左侧选择或上传 PDF
              </n-text>
            </div>
          </n-card>
        </n-gi>

        <n-gi span="1 m:2 xl:1">
          <n-card
            class="panel panel-fill panel-side"
            size="small"
            :bordered="false"
            :class="{
              'panel-side-active': showProgressPanel,
              'panel-side-done': status === 'done',
            }"
          >
            <template #header>
              <div class="panel-header">
                <span
                  class="panel-header-icon"
                  :class="status === 'done' ? 'panel-header-icon--done' : 'panel-header-icon--result'"
                >
                  <n-icon
                    :size="18"
                    :component="status === 'done' ? CheckmarkCircleOutline : CloudDownloadOutline"
                  />
                </span>
                <div class="panel-header-text">
                  <span class="panel-header-title">进度与下载</span>
                  <span class="panel-header-desc">
                    {{ status === "done" ? "翻译已完成，可下载成果文件" : "提交后在此查看状态" }}
                  </span>
                </div>
              </div>
            </template>

            <div v-if="!showProgressPanel" class="side-idle">
              <div class="side-idle-visual">
                <n-icon :size="36" :depth="3"><time-outline /></n-icon>
              </div>
              <n-text strong class="side-idle-title">等待开始翻译</n-text>
              <n-text depth="3" class="side-idle-desc">
                配置语言与模型后点击「开始翻译」，进度与下载链接将显示在此处
              </n-text>
            </div>

            <div v-else class="side-body">
              <div class="status-card" :class="`status-card--${status}`">
                <div class="status-row">
                  <n-tag :type="statusType" round size="medium">{{ statusLabel }}</n-tag>
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
                  <n-text depth="3">整体进度</n-text>
                  <n-text strong class="progress-pct">{{ Math.round(progress) }}%</n-text>
                </div>
                <n-progress
                  type="line"
                  :percentage="Math.round(progress)"
                  indicator-placement="inside"
                  :processing="status === 'running'"
                  :status="status === 'done' ? 'success' : 'default'"
                  :height="10"
                  :border-radius="6"
                />
                <n-text v-if="stage" depth="2" class="stage-text">{{ stage }}</n-text>
              </div>

              <template v-if="status === 'done'">
                <n-text class="download-section-label">下载译文</n-text>
                <div class="download-grid">
                  <button
                    type="button"
                    class="download-card download-card--primary"
                    @click="dl('dual', 'dual.pdf')"
                  >
                    <span class="download-card-icon">
                      <n-icon :size="22" :component="DownloadOutline" />
                    </span>
                    <span class="download-card-body">
                      <strong>双语 PDF</strong>
                      <span>左原文 · 右译文对照</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    class="download-card"
                    @click="dl('mono', 'mono.pdf')"
                  >
                    <span class="download-card-icon">
                      <n-icon :size="22" :component="DownloadOutline" />
                    </span>
                    <span class="download-card-body">
                      <strong>单语 PDF</strong>
                      <span>仅保留译文排版</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    class="download-card"
                    @click="dl('glossary', 'glossary.csv')"
                  >
                    <span class="download-card-icon download-card-icon--muted">
                      <n-icon :size="22" :component="BookOutline" />
                    </span>
                    <span class="download-card-body">
                      <strong>术语表</strong>
                      <span>自动提取的 CSV</span>
                    </span>
                  </button>
                </div>
                <n-text class="download-section-label download-section-label--sub">
                  结构化导出
                </n-text>
                <div class="download-chips">
                  <n-button
                    size="small"
                    round
                    secondary
                    @click="dl('extracted-json', 'extracted.json')"
                  >
                    JSON
                  </n-button>
                  <n-button
                    size="small"
                    round
                    secondary
                    @click="dl('extracted-md', 'extracted.md')"
                  >
                    Markdown
                  </n-button>
                </div>
              </template>
            </div>
          </n-card>
        </n-gi>
      </n-grid>
    </div>

    <n-modal
      v-model:show="showLibraryModal"
      preset="card"
      title="选择文档库 PDF"
      class="library-modal"
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
  </FeatureSubsystemShell>
</template>

<style scoped>
.translate-steps-bar {
  flex-shrink: 0;
  margin-bottom: 8px;
}

.translate-steps {
  max-width: 520px;
}

.page-alerts {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.page-alert {
  margin: 0;
}

.translate-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  max-width: none;
  --translate-accent: #3b82f6;
  --translate-accent-soft: rgba(59, 130, 246, 0.08);
  --translate-success-soft: rgba(24, 160, 88, 0.08);
}

.translate-grid {
  width: 100%;
  flex: 1;
  min-height: 0;
}

.translate-grid :deep(> div) {
  height: 100%;
}

.translate-grid :deep(.n-grid-item) {
  display: flex;
  min-height: 0;
}

.panel {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  overflow: hidden;
}

.panel :deep(.n-card-header) {
  padding: 14px 18px 10px;
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.06));
}

.panel :deep(.n-card__content) {
  padding: 14px 18px 18px;
}

.panel-fill :deep(.n-card__content) {
  display: flex;
  flex-direction: column;
  gap: 14px;
  flex: 1;
  min-height: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.panel-header-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.panel-header-icon--doc {
  color: #0d9488;
  background: rgba(13, 148, 136, 0.1);
}

.panel-header-icon--config {
  color: var(--translate-accent);
  background: var(--translate-accent-soft);
}

.panel-header-icon--result {
  color: #6366f1;
  background: rgba(99, 102, 241, 0.1);
}

.panel-header-icon--done {
  color: #18a058;
  background: var(--translate-success-soft);
}

.panel-header-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.panel-header-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--n-text-color);
  line-height: 1.3;
}

.panel-header-desc {
  font-size: 12px;
  color: var(--platform-muted, #64748b);
  line-height: 1.4;
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
  flex: 1;
  min-height: 200px;
  display: flex;
}

.upload-fill :deep(.drop-zone) {
  flex: 1;
  width: 100%;
  min-height: 200px;
  border-radius: 12px;
}

.config-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-block--glossary {
  margin-top: 2px;
}

.block-label {
  font-size: 13px;
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
  margin-bottom: 2px;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.1));
  border-radius: 50%;
  background: var(--n-color);
  color: var(--platform-muted, #64748b);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: default;
  transition: background 0.2s, border-color 0.2s;
}

.lang-pair-tag {
  align-self: flex-start;
  font-size: 12px;
  background: var(--translate-accent-soft) !important;
  color: var(--translate-accent) !important;
}

.field-label {
  display: block;
  font-size: 12px;
  margin-bottom: 6px;
}

.engine-hint {
  font-size: 12px;
  margin-top: -2px;
}

.start-wrap {
  margin-top: auto;
  padding-top: 8px;
}

.start-btn {
  font-weight: 600;
  height: 44px;
  border-radius: 10px;
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.28);
}

.start-btn:not(:disabled):hover {
  box-shadow: 0 6px 18px rgba(59, 130, 246, 0.34);
}

.start-hint {
  display: block;
  text-align: center;
  font-size: 12px;
  margin-top: 8px;
}

.library-pick {
  display: flex;
  flex-direction: column;
  gap: 14px;
  flex: 1;
  min-height: 200px;
}

.library-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px 16px;
  border-radius: 12px;
  border: 1.5px dashed var(--n-border-color);
  background: rgba(15, 23, 42, 0.02);
  text-align: center;
  font-size: 13px;
}

.library-selected {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(24, 160, 88, 0.3);
  background: var(--translate-success-soft);
}

.library-selected-icon {
  color: #18a058;
  flex-shrink: 0;
  margin-top: 1px;
}

.library-selected-body {
  min-width: 0;
  flex: 1;
}

.library-file-name {
  display: block;
  font-size: 12px;
  margin-top: 4px;
}

.library-actions {
  margin-top: auto;
}

.panel-side-active {
  border-color: rgba(59, 130, 246, 0.28);
  box-shadow:
    var(--platform-shadow),
    0 0 0 1px rgba(59, 130, 246, 0.08);
}

.panel-side-done {
  border-color: rgba(24, 160, 88, 0.28);
}

.side-idle {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 260px;
  text-align: center;
  padding: 16px;
}

.side-idle-visual {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 4px;
  background: rgba(15, 23, 42, 0.04);
}

.side-idle-title {
  font-size: 15px;
}

.side-idle-desc {
  font-size: 13px;
  line-height: 1.55;
  max-width: 260px;
}

.side-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  flex: 1;
}

.status-card {
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.03);
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.06));
}

.status-card--done {
  background: var(--translate-success-soft);
  border-color: rgba(24, 160, 88, 0.22);
}

.status-card--running {
  background: var(--translate-accent-soft);
  border-color: rgba(59, 130, 246, 0.18);
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
  background: var(--translate-accent);
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
  font-size: 13px;
  margin-top: 8px;
  word-break: break-all;
  line-height: 1.45;
}

.status-meta {
  display: block;
  font-size: 12px;
  margin-top: 4px;
}

.progress-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
}

.progress-pct {
  font-size: 14px;
  color: var(--translate-accent);
}

.stage-text {
  font-size: 13px;
  line-height: 1.5;
}

.download-section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--platform-muted, #64748b);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.download-section-label--sub {
  margin-top: 4px;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
}

.download-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.download-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.1));
  background: var(--n-color);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s,
    background 0.2s,
    transform 0.15s,
    box-shadow 0.2s;
}

.download-card:hover {
  border-color: rgba(59, 130, 246, 0.35);
  background: var(--translate-accent-soft);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
}

.download-card:active {
  transform: scale(0.99);
}

.download-card--primary {
  border-color: rgba(59, 130, 246, 0.35);
  background: linear-gradient(
    135deg,
    rgba(59, 130, 246, 0.1) 0%,
    rgba(59, 130, 246, 0.04) 100%
  );
}

.download-card--primary:hover {
  border-color: rgba(59, 130, 246, 0.5);
}

.download-card-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--translate-accent);
  background: var(--translate-accent-soft);
}

.download-card-icon--muted {
  color: var(--platform-muted, #64748b);
  background: rgba(15, 23, 42, 0.05);
}

.download-card-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.download-card-body strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--n-text-color);
}

.download-card-body span {
  font-size: 12px;
  color: var(--platform-muted, #64748b);
}

.download-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 1279px) {
  .translate-workspace {
    overflow-y: auto;
  }

  .translate-grid {
    flex: none;
    min-height: min(72vh, 760px);
  }

  .translate-steps {
    max-width: none;
    width: 100%;
  }
}

@media (max-width: 639px) {
  .lang-swap-btn {
    display: none;
  }
}
</style>
