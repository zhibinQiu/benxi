<script setup>
import { ref } from "vue";

defineProps({
  citations: { type: Array, default: () => [] },
  /** 点击引用编号/标题时打开溯源弹窗（知识检索） */
  previewOnClick: { type: Boolean, default: false },
});

const emit = defineEmits(["open-citation", "open-document"]);

const expanded = ref({});

function toggle(index) {
  expanded.value[index] = !expanded.value[index];
}

function formatScore(score) {
  if (score == null || Number.isNaN(Number(score))) return "";
  const n = Number(score);
  if (n <= 1) return `${Math.round(n * 100)}%`;
  return `${n.toFixed(1)}`;
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
    <div class="chat-citations-title">引用来源</div>
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
            相关度 {{ formatScore(c.score) }}
          </span>
          <span v-if="!previewOnClick" class="chat-citation-chevron">
            {{ expanded[c.index] ? "▾" : "▸" }}
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
          相关度 {{ formatScore(c.score) }}
        </span>
      </div>
      <p
        v-if="!previewOnClick && c.snippet && expanded[c.index]"
        class="chat-citation-snippet"
        v-html="c.snippet"
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
  color: var(--platform-accent-pressed);
  margin-bottom: 8px;
}

.chat-citation-item {
  margin-bottom: 6px;
}

.chat-citation-item:last-child {
  margin-bottom: 0;
}

.chat-citation-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  font-size: 12px;
  color: #334155;
  background: var(--platform-accent-muted);
  border: 1px solid var(--platform-accent-border-soft);
  border-radius: 8px;
}

.chat-citation-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.chat-citation-toggle--preview:hover .chat-citation-num {
  text-decoration: underline;
}

.chat-citation-num {
  font-weight: 600;
  color: var(--platform-accent);
}

.chat-citation-doc {
  flex: 1;
  min-width: 0;
  font-weight: 500;
  text-align: left;
}

.chat-citation-doc--link {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--platform-accent);
  cursor: pointer;
}

.chat-citation-doc--link:hover {
  text-decoration: underline;
}

.chat-citation-score {
  font-size: 11px;
  color: #64748b;
}

.chat-citation-chevron {
  color: #94a3b8;
  font-size: 10px;
}

.chat-citation-snippet {
  margin: 6px 0 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.55;
  color: #64748b;
  background: #f8fafc;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-citation-snippet :deep(em) {
  font-style: normal;
  background: rgba(250, 204, 21, 0.45);
  padding: 0 1px;
}
</style>
