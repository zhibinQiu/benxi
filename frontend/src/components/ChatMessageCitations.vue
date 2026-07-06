<script setup>
import { ref } from "vue";
import { useI18n } from "../composables/useI18n.js";
import { formatCitationSnippet } from "../utils/knowledgeCitation.js";

const props = defineProps({
  citations: { type: Array, default: () => [] },
  question: { type: String, default: "" },
  /** 点击引用编号/标题时打开溯源弹窗（知识检索、报告生成） */
  previewOnClick: { type: Boolean, default: false },
  showTitle: { type: Boolean, default: true },
  hint: { type: String, default: "" },
});

const emit = defineEmits(["open-citation", "open-document"]);

const { t } = useI18n();
const expanded = ref({});

function toggle(index) {
  if (props.previewOnClick) return;
  expanded.value[index] = !expanded.value[index];
}

function isExpanded(citation) {
  if (props.previewOnClick) return false;
  return Boolean(expanded.value[citation.index]);
}

function formatScore(score) {
  if (score == null || Number.isNaN(Number(score))) return "";
  const n = Number(score);
  if (n <= 1) return `${Math.round(n * 100)}%`;
  return `${n.toFixed(1)}`;
}

function snippetHtml(citation) {
  return formatCitationSnippet(
    citation?.snippet || "",
    props.question,
    citation?.highlight_terms
  );
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
    <div v-if="showTitle" class="chat-citations-title">{{ t("knowledgeSearch.citations.title") }}</div>
    <p v-if="hint" class="chat-citations-hint">{{ hint }}</p>
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
        <a
          v-else-if="c.url"
          class="chat-citation-doc chat-citation-doc--link"
          :href="c.url"
          target="_blank"
          rel="noopener noreferrer"
          @click.stop
        >
          {{ c.title }}
        </a>
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
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--platform-accent-border-soft);
}

.chat-citations-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--platform-text-secondary);
  margin-bottom: 10px;
}

.chat-citations-hint {
  margin: 0 0 10px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--platform-text-tertiary);
}

.chat-citation-item + .chat-citation-item {
  margin-top: 10px;
}

.chat-citation-head {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}

.chat-citation-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0;
  border: none;
  background: none;
  color: var(--platform-accent);
  font-size: 14px;
  cursor: pointer;
}

.chat-citation-toggle--preview {
  cursor: pointer;
}

.chat-citation-num {
  font-weight: 600;
}

.chat-citation-score {
  font-size: 13px;
  color: var(--platform-text-tertiary);
}

.chat-citation-chevron {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.chat-citation-doc {
  font-size: 14px;
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
  margin-top: 7px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--platform-accent-muted);
  border: 1px solid var(--platform-accent-border-soft);
  font-size: 14px;
  line-height: 1.6;
  color: var(--platform-text);
}

.chat-citation-snippet :deep(mark.cite-hl),
.chat-citation-snippet :deep(em) {
  font-style: normal;
  color: #713f12;
  background: rgba(234, 179, 8, 0.55);
  padding: 0 4px;
  border-radius: 4px;
  font-weight: 700;
}
</style>
