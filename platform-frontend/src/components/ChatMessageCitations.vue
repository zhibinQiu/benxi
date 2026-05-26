<script setup>
import { ref } from "vue";

const props = defineProps({
  citations: { type: Array, default: () => [] },
});

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
</script>

<template>
  <div v-if="citations.length" class="chat-citations">
    <div class="chat-citations-title">引用来源</div>
    <div
      v-for="c in citations"
      :key="`${c.index}-${c.document_id || c.title}`"
      class="chat-citation-item"
    >
      <button type="button" class="chat-citation-head" @click="toggle(c.index)">
        <span class="chat-citation-num">[{{ c.index }}]</span>
        <span class="chat-citation-doc">{{ c.title }}</span>
        <span v-if="formatScore(c.score)" class="chat-citation-score">
          相关度 {{ formatScore(c.score) }}
        </span>
        <span class="chat-citation-chevron">{{ expanded[c.index] ? "▾" : "▸" }}</span>
      </button>
      <p v-if="c.snippet && expanded[c.index]" class="chat-citation-snippet">
        {{ c.snippet }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.chat-citations {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(13, 148, 136, 0.15);
}

.chat-citations-title {
  font-size: 12px;
  font-weight: 600;
  color: #0f766e;
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
  text-align: left;
  font-size: 12px;
  color: #334155;
  background: rgba(13, 148, 136, 0.06);
  border: 1px solid rgba(13, 148, 136, 0.12);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.chat-citation-head:hover {
  background: rgba(13, 148, 136, 0.1);
}

.chat-citation-num {
  font-weight: 600;
  color: #0d9488;
}

.chat-citation-doc {
  flex: 1;
  min-width: 0;
  font-weight: 500;
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
</style>
