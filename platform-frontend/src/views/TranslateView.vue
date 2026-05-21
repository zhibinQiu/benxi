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
  if (status.value === "done") return 4;
  if (["running", "submitting"].includes(status.value)) return 4;
  if (hasPdfSource.value && glossaryFiles.value.length) return 3;
  if (hasPdfSource.value) return 2;
  return 1;
});
const hasExtractedExport = computed(
  () => !!(files.value.extracted_json || files.value.extracted_md)
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
    <n-space align="center" justify="space-between" style="margin-bottom: 16px">
      <n-button quaternary @click="router.push({ name: 'system-functions' })">
        <template #icon>
          <n-icon :component="ArrowBackOutline" />
        </template>
        返回系统功能
      </n-button>
      <n-tag v-if="platformJobId" size="small" round>任务 {{ platformJobId.slice(0, 8) }}…</n-tag>
    </n-space>

    <n-alert
      v-if="status === 'running'"
      type="info"
      title="后台翻译中"
      style="margin-bottom: 16px"
      closable
    >
      可切换至其他菜单，翻译不会中断。完成后将通过消息通知，或在「任务中心」查看。
    </n-alert>

    <n-alert v-if="error" type="error" :title="error" closable style="margin-bottom: 16px" @close="error = ''" />

    <n-steps :current="currentStep" size="small" style="margin-bottom: 20px">
      <n-step title="文档" description="上传或文档库" />
      <n-step title="术语表" description="可选" />
      <n-step title="翻译" description="语言与引擎" />
      <n-step title="结果" description="下载" />
    </n-steps>

    <n-grid :cols="1" :y-gap="16" style="max-width: 880px">
      <n-gi>
        <n-card title="选择文档" :bordered="false" class="panel">
          <template #header-extra><n-tag size="small" round>必填</n-tag></template>
          <n-radio-group
            v-model:value="sourceMode"
            size="small"
            style="margin-bottom: 14px"
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
            hint="或点击选择 · 支持学术论文与扫描件"
            :file-name="displayFileName"
            icon="doc"
            :disabled="status === 'running'"
            @change="onPdfChange"
          />

          <div v-else class="library-pick">
            <n-text v-if="libraryDoc" depth="2" style="display: block; margin-bottom: 10px">
              已选：{{ libraryDoc.title }}
              <n-text depth="3">（{{ libraryDoc.file_name }}）</n-text>
            </n-text>
            <n-text v-else depth="3" style="display: block; margin-bottom: 10px">
              仅显示您有权限使用且已上传 PDF 的文档
            </n-text>
            <n-space>
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

        <n-modal
          v-model:show="showLibraryModal"
          preset="card"
          title="选择文档库 PDF"
          style="width: min(720px, 92vw)"
        >
          <n-space vertical :size="12">
            <n-input
              v-model:value="libraryKeyword"
              placeholder="搜索文档标题"
              clearable
              @keyup.enter="libraryPage = 1; loadLibraryDocs()"
            >
              <template #prefix>
                <n-icon :component="SearchOutline" />
              </template>
            </n-input>
            <n-button size="small" @click="libraryPage = 1; loadLibraryDocs()">搜索</n-button>
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
          </n-space>
        </n-modal>
      </n-gi>

      <n-gi>
        <n-card :bordered="false" class="panel panel-glossary">
          <template #header>
            <n-space align="center" :size="8">
              <n-icon :size="18" :depth="2"><book-outline /></n-icon>
              <span>术语表</span>
              <n-tag size="small" type="primary" round>推荐</n-tag>
            </n-space>
          </template>
          <template #header-extra>
            <n-tag v-if="glossarySupported" size="small" type="success" round>当前引擎可用</n-tag>
            <n-tag v-else size="small" type="warning" round>需 LLM 引擎</n-tag>
          </template>
          <n-text depth="3" class="glossary-desc">
            CSV 表头：<code>source,target,tgt_lng</code> · 目标语言需与下方一致
          </n-text>
          <file-drop-zone
            accept=".csv"
            multiple
            :disabled="!glossarySupported || status === 'running'"
            title="上传术语表 CSV"
            hint="支持多文件"
            :file-name="
              glossaryFiles.length
                ? `已选 ${glossaryFiles.length} 个：${glossaryFiles.map((f) => f.name).join('、')}`
                : ''
            "
            @change="onGlossaryChange"
          />
        </n-card>
      </n-gi>

      <n-gi>
        <n-card title="翻译设置" :bordered="false" class="panel">
          <n-grid :cols="2" :x-gap="16" :y-gap="16">
            <n-gi>
              <n-text depth="2" class="field-label">源语言</n-text>
              <n-select v-model:value="langIn" :options="langOptions" filterable />
            </n-gi>
            <n-gi>
              <n-text depth="2" class="field-label">目标语言</n-text>
              <n-select v-model:value="langOut" :options="langOptions" filterable />
            </n-gi>
            <n-gi :span="2">
              <n-text depth="2" class="field-label">翻译引擎</n-text>
              <n-select v-model:value="service" :options="engineOptions" />
            </n-gi>
          </n-grid>
          <n-divider />
          <n-button
            type="primary"
            size="large"
            block
            :disabled="!canStart"
            :loading="status === 'running' || status === 'submitting'"
            :render-icon="renderIcon(RocketOutline)"
            @click="startTranslation"
          >
            {{ status === "running" || status === "submitting" ? "翻译进行中…" : "开始翻译" }}
          </n-button>
        </n-card>
      </n-gi>

      <n-gi v-if="status !== 'idle'">
        <n-card title="进度与下载" :bordered="false" class="panel">
          <n-space vertical :size="14">
            <n-tag :type="statusType" round size="small">{{ status }}</n-tag>
            <n-progress
              v-if="status === 'running' || status === 'done'"
              type="line"
              :percentage="Math.round(progress)"
              indicator-placement="inside"
              processing
              :height="22"
            />
            <n-text v-if="stage" depth="2" style="font-size: 0.85rem">{{ stage }}</n-text>

            <template v-if="status === 'done'">
              <n-space wrap>
                <n-button secondary :render-icon="renderIcon(DownloadOutline)" @click="dl('mono', 'mono.pdf')">
                  单语 PDF
                </n-button>
                <n-button secondary :render-icon="renderIcon(DownloadOutline)" @click="dl('dual', 'dual.pdf')">
                  双语 PDF
                </n-button>
                <n-button quaternary :render-icon="renderIcon(BookOutline)" @click="dl('glossary', 'glossary.csv')">
                  术语表
                </n-button>
              </n-space>
              <n-divider />
              <n-text depth="2" class="export-section-title">导出提取内容</n-text>
              <n-space wrap>
                <n-button type="primary" ghost :render-icon="renderIcon(DownloadOutline)" @click="dl('extracted-json', 'extracted.json')">
                  JSON
                </n-button>
                <n-button ghost :render-icon="renderIcon(DownloadOutline)" @click="dl('extracted-md', 'extracted.md')">
                  Markdown
                </n-button>
              </n-space>
            </template>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>
  </div>
</template>

<style scoped>
.panel {
  border-radius: 8px;
}
.panel-glossary {
  border: 1px solid var(--n-border-color);
}
.glossary-desc {
  display: block;
  font-size: 0.82rem;
  margin-bottom: 1rem;
}
.glossary-desc code {
  font-size: 12px;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  background: var(--n-action-color);
}
.field-label {
  display: block;
  font-size: 0.78rem;
  font-weight: 600;
  margin-bottom: 0.4rem;
}
.export-section-title {
  font-size: 0.82rem;
  font-weight: 600;
}
.library-pick {
  padding: 4px 0;
}
</style>
