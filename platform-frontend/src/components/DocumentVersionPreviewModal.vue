<script setup>
import { computed, defineAsyncComponent, nextTick, ref, watch } from "vue";
import { useI18n } from "../composables/useI18n.js";
import { NButton, NEmpty, NSpace, NSpin, NTag, NText, NRadioButton, NRadioGroup } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
const ComparePdfPreview = defineAsyncComponent(() => import("./ComparePdfPreview.vue"));
import { fetchDocumentFileBlob } from "../api/documents.js";
import { fetchCompareDocumentContent } from "../api/compare.js";
import {
  PREVIEW_KIND,
  isStructuredOfficePreviewKind,
  previewKindLabel,
} from "../utils/documentPreview.js";
import {
  loadOfficeStructuredPreview,
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
  width: { type: [Number, String], default: "min(960px, 96vw)" },
  viewportHeight: { type: String, default: "min(45vh, 480px)" },
  /** PDF 预览缩放：width 按弹窗宽度铺满（竖版文档可读性更好）；page 整页缩放进视口 */
  pdfFitMode: { type: String, default: "width" },
});

const emit = defineEmits(["update:show", "download"]);

const { t } = useI18n();

const loading = ref(false);
const error = ref("");
const previewKind = ref(PREVIEW_KIND.UNSUPPORTED);
const objectUrl = ref("");
const textContent = ref("");
const textFallback = ref("");
const previewViewMode = ref("pdf");
const wordHtml = ref("");
const previewLoadToken = ref(0);
const pdfPage = ref(1);
const pdfNumPages = ref(1);

const showTextFallback = computed(
  () => previewKind.value === PREVIEW_KIND.PDF && Boolean(textFallback.value?.trim()),
);

const visible = computed({
  get: () => props.show,
  set: (value) => emit("update:show", value),
});

const modalTitle = computed(() => {
  if (props.previewTitle) return props.previewTitle;
  return t("documents.detail.preview");
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
  textFallback.value = "";
  previewViewMode.value = "pdf";
  wordHtml.value = "";
  pdfPage.value = 1;
  pdfNumPages.value = 1;
  error.value = "";
  previewKind.value = PREVIEW_KIND.UNSUPPORTED;
  loading.value = false;
}

async function loadPdfTextFallback(documentId, versionId) {
  if (!documentId || !versionId) return;
  try {
    const content = await fetchCompareDocumentContent(documentId, versionId);
    const text = String(content?.full_text || "").trim();
    if (text) {
      textFallback.value = text;
    }
  } catch {
    /* 解析文本不可用时仅展示 PDF */
  }
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
          error.value = t("documents.detail.previewNoFile");
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
        error.value = t("documents.detail.previewTextEmpty");
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
      error.value = t("documents.detail.previewWordEmpty");
      return;
    }

    if (
      previewKind.value === PREVIEW_KIND.EXCEL ||
      previewKind.value === PREVIEW_KIND.PRESENTATION
    ) {
      const { html, text } = await loadOfficeStructuredPreview(blob, {
        documentId: props.documentId,
        versionId: props.version?.id || null,
        fileName,
        mimeType,
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
      error.value = t("documents.detail.previewOfficeEmpty");
      return;
    }

    if (previewKind.value === PREVIEW_KIND.UNSUPPORTED) {
      error.value = t("documents.detail.previewUnsupported");
      return;
    }

    if (previewKind.value === PREVIEW_KIND.PDF) {
      objectUrl.value = URL.createObjectURL(
        blob.type === "application/pdf"
          ? blob
          : new Blob([blob], { type: "application/pdf" }),
      );
      if (useDocumentSource.value && props.documentId && props.version?.id) {
        void loadPdfTextFallback(props.documentId, props.version.id);
      }
      return;
    }

    objectUrl.value = URL.createObjectURL(blob);
  } catch (e) {
    if (token === previewLoadToken.value) {
      error.value = e?.message || t("documents.detail.previewLoadFailed");
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

function onPdfReady({ numPages }) {
  pdfNumPages.value = Math.max(1, Number(numPages) || 1);
  if (pdfPage.value > pdfNumPages.value) {
    pdfPage.value = 1;
  }
}

function goPdfPage(delta) {
  const next = pdfPage.value + delta;
  if (next >= 1 && next <= pdfNumPages.value) {
    pdfPage.value = next;
  }
}

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
      <n-space align="center" :size="10">
        <n-tag size="small" :bordered="false" type="info">{{ kindLabel }}</n-tag>
        <n-radio-group
          v-if="showTextFallback"
          v-model:value="previewViewMode"
          size="small"
        >
          <n-radio-button value="pdf">PDF</n-radio-button>
          <n-radio-button value="text">文本</n-radio-button>
        </n-radio-group>
        <n-space
          v-if="previewKind === PREVIEW_KIND.PDF && objectUrl && previewViewMode === 'pdf' && pdfNumPages > 1"
          align="center"
          :size="6"
        >
          <n-button size="tiny" :disabled="pdfPage <= 1" @click="goPdfPage(-1)">上一页</n-button>
          <n-text depth="3">{{ pdfPage }} / {{ pdfNumPages }}</n-text>
          <n-button size="tiny" :disabled="pdfPage >= pdfNumPages" @click="goPdfPage(1)">下一页</n-button>
        </n-space>
      </n-space>
    </div>

    <n-spin :show="loading" class="document-preview-modal__spin" local>
      <div
        class="document-preview-modal__viewport"
        :class="{ 'document-preview-modal__viewport--pdf': previewKind === PREVIEW_KIND.PDF && previewViewMode === 'pdf' }"
      >
        <ComparePdfPreview
          v-if="previewKind === PREVIEW_KIND.PDF && objectUrl && previewViewMode === 'pdf'"
          :key="objectUrl"
          :src="objectUrl"
          :page="pdfPage"
          :fit-mode="pdfFitMode"
          class="document-preview-modal__pdf"
          @ready="onPdfReady"
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
        <pre
          v-else-if="
            (previewKind === PREVIEW_KIND.PDF && previewViewMode === 'text' && textFallback) ||
            (previewKind === PREVIEW_KIND.TEXT && textContent)
          "
          class="document-preview-modal__text"
        >{{
          previewKind === PREVIEW_KIND.PDF ? textFallback : textContent
        }}</pre>
        <div
          v-else-if="isStructuredOfficePreviewKind(previewKind) && wordHtml"
          class="document-preview-modal__word"
          v-html="wordHtml"
        />
        <n-empty
          v-else-if="error"
          :description="t('documents.detail.previewLoadFailed')"
          class="document-preview-modal__empty"
        >
          <template #extra>
            <n-text depth="3">{{ error }}</n-text>
          </template>
        </n-empty>
        <n-empty
          v-else-if="previewKind === PREVIEW_KIND.UNSUPPORTED && !loading"
          :description="t('documents.detail.previewUnsupported')"
          class="document-preview-modal__empty"
        >
          <template #extra>
            <n-text depth="3">{{ t("documents.detail.previewDownloadHint") }}</n-text>
          </template>
        </n-empty>
        <n-empty
          v-else-if="!loading"
          :description="t('documents.detail.previewContentEmpty')"
          class="document-preview-modal__empty"
        >
          <template #extra>
            <n-text depth="3">{{ t("documents.detail.previewRetryHint") }}</n-text>
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
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.document-preview-modal__spin :deep(.n-spin-container),
.document-preview-modal__spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.document-preview-modal__viewport {
  display: flex;
  flex: 0 1 auto;
  align-self: center;
  align-items: stretch;
  justify-content: center;
  aspect-ratio: 210 / 297;
  width: min(720px, 100%, calc(v-bind(viewportHeight) * 210 / 297));
  max-height: v-bind(viewportHeight);
  min-height: 0;
  border-radius: calc(var(--platform-radius-sm) + 4px);
  border: 1px solid var(--platform-border);
  background: color-mix(in srgb, var(--platform-text) 3%, transparent);
  overflow: hidden;
}

.document-preview-modal__viewport--pdf {
  align-self: stretch;
  width: 100%;
  flex: 1 1 0;
  min-height: 0;
  max-height: none;
  height: auto;
  aspect-ratio: unset;
  overflow: hidden;
}

.document-preview-modal__pdf {
  flex: 1;
  width: 100%;
  min-height: 0;
}

.document-preview-modal__frame {
  width: 100%;
  height: 100%;
  min-height: 0;
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
/* Naive UI card preset 将 attrs.class 合并在 .n-card.n-modal 同一节点，勿用 .n-modal .n-card 后代选择器 */
.n-card.n-modal.document-preview-modal.admin-form-modal {
  max-height: calc(100dvh - 32px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.n-card.n-modal.document-preview-modal.admin-form-modal > .n-card-header {
  flex-shrink: 0;
}

.n-card.n-modal.document-preview-modal.admin-form-modal > .n-card-content,
.n-card.n-modal.document-preview-modal.admin-form-modal > .n-card__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.n-card.n-modal.document-preview-modal.admin-form-modal > .n-card__footer {
  flex-shrink: 0;
}

.n-card.n-modal.document-preview-modal.admin-form-modal .admin-form-modal__body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
