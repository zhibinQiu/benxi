<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  NButton,
  NIcon,
  NInput,
  NSelect,
  NSpace,
  NSpin } from "naive-ui";
import {
  ArrowUndoOutline,
  ArrowRedoOutline,
  SendOutline } from "@vicons/ionicons5";
import { marked } from "marked";
import {
  assistWritingCompose,
  fetchAssistWritingPresets } from "../api/client";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";

const ui = usePlatformUi();

marked.setOptions({ gfm: true, breaks: true });

const markdown = ref("");
const history = ref([""]);
const historyIndex = ref(0);
const presets = ref([]);
const presetId = ref(null);
const instruction = ref("");
const composing = ref(false);
let typingTimer = null;

const canUndo = computed(() => historyIndex.value > 0);
const canRedo = computed(() => historyIndex.value < history.value.length - 1);

const presetOptions = computed(() =>
  presets.value.map((p) => ({
    label: p.label,
    value: p.id}))
);

const previewHtml = computed(() => {
  const raw = markdown.value || "";
  if (!raw.trim()) return "<p class=\"md-empty\">预览将显示在此处</p>";
  try {
    return marked.parse(raw);
  } catch {
    return "<p class=\"md-error\">预览解析失败</p>";
  }
});

function pushHistory(val) {
  const stack = history.value.slice(0, historyIndex.value + 1);
  if (stack[stack.length - 1] === val) return;
  history.value = [...stack, val];
  historyIndex.value = history.value.length - 1;
}

function applyMarkdown(val) {
  markdown.value = val;
  pushHistory(val);
}

function undo() {
  if (!canUndo.value) return;
  historyIndex.value -= 1;
  markdown.value = history.value[historyIndex.value];
}

function redo() {
  if (!canRedo.value) return;
  historyIndex.value += 1;
  markdown.value = history.value[historyIndex.value];
}

function onEditorInput() {
  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => pushHistory(markdown.value), 700);
}

async function loadPresets() {
  try {
    presets.value = (await fetchAssistWritingPresets()) || [];
  } catch (e) {
    ui.warning(e.message || "无法加载提示词模板");
  }
}

async function runCompose() {
  const extra = instruction.value.trim();
  if (!presetId.value && !extra) {
    ui.warning("请选择提示词模板或输入补充说明");
    return;
  }
  composing.value = true;
  const before = markdown.value;
  try {
    const data = await assistWritingCompose({
      markdown: before,
      instruction: extra,
      preset_id: presetId.value || null});
    pushHistory(before);
    applyMarkdown(data.markdown || "");
    ui.success("已写入左侧编辑器");
  } catch (e) {
    ui.error(e.message || "AI 处理失败");
  } finally {
    composing.value = false;
  }
}

function onComposeKeydown(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    runCompose();
  }
}

onMounted(loadPresets);

onBeforeUnmount(() => {
  clearTimeout(typingTimer);
});

watch(presetId, (id) => {
  const p = presets.value.find((x) => x.id === id);
  if (p && !instruction.value.trim()) {
    instruction.value = p.description || "";
  }
});
</script>

<template>
  <FeatureSubsystemShell fill>
    <template #extra>
      <n-space align="center" :size="8" wrap>
        <n-button
          size="small"
          secondary
          :disabled="!canUndo"
          title="撤销"
          @click="undo"
        >
          <template #icon>
            <n-icon :component="ArrowUndoOutline" />
          </template>
          撤销
        </n-button>
        <n-button
          size="small"
          secondary
          :disabled="!canRedo"
          title="重做"
          @click="redo"
        >
          <template #icon>
            <n-icon :component="ArrowRedoOutline" />
          </template>
          重做
        </n-button>
      </n-space>
    </template>

    <div class="assist-workspace">
      <div class="assist-columns">
        <section class="doc-panel doc-panel--editor">
          <header class="doc-panel-head">
            <div class="doc-panel-head-main">
              <span class="doc-panel-badge doc-panel-badge--editor">源码</span>
              <span class="doc-panel-label">Markdown</span>
            </div>
          </header>
          <div class="doc-panel-body doc-panel-body--editor">
            <textarea
              v-model="markdown"
              class="md-editor"
              spellcheck="false"
              placeholder="# 标题&#10;&#10;在此编写 Markdown…"
              @input="onEditorInput"
            />
          </div>
        </section>

        <section class="doc-panel doc-panel--preview">
          <header class="doc-panel-head">
            <div class="doc-panel-head-main">
              <span class="doc-panel-badge doc-panel-badge--preview">预览</span>
              <span class="doc-panel-label">渲染效果</span>
            </div>
          </header>
          <div class="doc-panel-body doc-panel-body--preview">
            <div class="md-preview" v-html="previewHtml" />
          </div>
        </section>
      </div>
    </div>

    <footer class="assist-compose-bar">
      <n-spin :show="composing" class="assist-compose-spin">
        <div class="assist-compose-row">
          <n-select
            v-model:value="presetId"
            size="small"
            :options="presetOptions"
            placeholder="提示词模板"
            clearable
            class="preset-select"
          />
          <n-input
            v-model:value="instruction"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="补充说明（可选）"
            class="instruction-input"
            @keydown="onComposeKeydown"
          />
          <n-button
            type="primary"
            size="small"
            :loading="composing"
            class="send-btn"
            @click="runCompose"
          >
            <template #icon>
              <n-icon :component="SendOutline" />
            </template>
            AI 改写
          </n-button>
        </div>
      </n-spin>
    </footer>
  </FeatureSubsystemShell>
</template>

<style scoped>
.assist-page {
  gap: 0;
}

.assist-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.assist-columns {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
  align-items: stretch;
}

.doc-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--platform-surface, #fff);
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-radius: var(--platform-radius-sm, 8px);
  box-shadow: var(--platform-shadow);
  overflow: hidden;
}

.doc-panel--editor {
  border-top: 2px solid var(--platform-accent);
}

.doc-panel--preview {
  border-top: 2px solid #94a3b8;
}

.doc-panel-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.06));
  background: rgba(248, 250, 252, 0.9);
}

.doc-panel-head-main {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.doc-panel-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.doc-panel-badge--editor {
  background: var(--platform-accent-soft);
  color: var(--platform-accent-pressed);
}

.doc-panel-badge--preview {
  background: rgba(148, 163, 184, 0.2);
  color: #475569;
}

.doc-panel-label {
  font-size: 12px;
  color: var(--platform-muted, #64748b);
}

.doc-panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.doc-panel-body--editor {
  background: #f8fafc;
}

.doc-panel-body--preview {
  background: #fff;
}

.md-editor {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  padding: 12px 14px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.55;
  color: #0f172a;
  background: transparent;
  box-sizing: border-box;
}

.md-preview {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px 16px;
  font-size: 14px;
  line-height: 1.65;
  color: #334155;
}

.md-preview :deep(h1),
.md-preview :deep(h2),
.md-preview :deep(h3) {
  margin: 0.75em 0 0.4em;
  font-weight: 600;
  line-height: 1.3;
  color: #0f172a;
}

.md-preview :deep(h1) {
  font-size: 1.5em;
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  padding-bottom: 0.25em;
}

.md-preview :deep(h2) {
  font-size: 1.25em;
}

.md-preview :deep(p) {
  margin: 0.5em 0;
}

.md-preview :deep(ul),
.md-preview :deep(ol) {
  padding-left: 1.4em;
  margin: 0.5em 0;
}

.md-preview :deep(code) {
  font-family: ui-monospace, monospace;
  font-size: 0.9em;
  padding: 0.15em 0.35em;
  border-radius: 4px;
  background: #f1f5f9;
  color: #0f172a;
}

.md-preview :deep(pre) {
  overflow: auto;
  padding: 10px 12px;
  border-radius: var(--platform-radius-sm, 8px);
  background: #f1f5f9;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.06));
  margin: 0.6em 0;
}

.md-preview :deep(pre code) {
  padding: 0;
  background: none;
  border: none;
}

.md-preview :deep(blockquote) {
  margin: 0.6em 0;
  padding-left: 12px;
  border-left: 3px solid var(--platform-accent);
  color: var(--platform-muted, #64748b);
}

.md-preview :deep(.md-empty) {
  color: #94a3b8;
  font-style: italic;
}

.md-preview :deep(.md-error) {
  color: #dc2626;
}

.assist-compose-bar {
  flex-shrink: 0;
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--platform-surface, #fff);
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-radius: var(--platform-radius-sm, 8px);
  box-shadow: var(--platform-shadow);
}

.assist-compose-spin {
  width: 100%;
}

.assist-compose-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.preset-select {
  width: 200px;
  flex-shrink: 0;
}

.instruction-input {
  flex: 1;
  min-width: 0;
}

.send-btn {
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .assist-columns {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(200px, 1fr) minmax(200px, 1fr);
  }
}
</style>
