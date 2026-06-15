<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { NIcon, NSpin } from "naive-ui";
import { ExpandOutline } from "@vicons/ionicons5";
import AdminFormModal from "./AdminFormModal.vue";
import { useI18n } from "../composables/useI18n.js";
import { renderMermaidSvg } from "../utils/systemDocMarkdown.js";
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

watch(
  () => [props.question, props.answer],
  () => {
    svgHtml.value = "";
    source.value = "";
    error.value = "";
    expandOpen.value = false;
  }
);

watch(
  () => [props.active, props.autoLoad, props.answer],
  ([active, autoLoad, answer]) => {
    if (active && autoLoad && (answer || "").trim() && !svgHtml.value && !loading.value) {
      loadMindmap();
    }
  },
  { immediate: true }
);

defineExpose({ loadMindmap });
</script>

<template>
  <div class="knowledge-mindmap" @click="onBlankClick">
    <n-spin :show="loading">
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
          <n-icon :component="ExpandOutline" :size="14" />
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
    </n-spin>

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
  min-height: 200px;
}

.knowledge-mindmap__canvas {
  position: relative;
  width: 100%;
  overflow-x: auto;
  padding: 8px 4px 4px;
  border-radius: 12px;
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
  right: 10px;
  bottom: 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--platform-text-secondary);
  background: color-mix(in srgb, var(--platform-surface) 88%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-border) 70%, transparent);
  pointer-events: none;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.knowledge-mindmap__canvas--expandable:hover .knowledge-mindmap__expand-hint,
.knowledge-mindmap__canvas--expandable:focus-visible .knowledge-mindmap__expand-hint {
  opacity: 1;
  transform: translateY(0);
}

.knowledge-mindmap__expand-viewport {
  overflow: auto;
  max-height: min(80vh, 860px);
  padding: 12px 8px 16px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--platform-bg) 45%, transparent);
}

.knowledge-mindmap__expand-viewport :deep(svg) {
  max-width: none;
  min-width: min(100%, 720px);
}

.knowledge-mindmap__hint,
.knowledge-mindmap__retry {
  display: block;
  width: 100%;
  margin: 0;
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
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
