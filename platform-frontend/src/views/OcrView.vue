<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
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

const ui = usePlatformUi();

const meta = ref(null);
const loadingMeta = ref(true);
const error = ref("");
const language = ref("");
const displayFormat = ref("text");
const processing = ref(false);
const exporting = ref(false);
const fileItems = ref([]);
const selectedId = ref(null);

const languageOptions = [
  { label: "自动检测", value: "" },
  { label: "简体中文", value: "zh" },
  { label: "英语", value: "en" },
  { label: "日语", value: "ja" },
  { label: "韩语", value: "ko" },
];

const displayFormatOptions = [
  { label: "纯文本", value: "text" },
  { label: "Markdown", value: "markdown" },
  { label: "JSON", value: "json" },
];

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
  return `已添加 ${n} 个文件`;
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
    return `识别中 ${done + failed}/${total}`;
  }
  if (done || failed) return `已完成 ${done}，失败 ${failed}`;
  return `${total} 个文件待识别`;
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
    pending: "待识别",
    processing: "识别中",
    done: "完成",
    error: "失败",
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
      item.error = e.message || "识别失败";
      error.value = `${item.file.name}：${item.error}`;
    }
  }
  processing.value = false;
}

function copyResult() {
  const text = resultDisplayText.value;
  if (!text.trim()) {
    ui.warning("暂无识别结果");
    return;
  }
  navigator.clipboard?.writeText(text).then(
    () => ui.success("已复制到剪贴板"),
    () => ui.error("复制失败")
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
    ui.success(format === "markdown" ? "已导出 Markdown 压缩包" : "已导出 JSON 压缩包");
  } catch (e) {
    ui.error(e.message || "导出失败");
  } finally {
    exporting.value = false;
  }
}

async function exportCurrent(format) {
  const item = selectedItem.value;
  if (!item?.result) {
    ui.warning("请先选择已完成的文件");
    return;
  }
  exporting.value = true;
  try {
    await downloadOcrExportZip({
      format,
      items: buildExportItems([item]),
    });
    ui.success("已导出当前文件");
  } catch (e) {
    ui.error(e.message || "导出失败");
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
        <n-tag v-if="meta?.model" size="small" round type="info" :bordered="false">
          {{ meta.provider || "文件内容提取" }} · {{ meta.model }}
        </n-tag>
      </n-space>
    </template>

    <n-spin :show="loadingMeta" class="ocr-spin">
      <div class="ocr-alerts">
        <n-alert
          v-if="!loadingMeta && !configured"
          type="warning"
          title="文件内容提取服务未配置"
          class="page-alert"
        >
          <p>{{ meta?.service_hint || "请在资源管理中配置 PaddleOCR-VL。" }}</p>
          <template #action>
            <n-button size="small" :loading="loadingMeta" @click="loadMeta">重新检测</n-button>
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
        <n-card title="文件与选项" class="panel panel-source" size="small">
          <div class="panel-body">
            <file-drop-zone
              :accept="acceptTypes"
              multiple
              title="拖拽文件到此处"
              hint="支持 PNG、JPG、WEBP、BMP、TIFF、PDF，可多选"
              :file-name="dropSummary"
              icon="upload"
              :disabled="!configured || processing"
              @change="onFilesChange"
            />

            <div v-if="fileItems.length" class="file-list">
              <div class="file-list-head">
                <n-text depth="3">文件列表</n-text>
                <n-button size="tiny" quaternary @click="clearAll">清空</n-button>
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
              <n-text depth="3" class="field-label">预览</n-text>
              <img :src="selectedItem.previewUrl" alt="预览" class="preview-img" />
            </div>

            <div>
              <n-text depth="3" class="field-label">识别语言</n-text>
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
                {{ processing ? "批量识别中…" : `开始识别${pendingCount ? `（${pendingCount}）` : ""}` }}
              </n-button>
              <n-button
                secondary
                :disabled="!canExport"
                :loading="exporting"
                @click="exportBatch('markdown')"
              >
                <template #icon><n-icon :component="DownloadOutline" /></template>
                导出全部 MD
              </n-button>
              <n-button
                secondary
                :disabled="!canExport"
                :loading="exporting"
                @click="exportBatch('json')"
              >
                <template #icon><n-icon :component="DownloadOutline" /></template>
                导出全部 JSON
              </n-button>
            </n-space>
            <n-text depth="3" class="hint-text">
              使用资源管理中的 PaddleOCR-VL 服务；JSON 含页码与坐标（版面解析可用时）。
            </n-text>
          </div>
        </n-card>

        <n-card title="识别结果" class="panel panel-result" size="small">
          <div class="panel-body">
            <div v-if="!hasResultPanel" class="result-idle">
              <n-icon :size="40" :depth="3" :component="ScanOutline" />
              <n-text depth="2">添加文件并开始识别后，结果将显示在此处</n-text>
              <n-text depth="3" class="result-idle-hint">
                支持批量识别，并可一键导出 Markdown / JSON 压缩包
              </n-text>
            </div>

            <div v-else-if="selectedItem?.status === 'processing'" class="result-processing">
              <n-text>正在识别 {{ selectedItem.file.name }}…</n-text>
              <n-text depth="3">大文件或 PDF 可能需要数十秒</n-text>
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
                    复制
                  </n-button>
                  <n-button size="small" secondary @click="exportCurrent('markdown')">
                    导出 MD
                  </n-button>
                  <n-button size="small" secondary @click="exportCurrent('json')">
                    导出 JSON
                  </n-button>
                </n-space>
              </div>
              <n-input
                :value="resultDisplayText"
                type="textarea"
                readonly
                placeholder="识别结果"
                class="result-textarea textarea-fill"
              />
            </template>

            <div v-else-if="selectedItem?.status === 'error'" class="result-idle">
              <n-text type="error">{{ selectedItem.error || "识别失败" }}</n-text>
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
