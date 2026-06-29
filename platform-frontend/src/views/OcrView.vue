<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { useI18n } from "../composables/useI18n.js";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NIcon,
  NInput,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText,
} from "naive-ui";
import {
  CopyOutline,
  DownloadOutline,
  DocumentTextOutline,
  ImageOutline,
  ScanOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import FileDropZone from "../components/FileDropZone.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  downloadOcrExportZip,
  fetchOcrMeta,
  recognizeOcr,
} from "../api/client";
import { FEATURE_UNAVAILABLE } from "../utils/uiMessage";

const ui = usePlatformUi();
const { t } = useI18n();

const meta = ref(null);
const loadingMeta = ref(true);
const error = ref("");
const language = ref("");
const displayFormat = ref("text");
const processing = ref(false);
const exporting = ref(false);
const fileItems = ref([]);
const selectedId = ref(null);

const languageOptions = computed(() => [
  { label: t("ocr.langAuto"), value: "" },
  { label: t("ocr.langZh"), value: "zh" },
  { label: t("ocr.langEn"), value: "en" },
  { label: t("ocr.langJa"), value: "ja" },
  { label: t("ocr.langKo"), value: "ko" },
]);

const displayFormatOptions = computed(() => [
  { label: t("ocr.formatText"), value: "text" },
  { label: t("ocr.formatMarkdown"), value: "markdown" },
  { label: t("ocr.formatJson"), value: "json" },
]);

const acceptTypes = ".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.pdf";

const configured = computed(() => meta.value?.configured ?? false);

const selectedItem = computed(() =>
  fileItems.value.find((item) => item.id === selectedId.value) || null
);

const doneItems = computed(() => fileItems.value.filter((item) => item.status === "done"));

const pendingCount = computed(() =>
  fileItems.value.filter((item) => item.status === "pending").length
);

const processingCount = computed(() =>
  fileItems.value.filter((item) => item.status === "processing").length
);

const dropSummary = computed(() => {
  const n = fileItems.value.length;
  if (!n) return "";
  return t("ocr.filesAdded", { count: n });
});

const canRecognize = computed(
  () =>
    configured.value &&
    pendingCount.value > 0 &&
    !processing.value &&
    processingCount.value === 0
);

const canExport = computed(() => doneItems.value.length > 0 && !exporting.value);

const hasResultPanel = computed(
  () => selectedItem.value?.status === "done" || selectedItem.value?.status === "processing"
);

const resultDisplayText = computed(() => {
  const item = selectedItem.value;
  if (!item?.result) return "";
  if (displayFormat.value === "markdown") return item.result.markdown || item.result.text || "";
  if (displayFormat.value === "json") {
    return JSON.stringify(
      {
        file_name: item.result.file_name,
        text: item.result.text,
        pages: item.result.pages,
        blocks: item.result.blocks,
      },
      null,
      2
    );
  }
  return item.result.text || "";
});

const progressLabel = computed(() => {
  const total = fileItems.value.length;
  const done = doneItems.value.length;
  const failed = fileItems.value.filter((item) => item.status === "error").length;
  if (!total) return "";
  if (processing.value || processingCount.value) {
    return t("ocr.progressRecognizing", { done: done + failed, total });
  }
  if (done || failed) return t("ocr.progressCompleted", { done, failed });
  return t("ocr.progressPending", { total });
});

function makeId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function revokePreview(item) {
  if (item?.previewUrl) {
    URL.revokeObjectURL(item.previewUrl);
    item.previewUrl = "";
  }
}

async function loadMeta() {
  loadingMeta.value = true;
  try {
    meta.value = await fetchOcrMeta();
  } catch (e) {
    error.value = e.message;
  } finally {
    loadingMeta.value = false;
  }
}

function onFilesChange(e) {
  const files = Array.from(e.target?.files || []);
  if (!files.length) return;
  const next = [...fileItems.value];
  for (const file of files) {
    const previewUrl =
      file.type.startsWith("image/") ? URL.createObjectURL(file) : "";
    next.push({
      id: makeId(),
      file,
      previewUrl,
      status: "pending",
      error: "",
      result: null,
    });
  }
  fileItems.value = next;
  if (!selectedId.value && next.length) {
    selectedId.value = next[0].id;
  }
}

function selectItem(id) {
  selectedId.value = id;
}

function removeItem(id) {
  const idx = fileItems.value.findIndex((item) => item.id === id);
  if (idx < 0) return;
  const item = fileItems.value[idx];
  revokePreview(item);
  fileItems.value = fileItems.value.filter((entry) => entry.id !== id);
  if (selectedId.value === id) {
    selectedId.value = fileItems.value[0]?.id || null;
  }
}

function clearAll() {
  fileItems.value.forEach(revokePreview);
  fileItems.value = [];
  selectedId.value = null;
  error.value = "";
}

function statusTagType(status) {
  if (status === "done") return "success";
  if (status === "error") return "error";
  if (status === "processing") return "info";
  return "default";
}

function statusLabel(status) {
  const map = {
    pending: t("ocr.statusPending"),
    processing: t("ocr.statusProcessing"),
    done: t("ocr.statusDone"),
    error: t("ocr.statusError"),
  };
  return map[status] || status;
}

async function startRecognize() {
  if (!canRecognize.value) return;
  processing.value = true;
  error.value = "";
  const queue = fileItems.value.filter((item) => item.status === "pending");
  for (const item of queue) {
    item.status = "processing";
    item.error = "";
    selectedId.value = item.id;
    try {
      const result = await recognizeOcr({ file: item.file, language: language.value });
      item.result = result;
      item.status = "done";
    } catch (e) {
      item.status = "error";
      item.error = e.message || t("ocr.recognizeFailed");
      error.value = t("ocr.fileError", { name: item.file.name, error: item.error });
    }
  }
  processing.value = false;
}

function copyResult() {
  const text = resultDisplayText.value;
  if (!text.trim()) {
    ui.warning(t("ocr.noResult"));
    return;
  }
  navigator.clipboard?.writeText(text).then(
    () => ui.success(t("ocr.copied")),
    () => ui.error(t("ocr.copyFailed"))
  );
}

function buildExportItems(items) {
  return items.map((item) => ({
    file_name: item.result.file_name || item.file.name,
    text: item.result.text || "",
    markdown: item.result.markdown || "",
    blocks: item.result.blocks || [],
    pages: item.result.pages || [],
  }));
}

async function exportBatch(format) {
  if (!canExport.value) return;
  exporting.value = true;
  try {
    await downloadOcrExportZip({
      format,
      items: buildExportItems(doneItems.value),
    });
    ui.success(format === "markdown" ? t("ocr.exportedMarkdownZip") : t("ocr.exportedJsonZip"));
  } catch (e) {
    ui.error(e.message || t("ocr.exportFailed"));
  } finally {
    exporting.value = false;
  }
}

async function exportCurrent(format) {
  const item = selectedItem.value;
  if (!item?.result) {
    ui.warning(t("ocr.selectDoneFileFirst"));
    return;
  }
  exporting.value = true;
  try {
    await downloadOcrExportZip({
      format,
      items: buildExportItems([item]),
    });
    ui.success(t("ocr.exportedCurrent"));
  } catch (e) {
    ui.error(e.message || t("ocr.exportFailed"));
  } finally {
    exporting.value = false;
  }
}

onMounted(loadMeta);
onBeforeUnmount(() => fileItems.value.forEach(revokePreview));
</script>

<template>
  <FeatureSubsystemShell fill>
    <template #extra>
      <n-space v-if="progressLabel" align="center" :size="8">
        <n-tag size="small" round :bordered="false">{{ progressLabel }}</n-tag>
      </n-space>
    </template>

    <n-spin :show="loadingMeta" class="ocr-spin" local>
      <div class="ocr-alerts">
        <n-alert
          v-if="!loadingMeta && !configured"
          type="warning"
          :title="t('ocr.unavailableTitle')"
          class="page-alert"
        >
          <p>{{ FEATURE_UNAVAILABLE }}</p>
          <template #action>
            <n-button size="small" :loading="loadingMeta" @click="loadMeta">{{ t('ocr.recheck') }}</n-button>
          </template>
        </n-alert>

        <n-alert
          v-if="error"
          type="error"
          :title="error"
          class="page-alert"
          closable
          @close="error = ''"
        />
      </div>

      <div class="ocr-layout">
        <n-card :title="t('ocr.filesAndOptions')" class="panel panel-source" size="small">
          <div class="panel-body">
            <file-drop-zone
              :accept="acceptTypes"
              multiple
              :title="t('ocr.dropTitle')"
              :hint="t('ocr.dropHint')"
              :file-name="dropSummary"
              icon="upload"
              :disabled="!configured || processing"
              @change="onFilesChange"
            />

            <div v-if="fileItems.length" class="file-list">
              <div class="file-list-head">
                <n-text depth="3">{{ t('ocr.fileList') }}</n-text>
                <n-button size="tiny" quaternary @click="clearAll">{{ t('ocr.clear') }}</n-button>
              </div>
              <div
                v-for="item in fileItems"
                :key="item.id"
                class="file-row"
                :class="{ active: item.id === selectedId }"
                @click="selectItem(item.id)"
              >
                <n-icon
                  :component="item.file.type.startsWith('image/') ? ImageOutline : DocumentTextOutline"
                  :size="16"
                />
                <div class="file-row-main">
                  <n-text class="file-name">{{ item.file.name }}</n-text>
                  <n-text v-if="item.error" depth="3" class="file-error">{{ item.error }}</n-text>
                </div>
                <n-tag size="tiny" :type="statusTagType(item.status)" :bordered="false">
                  {{ statusLabel(item.status) }}
                </n-tag>
                <n-button
                  size="tiny"
                  quaternary
                  :disabled="processing"
                  @click.stop="removeItem(item.id)"
                >
                  <template #icon><n-icon :component="TrashOutline" /></template>
                </n-button>
              </div>
            </div>

            <div v-if="selectedItem?.previewUrl" class="preview-box">
              <n-text depth="3" class="field-label">{{ t('ocr.preview') }}</n-text>
              <img :src="selectedItem.previewUrl" :alt="t('ocr.previewAlt')" class="preview-img" />
            </div>

            <div>
              <n-text depth="3" class="field-label">{{ t('ocr.recognizeLanguage') }}</n-text>
              <n-select
                v-model:value="language"
                :options="languageOptions"
                :disabled="!configured"
              />
            </div>

            <n-space :size="8" class="source-actions">
              <n-button
                type="primary"
                :disabled="!canRecognize"
                :loading="processing"
                @click="startRecognize"
              >
                {{ processing ? t('ocr.batchRecognizing') : pendingCount ? t('ocr.startRecognizeWithCount', { count: pendingCount }) : t('ocr.startRecognize') }}
              </n-button>
              <n-button
                secondary
                :disabled="!canExport"
                :loading="exporting"
                @click="exportBatch('markdown')"
              >
                <template #icon><n-icon :component="DownloadOutline" /></template>
                {{ t('ocr.exportAllMd') }}
              </n-button>
              <n-button
                secondary
                :disabled="!canExport"
                :loading="exporting"
                @click="exportBatch('json')"
              >
                <template #icon><n-icon :component="DownloadOutline" /></template>
                {{ t('ocr.exportAllJson') }}
              </n-button>
            </n-space>
            <n-text depth="3" class="hint-text">
              {{ t('ocr.jsonExportHint') }}
            </n-text>
          </div>
        </n-card>

        <n-card :title="t('ocr.results')" class="panel panel-result" size="small">
          <div class="panel-body">
            <div v-if="!hasResultPanel" class="result-idle">
              <n-icon :size="40" :depth="3" :component="ScanOutline" />
              <n-text depth="2">{{ t('ocr.resultIdle') }}</n-text>
              <n-text depth="3" class="result-idle-hint">
                {{ t('ocr.resultIdleHint') }}
              </n-text>
            </div>

            <div v-else-if="selectedItem?.status === 'processing'" class="result-processing">
              <n-text>{{ t('ocr.recognizingFile', { name: selectedItem.file.name }) }}</n-text>
              <n-text depth="3">{{ t('ocr.largeFileHint') }}</n-text>
            </div>

            <template v-else-if="selectedItem?.status === 'done'">
              <div class="result-toolbar">
                <n-select
                  v-model:value="displayFormat"
                  :options="displayFormatOptions"
                  size="small"
                  class="format-select"
                />
                <n-space :size="8" wrap>
                  <n-button size="small" @click="copyResult">
                    <template #icon><n-icon :component="CopyOutline" /></template>
                    {{ t('ocr.copy') }}
                  </n-button>
                  <n-button size="small" secondary @click="exportCurrent('markdown')">
                    {{ t('ocr.exportMd') }}
                  </n-button>
                  <n-button size="small" secondary @click="exportCurrent('json')">
                    {{ t('ocr.exportJson') }}
                  </n-button>
                </n-space>
              </div>
              <n-input
                :value="resultDisplayText"
                type="textarea"
                readonly
                :placeholder="t('ocr.resultPlaceholder')"
                class="result-textarea textarea-fill"
              />
            </template>

            <div v-else-if="selectedItem?.status === 'error'" class="result-idle">
              <n-text type="error">{{ selectedItem.error || t('ocr.recognizeFailed') }}</n-text>
            </div>
          </div>
        </n-card>
      </div>
    </n-spin>
  </FeatureSubsystemShell>
</template>

<style scoped>
.ocr-spin {
  flex: 1;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}
.ocr-spin :deep(.n-spin-container) {
  flex: 1;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}
.ocr-alerts {
  flex-shrink: 0;
}
.page-alert {
  margin-bottom: 12px;
}
.ocr-layout {
  flex: 1;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 16px;
  align-items: stretch;
  width: 100%;
  box-sizing: border-box;
  overflow: hidden;
}
.panel {
  border-radius: 10px;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
}
.panel :deep(.n-card) {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.panel :deep(.n-card__content) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.panel-source :deep(.drop-zone) {
  min-height: 140px;
}
.file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 220px;
  overflow: auto;
  border: 1px solid var(--n-border-color);
  border-radius: 8px;
  padding: 8px;
  background: rgba(0, 0, 0, 0.02);
}
.file-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.file-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.file-row:hover,
.file-row.active {
  background: var(--platform-accent-bg-soft, rgba(32, 128, 240, 0.08));
}
.file-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.file-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-error {
  font-size: 11px;
  line-height: 1.3;
}
.preview-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.preview-img {
  max-width: 100%;
  max-height: 160px;
  object-fit: contain;
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
  background: var(--n-color-modal);
}
.field-label {
  font-size: 12px;
  display: block;
  margin-bottom: 4px;
}
.source-actions {
  flex-wrap: wrap;
}
.hint-text {
  font-size: 12px;
  line-height: 1.45;
}
.result-idle,
.result-processing {
  flex: 1;
  min-height: 240px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  padding: 24px;
}
.result-idle-hint {
  font-size: 12px;
  max-width: 320px;
}
.result-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.format-select {
  width: 140px;
}
.textarea-fill {
  flex: 1;
  min-height: 0;
  display: flex;
}
.textarea-fill :deep(.n-input) {
  height: 100%;
}
.result-textarea :deep(textarea) {
  height: 100% !important;
  min-height: 240px;
  resize: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.55;
}
@media (max-width: 960px) {
  .ocr-layout {
    grid-template-columns: 1fr;
  }
}
</style>
