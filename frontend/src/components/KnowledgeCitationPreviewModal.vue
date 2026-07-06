<script setup>
import { computed, ref, watch } from "vue";
import { NButton, NEmpty, NSpace, NSpin, NTag, NText } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import { useI18n } from "../composables/useI18n.js";
import {
  citationCanPreviewImage,
  citationPageLabel,
  citationPreviewCacheKey,
  fetchKnowledgeCitationPreviewBlob,
  formatCitationSnippet,
  isCitationPreviewUnavailableError,
} from "../utils/knowledgeCitation.js";
import { navigateWithReturn } from "../utils/navigationReturn.js";
import { useRoute, useRouter } from "vue-router";

const props = defineProps({
  show: { type: Boolean, default: false },
  citation: { type: Object, default: null },
  question: { type: String, default: "" },
});

const emit = defineEmits(["update:show"]);

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const imageLoading = ref(false);
const imageError = ref("");
const imageOk = ref(false);
const imageObjectUrl = ref("");
let loadSeq = 0;
let loadAbort = null;

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

const snippetHtml = computed(() =>
  formatCitationSnippet(
    props.citation?.snippet || "",
    props.question,
    props.citation?.highlight_terms
  )
);

const canPreviewImage = computed(() => citationCanPreviewImage(props.citation));

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
  loadAbort?.abort();
  const ac = new AbortController();
  loadAbort = ac;
  const seq = ++loadSeq;
  resetImageState();
  if (!citation || !citationCanPreviewImage(citation)) {
    return;
  }
  imageLoading.value = true;
  try {
    const blob = await fetchKnowledgeCitationPreviewBlob(citation, { signal: ac.signal });
    if (seq !== loadSeq || ac.signal.aborted) return;
    imageObjectUrl.value = URL.createObjectURL(blob);
    imageOk.value = true;
  } catch (e) {
    if (ac.signal.aborted || seq !== loadSeq) return;
    if (isCitationPreviewUnavailableError(e)) {
      imageError.value = t("knowledgeSearch.citations.textOnlyHint");
      return;
    }
    imageError.value = e?.message || t("knowledgeSearch.citations.loadFailed");
  } finally {
    if (seq === loadSeq) {
      imageLoading.value = false;
    }
  }
}

watch(
  () => [props.show, citationPreviewCacheKey(props.citation)],
  ([open, key]) => {
    if (!open) {
      loadAbort?.abort();
      resetImageState();
      return;
    }
    if (key) loadCitationPreview(props.citation);
    else resetImageState();
  }
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
        <n-text v-if="!canPreviewImage" depth="3" class="knowledge-citation-preview__text-only">
          {{ t("knowledgeSearch.citations.textOnlyHint") }}
        </n-text>
      </div>

      <div v-if="canPreviewImage" class="knowledge-citation-preview__image-wrap">
        <n-spin :show="imageLoading" local>
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
          :description="imageError || t('knowledgeSearch.citations.loadFailed')"
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
  gap: 14px;
}

.knowledge-citation-preview__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.knowledge-citation-preview__hint {
  font-size: 14px;
  flex: 1;
  min-width: 240px;
}

.knowledge-citation-preview__score {
  font-size: 14px;
}

.knowledge-citation-preview__snippet-block {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.knowledge-citation-preview__snippet-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--platform-text-secondary);
}

.knowledge-citation-preview__snippet {
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--platform-accent-muted);
  border: 1px solid var(--platform-accent-border-soft);
  font-size: 16px;
  line-height: 1.65;
  color: var(--platform-text);
  max-height: 144px;
  overflow: auto;
}

.knowledge-citation-preview__snippet :deep(mark.cite-hl),
.knowledge-citation-preview__snippet :deep(em) {
  font-style: normal;
  color: #713f12;
  background: rgba(234, 179, 8, 0.55);
  padding: 0 4px;
  border-radius: 4px;
  font-weight: 700;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}

.knowledge-citation-preview__text-only {
  font-size: 14px;
  line-height: 1.5;
}

.knowledge-citation-preview__image-wrap {
  border: 1px solid var(--platform-border);
  border-radius: 10px;
  background: #eef2f7;
  overflow: auto;
  max-height: min(68vh, 768px);
  min-height: 288px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 14px;
}

.knowledge-citation-preview__image {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  border-radius: 5px;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.1);
  outline: 4px solid #eab308;
  outline-offset: 2px;
}

.knowledge-citation-preview__image-fallback {
  padding: 29px 19px;
}

.knowledge-citation-preview__actions {
  margin-top: 5px;
}
</style>
