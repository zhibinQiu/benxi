<script setup>
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import {
  bindEchartsResize,
  disposeEchartsInElement,
  mountRichMediaInElement,
  renderRichMarkdown,
  unbindEchartsResize,
} from "../utils/richMarkdown.js";
import { unmountMermaidInElement } from "../utils/mermaidRender.js";

const props = defineProps({
  content: { type: String, default: "" },
  citations: { type: Array, default: () => [] },
});

const emit = defineEmits(["open-citation"]);

const rootRef = ref(null);
const domActive = ref(true);
let refreshTimer = null;

const citationIndexes = computed(() => {
  const set = new Set((props.citations || []).map((c) => Number(c.index)).filter(Boolean));
  return set;
});

const CITE_GROUP_RE = /(?:[\[【]\d{1,2}[\]】])+/g;
const CITE_NUM_RE = /[\[【](\d{1,2})[\]】]/g;

const html = computed(() => {
  if (!domActive.value) return "";
  let text = props.content || "";
  if (!text) return "";
  text = text.replace(CITE_GROUP_RE, (group) => {
    const nums = [...group.matchAll(CITE_NUM_RE)].map((m) => Number(m[1]));
    const seen = new Set();
    const linked = [];
    for (const num of nums) {
      if (!citationIndexes.value.has(num) || seen.has(num)) continue;
      seen.add(num);
      linked.push(num);
    }
    if (!linked.length) return group;
    return linked
      .map(
        (num) =>
          `<button type="button" class="knowledge-cite-mark" data-cite-index="${num}">[${num}]</button>`
      )
      .join("");
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

async function refreshRichMedia() {
  if (!domActive.value) return;
  await nextTick();
  const root = rootRef.value;
  if (!root) return;
  disposeEchartsInElement(root);
  unmountMermaidInElement(root);
  await mountRichMediaInElement(root);
  bindCiteButtons();
}

function scheduleRefresh() {
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    void refreshRichMedia();
  }, 280);
}

function releaseDom() {
  const root = rootRef.value;
  if (root) {
    disposeEchartsInElement(root);
    unmountMermaidInElement(root);
  }
  domActive.value = false;
}

watch(() => props.content, scheduleRefresh);

onMounted(() => {
  bindEchartsResize();
  void refreshRichMedia();
});

onActivated(() => {
  domActive.value = true;
  void refreshRichMedia();
});

onDeactivated(releaseDom);

onBeforeUnmount(() => {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  releaseDom();
  unbindEchartsResize();
});

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
.knowledge-chat-content :deep(p) {
  margin: 0 0 0.5em;
}

.knowledge-chat-content :deep(p:last-child) {
  margin-bottom: 0;
}

.knowledge-chat-content :deep(.knowledge-cite-mark) {
  display: inline;
  margin: 0 1px;
  padding: 0 2px;
  border: none;
  background: transparent;
  color: var(--primary-color, #18a058);
  font: inherit;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.knowledge-chat-content :deep(.knowledge-cite-mark:hover) {
  opacity: 0.85;
}
</style>
