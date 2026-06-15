<script setup>
import { computed, ref, watch } from "vue";
import { NButton, NEmpty, NSpace, NSpin, NTag, NText } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import ComparePdfPreview from "./ComparePdfPreview.vue";
import { fetchDocumentFileBlob } from "../api/documents.js";
import {
  PREVIEW_KIND,
  previewKindLabel,
  resolveDocumentPreviewKind,
} from "../utils/documentPreview.js";

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
  width: { type: [Number, String], default: "min(1200px, 96vw)" },
  viewportHeight: { type: String, default: "min(90vh, 980px)" },
});

const emit = defineEmits(["update:show", "download"]);

const loading = ref(false);
const error = ref("");
const previewKind = ref(PREVIEW_KIND.UNSUPPORTED);
const objectUrl = ref("");
const textContent = ref("");

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
  error.value = "";
  previewKind.value = PREVIEW_KIND.UNSUPPORTED;
  loading.value = false;
}

async function loadPreview() {
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
      if (!props.documentId || !ver?.id || !ver.uploaded) return;
      fileName = ver.file_name || "";
      mimeType = ver.mime_type || "";
      blob = await fetchDocumentFileBlob(props.documentId, ver.id);
    }

    previewKind.value = resolveDocumentPreviewKind(fileName, mimeType);

    if (previewKind.value === PREVIEW_KIND.TEXT) {
      textContent.value = await blob.text();
      return;
    }

    if (previewKind.value === PREVIEW_KIND.UNSUPPORTED) {
      return;
    }

    objectUrl.value = URL.createObjectURL(blob);
  } catch (e) {
    error.value = e?.message || "预览加载失败";
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.show, props.version?.id, props.blobLoader, props.previewFileName],
  ([open]) => {
    if (open) loadPreview();
  }
);

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
    @after-leave="onAfterLeave"
  >
    <div class="document-preview-modal__toolbar">
      <n-tag size="small" :bordered="false" type="info">{{ kindLabel }}</n-tag>
    </div>

    <n-spin :show="loading" class="document-preview-modal__spin">
      <div class="document-preview-modal__viewport">
        <ComparePdfPreview
          v-if="previewKind === PREVIEW_KIND.PDF && objectUrl"
          :key="objectUrl"
          :src="objectUrl"
          fit-mode="page"
          class="document-preview-modal__pdf"
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
  margin-bottom: 12px;
}

.document-preview-modal__spin {
  width: 100%;
}

.document-preview-modal__spin :deep(.n-spin-content) {
  min-height: v-bind(viewportHeight);
}

.document-preview-modal__viewport {
  display: flex;
  align-items: stretch;
  justify-content: center;
  height: v-bind(viewportHeight);
  min-height: v-bind(viewportHeight);
  border-radius: calc(var(--platform-radius-sm) + 4px);
  border: 1px solid var(--platform-border);
  background: color-mix(in srgb, var(--platform-text) 3%, transparent);
  overflow: hidden;
}

.document-preview-modal__pdf {
  flex: 1;
  width: 100%;
  min-height: 0;
  height: 100%;
}

.document-preview-modal__frame {
  width: 100%;
  min-height: v-bind(viewportHeight);
  border: 0;
  background: #fff;
}

.document-preview-modal__image {
  max-width: 100%;
  max-height: v-bind(viewportHeight);
  object-fit: contain;
  margin: auto;
  padding: 16px;
}

.document-preview-modal__text {
  width: 100%;
  max-height: v-bind(viewportHeight);
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

.document-preview-modal__empty {
  margin: auto;
  padding: 32px 16px;
}
</style>
