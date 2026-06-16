<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { NSpin, NTag, NText } from "naive-ui";
import {
  citationCanPreviewImage,
  citationPageLabel,
  fetchKnowledgeCitationPreviewBlob,
  formatCitationSnippet,
} from "../utils/knowledgeCitation.js";
import { formatDocumentFormatLabel } from "../constants/documentUpload.js";
import { useI18n } from "../composables/useI18n.js";
import { navigateWithReturn } from "../utils/navigationReturn.js";
import { useRoute, useRouter } from "vue-router";

const props = defineProps({
  citation: { type: Object, required: true },
  question: { type: String, default: "" },
});

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

const imageLoading = ref(false);
const imageError = ref("");
const imageObjectUrl = ref("");

const pageLabel = computed(() => citationPageLabel(props.citation, t));

const fileName = computed(() => {
  const name = String(props.citation?.file_name || "").trim();
  if (name) return name;
  return String(props.citation?.title || "").trim();
});

const fileTypeLabel = computed(() =>
  formatDocumentFormatLabel(props.citation?.file_format)
);

const snippetHtml = computed(() =>
  formatCitationSnippet(
    props.citation?.snippet || "",
    props.question,
    props.citation?.highlight_terms
  )
);

const canPreviewImage = computed(() => citationCanPreviewImage(props.citation));

const textOnlyHint = computed(() => {
  if (props.citation?.source === "pageindex") {
    return t("knowledgeSearch.citations.textOnlyHintPageindex");
  }
  return t("knowledgeSearch.citations.textOnlyHint");
});

const relevanceLabel = computed(() => {
  const score = props.citation?.score;
  if (score == null || Number.isNaN(Number(score))) return "";
  const n = Number(score);
  const pct = n <= 1 ? Math.round(n * 100) : Math.round(n);
  return t("knowledgeSearch.citations.relevance", { score: `${pct}%` });
});

function cleanupImage() {
  if (imageObjectUrl.value) {
    URL.revokeObjectURL(imageObjectUrl.value);
    imageObjectUrl.value = "";
  }
  imageLoading.value = false;
  imageError.value = "";
}

async function loadImage(citation) {
  cleanupImage();
  if (!citation || !citationCanPreviewImage(citation)) {
    return;
  }
  imageLoading.value = true;
  try {
    const blob = await fetchKnowledgeCitationPreviewBlob(citation);
    imageObjectUrl.value = URL.createObjectURL(blob);
  } catch (e) {
    const fallback =
      props.citation?.source === "pageindex"
        ? t("knowledgeSearch.citations.loadFailedPageindex")
        : t("knowledgeSearch.citations.loadFailed");
    imageError.value = e?.message || fallback;
  } finally {
    imageLoading.value = false;
  }
}

watch(
  () => props.citation,
  (citation) => {
    if (citation) loadImage(citation);
    else cleanupImage();
  },
  { immediate: true, deep: true }
);

onBeforeUnmount(cleanupImage);

function openDocument() {
  const id = props.citation?.document_id;
  if (!id) return;
  navigateWithReturn(router, { name: "document-detail", params: { id } }, route);
}
</script>

<template>
  <article class="knowledge-citation-card">
    <header class="knowledge-citation-card__head">
      <span class="knowledge-citation-card__index">[{{ citation.index }}]</span>
      <button
        v-if="citation.document_id"
        type="button"
        class="knowledge-citation-card__title"
        @click="openDocument"
      >
        {{ citation.title || t("knowledgeSearch.citations.openDocument") }}
      </button>
      <span v-else class="knowledge-citation-card__title knowledge-citation-card__title--plain">
        {{ citation.title || "—" }}
      </span>
      <n-text v-if="relevanceLabel" depth="3" class="knowledge-citation-card__score">
        {{ relevanceLabel }}
      </n-text>
    </header>

    <div v-if="snippetHtml" class="knowledge-citation-card__snippet" v-html="snippetHtml" />

    <p v-if="!canPreviewImage && snippetHtml" class="knowledge-citation-card__text-only">
      {{ textOnlyHint }}
    </p>

    <div v-if="canPreviewImage" class="knowledge-citation-card__shot">
      <n-spin :show="imageLoading">
        <img
          v-if="imageObjectUrl"
          :src="imageObjectUrl"
          class="knowledge-citation-card__shot-img"
          :class="{
            'knowledge-citation-card__shot-img--page': citation.source === 'pageindex',
          }"
          :alt="t('knowledgeSearch.citations.screenshotAlt')"
        />
        <div v-else-if="!imageLoading && imageError" class="knowledge-citation-card__shot-empty">
          {{ imageError }}
        </div>
      </n-spin>
    </div>

    <footer v-if="fileName || pageLabel || fileTypeLabel !== '—'" class="knowledge-citation-card__foot">
      <button
        v-if="fileName && citation.document_id"
        type="button"
        class="knowledge-citation-card__file"
        :title="fileName"
        @click="openDocument"
      >
        {{ fileName }}
      </button>
      <span v-else-if="fileName" class="knowledge-citation-card__file knowledge-citation-card__file--plain">
        {{ fileName }}
      </span>
      <span v-if="pageLabel" class="knowledge-citation-card__meta-sep" aria-hidden="true">·</span>
      <span v-if="pageLabel" class="knowledge-citation-card__page">{{ pageLabel }}</span>
      <n-tag
        v-if="citation.file_format"
        size="small"
        :bordered="false"
        class="knowledge-citation-card__type"
      >
        {{ fileTypeLabel }}
      </n-tag>
    </footer>
  </article>
</template>

<style scoped>
.knowledge-citation-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border-radius: calc(var(--platform-radius-sm) + 4px);
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  box-sizing: border-box;
  width: 100%;
}

.knowledge-citation-card__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.knowledge-citation-card__index {
  font-size: 13px;
  font-weight: 700;
  color: var(--platform-accent-pressed);
}

.knowledge-citation-card__title {
  margin: 0;
  padding: 0;
  border: 0;
  background: none;
  font-size: 14px;
  font-weight: 600;
  color: var(--platform-text);
  cursor: pointer;
  text-align: left;
}

.knowledge-citation-card__title:hover {
  color: var(--platform-accent-pressed);
  text-decoration: underline;
}

.knowledge-citation-card__title--plain {
  cursor: default;
}

.knowledge-citation-card__score {
  margin-left: auto;
  font-size: 12px;
}

.knowledge-citation-card__snippet {
  font-size: 13px;
  line-height: 1.65;
  color: var(--platform-text-secondary);
}

.knowledge-citation-card__snippet :deep(mark.cite-hl),
.knowledge-citation-card__snippet :deep(em) {
  font-style: normal;
  color: #713f12;
  background: rgba(234, 179, 8, 0.55);
  padding: 0 3px;
  border-radius: 3px;
  font-weight: 700;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}

.knowledge-citation-card__text-only {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--platform-text-secondary);
}

.knowledge-citation-card__shot {
  border-radius: 8px;
  border: 1px solid var(--platform-border);
  background: #eef2f7;
  overflow: hidden;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.knowledge-citation-card__shot-img {
  display: block;
  width: 100%;
  height: auto;
  max-height: 420px;
  object-fit: contain;
  outline: 3px solid #eab308;
  outline-offset: 2px;
  box-shadow: 0 0 0 4px rgba(234, 179, 8, 0.28);
}

.knowledge-citation-card__shot-img--page {
  outline: none;
  box-shadow: none;
}

.knowledge-citation-card__shot-empty {
  padding: 24px 16px;
  font-size: 12px;
  color: var(--platform-text-secondary);
  text-align: center;
}

.knowledge-citation-card__foot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 8px;
  margin-top: 2px;
  padding-top: 10px;
  border-top: 1px solid color-mix(in srgb, var(--platform-border) 75%, transparent);
  font-size: 12px;
  line-height: 1.4;
  color: var(--platform-text-secondary);
}

.knowledge-citation-card__file {
  margin: 0;
  padding: 0;
  border: 0;
  background: none;
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
  cursor: pointer;
  text-align: left;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-citation-card__file:hover {
  color: var(--platform-accent-pressed);
  text-decoration: underline;
}

.knowledge-citation-card__file--plain {
  cursor: default;
  font-weight: 500;
  color: var(--platform-text);
}

.knowledge-citation-card__meta-sep {
  opacity: 0.45;
  user-select: none;
}

.knowledge-citation-card__page {
  flex-shrink: 0;
  color: var(--platform-text-secondary);
}

.knowledge-citation-card__type {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
</style>
