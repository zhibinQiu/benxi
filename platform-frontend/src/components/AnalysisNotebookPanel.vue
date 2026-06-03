<script setup>
import { ref, watch } from "vue";
import { NButton, NIcon, NInput, NSpin, NTag } from "naive-ui";
import { PlayOutline, RefreshOutline } from "@vicons/ionicons5";
import { runDataAnalysisCell, updateDataAnalysisCell } from "../api/dataAnalysis";

const props = defineProps({
  sessionId: { type: String, required: true },
  cells: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:cells"]);

const localCells = ref([]);
const runningId = ref("");
const savingId = ref("");

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
      title: cell.title,
    });
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
        stderr: e.message || "执行失败",
      };
      emitCells();
    }
  } finally {
    runningId.value = "";
  }
}

function statusTag(status) {
  if (status === "success") return { type: "success", label: "已完成" };
  if (status === "error") return { type: "error", label: "出错" };
  if (status === "running") return { type: "warning", label: "运行中" };
  return { type: "default", label: "待运行" };
}
</script>

<template>
  <div class="notebook-panel">
    <div v-if="!localCells.length" class="notebook-empty">
      <p>Notebook 为空</p>
      <p class="hint">在左侧描述分析需求，AI 将在此生成 Python 单元格。</p>
    </div>

    <article v-for="cell in localCells" :key="cell.id" class="notebook-cell">
      <header class="cell-header">
        <n-input
          v-model:value="cell.title"
          size="small"
          class="cell-title-input"
          placeholder="单元标题"
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
        placeholder="# pandas / matplotlib / seaborn"
        @blur="onCodeBlur(cell)"
      />

      <div v-if="cell.status === 'running'" class="cell-output running">
        <n-spin size="small" /> 正在执行…
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
          alt="chart"
        />
      </div>
    </article>

    <div v-if="savingId" class="notebook-saving">
      <n-icon><RefreshOutline /></n-icon> 保存中…
    </div>
  </div>
</template>

<style scoped>
.notebook-panel {
  height: 100%;
  overflow: auto;
  padding: 12px 14px 24px;
  background: #fafafa;
}

.notebook-empty {
  margin-top: 18vh;
  text-align: center;
  color: var(--n-text-color-3);
}

.notebook-empty .hint {
  margin-top: 8px;
  font-size: 13px;
}

.notebook-cell {
  background: #fff;
  border: 1px solid #e8e8ec;
  border-radius: 10px;
  margin-bottom: 14px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.cell-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
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
  padding: 10px 12px;
  border-top: 1px solid #f0f0f0;
  font-size: 13px;
}

.cell-output pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.cell-output.stdout {
  background: #f8fffe;
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
  border: 1px solid #eee;
  border-radius: 6px;
  background: #fff;
}

.notebook-saving {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px;
  font-size: 12px;
  color: var(--n-text-color-3);
}
</style>
