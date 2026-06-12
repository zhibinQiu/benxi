<script setup>
import { computed, ref, watch } from "vue";
import { NButton, NEmpty, NSpace, NSpin, NTag, NText } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import { useI18n } from "../composables/useI18n.js";
import {
  citationCanPreviewImage,
  citationPageLabel,
  fetchKnowledgeCitationPreviewBlob,
  formatCitationSnippet,
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
const { t } = useI18n();

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
  if (!c) return t("knowledgeSearch.citations.locateTitle");
  return t("knowledgeSearch.citations.locateTitleIndexed", { index: c.index });
});

const pageLabel = computed(() => citationPageLabel(props.citation, t));

const snippetHtml = computed(() => formatCitationSnippet(props.citation?.snippet || ""));

const relevanceLabel = computed(() => {
  const score = props.citation?.score;
  if (score == null || Number.isNaN(Number(score))) return "";
  const n = Number(score);
  const pct = n <= 1 ? Math.round(n * 100) : Math.round(n);
  return t("knowledgeSearch.citations.relevance", { score: `${pct}%` });
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
    imageError.value = t("knowledgeSearch.citations.noScreenshot");
    return;
  }
  imageLoading.value = true;
  try {
    const blob = await fetchKnowledgeCitationPreviewBlob(citation);
    imageObjectUrl.value = URL.createObjectURL(blob);
    imageOk.value = true;
  } catch (e) {
    imageError.value = e?.message || t("knowledgeSearch.citations.loadFailed");
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
          {{ t("knowledgeSearch.citations.locateHint") }}
        </n-text>
        <n-text v-if="relevanceLabel" depth="3" class="knowledge-citation-preview__score">
          {{ relevanceLabel }}
        </n-text>
      </div>

      <div v-if="snippetHtml" class="knowledge-citation-preview__snippet-block">
        <div class="knowledge-citation-preview__snippet-title">
          {{ t("knowledgeSearch.citations.snippetTitle") }}
        </div>
        <div class="knowledge-citation-preview__snippet" v-html="snippetHtml" />
      </div>

      <div class="knowledge-citation-preview__image-wrap">
        <n-spin :show="imageLoading">
          <img
            v-if="imageObjectUrl"
            :src="imageObjectUrl"
            class="knowledge-citation-preview__image"
            :alt="t('knowledgeSearch.citations.screenshotAlt')"
          />
        </n-spin>
        <n-empty
          v-if="!imageLoading && !imageOk"
          size="small"
          :description="imageError || t('knowledgeSearch.citations.noScreenshot')"
          class="knowledge-citation-preview__image-fallback"
        />
      </div>

      <n-space justify="end" class="knowledge-citation-preview__actions">
        <n-button v-if="citation.document_id" size="small" @click="openDocument">
          {{ t("knowledgeSearch.citations.openDocument") }}
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

.knowledge-citation-preview__snippet-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.knowledge-citation-preview__snippet-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--platform-text-secondary);
}

.knowledge-citation-preview__snippet {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--platform-accent-muted);
  border: 1px solid var(--platform-accent-border-soft);
  font-size: 13px;
  line-height: 1.6;
  color: var(--platform-text);
  max-height: 180px;
  overflow: auto;
}

.knowledge-citation-preview__snippet :deep(em) {
  font-style: normal;
  background: rgba(250, 204, 21, 0.5);
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 600;
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

.knowledge-citation-preview__actions {
  margin-top: 4px;
}
</style>
