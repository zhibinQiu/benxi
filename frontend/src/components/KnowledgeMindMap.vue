<script setup>
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import { NIcon } from "naive-ui";
import { ExpandOutline } from "@vicons/ionicons5";
import AdminFormModal from "./AdminFormModal.vue";
import PlatformSpin from "./PlatformSpin.vue";
import { useI18n } from "../composables/useI18n.js";
import { renderMermaidSvg } from "../utils/mermaidRender.js";
import { buildMindmapFromAnswer } from "../utils/knowledgeMindmap.js";
import { fetchKnowledgeMindmap } from "../api/knowledge.js";

const props = defineProps({
  question: { type: String, default: "" },
  answer: { type: String, default: "" },
  /** 自定义思维导图 API，签名 ({ question, answer }) => Promise<{ mermaid }> */
  fetchMindmap: { type: Function, default: null },
  /** 为 true 时挂载后自动尝试生成（避免切换 Tab 后空白） */
  autoLoad: { type: Boolean, default: false },
  /** 外层 Tab 是否处于激活状态 */
  active: { type: Boolean, default: true },
});

const { t } = useI18n();

const loading = ref(false);
const error = ref("");
const svgHtml = ref("");
const source = ref("");
const expandOpen = ref(false);
const rootRef = ref(null);
let visibilityObserver = null;

const expandTitle = computed(() => {
  const q = (props.question || "").trim();
  return q ? `${t("mindmap.expandTitle")} · ${q}` : t("mindmap.expandTitle");
});

async function renderSource(mermaidSource) {
  error.value = "";
  svgHtml.value = "";
  source.value = mermaidSource;
  if (!mermaidSource?.trim()) {
    error.value = "暂无足够内容生成思维导图";
    return;
  }
  loading.value = true;
  try {
    await nextTick();
    svgHtml.value = await renderMermaidSvg(mermaidSource);
  } catch (e) {
    error.value = e?.message || "思维导图渲染失败";
  } finally {
    loading.value = false;
  }
}

async function loadMindmap() {
  if (loading.value) return;
  if (!(props.answer || "").trim()) {
    error.value = "暂无足够内容生成思维导图";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const fetcher = props.fetchMindmap || fetchKnowledgeMindmap;
    const data = await fetcher({
      question: props.question,
      answer: props.answer,
    });
    const mermaid = (data?.mermaid || "").trim();
    if (mermaid) {
      await renderSource(mermaid);
      return;
    }
  } catch {
    /* 回退本地结构解析 */
  }
  await renderSource(buildMindmapFromAnswer(props.question, props.answer));
}

function onBlankClick() {
  if (svgHtml.value || loading.value) return;
  loadMindmap();
}

function openExpand(event) {
  event?.stopPropagation?.();
  if (!svgHtml.value) return;
  expandOpen.value = true;
}

function disconnectVisibilityObserver() {
  visibilityObserver?.disconnect();
  visibilityObserver = null;
}

function scheduleVisibleLoad() {
  if (!props.active || !props.autoLoad || !(props.answer || "").trim() || svgHtml.value || loading.value) {
    return;
  }
  disconnectVisibilityObserver();
  if (typeof IntersectionObserver === "undefined") {
    void loadMindmap();
    return;
  }
  visibilityObserver = new IntersectionObserver(
    (entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      disconnectVisibilityObserver();
      void loadMindmap();
    },
    { rootMargin: "96px 0px", threshold: 0.01 }
  );
  if (rootRef.value) visibilityObserver.observe(rootRef.value);
}

watch(
  () => [props.active, props.autoLoad, props.answer],
  () => {
    nextTick(() => scheduleVisibleLoad());
  },
  { immediate: true }
);

watch(
  () => [props.question, props.answer],
  () => {
    svgHtml.value = "";
    source.value = "";
    error.value = "";
    expandOpen.value = false;
    loading.value = false;
    disconnectVisibilityObserver();
  }
);

onDeactivated(() => {
  disconnectVisibilityObserver();
  svgHtml.value = "";
  expandOpen.value = false;
  loading.value = false;
});

onActivated(() => {
  nextTick(() => scheduleVisibleLoad());
});

onBeforeUnmount(() => {
  disconnectVisibilityObserver();
});

function getMermaidSource() {
  return (source.value || "").trim();
}

defineExpose({ loadMindmap, getMermaidSource });
</script>

<template>
  <div ref="rootRef" class="knowledge-mindmap" @click="onBlankClick">
    <PlatformSpin :show="loading" local class="knowledge-mindmap__spin">
      <div
        v-if="svgHtml"
        class="knowledge-mindmap__canvas knowledge-mindmap__canvas--expandable"
        role="button"
        tabindex="0"
        :aria-label="t('mindmap.expandHint')"
        @click.stop="openExpand"
        @keydown.enter.prevent="openExpand"
        @keydown.space.prevent="openExpand"
      >
        <div class="knowledge-mindmap__canvas-inner" v-html="svgHtml" />
        <span class="knowledge-mindmap__expand-hint" aria-hidden="true">
          <n-icon :component="ExpandOutline" :size="17" />
          {{ t("mindmap.expandHint") }}
        </span>
      </div>
      <button
        v-else-if="error"
        type="button"
        class="knowledge-mindmap__retry"
        @click.stop="loadMindmap"
      >
        {{ error }}，点击重试
      </button>
      <button
        v-else
        type="button"
        class="knowledge-mindmap__hint knowledge-mindmap__hint--clickable"
        @click.stop="loadMindmap"
      >
        点击生成思维导图
      </button>
    </PlatformSpin>

    <AdminFormModal
      v-model:show="expandOpen"
      :title="expandTitle"
      width="min(1200px, 96vw)"
    >
      <div class="knowledge-mindmap__expand-viewport" v-html="svgHtml" />
    </AdminFormModal>
  </div>
</template>

<style scoped>
.knowledge-mindmap {
  width: 100%;
  min-height: 240px;
}

.knowledge-mindmap__spin {
  display: block;
  width: 100%;
  min-height: inherit;
}

.knowledge-mindmap__spin :deep(.n-spin-container) {
  min-height: 240px;
}

.knowledge-mindmap__canvas {
  position: relative;
  width: 100%;
  overflow-x: auto;
  padding: 10px 5px 5px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--platform-bg) 55%, transparent);
}

.knowledge-mindmap__canvas--expandable {
  cursor: zoom-in;
  transition: box-shadow 0.2s ease;
}

.knowledge-mindmap__canvas--expandable:hover {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--platform-accent) 35%, transparent);
}

.knowledge-mindmap__canvas--expandable:focus-visible {
  outline: 2px solid var(--platform-accent);
  outline-offset: 2px;
}

.knowledge-mindmap__canvas-inner :deep(svg),
.knowledge-mindmap__expand-viewport :deep(svg) {
  display: block;
  height: auto;
  margin: 0 auto;
}

.knowledge-mindmap__canvas-inner :deep(svg) {
  max-width: 100%;
}

.knowledge-mindmap__expand-hint {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 1199px;
  font-size: 14px;
  line-height: 1.4;
  color: var(--platform-text-secondary);
  background: color-mix(in srgb, var(--platform-surface) 88%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-border) 70%, transparent);
  pointer-events: none;
  opacity: 0;
  transform: translateY(5px);
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.knowledge-mindmap__canvas--expandable:hover .knowledge-mindmap__expand-hint,
.knowledge-mindmap__canvas--expandable:focus-visible .knowledge-mindmap__expand-hint {
  opacity: 1;
  transform: translateY(0);
}

.knowledge-mindmap__expand-viewport {
  overflow: auto;
  max-height: min(80vh, 1032px);
  padding: 14px 10px 19px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--platform-bg) 45%, transparent);
}

.knowledge-mindmap__expand-viewport :deep(svg) {
  max-width: none;
  min-width: min(100%, 864px);
}

.knowledge-mindmap__hint,
.knowledge-mindmap__retry {
  display: block;
  width: 100%;
  margin: 0;
  padding: 29px 14px;
  text-align: center;
  font-size: 16px;
  line-height: 1.6;
  color: var(--platform-text-secondary);
  border: none;
  background: transparent;
}

.knowledge-mindmap__hint--clickable,
.knowledge-mindmap__retry {
  cursor: pointer;
  color: var(--platform-accent);
}

.knowledge-mindmap__hint--clickable:hover,
.knowledge-mindmap__retry:hover {
  text-decoration: underline;
}

.knowledge-mindmap__retry {
  color: var(--platform-danger, #dc2626);
}
</style>
