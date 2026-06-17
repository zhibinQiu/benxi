<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { NButton, NEmpty, NSpace, NSpin, NTag, NText } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import { fetchDocumentFileBlob } from "../api/documents.js";
import {
  PREVIEW_KIND,
  previewKindLabel,
} from "../utils/documentPreview.js";
import {
  loadWordPreview,
  readTextBlob,
  resolvePreviewContent,
} from "../utils/documentPreviewLoad.js";

const props = defineProps({
  show: { type: Boolean, default: false },
  /** 文档中心：documentId + version */
  documentId: { type: String, default: "" },
  version: { type: Object, default: null },
  /** 通用：外部提供 Blob 加载器（如翻译结果 PDF） */
  blobLoader: { type: Function, default: null },
  previewTitle: { type: String, default: "" },
  previewSubtitle: { type: String, default: "" },
  previewFileName: { type: String, default: "" },
  showDownloadAction: { type: Boolean, default: null },
  width: { type: [Number, String], default: "min(1280px, 98vw)" },
  viewportHeight: { type: String, default: "72vh" },
  /** PDF 预览缩放：width 按弹窗宽度铺满（竖版文档可读性更好）；page 整页缩放进视口 */
  pdfFitMode: { type: String, default: "width" },
});

const emit = defineEmits(["update:show", "download"]);

const loading = ref(false);
const error = ref("");
const previewKind = ref(PREVIEW_KIND.UNSUPPORTED);
const objectUrl = ref("");
const textContent = ref("");
const wordHtml = ref("");
const previewLoadToken = ref(0);

const visible = computed({
  get: () => props.show,
  set: (value) => emit("update:show", value),
});

const modalTitle = computed(() => {
  if (props.previewTitle) return props.previewTitle;
  const ver = props.version;
  if (!ver) return "文件预览";
  return `预览 v${ver.version_no}`;
});

const modalSubtitle = computed(
  () => props.previewSubtitle || props.version?.file_name || props.previewFileName || ""
);

const useDocumentSource = computed(
  () => Boolean(props.documentId && props.version?.id && !props.blobLoader)
);

const downloadVisible = computed(() => {
  if (props.showDownloadAction != null) return props.showDownloadAction;
  return Boolean(props.version?.uploaded);
});

const kindLabel = computed(() => previewKindLabel(previewKind.value));

function cleanupPreview() {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value);
    objectUrl.value = "";
  }
  textContent.value = "";
  wordHtml.value = "";
  error.value = "";
  previewKind.value = PREVIEW_KIND.UNSUPPORTED;
  loading.value = false;
}

async function loadPreview() {
  const token = ++previewLoadToken.value;
  cleanupPreview();
  loading.value = true;

  let blob;
  let fileName = "";
  let mimeType = "";

  try {
    if (props.blobLoader) {
      fileName = props.previewFileName || props.previewSubtitle || "file.pdf";
      mimeType = "application/pdf";
      blob = await props.blobLoader();
    } else {
      const ver = props.version;
      if (!props.documentId || !ver?.id || !ver.uploaded) {
        if (token === previewLoadToken.value) {
          error.value = "该版本暂无可预览文件";
        }
        return;
      }
      fileName = ver.file_name || "";
      mimeType = ver.mime_type || "";
      blob = await fetchDocumentFileBlob(props.documentId, ver.id);
    }

    if (token !== previewLoadToken.value) return;

    const resolved = await resolvePreviewContent(blob, fileName, mimeType);
    if (token !== previewLoadToken.value) return;

    if (resolved.error) {
      error.value = resolved.error;
      return;
    }
    previewKind.value = resolved.kind;

    if (previewKind.value === PREVIEW_KIND.TEXT) {
      textContent.value = resolved.text || (await readTextBlob(blob));
      if (token !== previewLoadToken.value) return;
      if (!textContent.value?.trim()) {
        error.value = "文本内容为空";
      }
      return;
    }

    if (previewKind.value === PREVIEW_KIND.WORD) {
      const { html, text } = await loadWordPreview(blob, {
        documentId: props.documentId,
        versionId: props.version?.id || null,
        fileName,
      });
      if (token !== previewLoadToken.value) return;
      if (html) {
        wordHtml.value = html;
        return;
      }
      if (text) {
        previewKind.value = PREVIEW_KIND.TEXT;
        textContent.value = text;
        return;
      }
      error.value = "Word 文档内容为空";
      return;
    }

    if (previewKind.value === PREVIEW_KIND.UNSUPPORTED) {
      error.value = "此格式暂不支持在线预览";
      return;
    }

    objectUrl.value = URL.createObjectURL(
      blob.type === "application/pdf"
        ? blob
        : new Blob([blob], { type: "application/pdf" }),
    );
  } catch (e) {
    if (token === previewLoadToken.value) {
      error.value = e?.message || "预览加载失败";
    }
  } finally {
    if (token === previewLoadToken.value) {
      loading.value = false;
    }
  }
}

watch(
  () => [
    props.documentId,
    props.version?.id,
    props.blobLoader,
    props.previewFileName,
  ],
  () => {
    if (props.show) {
      nextTick(() => loadPreview());
    }
  },
);

function onAfterEnter() {
  nextTick(() => loadPreview());
}

function onAfterLeave() {
  cleanupPreview();
}
</script>

<template>
  <AdminFormModal
    v-model:show="visible"
    class="document-preview-modal"
    :title="modalTitle"
    :subtitle="modalSubtitle"
    :width="width"
    @after-enter="onAfterEnter"
    @after-leave="onAfterLeave"
  >
    <div class="document-preview-modal__toolbar">
      <n-tag size="small" :bordered="false" type="info">{{ kindLabel }}</n-tag>
    </div>

    <n-spin :show="loading" class="document-preview-modal__spin">
      <div class="document-preview-modal__viewport">
        <iframe
          v-if="previewKind === PREVIEW_KIND.PDF && objectUrl"
          :key="`${documentId}-${version?.id || ''}-${objectUrl}`"
          :src="objectUrl"
          class="document-preview-modal__frame document-preview-modal__pdf-frame"
          title="PDF 预览"
        />
        <iframe
          v-else-if="previewKind === PREVIEW_KIND.HTML && objectUrl"
          :key="objectUrl"
          :src="objectUrl"
          class="document-preview-modal__frame"
          sandbox="allow-same-origin"
          title="HTML 预览"
        />
        <img
          v-else-if="previewKind === PREVIEW_KIND.IMAGE && objectUrl"
          :src="objectUrl"
          :alt="modalSubtitle"
          class="document-preview-modal__image"
        />
        <pre v-else-if="previewKind === PREVIEW_KIND.TEXT && textContent" class="document-preview-modal__text">{{
          textContent
        }}</pre>
        <div
          v-else-if="previewKind === PREVIEW_KIND.WORD && wordHtml"
          class="document-preview-modal__word"
          v-html="wordHtml"
        />
        <n-empty
          v-else-if="error"
          description="预览加载失败"
          class="document-preview-modal__empty"
        >
          <template #extra>
            <n-text depth="3">{{ error }}</n-text>
          </template>
        </n-empty>
        <n-empty
          v-else-if="previewKind === PREVIEW_KIND.UNSUPPORTED && !loading"
          description="此格式暂不支持在线预览"
          class="document-preview-modal__empty"
        >
          <template #extra>
            <n-text depth="3">请下载后在本地应用中打开查看</n-text>
          </template>
        </n-empty>
        <n-empty
          v-else-if="!loading"
          description="预览内容为空"
          class="document-preview-modal__empty"
        >
          <template #extra>
            <n-text depth="3">请尝试下载文件或等待后台导入任务完成后再预览</n-text>
          </template>
        </n-empty>
      </div>
    </n-spin>

    <template #footer>
      <n-space justify="end" :size="10">
        <n-button @click="visible = false">关闭</n-button>
        <n-button
          v-if="downloadVisible && useDocumentSource"
          type="primary"
          @click="emit('download', version)"
        >
          下载
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>
</template>

<style scoped>
.document-preview-modal__toolbar {
  flex-shrink: 0;
  margin-bottom: 12px;
}

.document-preview-modal__spin {
  flex: 1;
  width: 100%;
  min-height: 360px;
  display: flex;
  flex-direction: column;
}

.document-preview-modal__spin :deep(.n-spin-container),
.document-preview-modal__spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.document-preview-modal__viewport {
  display: flex;
  flex: 1;
  align-items: stretch;
  justify-content: center;
  width: 100%;
  min-height: 360px;
  height: 100%;
  max-height: v-bind(viewportHeight);
  border-radius: calc(var(--platform-radius-sm) + 4px);
  border: 1px solid var(--platform-border);
  background: color-mix(in srgb, var(--platform-text) 3%, transparent);
  overflow: hidden;
}

.document-preview-modal__frame {
  width: 100%;
  height: 100%;
  min-height: 360px;
  border: 0;
  background: #fff;
}

.document-preview-modal__pdf-frame {
  flex: 1;
  min-height: 0;
  background: #525659;
}

.document-preview-modal__image {
  width: 100%;
  max-width: 100%;
  height: auto;
  max-height: 100%;
  object-fit: contain;
  margin: auto;
  padding: 16px;
  box-sizing: border-box;
}

.document-preview-modal__text {
  width: 100%;
  height: 100%;
  max-height: 100%;
  margin: 0;
  padding: 16px 18px;
  overflow: auto;
  font-family: var(--platform-font-mono);
  font-size: 13px;
  line-height: 1.55;
  color: var(--platform-text);
  white-space: pre-wrap;
  word-break: break-word;
  box-sizing: border-box;
}

.document-preview-modal__word {
  width: 100%;
  height: 100%;
  max-height: 100%;
  margin: 0;
  padding: 20px 28px;
  overflow: auto;
  font-size: 14px;
  line-height: 1.65;
  color: var(--platform-text);
  background: #fff;
  box-sizing: border-box;
}

.document-preview-modal__word :deep(p) {
  margin: 0 0 0.75em;
}

.document-preview-modal__word :deep(h1),
.document-preview-modal__word :deep(h2),
.document-preview-modal__word :deep(h3),
.document-preview-modal__word :deep(h4),
.document-preview-modal__word :deep(h5),
.document-preview-modal__word :deep(h6) {
  margin: 1.1em 0 0.5em;
  line-height: 1.35;
}

.document-preview-modal__word :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75em 0;
}

.document-preview-modal__word :deep(th),
.document-preview-modal__word :deep(td) {
  border: 1px solid color-mix(in srgb, var(--platform-text) 18%, transparent);
  padding: 6px 10px;
  vertical-align: top;
}

.document-preview-modal__word :deep(ul),
.document-preview-modal__word :deep(ol) {
  margin: 0.5em 0 0.75em;
  padding-left: 1.5em;
}

.document-preview-modal__word :deep(img) {
  max-width: 100%;
  height: auto;
}

.document-preview-modal__empty {
  margin: auto;
  padding: 32px 16px;
}
</style>

<style>
.document-preview-modal.admin-form-modal.n-modal .n-card {
  max-height: 96vh;
  display: flex;
  flex-direction: column;
}

.document-preview-modal.admin-form-modal.n-modal .n-card__content {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.document-preview-modal.admin-form-modal.n-modal .admin-form-modal__body {
  flex: 1 1 auto;
  min-height: 360px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
