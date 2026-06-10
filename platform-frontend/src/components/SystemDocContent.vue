<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { NSpin } from "naive-ui";
import { getApiBase } from "../api/http.js";
import {
  disposeSystemDocContent,
  mountSystemDocContent,
  renderSystemDocMarkdown,
  resolveDocLink,
  unbindSystemDocContent,
} from "../utils/systemDocMarkdown";

const props = defineProps({
  content: { type: String, default: "" },
  docPath: { type: String, default: "" },
  loading: { type: Boolean, default: false },
});

const emit = defineEmits(["navigate"]);

const bodyRef = ref(null);

const html = computed(() => renderSystemDocMarkdown(props.content));

function prefixApiAssets(root) {
  const base = getApiBase().replace(/\/$/, "");
  root.querySelectorAll('img[src^="/api/"]').forEach((img) => {
    img.src = `${base}${img.getAttribute("src")}`;
  });
}

function onContentClick(event) {
  const anchor = event.target.closest("a");
  if (!anchor) return;
  const target = resolveDocLink(props.docPath, anchor.getAttribute("href") || "");
  if (!target) return;
  event.preventDefault();
  emit("navigate", target);
}

async function refreshMounts() {
  await nextTick();
  const root = bodyRef.value;
  if (!root) return;
  prefixApiAssets(root);
  disposeSystemDocContent(root);
  await mountSystemDocContent(root);
  if (targetHash.value) {
    scrollToHash(targetHash.value);
    targetHash.value = "";
  }
}

const targetHash = ref("");

function scrollToHash(hash) {
  const id = String(hash || "").replace(/^#/, "");
  if (!id) return;
  const el = bodyRef.value?.querySelector(`[id="${CSS.escape(id)}"]`);
  el?.scrollIntoView({ behavior: "smooth", block: "start" });
}

watch(
  () => [props.content, props.docPath],
  () => {
    refreshMounts();
  },
  { flush: "post" }
);

defineExpose({
  scrollToHash: (hash) => {
    targetHash.value = hash;
    scrollToHash(hash);
  },
});

onBeforeUnmount(() => {
  disposeSystemDocContent(bodyRef.value);
  unbindSystemDocContent();
});
</script>

<template>
  <div class="system-doc-content">
    <NSpin :show="loading">
      <article
        ref="bodyRef"
        class="system-doc-content__body article-content article-html"
        @click="onContentClick"
        v-html="html"
      />
    </NSpin>
  </div>
</template>

<style scoped>
.system-doc-content {
  min-height: 120px;
}

.system-doc-content__body {
  padding: 4px 2px 24px;
}

.system-doc-content__body :deep(.md-mermaid-wrap) {
  margin: 16px 0;
  padding: 12px;
  overflow-x: auto;
  border-radius: var(--platform-radius-sm);
  background: var(--platform-bg-glass-subtle);
  border: 1px solid var(--platform-border);
}

.system-doc-content__body :deep(.md-mermaid-svg svg) {
  max-width: 100%;
  height: auto;
}

.system-doc-content__body :deep(.md-mermaid--error) {
  color: var(--platform-danger);
  white-space: pre-wrap;
  font-size: 13px;
}

.system-doc-content__body :deep(pre) {
  overflow-x: auto;
}

.system-doc-content__body :deep(table) {
  display: block;
  overflow-x: auto;
}
</style>
