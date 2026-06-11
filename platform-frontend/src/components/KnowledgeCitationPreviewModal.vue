<script setup>
import { computed, ref, watch } from "vue";
import { NButton, NEmpty, NSpace, NSpin, NTag, NText } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import {
  citationPageLabel,
  fetchKnowledgeCitationImageBlob } from "../utils/knowledgeCitation.js";
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
  if (!c) return "引用溯源";
  return `引用 [${c.index}]`;
});

const pageLabel = computed(() => citationPageLabel(props.citation));

const hasImageId = computed(() => Boolean(props.citation?.image_id));

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

async function loadCitationImage(imageId) {
  resetImageState();
  if (!imageId) return;
  imageLoading.value = true;
  try {
    const blob = await fetchKnowledgeCitationImageBlob(imageId);
    imageObjectUrl.value = URL.createObjectURL(blob);
    imageOk.value = true;
  } catch (e) {
    imageError.value = e?.message || "无法加载原文截图，请查看下方片段或打开文档详情";
  } finally {
    imageLoading.value = false;
  }
}

watch(
  () => [props.show, props.citation?.image_id],
  ([open, imageId]) => {
    if (!open) {
      resetImageState();
      return;
    }
    if (imageId) loadCitationImage(imageId);
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
    width="min(920px, 96vw)"
    :show-footer="false"
  >
    <div v-if="citation" class="knowledge-citation-preview">
      <div class="knowledge-citation-preview__meta">
        <n-tag v-if="pageLabel" size="small" type="info" :bordered="false">{{ pageLabel }}</n-tag>
        <n-text v-if="citation.score != null" depth="3" class="knowledge-citation-preview__score">
          相关度 {{ Math.round(Number(citation.score) <= 1 ? Number(citation.score) * 100 : Number(citation.score)) }}%
        </n-text>
      </div>

      <div v-if="hasImageId" class="knowledge-citation-preview__image-wrap">
        <n-spin :show="imageLoading">
          <img
            v-if="imageObjectUrl"
            :src="imageObjectUrl"
            class="knowledge-citation-preview__image"
            alt="引用原文截图"
          />
        </n-spin>
        <n-empty
          v-if="imageError && !imageOk"
          size="small"
          :description="imageError"
          class="knowledge-citation-preview__image-fallback"
        />
      </div>

      <div v-if="snippetHtml" class="knowledge-citation-preview__snippet" v-html="snippetHtml" />

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

.knowledge-citation-preview__score {
  font-size: 12px;
}

.knowledge-citation-preview__image-wrap {
  border: 1px solid var(--platform-border);
  border-radius: 8px;
  background: #f8fafc;
  overflow: auto;
  max-height: min(52vh, 520px);
}

.knowledge-citation-preview__image {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
}

.knowledge-citation-preview__image-fallback {
  padding: 16px 0;
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
  background: rgba(250, 204, 21, 0.45);
  padding: 0 2px;
  border-radius: 2px;
}

.knowledge-citation-preview__actions {
  margin-top: 4px;
}
</style>
