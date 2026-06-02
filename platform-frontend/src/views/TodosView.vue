<script setup>
import { computed, onMounted, ref } from "vue";
import {
  NButton,
  NCard,
  NCheckbox,
  NEmpty,
  NIcon,
  NInput,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSpace,
  NSpin,
  NTag,
  NText,
  useDialog,
  useMessage,
} from "naive-ui";
import { ReorderThreeOutline, SparklesOutline } from "@vicons/ionicons5";
import {
  batchCreateTodos,
  createTodo,
  deleteTodo,
  fetchTodos,
  reorderTodos,
  replacePendingTodos,
  todoLlmPreview,
  updateTodo,
} from "../api/client";
import { deleteSequentially } from "../utils/batchActions";

const message = useMessage();
const dialog = useDialog();

const loading = ref(false);
const pending = ref([]);
const done = ref([]);

const newTitle = ref("");
const adding = ref(false);

const llmText = ref("");
const llmMode = ref("parse");
const llmLoading = ref(false);
const llmPreview = ref(null);
const showLlmModal = ref(false);

const dragFrom = ref(-1);
const dragStatus = ref(null);
const selectedPendingIds = ref([]);
const selectedDoneIds = ref([]);

const canBatchDeletePending = computed(() => selectedPendingIds.value.length > 0);
const canBatchDeleteDone = computed(() => selectedDoneIds.value.length > 0);

function isTodoSelected(status, id) {
  const list = status === "pending" ? selectedPendingIds.value : selectedDoneIds.value;
  return list.includes(id);
}

function toggleTodoSelected(status, id, checked) {
  const target = status === "pending" ? selectedPendingIds : selectedDoneIds;
  if (checked) {
    if (!target.value.includes(id)) target.value = [...target.value, id];
  } else {
    target.value = target.value.filter((x) => x !== id);
  }
}

async function load() {
  loading.value = true;
  try {
    const [p, d] = await Promise.all([fetchTodos("pending"), fetchTodos("done")]);
    pending.value = p;
    done.value = d;
    selectedPendingIds.value = [];
    selectedDoneIds.value = [];
  } catch (e) {
    message.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function addTodo() {
  const title = newTitle.value.trim();
  if (!title) {
    message.warning("请输入待办内容");
    return;
  }
  adding.value = true;
  try {
    await createTodo({ title, note: "" });
    newTitle.value = "";
    await load();
    message.success("已添加");
  } catch (e) {
    message.error(e.message);
  } finally {
    adding.value = false;
  }
}

async function toggleDone(item, checked) {
  try {
    await updateTodo(item.id, { status: checked ? "done" : "pending" });
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

function handleBatchDelete(status) {
  const ids = status === "pending" ? selectedPendingIds.value : selectedDoneIds.value;
  const rows =
    status === "pending"
      ? pending.value.filter((item) => ids.includes(item.id))
      : done.value.filter((item) => ids.includes(item.id));
  if (!rows.length) return;
  const summary = rows.length === 1 ? "该待办" : `选中的 ${rows.length} 条待办`;
  dialog.warning({
    title: "批量删除待办",
    content: `确定删除${summary}？`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      const { deleted, failed } = await deleteSequentially(rows, (row) => deleteTodo(row.id));
      if (status === "pending") selectedPendingIds.value = [];
      else selectedDoneIds.value = [];
      if (failed.length) {
        message.warning(
          `已删除 ${deleted} 条，${failed.length} 条失败：${failed[0].message || "未知错误"}`
        );
      } else {
        message.success(deleted > 1 ? `已删除 ${deleted} 条待办` : "已删除");
      }
      await load();
      return !failed.length;
    },
  });
}

function onDragStart(index, status) {
  dragFrom.value = index;
  dragStatus.value = status;
}

function onDragOver(e) {
  e.preventDefault();
}

async function onDrop(toIndex, status) {
  if (dragFrom.value < 0 || dragStatus.value !== status || dragFrom.value === toIndex) {
    dragFrom.value = -1;
    dragStatus.value = null;
    return;
  }
  const source = status === "pending" ? pending.value : done.value;
  const arr = [...source];
  const [moved] = arr.splice(dragFrom.value, 1);
  arr.splice(toIndex, 0, moved);
  dragFrom.value = -1;
  dragStatus.value = null;
  try {
    if (status === "pending") pending.value = arr;
    else done.value = arr;
    await reorderTodos(status, arr.map((x) => x.id));
  } catch (e) {
    message.error(e.message);
    await load();
  }
}

function openLlm() {
  llmPreview.value = null;
  showLlmModal.value = true;
}

async function runLlmPreview() {
  if (!llmText.value.trim()) {
    message.warning("请输入描述或调整指令");
    return;
  }
  llmLoading.value = true;
  try {
    llmPreview.value = await todoLlmPreview(llmText.value.trim(), llmMode.value);
  } catch (e) {
    message.error(e.message);
  } finally {
    llmLoading.value = false;
  }
}

async function applyLlm() {
  if (!llmPreview.value?.items?.length) {
    message.warning("请先预览并确认有待办项");
    return;
  }
  llmLoading.value = true;
  try {
    const items = llmPreview.value.items.map((x) => ({
      title: x.title,
      note: x.note || "",
    }));
    if (llmPreview.value.mode === "adjust") {
      await replacePendingTodos(items);
      message.success("已按 AI 建议更新待办列表");
    } else {
      await batchCreateTodos(items);
      message.success(`已添加 ${items.length} 条待办`);
    }
    showLlmModal.value = false;
    llmText.value = "";
    llmPreview.value = null;
    await load();
  } catch (e) {
    message.error(e.message);
  } finally {
    llmLoading.value = false;
  }
}

function formatDoneTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return "";
  }
}

function isDragging(index, status) {
  return dragFrom.value === index && dragStatus.value === status;
}

onMounted(load);
</script>

<template>
  <div class="todos-page feature-page">
    <n-card size="small" class="todos-card">
      <template #header>
        <n-space align="center" justify="space-between" style="width: 100%">
          <n-text strong>待办事项</n-text>
          <n-button size="small" quaternary @click="openLlm">
            <template #icon>
              <n-icon :component="SparklesOutline" />
            </template>
            智能录入
          </n-button>
        </n-space>
      </template>

      <div class="add-row">
        <n-input
          v-model:value="newTitle"
          placeholder="添加待办，回车确认"
          clearable
          @keyup.enter="addTodo"
        />
        <n-button type="primary" :loading="adding" @click="addTodo">添加</n-button>
      </div>
      <p class="feature-tip">左右分栏同时查看；拖拽手柄排序；勾选移至右侧「已完成」。</p>

      <n-spin :show="loading">
        <div class="todos-columns">
          <section class="todo-column todo-column--pending">
            <header class="column-head">
              <span class="column-title">待办</span>
              <n-tag size="small" :bordered="false" type="info">{{ pending.length }}</n-tag>
              <n-button
                size="tiny"
                type="error"
                secondary
                :disabled="!canBatchDeletePending"
                @click="handleBatchDelete('pending')"
              >
                删除
              </n-button>
            </header>
            <n-empty
              v-if="!pending.length && !loading"
              description="暂无待办"
              size="small"
              class="column-empty"
            />
            <ul v-else class="todo-list">
              <li
                v-for="(item, index) in pending"
                :key="item.id"
                class="todo-item"
                :class="{ 'todo-item--dragging': isDragging(index, 'pending') }"
                draggable="true"
                @dragstart="onDragStart(index, 'pending')"
                @dragover="onDragOver"
                @drop="onDrop(index, 'pending')"
              >
                <n-checkbox
                  :checked="isTodoSelected('pending', item.id)"
                  @update:checked="(v) => toggleTodoSelected('pending', item.id, v)"
                />
                <span class="todo-drag" title="拖拽排序">
                  <n-icon :component="ReorderThreeOutline" :size="18" />
                </span>
                <n-checkbox
                  :checked="false"
                  @update:checked="(v) => v && toggleDone(item, true)"
                />
                <div class="todo-body">
                  <n-text class="todo-title">{{ item.title }}</n-text>
                  <n-text v-if="item.note" depth="3" class="todo-note">{{ item.note }}</n-text>
                </div>
              </li>
            </ul>
          </section>

          <section class="todo-column todo-column--done">
            <header class="column-head">
              <span class="column-title">已完成</span>
              <n-tag size="small" :bordered="false" type="success">{{ done.length }}</n-tag>
              <n-button
                size="tiny"
                type="error"
                secondary
                :disabled="!canBatchDeleteDone"
                @click="handleBatchDelete('done')"
              >
                删除
              </n-button>
            </header>
            <n-empty
              v-if="!done.length && !loading"
              description="暂无已完成"
              size="small"
              class="column-empty"
            />
            <ul v-else class="todo-list">
              <li
                v-for="(item, index) in done"
                :key="item.id"
                class="todo-item todo-item--done"
                :class="{ 'todo-item--dragging': isDragging(index, 'done') }"
                draggable="true"
                @dragstart="onDragStart(index, 'done')"
                @dragover="onDragOver"
                @drop="onDrop(index, 'done')"
              >
                <n-checkbox
                  :checked="isTodoSelected('done', item.id)"
                  @update:checked="(v) => toggleTodoSelected('done', item.id, v)"
                />
                <span class="todo-drag" title="拖拽排序">
                  <n-icon :component="ReorderThreeOutline" :size="18" />
                </span>
                <n-checkbox
                  :checked="true"
                  @update:checked="(v) => !v && toggleDone(item, false)"
                />
                <div class="todo-body">
                  <n-text delete class="todo-title">{{ item.title }}</n-text>
                  <n-text v-if="item.note" depth="3" class="todo-note">{{ item.note }}</n-text>
                  <n-text v-if="item.completed_at" depth="3" class="todo-time">
                    {{ formatDoneTime(item.completed_at) }}
                  </n-text>
                </div>
              </li>
            </ul>
          </section>
        </div>
      </n-spin>
    </n-card>

    <n-modal
      v-model:show="showLlmModal"
      preset="card"
      title="LLM 智能录入 / 调整"
      style="width: min(560px, 92vw)"
    >
      <n-space vertical :size="12">
        <n-radio-group v-model:value="llmMode" size="small">
          <n-radio-button value="parse">智能录入（从文本解析）</n-radio-button>
          <n-radio-button value="adjust">智能调整（优化当前待办）</n-radio-button>
        </n-radio-group>
        <n-input
          v-model:value="llmText"
          type="textarea"
          :rows="5"
          :placeholder="
            llmMode === 'parse'
              ? '粘贴会议纪要、邮件或想法，例如：下周完成碳排放报告初稿；联系财务部核对数据'
              : '描述如何调整，例如：把报告相关合并为一条并置顶；删除已过期的会议准备'
          "
        />
        <n-space>
          <n-button :loading="llmLoading" @click="runLlmPreview">预览</n-button>
          <n-button
            type="primary"
            :loading="llmLoading"
            :disabled="!llmPreview?.items?.length"
            @click="applyLlm"
          >
            确认应用
          </n-button>
        </n-space>
        <div v-if="llmPreview?.items?.length" class="llm-preview">
          <n-text depth="3" style="font-size: 12px">{{ llmPreview.message }}</n-text>
          <ul>
            <li v-for="(row, i) in llmPreview.items" :key="i">
              <n-tag v-if="llmPreview.mode === 'adjust'" size="tiny" :bordered="false">#{{ i + 1 }}</n-tag>
              {{ row.title }}
              <n-text v-if="row.note" depth="3"> — {{ row.note }}</n-text>
            </li>
          </ul>
          <n-text v-if="llmPreview.mode === 'adjust'" depth="3" type="warning" style="font-size: 12px">
            确认后将替换左侧「待办」列表（已完成不受影响）
          </n-text>
        </div>
      </n-space>
    </n-modal>
  </div>
</template>

<style scoped>
.todos-page {
  max-width: 1100px;
  margin: 0 auto;
}
.todos-card :deep(.n-card-header) {
  padding-bottom: 8px;
}
.add-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.add-row :deep(.n-input) {
  flex: 1;
}
.todos-columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}
.todo-column {
  min-height: 200px;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-radius: var(--platform-radius-sm, 8px);
  background: rgba(248, 250, 252, 0.6);
  overflow: hidden;
}
.todo-column--pending {
  border-top: 2px solid #38bdf8;
}
.todo-column--done {
  border-top: 2px solid #14b8a6;
}
.column-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.06));
  background: #fff;
}
.column-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}
.column-empty {
  padding: 28px 12px;
}
.todo-list {
  list-style: none;
  margin: 0;
  padding: 4px 6px 8px;
  max-height: min(65vh, 560px);
  overflow-y: auto;
}
.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 6px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: #fff;
  margin-bottom: 4px;
  transition: background 0.15s, border-color 0.15s;
}
.todo-item:hover {
  border-color: var(--platform-border, rgba(15, 23, 42, 0.1));
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.todo-item--done {
  opacity: 0.92;
}
.todo-item--dragging {
  opacity: 0.55;
}
.todo-drag {
  flex-shrink: 0;
  color: var(--n-text-color-3);
  cursor: grab;
  padding-top: 2px;
}
.todo-drag:active {
  cursor: grabbing;
}
.todo-body {
  flex: 1;
  min-width: 0;
}
.todo-title {
  display: block;
  font-size: 14px;
  line-height: 1.45;
}
.todo-note,
.todo-time {
  display: block;
  font-size: 12px;
  margin-top: 2px;
}
.llm-preview ul {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.55;
}
@media (max-width: 768px) {
  .todos-columns {
    grid-template-columns: 1fr;
  }
  .todo-list {
    max-height: none;
  }
}
</style>
