<script setup>
import { useI18n } from "../composables/useI18n.js";
import { computed, ref, watch } from "vue";
import {
  NButton,
  NIcon,
  NInput,
  NModal,
  NSpin,
  NTag,
  NScrollbar,
} from "naive-ui";
import {
  AddOutline,
  PlayOutline,
  RefreshOutline,
  ArrowUndoOutline,
  ArrowRedoOutline,
  EyeOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  createDataAnalysisCell,
  runDataAnalysisCell,
  updateDataAnalysisCell,
  previewDataAnalysisData,
} from "../api/dataAnalysis";

const props = defineProps({
  sessionId: { type: String, required: true },
  cells: { type: Array, default: () => [] },
  libraries: { type: Array, default: () => ["pandas", "numpy", "matplotlib", "seaborn"] },
});

const emit = defineEmits(["update:cells", "repair"]);

const ui = usePlatformUi();
const { t } = useI18n();
const localCells = ref([]);
const runningId = ref("");
const savingId = ref("");
const creating = ref(false);

/* ── undo/redo history ── */
const MAX_HISTORY = 60;
const historyStack = ref([[]]);
const historyIndex = ref(0);

function pushHistory() {
  const snapshot = (localCells.value || []).map((c) => ({ ...c }));
  historyStack.value = historyStack.value.slice(0, historyIndex.value + 1);
  historyStack.value.push(snapshot);
  if (historyStack.value.length > MAX_HISTORY) {
    historyStack.value.shift();
  }
  historyIndex.value = historyStack.value.length - 1;
}

const canUndo = computed(() => historyIndex.value > 0);
const canRedo = computed(() => historyIndex.value < historyStack.value.length - 1);

function applySnapshot(snapshot) {
  localCells.value = snapshot.map((c) => ({ ...c }));
  emitCells();
}

function undo() {
  if (!canUndo.value) return;
  historyIndex.value--;
  applySnapshot(historyStack.value[historyIndex.value]);
}

function redo() {
  if (!canRedo.value) return;
  historyIndex.value++;
  applySnapshot(historyStack.value[historyIndex.value]);
}

/* ── preview modal ── */
const showPreview = ref(false);
const previewLoading = ref(false);
const previewData = ref(null);

async function openPreview() {
  showPreview.value = true;
  previewLoading.value = true;
  try {
    const data = await previewDataAnalysisData(props.sessionId, { limit: 20 });
    previewData.value = data;
  } catch (e) {
    ui.error(e.message || "预览失败");
    showPreview.value = false;
  } finally {
    previewLoading.value = false;
  }
}

/* ── cells ── */

const libraryHint = computed(() => props.libraries.join(" · "));

watch(
  () => props.cells,
  (val) => {
    localCells.value = (val || []).map((c) => ({ ...c }));
  },
  { immediate: true, deep: true }
);

function emitCells() {
  emit("update:cells", localCells.value.map((c) => ({ ...c })));
}

async function onCodeBlur(cell) {
  if (!cell?.id) return;
  savingId.value = cell.id;
  try {
    const data = await updateDataAnalysisCell(props.sessionId, cell.id, {
      code: cell.code,
      title: cell.title});
    const idx = localCells.value.findIndex((c) => c.id === cell.id);
    if (idx >= 0 && data?.cell) {
      localCells.value[idx] = { ...localCells.value[idx], ...data.cell };
      emitCells();
    }
  } catch {
    /* 静默 */
  } finally {
    savingId.value = "";
  }
}

async function runCell(cell) {
  if (!cell?.id || runningId.value) return;
  pushHistory();
  runningId.value = cell.id;
  const idx = localCells.value.findIndex((c) => c.id === cell.id);
  if (idx >= 0) {
    localCells.value[idx] = { ...localCells.value[idx], status: "running" };
  }
  try {
    const data = await runDataAnalysisCell(props.sessionId, cell.id);
    if (idx >= 0 && data?.cell) {
      localCells.value[idx] = { ...data.cell };
      emitCells();
    }
  } catch (e) {
    if (idx >= 0) {
      localCells.value[idx] = {
        ...localCells.value[idx],
        status: "error",
        stderr: e.message || t("tableAnalysis.runFailed"),
      };
      emitCells();
    }
  } finally {
    runningId.value = "";
  }
}

async function addCell() {
  if (creating.value) return;
  pushHistory();
  creating.value = true;
  try {
    const data = await createDataAnalysisCell(props.sessionId);
    if (data?.cell) {
      localCells.value = [...localCells.value, { ...data.cell }];
      emitCells();
    }
  } catch (e) {
    ui.error(e.message || t("tableAnalysis.addCellFailed"));
  } finally {
    creating.value = false;
  }
}

function deleteCell(cell) {
  if (!cell?.id) return;
  pushHistory();
  localCells.value = localCells.value.filter((c) => c.id !== cell.id);
  emitCells();
}

function statusTag(status) {
  if (status === "success") return { type: "success", label: t("tableAnalysis.statusSuccess") };
  if (status === "error") return { type: "error", label: t("tableAnalysis.statusError") };
  if (status === "running") return { type: "warning", label: t("tableAnalysis.statusRunning") };
  return { type: "default", label: t("tableAnalysis.statusPending") };
}
</script>

<template>
  <div class="notebook-panel">
    <div class="notebook-toolbar">
      <div class="toolbar-left">
        <n-button size="small" quaternary circle :disabled="!canUndo" @click="undo">
          <template #icon><n-icon><ArrowUndoOutline /></n-icon></template>
        </n-button>
        <n-button size="small" quaternary circle :disabled="!canRedo" @click="redo">
          <template #icon><n-icon><ArrowRedoOutline /></n-icon></template>
        </n-button>
        <div class="toolbar-divider" />
        <n-button size="small" quaternary @click="openPreview">
          <template #icon><n-icon><EyeOutline /></n-icon></template>
          {{ t("tableAnalysis.preview") }}
        </n-button>
      </div>
      <div class="toolbar-right">
        <div class="library-tags">
          <n-tag
            v-for="lib in libraries"
            :key="lib"
            size="small"
            :bordered="false"
            type="info"
          >
            {{ lib }}
          </n-tag>
          <span class="library-hint">{{ t("tableAnalysis.libraryHint") }}</span>
        </div>
        <n-button size="small" type="primary" class="platform-btn--create" :loading="creating" @click="addCell">
          <template #icon><n-icon><AddOutline /></n-icon></template>
          {{ t("tableAnalysis.addCell") }}
        </n-button>
      </div>
    </div>

    <div v-if="!localCells.length" class="notebook-empty">
      <p>{{ t("tableAnalysis.notebookEmpty") }}</p>
      <p class="hint">
        {{ t("tableAnalysis.notebookEmptyHint") }}
      </p>
      <p class="hint">{{ t("tableAnalysis.notebookEmptyLibraries", { libraries: libraryHint }) }}</p>
    </div>

    <article v-for="cell in localCells" :key="cell.id" class="notebook-cell">
      <header class="cell-header">
        <n-input
          v-model:value="cell.title"
          size="small"
          class="cell-title-input"
          :placeholder="t('tableAnalysis.cellTitlePlaceholder')"
          @blur="onCodeBlur(cell)"
        />
        <n-tag size="small" :type="statusTag(cell.status).type" :bordered="false">
          {{ statusTag(cell.status).label }}
        </n-tag>
        <n-button
          v-if="cell.status === 'error'"
          size="small"
          type="warning"
          quaternary
          @click="emit('repair', cell.id)"
        >
          <template #icon><n-icon><svg viewBox="0 0 512 512"><path d="M491.4 101.8l-76.7-76.7c-6.2-6.2-16.4-6.2-22.6 0l-25 25c-6.2 6.2-6.2 16.4 0 22.6l11.3 11.3-101 101c-5.7 5.7-13.4 8.8-21.4 8.8H200c-8.5 0-16.6 3.4-22.6 9.4L81 350.1c-6.2 6.2-6.2 16.4 0 22.6l11.3 11.3c6.2 6.2 16.4 6.2 22.6 0l96.4-96.4c6-6 9.4-14.1 9.4-22.6v-56.4c0-8 3.1-15.7 8.8-21.4l101-101 11.3 11.3c6.2 6.2 16.4 6.2 22.6 0l25-25c6.2-6.2 6.2-16.4 0-22.6z"/><path d="M80 352l-32 96 96-32c-4.7-4.7-9.5-9.5-14.1-14.1l-8.5-8.5c-4.7-4.7-9.2-9.4-13.5-14.1z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="32"/></svg></n-icon></template>
          修复
        </n-button>
        <n-button
          size="small"
          type="error"
          quaternary
          circle
          @click="deleteCell(cell)"
        >
          <template #icon><n-icon><TrashOutline /></n-icon></template>
        </n-button>
        <n-button
          size="small"
          type="primary"
          quaternary
          circle
          :loading="runningId === cell.id"
          :disabled="Boolean(runningId && runningId !== cell.id)"
          @click="runCell(cell)"
        >
          <template #icon>
            <n-icon><PlayOutline /></n-icon>
          </template>
        </n-button>
      </header>

      <n-input
        v-model:value="cell.code"
        type="textarea"
        class="cell-code"
        :autosize="{ minRows: 6, maxRows: 18 }"
        :placeholder="t('tableAnalysis.cellCodePlaceholder')"
        @blur="onCodeBlur(cell)"
      />

      <div v-if="cell.status === 'running'" class="cell-output running">
        <n-spin size="small" /> {{ t("tableAnalysis.cellRunning") }}
      </div>

      <div v-if="cell.stdout" class="cell-output stdout">
        <pre>{{ cell.stdout }}</pre>
      </div>
      <div v-if="cell.stderr" class="cell-output stderr">
        <pre>{{ cell.stderr }}</pre>
      </div>
      <div v-if="cell.images?.length" class="cell-images">
        <img
          v-for="(img, i) in cell.images"
          :key="`${cell.id}-img-${i}`"
          :src="`data:image/png;base64,${img}`"
          :alt="t('tableAnalysis.chartAlt', { index: i + 1 })"
          loading="lazy"
        />
      </div>
    </article>

    <div v-if="savingId" class="notebook-saving">
      <n-icon><RefreshOutline /></n-icon> {{ t("tableAnalysis.saving") }}
    </div>

    <!-- 数据预览弹窗 -->
    <n-modal v-model:show="showPreview" preset="card" style="width: 90vw; max-width: 1100px;" :title="t('tableAnalysis.preview')" :bordered="false" size="huge">
      <n-spin :show="previewLoading">
        <template v-if="previewData">
          <div class="preview-meta">
            <n-tag size="small" type="info" :bordered="false">
              共 {{ previewData.total_rows }} 行 · 预览前 {{ previewData.preview_rows }} 行
            </n-tag>
          </div>
          <n-scrollbar x-scrollable>
            <table class="preview-table">
              <thead>
                <tr>
                  <th class="preview-row-num">#</th>
                  <th v-for="col in previewData.columns" :key="col">{{ col }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in previewData.rows" :key="ri">
                  <td class="preview-row-num">{{ ri + 1 }}</td>
                  <td v-for="(val, ci) in row.columns" :key="ci">{{ val }}</td>
                </tr>
              </tbody>
            </table>
          </n-scrollbar>
          <p v-if="!previewData.rows?.length" class="preview-empty">数据为空</p>
        </template>
      </n-spin>
    </n-modal>
  </div>
</template>

<style scoped>
.notebook-panel {
  height: 100%;
  overflow: auto;
  padding: 10px 14px 20px;
  background: #fafafa;
}

.notebook-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 2px;
}

.toolbar-divider {
  width: 1px;
  height: 18px;
  background: var(--platform-border, #ddd);
  margin: 0 4px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.library-tags {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  min-width: 0;
}

.library-hint {
  font-size: 13px;
  color: var(--n-text-color-3);
}

.notebook-empty {
  margin-top: 15vh;
  text-align: center;
  color: var(--n-text-color-3);
}

.notebook-empty .hint {
  margin-top: 8px;
  font-size: 14px;
}

.notebook-cell {
  background: #fff;
  border: 1px solid #e8e8ec;
  border-radius: 10px;
  margin-bottom: 12px;
  overflow: hidden;
}

.cell-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-bottom: 1px solid #f0f0f0;
  background: #fcfcfd;
}

.cell-title-input {
  flex: 1;
  min-width: 0;
}

.cell-code :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.45;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: #fff;
}

.cell-output {
  padding: 8px 12px;
  border-top: 1px solid #f0f0f0;
  font-size: 13px;
}

.cell-output pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
}

.cell-output.stdout {
  background: var(--platform-accent-gradient-soft);
}

.cell-output.stderr {
  background: #fff7f7;
  color: #c0392b;
}

.cell-output.running {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--n-text-color-3);
  font-size: 13px;
}

.cell-images {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 12px;
  border-top: 1px solid #f0f0f0;
}

.cell-images img {
  max-width: 100%;
  max-height: 480px;
  object-fit: contain;
  border: 1px solid #eee;
  border-radius: 6px;
  background: #fff;
  cursor: zoom-in;
}

.notebook-saving {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 5px;
  font-size: 13px;
  color: var(--n-text-color-3);
}

/* preview modal */
.preview-meta {
  margin-bottom: 10px;
}

.preview-table {
  border-collapse: collapse;
  font-size: 13px;
  white-space: nowrap;
}

.preview-table th,
.preview-table td {
  border: 1px solid #e0e0e0;
  padding: 4px 8px;
  text-align: left;
}

.preview-table th {
  background: #f5f5f5;
  font-weight: 600;
  position: sticky;
  top: 0;
}

.preview-row-num {
  color: #999;
  font-size: 12px;
  min-width: 28px;
  text-align: center;
}

.preview-empty {
  text-align: center;
  color: var(--n-text-color-3);
  padding: 16px;
}
</style>
