<script setup>
import { ref } from "vue";
import { useI18n } from "../composables/useI18n.js";
import { formatCitationSnippet } from "../utils/knowledgeCitation.js";

const props = defineProps({
  citations: { type: Array, default: () => [] },
  /** 点击引用编号/标题时打开溯源弹窗（知识检索） */
  previewOnClick: { type: Boolean, default: false },
});

const emit = defineEmits(["open-citation", "open-document"]);

const { t } = useI18n();
const expanded = ref({});

function toggle(index) {
  if (props.previewOnClick) return;
  expanded.value[index] = !expanded.value[index];
}

function isExpanded(citation) {
  if (props.previewOnClick) return Boolean(citation?.snippet);
  return Boolean(expanded.value[citation.index]);
}

function formatScore(score) {
  if (score == null || Number.isNaN(Number(score))) return "";
  const n = Number(score);
  if (n <= 1) return `${Math.round(n * 100)}%`;
  return `${n.toFixed(1)}`;
}

function snippetHtml(citation) {
  return formatCitationSnippet(citation?.snippet || "");
}

function openCitation(citation, event) {
  event?.stopPropagation?.();
  if (!citation) return;
  emit("open-citation", citation);
}

function openDocument(citation, event) {
  event?.stopPropagation?.();
  if (!citation?.document_id) return;
  emit("open-document", citation);
}
</script>

<template>
  <div v-if="citations.length" class="chat-citations">
    <div class="chat-citations-title">{{ t("knowledgeSearch.citations.title") }}</div>
    <div
      v-for="c in citations"
      :key="`${c.index}-${c.document_id || c.title}`"
      class="chat-citation-item"
    >
      <div class="chat-citation-head">
        <button
          type="button"
          class="chat-citation-toggle"
          :class="{ 'chat-citation-toggle--preview': previewOnClick }"
          @click="previewOnClick ? openCitation(c, $event) : toggle(c.index)"
        >
          <span class="chat-citation-num">[{{ c.index }}]</span>
          <span v-if="!previewOnClick && formatScore(c.score)" class="chat-citation-score">
            {{ t("knowledgeSearch.citations.relevance", { score: formatScore(c.score) }) }}
          </span>
          <span v-if="!previewOnClick" class="chat-citation-chevron">
            {{ isExpanded(c) ? "▾" : "▸" }}
          </span>
        </button>
        <button
          v-if="previewOnClick"
          type="button"
          class="chat-citation-doc chat-citation-doc--link"
          @click="openCitation(c, $event)"
        >
          {{ c.title }}
        </button>
        <button
          v-else-if="c.document_id"
          type="button"
          class="chat-citation-doc chat-citation-doc--link"
          @click="openDocument(c, $event)"
        >
          {{ c.title }}
        </button>
        <span v-else class="chat-citation-doc">{{ c.title }}</span>
        <span v-if="previewOnClick && formatScore(c.score)" class="chat-citation-score">
          {{ t("knowledgeSearch.citations.relevance", { score: formatScore(c.score) }) }}
        </span>
      </div>
      <div
        v-if="snippetHtml(c) && isExpanded(c)"
        class="chat-citation-snippet"
        v-html="snippetHtml(c)"
      />
    </div>
  </div>
</template>

<style scoped>
.chat-citations {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--platform-accent-border-soft);
}

.chat-citations-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--platform-text-secondary);
  margin-bottom: 8px;
}

.chat-citation-item + .chat-citation-item {
  margin-top: 8px;
}

.chat-citation-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.chat-citation-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: none;
  background: none;
  color: var(--platform-accent);
  font-size: 12px;
  cursor: pointer;
}

.chat-citation-toggle--preview {
  cursor: pointer;
}

.chat-citation-num {
  font-weight: 600;
}

.chat-citation-score {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}

.chat-citation-chevron {
  font-size: 10px;
  color: var(--platform-text-tertiary);
}

.chat-citation-doc {
  font-size: 12px;
  color: var(--platform-text);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-citation-doc--link {
  padding: 0;
  border: none;
  background: none;
  color: var(--platform-accent);
  cursor: pointer;
  text-align: left;
}

.chat-citation-doc--link:hover {
  text-decoration: underline;
}

.chat-citation-snippet {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--platform-accent-muted);
  border: 1px solid var(--platform-accent-border-soft);
  font-size: 12px;
  line-height: 1.6;
  color: var(--platform-text);
}

.chat-citation-snippet :deep(em) {
  font-style: normal;
  background: rgba(250, 204, 21, 0.5);
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 600;
}
</style>
