<script setup>
import { computed, ref, watch } from "vue";
import { NButton, NEmpty, NSpace, NSpin, NTag, NText } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import {
  citationCanPreviewImage,
  citationPageLabel,
  fetchKnowledgeCitationPreviewBlob,
} from "../utils/knowledgeCitation.js";
import { navigateWithReturn } from "../utils/navigationReturn.js";
import { useRoute, useRouter } from "vue-router";

const props = defineProps({
  show: { type: Boolean, default: false },
  citation: { type: Object, default: null },
});

const emit = defineEmits(["update:show"]);

const route = useRoute();
const router = useRouter();

const imageLoading = ref(false);
const imageError = ref("");
const imageOk = ref(false);
const imageObjectUrl = ref("");

const visible = computed({
  get: () => props.show,
  set: (value) => emit("update:show", value),
});

const modalTitle = computed(() => {
  const c = props.citation;
  if (!c) return "原文定位";
  return `原文定位 [${c.index}]`;
});

const pageLabel = computed(() => citationPageLabel(props.citation));

const snippetHtml = computed(() => {
  const raw = props.citation?.snippet || "";
  if (!raw) return "";
  if (/<em>|<\/em>/i.test(raw)) return raw;
  return raw.replace(/\n/g, "<br/>");
});

function resetImageState() {
  if (imageObjectUrl.value) {
    URL.revokeObjectURL(imageObjectUrl.value);
    imageObjectUrl.value = "";
  }
  imageLoading.value = false;
  imageError.value = "";
  imageOk.value = false;
}

async function loadCitationPreview(citation) {
  resetImageState();
  if (!citation || !citationCanPreviewImage(citation)) {
    imageError.value =
      "暂无原文截图。请确认文档已通过 KnowFlow 成功索引（PDF 解析后会生成切片快照）。";
    return;
  }
  imageLoading.value = true;
  try {
    const blob = await fetchKnowledgeCitationPreviewBlob(citation);
    imageObjectUrl.value = URL.createObjectURL(blob);
    imageOk.value = true;
  } catch (e) {
    imageError.value =
      e?.message ||
      "无法加载原文截图。请确认文档已索引，或在 KnowFlow 中重新解析该 PDF。";
  } finally {
    imageLoading.value = false;
  }
}

watch(
  () => [props.show, props.citation],
  ([open, citation]) => {
    if (!open) {
      resetImageState();
      return;
    }
    if (citation) loadCitationPreview(citation);
    else resetImageState();
  },
  { deep: true }
);

function openDocument() {
  const id = props.citation?.document_id;
  if (!id) return;
  visible.value = false;
  navigateWithReturn(router, { name: "document-detail", params: { id } }, route);
}
</script>

<template>
  <AdminFormModal
    v-model:show="visible"
    :title="modalTitle"
    :subtitle="citation?.title || ''"
    width="min(960px, 96vw)"
    :show-footer="false"
  >
    <div v-if="citation" class="knowledge-citation-preview">
      <div class="knowledge-citation-preview__meta">
        <n-tag v-if="pageLabel" size="small" type="info" :bordered="false">{{ pageLabel }}</n-tag>
        <n-text depth="3" class="knowledge-citation-preview__hint">
          以下为源 PDF 中的引用区域（KnowFlow 切片快照，高亮为检索命中内容）
        </n-text>
        <n-text v-if="citation.score != null" depth="3" class="knowledge-citation-preview__score">
          相关度 {{ Math.round(Number(citation.score) <= 1 ? Number(citation.score) * 100 : Number(citation.score)) }}%
        </n-text>
      </div>

      <div class="knowledge-citation-preview__image-wrap">
        <n-spin :show="imageLoading">
          <img
            v-if="imageObjectUrl"
            :src="imageObjectUrl"
            class="knowledge-citation-preview__image"
            alt="源 PDF 引用区域截图"
          />
        </n-spin>
        <n-empty
          v-if="!imageLoading && !imageOk"
          size="small"
          :description="imageError || '暂无原文截图'"
          class="knowledge-citation-preview__image-fallback"
        />
      </div>

      <details v-if="snippetHtml && !imageOk" class="knowledge-citation-preview__text-fallback">
        <summary>查看提取文本片段</summary>
        <div class="knowledge-citation-preview__snippet" v-html="snippetHtml" />
      </details>

      <n-space justify="end" class="knowledge-citation-preview__actions">
        <n-button v-if="citation.document_id" size="small" @click="openDocument">
          打开文档详情
        </n-button>
      </n-space>
    </div>
  </AdminFormModal>
</template>

<style scoped>
.knowledge-citation-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.knowledge-citation-preview__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.knowledge-citation-preview__hint {
  font-size: 12px;
  flex: 1;
  min-width: 200px;
}

.knowledge-citation-preview__score {
  font-size: 12px;
}

.knowledge-citation-preview__image-wrap {
  border: 1px solid var(--platform-border);
  border-radius: 8px;
  background: #f1f5f9;
  overflow: auto;
  max-height: min(58vh, 560px);
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.knowledge-citation-preview__image {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
}

.knowledge-citation-preview__image-fallback {
  padding: 24px 16px;
}

.knowledge-citation-preview__text-fallback {
  font-size: 12px;
  color: var(--platform-text-secondary);
}

.knowledge-citation-preview__text-fallback summary {
  cursor: pointer;
  user-select: none;
}

.knowledge-citation-preview__snippet {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--platform-accent-muted);
  border: 1px solid var(--platform-accent-border-soft);
  font-size: 13px;
  line-height: 1.6;
  color: var(--platform-text);
  max-height: 160px;
  overflow: auto;
}

.knowledge-citation-preview__snippet :deep(em) {
  font-style: normal;
  background: rgba(250, 204, 21, 0.45);
  padding: 0 2px;
  border-radius: 2px;
}

.knowledge-citation-preview__actions {
  margin-top: 4px;
}
</style>
