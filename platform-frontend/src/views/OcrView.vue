<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
import { useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NGi,
  NGrid,
  NIcon,
  NInput,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NSteps,
  NStep,
  NTag,
  NText,
  useMessage,
} from "naive-ui";
import {
  ArrowBackOutline,
  ScanOutline,
  CopyOutline,
  DownloadOutline,
  ImageOutline,
  DocumentTextOutline,
} from "@vicons/ionicons5";
import FileDropZone from "../components/FileDropZone.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";

const router = useRouter();
const message = useMessage();

const sourceMode = ref("image");
const selectedFile = ref(null);
const previewUrl = ref("");
const language = ref("");
const outputFormat = ref("text");
const processing = ref(false);
const resultText = ref("");
const currentStep = ref(1);

const languageOptions = [
  { label: "自动检测", value: "" },
  { label: "简体中文", value: "zh" },
  { label: "英语", value: "en" },
  { label: "日语", value: "ja" },
  { label: "韩语", value: "ko" },
];

const outputFormatOptions = [
  { label: "纯文本", value: "text" },
  { label: "Markdown", value: "markdown" },
  { label: "JSON（含坐标）", value: "json" },
];

const acceptByMode = computed(() =>
  sourceMode.value === "image"
    ? ".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
    : ".pdf,.png,.jpg,.jpeg,.webp"
);

const dropTitle = computed(() =>
  sourceMode.value === "image" ? "拖拽图像到此处" : "拖拽文档到此处"
);

const dropHint = computed(() =>
  sourceMode.value === "image"
    ? "支持 PNG、JPG、WEBP、BMP、TIFF"
    : "支持 PDF 及常见图像格式"
);

const displayFileName = computed(() => selectedFile.value?.name || "");

const canRecognize = computed(() => !!selectedFile.value && !processing.value);

const hasResult = computed(() => !!resultText.value.trim());

function revokePreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
    previewUrl.value = "";
  }
}

function onSourceModeChange() {
  selectedFile.value = null;
  resultText.value = "";
  currentStep.value = 1;
  revokePreview();
}

function onFileChange(e) {
  const file = e.target.files?.[0] || null;
  selectedFile.value = file;
  resultText.value = "";
  currentStep.value = file ? 1 : 1;
  revokePreview();
  if (file && sourceMode.value === "image" && file.type.startsWith("image/")) {
    previewUrl.value = URL.createObjectURL(file);
  }
}

function startRecognize() {
  if (!selectedFile.value) return;
  processing.value = true;
  currentStep.value = 2;
  window.setTimeout(() => {
    processing.value = false;
    currentStep.value = 1;
    message.info("OCR 识别能力尚未接入，当前仅提供界面预览");
  }, 600);
}

function copyResult() {
  if (!resultText.value) {
    message.warning("暂无识别结果");
    return;
  }
  navigator.clipboard?.writeText(resultText.value).then(
    () => message.success("已复制到剪贴板"),
    () => message.error("复制失败")
  );
}

function downloadResult() {
  message.info("导出功能开发中");
}

onBeforeUnmount(revokePreview);
</script>

<template>
  <FeatureSubsystemShell fill>
    <template #extra>
      <n-tag size="small" round type="warning">界面预览</n-tag>
    </template>
    <header class="page-subheader feature-local-nav">
      <n-steps :current="currentStep" size="small" class="header-steps">
        <n-step title="上传" />
        <n-step title="识别" />
        <n-step title="结果" />
      </n-steps>
    </header>

    <n-alert type="info" class="page-alert" :show-icon="false">
      当前为界面原型：可上传文件并配置选项，识别与导出将在后续版本接入。
    </n-alert>

    <div class="ocr-workspace">
      <n-grid
        cols="1 m:2 xl:3"
        responsive="screen"
        item-responsive
        :x-gap="20"
        :y-gap="20"
        class="ocr-grid"
      >
        <n-gi span="1 m:1 xl:1">
          <n-card class="panel panel-fill" size="small" title="上传与配置">
            <n-radio-group
              v-model:value="sourceMode"
              size="small"
              class="source-toggle"
              @update:value="onSourceModeChange"
            >
              <n-radio-button value="image">
                <n-space align="center" :size="4">
                  <n-icon :component="ImageOutline" />
                  <span>图像</span>
                </n-space>
              </n-radio-button>
              <n-radio-button value="document">
                <n-space align="center" :size="4">
                  <n-icon :component="DocumentTextOutline" />
                  <span>文档</span>
                </n-space>
              </n-radio-button>
            </n-radio-group>

            <div class="upload-fill">
              <file-drop-zone
                :accept="acceptByMode"
                :title="dropTitle"
                :hint="dropHint"
                :file-name="displayFileName"
                icon="upload"
                @change="onFileChange"
              />
            </div>

            <div v-if="previewUrl" class="preview-box">
              <n-text depth="3" class="field-label">预览</n-text>
              <img :src="previewUrl" alt="预览" class="preview-img" />
            </div>

            <n-text depth="3" class="field-label">识别语言</n-text>
            <n-select
              v-model:value="language"
              :options="languageOptions"
              placeholder="自动检测"
            />

            <n-text depth="3" class="field-label">输出格式</n-text>
            <n-select v-model:value="outputFormat" :options="outputFormatOptions" />

            <n-button
              type="primary"
              size="large"
              block
              class="start-btn"
              :disabled="!canRecognize"
              :loading="processing"
              @click="startRecognize"
            >
              {{ processing ? "识别中…" : "开始识别" }}
            </n-button>
            <n-text v-if="!selectedFile" depth="3" class="start-hint">
              请先上传{{ sourceMode === "image" ? "图像" : "文档" }}
            </n-text>
          </n-card>
        </n-gi>

        <n-gi span="1 m:1 xl:2">
          <n-card
            class="panel panel-fill panel-result"
            size="small"
            title="识别结果"
            :class="{ 'panel-result-active': hasResult || processing }"
          >
            <div v-if="!hasResult && !processing" class="result-idle">
              <n-icon :size="40" :depth="3" :component="ScanOutline" />
              <n-text depth="2">上传文件并点击「开始识别」后，文字将显示在此处</n-text>
              <n-text depth="3" class="result-idle-hint">
                文档模式将按页输出；JSON 格式可包含文本框坐标（规划中）
              </n-text>
            </div>

            <div v-else-if="processing" class="result-processing">
              <n-text>正在识别…</n-text>
              <n-text depth="3">后端接入后将在此流式返回识别进度</n-text>
            </div>

            <template v-else>
              <n-input
                v-model:value="resultText"
                type="textarea"
                placeholder="识别结果将显示在这里"
                :autosize="{ minRows: 14, maxRows: 24 }"
                class="result-textarea"
              />
              <n-space :size="10" class="result-actions">
                <n-button @click="copyResult">
                  <template #icon>
                    <n-icon :component="CopyOutline" />
                  </template>
                  复制
                </n-button>
                <n-button secondary @click="downloadResult">
                  <template #icon>
                    <n-icon :component="DownloadOutline" />
                  </template>
                  导出
                </n-button>
              </n-space>
            </template>
          </n-card>
        </n-gi>
      </n-grid>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.ocr-page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
}
.page-subheader {
  flex-shrink: 0;
}
.header-steps {
  width: 100%;
  max-width: 420px;
}
.page-alert {
  flex-shrink: 0;
  margin-bottom: 12px;
}
.ocr-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ocr-grid {
  width: 100%;
  flex: 1;
  min-height: 0;
}
.ocr-grid :deep(> div) {
  height: 100%;
}
.ocr-grid :deep(.n-grid-item) {
  display: flex;
  min-height: 0;
}
.panel {
  border-radius: 10px;
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
}
.panel :deep(.n-card) {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.panel-fill :deep(.n-card__content) {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
}
.source-toggle {
  margin-bottom: 4px;
}
.upload-fill {
  flex: 1;
  min-height: 160px;
  display: flex;
}
.upload-fill :deep(.drop-zone) {
  flex: 1;
  width: 100%;
  min-height: 160px;
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
}
.start-btn {
  margin-top: 4px;
}
.start-hint {
  text-align: center;
  font-size: 12px;
}
.panel-result-active {
  border-color: var(--platform-accent-border-soft);
}
.result-idle,
.result-processing {
  flex: 1;
  min-height: 280px;
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
.result-textarea {
  flex: 1;
  min-height: 0;
}
.result-textarea :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.55;
}
.result-actions {
  flex-shrink: 0;
  justify-content: flex-end;
}
</style>
