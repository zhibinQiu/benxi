<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { renderRichMarkdown } from "../utils/richMarkdown.js";

const props = defineProps({
  content: { type: String, default: "" },
  citations: { type: Array, default: () => [] },
});

const emit = defineEmits(["open-citation"]);

const rootRef = ref(null);

const citationIndexes = computed(() => {
  const set = new Set((props.citations || []).map((c) => Number(c.index)).filter(Boolean));
  return set;
});

const html = computed(() => {
  let text = props.content || "";
  if (!text) return "";
  text = text.replace(/\[(\d{1,2})\]/g, (match, numRaw) => {
    const num = Number(numRaw);
    if (!citationIndexes.value.has(num)) return match;
    return `<button type="button" class="knowledge-cite-mark" data-cite-index="${num}">[${num}]</button>`;
  });
  return renderRichMarkdown(text);
});

function onClick(event) {
  const btn = event.target?.closest?.("[data-cite-index]");
  if (!btn) return;
  event.preventDefault();
  event.stopPropagation();
  const index = Number(btn.dataset.citeIndex);
  if (!index) return;
  emit("open-citation", index);
}

watch(() => props.content, () => nextTick(bindCiteButtons));

onMounted(() => nextTick(bindCiteButtons));
onBeforeUnmount(() => {});

function bindCiteButtons() {
  const root = rootRef.value;
  if (!root) return;
  root.querySelectorAll(".knowledge-cite-mark").forEach((el) => {
    el.setAttribute("type", "button");
  });
}
</script>

<template>
  <div ref="rootRef" class="knowledge-chat-content md-rich" v-html="html" @click="onClick" />
</template>

<style scoped>
.knowledge-chat-content :deep(.knowledge-cite-mark) {
  display: inline;
  margin: 0 1px;
  padding: 0 3px;
  border: none;
  border-radius: 4px;
  background: var(--platform-accent-muted);
  color: var(--platform-accent-pressed);
  font-size: 0.92em;
  font-weight: 600;
  line-height: 1.4;
  cursor: pointer;
  vertical-align: baseline;
}

.knowledge-chat-content :deep(.knowledge-cite-mark:hover) {
  background: var(--platform-accent-soft);
  text-decoration: underline;
}

.knowledge-chat-content :deep(p) {
  margin: 0 0 0.5em;
}

.knowledge-chat-content :deep(p:last-child) {
  margin-bottom: 0;
}

.knowledge-chat-content :deep(ul),
.knowledge-chat-content :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.25em;
}
</style>
