<script setup>
import { useI18n } from "../composables/useI18n.js";
import { computed, ref, watch } from "vue";
import { NButton, NIcon, NInput, NSpin, NTag } from "naive-ui";
import { AddOutline, PlayOutline, RefreshOutline } from "@vicons/ionicons5";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  createDataAnalysisCell,
  runDataAnalysisCell,
  updateDataAnalysisCell,
} from "../api/dataAnalysis";

const props = defineProps({
  sessionId: { type: String, required: true },
  cells: { type: Array, default: () => [] },
  libraries: { type: Array, default: () => ["pandas", "numpy", "matplotlib", "seaborn"] },
});

const emit = defineEmits(["update:cells"]);

const ui = usePlatformUi();
const { t } = useI18n();
const localCells = ref([]);
const runningId = ref("");
const savingId = ref("");
const creating = ref(false);

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
    /* 静默：失焦保存失败不阻断编辑 */
  } finally {
    savingId.value = "";
  }
}

async function runCell(cell) {
  if (!cell?.id || runningId.value) return;
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
        stderr: e.message || t("dataAnalysis.runFailed"),
      };
      emitCells();
    }
  } finally {
    runningId.value = "";
  }
}

async function addCell() {
  if (creating.value) return;
  creating.value = true;
  try {
    const data = await createDataAnalysisCell(props.sessionId);
    if (data?.cell) {
      localCells.value = [...localCells.value, { ...data.cell }];
      emitCells();
    }
  } catch (e) {
    ui.error(e.message || t("dataAnalysis.addCellFailed"));
  } finally {
    creating.value = false;
  }
}

function statusTag(status) {
  if (status === "success") return { type: "success", label: t("dataAnalysis.statusSuccess") };
  if (status === "error") return { type: "error", label: t("dataAnalysis.statusError") };
  if (status === "running") return { type: "warning", label: t("dataAnalysis.statusRunning") };
  return { type: "default", label: t("dataAnalysis.statusPending") };
}
</script>

<template>
  <div class="notebook-panel">
    <div class="notebook-toolbar">
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
        <span class="library-hint">{{ t("dataAnalysis.libraryHint") }}</span>
      </div>
      <n-button size="small" type="primary" :loading="creating" @click="addCell">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        {{ t("dataAnalysis.addCell") }}
      </n-button>
    </div>

    <div v-if="!localCells.length" class="notebook-empty">
      <p>{{ t("dataAnalysis.notebookEmpty") }}</p>
      <p class="hint">
        {{ t("dataAnalysis.notebookEmptyHint") }}
      </p>
      <p class="hint">{{ t("dataAnalysis.notebookEmptyLibraries", { libraries: libraryHint }) }}</p>
    </div>

    <article v-for="cell in localCells" :key="cell.id" class="notebook-cell">
      <header class="cell-header">
        <n-input
          v-model:value="cell.title"
          size="small"
          class="cell-title-input"
          :placeholder="t('dataAnalysis.cellTitlePlaceholder')"
          @blur="onCodeBlur(cell)"
        />
        <n-tag size="small" :type="statusTag(cell.status).type" :bordered="false">
          {{ statusTag(cell.status).label }}
        </n-tag>
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
        :placeholder="t('dataAnalysis.cellCodePlaceholder')"
        @blur="onCodeBlur(cell)"
      />

      <div v-if="cell.status === 'running'" class="cell-output running">
        <n-spin size="small" /> {{ t("dataAnalysis.cellRunning") }}
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
          :alt="t('dataAnalysis.chartAlt', { index: i + 1 })"
          loading="lazy"
        />
      </div>
    </article>

    <div v-if="savingId" class="notebook-saving">
      <n-icon><RefreshOutline /></n-icon> {{ t("dataAnalysis.saving") }}
    </div>
  </div>
</template>

<style scoped>
.notebook-panel {
  height: 100%;
  overflow: auto;
  padding: 14px 17px 29px;
  background: #fafafa;
}

.notebook-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.library-tags {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  min-width: 0;
}

.library-hint {
  font-size: 14px;
  color: var(--n-text-color-3);
}

.notebook-empty {
  margin-top: 18vh;
  text-align: center;
  color: var(--n-text-color-3);
}

.notebook-empty .hint {
  margin-top: 10px;
  font-size: 16px;
}

.notebook-cell {
  background: #fff;
  border: 1px solid #e8e8ec;
  border-radius: 12px;
  margin-bottom: 17px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.cell-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  background: #fcfcfd;
}

.cell-title-input {
  flex: 1;
  min-width: 0;
}

.cell-code :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 16px;
  line-height: 1.45;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: #fff;
}

.cell-output {
  padding: 12px 14px;
  border-top: 1px solid #f0f0f0;
  font-size: 16px;
}

.cell-output pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
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
  gap: 10px;
  color: var(--n-text-color-3);
}

.cell-images {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 14px;
  border-top: 1px solid #f0f0f0;
}

.cell-images img {
  max-width: 100%;
  max-height: 576px;
  object-fit: contain;
  border: 1px solid #eee;
  border-radius: 7px;
  background: #fff;
  cursor: zoom-in;
}

.notebook-saving {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 7px;
  font-size: 14px;
  color: var(--n-text-color-3);
}
</style>
