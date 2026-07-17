<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  NButton,
  NCard,
  NCheckbox,
  NDatePicker,
  NEmpty,
  NIcon,
  NInput,
  NRadioButton,
  NRadioGroup,
  NSpace,
  NSpin,
  NTag,
  NText,
  NTooltip } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import {
  CalendarClearOutline,
  ListOutline,
  RefreshOutline,
  ReorderThreeOutline,
  SparklesOutline,
  TimeOutline,
  TrashOutline } from "@vicons/ionicons5";
import IconAction from "./IconAction.vue";
import HintTooltip from "./HintTooltip.vue";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  batchCreateTodos,
  createTodo,
  deleteTodo,
  fetchTodos,
  reorderTodos,
  replacePendingTodos,
  todoLlmPreview,
  updateTodo } from "../api/client";
import { deleteSequentially } from "../utils/batchActions";

const props = defineProps({
  variant: {
    type: String,
    default: "page",
    validator: (v) => v === "page" || v === "popover"},
  active: {
    type: Boolean,
    default: true}});

const emit = defineEmits(["updated", "navigate"]);

const router = useRouter();
const { t } = useI18n();
const ui = usePlatformUi();

const loading = ref(false);
const pending = ref([]);
const done = ref([]);

const newTitle = ref("");
const newDueAt = ref(null);
const showDuePicker = ref(false);
const adding = ref(false);

const editingDueId = ref(null);
const editingDueValue = ref(null);

const llmText = ref("");
const llmMode = ref("parse");
const llmLoading = ref(false);
const llmPreview = ref(null);
const showLlmModal = ref(false);

const dragFrom = ref(-1);
const dragStatus = ref(null);
const selectedPendingIds = ref([]);
const selectedDoneIds = ref([]);
const statusToggleReady = ref(false);
let loadSeq = 0;

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
  const seq = ++loadSeq;
  loading.value = true;
  statusToggleReady.value = false;
  try {
    const [p, d] = await Promise.all([fetchTodos("pending"), fetchTodos("done")]);
    if (seq !== loadSeq) return;
    pending.value = Array.isArray(p) ? p : [];
    done.value = Array.isArray(d) ? d : [];
    selectedPendingIds.value = [];
    selectedDoneIds.value = [];
    emit("updated", { pending: pending.value.length, done: done.value.length });
  } catch (e) {
    if (seq !== loadSeq) return;
    ui.error(e.message);
  } finally {
    if (seq === loadSeq) {
      loading.value = false;
      await nextTick();
      statusToggleReady.value = true;
    }
  }
}

async function addTodo() {
  const title = newTitle.value.trim();
  if (!title) {
    ui.warning(t("todos.inputRequired"));
    return;
  }
  adding.value = true;
  try {
    const body = { title, note: "" };
    if (newDueAt.value != null) {
      body.due_at = new Date(newDueAt.value).toISOString();
    }
    await createTodo(body);
    newTitle.value = "";
    newDueAt.value = null;
    showDuePicker.value = false;
    await load();
    ui.success(t("todos.messages.added"));
  } catch (e) {
    ui.error(e.message);
  } finally {
    adding.value = false;
  }
}

async function toggleDone(item, checked) {
  try {
    await updateTodo(item.id, {
      status: checked ? "done" : "pending",
      due_at: item.due_at ?? null,
    });
    await load();
  } catch (e) {
    ui.error(e.message);
  }
}

function onStatusChange(item, checked) {
  if (!statusToggleReady.value) return;
  const isDone = item.status === "done";
  if (checked === isDone) return;
  toggleDone(item, checked);
}

function handleBatchDelete(status) {
  const ids = status === "pending" ? selectedPendingIds.value : selectedDoneIds.value;
  const rows =
    status === "pending"
      ? pending.value.filter((item) => ids.includes(item.id))
      : done.value.filter((item) => ids.includes(item.id));
  if (!rows.length) return;
  const summary =
    rows.length === 1
      ? t("todos.deleteSummaryOne")
      : t("todos.deleteSummaryMany", { count: rows.length });
  ui.confirmDelete({
    title: t("todos.batchDeleteTitle"),
    content: t("todos.confirmDeleteContent", { summary }),
    onPositive: async () => {
      const { deleted, failed } = await deleteSequentially(rows, (row) => deleteTodo(row.id));
      if (status === "pending") selectedPendingIds.value = [];
      else selectedDoneIds.value = [];
      if (failed.length) {
        ui.warning(
          t("todos.deletePartial", {
            deleted,
            failed: failed.length,
            message: failed[0].message || t("todos.unknownError"),
          })
        );
      } else {
        ui.success(
          deleted > 1 ? t("todos.deleteMultiple", { count: deleted }) : t("todos.messages.deleted")
        );
      }
      await load();
    }});
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
    ui.error(e.message);
    await load();
  }
}

function openLlm() {
  llmPreview.value = null;
  showLlmModal.value = true;
}

async function runLlmPreview() {
  if (!llmText.value.trim()) {
    ui.warning(t("todos.llmInputRequired"));
    return;
  }
  llmLoading.value = true;
  try {
    llmPreview.value = await todoLlmPreview(llmText.value.trim(), llmMode.value);
  } catch (e) {
    ui.error(e.message);
  } finally {
    llmLoading.value = false;
  }
}

async function applyLlm() {
  if (!llmPreview.value?.items?.length) {
    ui.warning(t("todos.previewRequired"));
    return;
  }
  llmLoading.value = true;
  try {
    const items = llmPreview.value.items.map((x) => ({
      title: x.title,
      note: x.note || ""}));
    if (llmPreview.value.mode === "adjust") {
      await replacePendingTodos(items);
      ui.success(t("todos.messages.aiUpdated"));
    } else {
      await batchCreateTodos(items);
      ui.success(t("todos.messages.aiAdded", { count: items.length }));
    }
    showLlmModal.value = false;
    llmText.value = "";
    llmPreview.value = null;
    await load();
  } catch (e) {
    ui.error(e.message);
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

function formatDueTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const todayStr = d.toDateString() === now.toDateString();
    const tomorrow = new Date(now.getTime() + 86400000);
    const tomorrowStr = d.toDateString() === tomorrow.toDateString();
    const timeStr = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (todayStr) return timeStr;
    if (tomorrowStr) return t("todos.tomorrow") + " " + timeStr;
    const dateStr = d.toLocaleDateString([], { month: "short", day: "numeric" });
    return dateStr + " " + timeStr;
  } catch {
    return "";
  }
}

function isOverdue(iso) {
  if (!iso) return false;
  try {
    return new Date(iso) < new Date();
  } catch {
    return false;
  }
}

function startEditDue(item) {
  editingDueId.value = item.id;
  editingDueValue.value = item.due_at ? new Date(item.due_at).getTime() : Date.now();
}

function cancelEditDue() {
  editingDueId.value = null;
  editingDueValue.value = null;
}

async function saveDue(item) {
  const val = editingDueValue.value;
  editingDueId.value = null;
  editingDueValue.value = null;
  if (val == null) return;
  try {
    const dueAt = new Date(val).toISOString();
    await updateTodo(item.id, { due_at: dueAt });
    await load();
  } catch (e) {
    ui.error(e.message);
  }
}

async function clearDue(item) {
  editingDueId.value = null;
  editingDueValue.value = null;
  try {
    await updateTodo(item.id, { due_at: null });
    await load();
  } catch (e) {
    ui.error(e.message);
  }
}

function isDragging(index, status) {
  return dragFrom.value === index && dragStatus.value === status;
}

function goTodosPage() {
  emit("navigate");
  router.push({ name: "todos" });
}

watch(
  () => props.active,
  (visible) => {
    if (visible) load();
  }
);

onMounted(() => {
  if (props.active) load();
});

onUnmounted(() => {
  loadSeq += 1;
});

defineExpose({ load, refresh: load });
</script>

<template>
  <div :class="['todos-panel', { 'todos-panel--popover': variant === 'popover' }]">
    <header v-if="variant === 'popover'" class="todos-panel__header">
      <strong class="platform-text-gradient todos-panel__title">
        {{ t("header.todos") }}
      </strong>
      <div class="todos-panel__actions panel-header-actions">
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="panel-header-btn"
              :aria-label="t('common.refresh')"
              :disabled="loading"
              @click="load"
            >
              <n-icon :size="19" :component="RefreshOutline" />
            </button>
          </template>
          {{ t("common.refresh") }}
        </n-tooltip>
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="panel-header-btn panel-header-btn--accent"
              :aria-label="t('todos.smartEntry')"
              @click="openLlm"
            >
              <n-icon :size="19" :component="SparklesOutline" />
            </button>
          </template>
          {{ t("todos.smartEntry") }}
        </n-tooltip>
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="panel-header-btn panel-header-btn--accent"
              :aria-label="t('todos.viewAll')"
              @click="goTodosPage"
            >
              <n-icon :size="19" :component="ListOutline" />
            </button>
          </template>
          {{ t("todos.viewAll") }}
        </n-tooltip>
      </div>
    </header>

    <n-card v-if="variant === 'page'" size="small" class="todos-card">
      <template #header-extra>
        <n-space align="center" :size="5">
          <HintTooltip :text="t('todos.pageHint')" />
          <n-button size="small" quaternary @click="openLlm">
            <template #icon>
              <n-icon :component="SparklesOutline" />
            </template>
            {{ t("todos.smartEntry") }}
          </n-button>
        </n-space>
      </template>

      <div class="add-row">
        <div class="add-row__input-group">
          <n-input
            v-model:value="newTitle"
            :placeholder="t('todos.addPlaceholderEnter')"
            clearable
            @keyup.enter="addTodo"
          />
          <n-tooltip placement="top">
            <template #trigger>
              <n-button
                size="small"
                quaternary
                :class="{ 'add-due-btn--active': showDuePicker }"
                class="add-due-btn"
                @click="showDuePicker = !showDuePicker"
              >
                <template #icon><n-icon :component="TimeOutline" :size="18" /></template>
              </n-button>
            </template>
            {{ newDueAt ? t("todos.setDueDateTime") : t("todos.setDueDate") }}
          </n-tooltip>
          <n-button type="primary" :loading="adding" @click="addTodo">{{ t("todos.add") }}</n-button>
        </div>
        <div v-if="showDuePicker" class="add-row__picker">
          <n-date-picker
            v-model:value="newDueAt"
            type="datetime"
            :placeholder="t('todos.setDueDateTime')"
            clearable
            style="width: 100%"
          />
          <n-tag v-if="newDueAt" closable size="tiny" @close="newDueAt = null" style="margin-top: 6px">
            {{ formatDueTime(new Date(newDueAt).toISOString()) }}
          </n-tag>
        </div>
      </div>

      <n-spin :show="loading" local>
        <div class="todos-columns">
          <section class="todo-column todo-column--pending">
            <header class="column-head">
              <span class="column-title">{{ t("todos.pendingColumn") }}</span>
              <n-tag size="small" :bordered="false" type="info">{{ pending.length }}</n-tag>
              <IconAction
                :label="t('common.delete')"
                :icon="TrashOutline"
                type="error"
                size="tiny"
                :disabled="!canBatchDeletePending"
                @click="handleBatchDelete('pending')"
              />
            </header>
            <n-empty
              v-if="!pending.length && !loading"
              :description="t('todos.emptyPendingShort')"
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
                <span class="todo-drag" :title="t('todos.dragSort')">
                  <n-icon :component="ReorderThreeOutline" :size="22" />
                </span>
                <n-checkbox
                  :checked="item.status === 'done'"
                  @update:checked="(v) => onStatusChange(item, v)"
                />
                <div class="todo-body">
                  <n-text class="todo-title">{{ item.title }}</n-text>
                  <n-text v-if="item.note" depth="3" class="todo-note">{{ item.note }}</n-text>
                  <div v-if="editingDueId === item.id" class="todo-due-edit">
                    <n-date-picker
                      v-model:value="editingDueValue"
                      type="datetime"
                      size="small"
                      style="width: 220px"
                    />
                    <n-button size="tiny" type="primary" @click="saveDue(item)">{{ t("todos.confirmApply") }}</n-button>
                    <n-button size="tiny" quaternary @click="cancelEditDue">{{ t("common.cancel") }}</n-button>
                    <n-button v-if="item.due_at" size="tiny" quaternary @click="clearDue(item)">{{ t("todos.clearDueDate") }}</n-button>
                  </div>
                  <div
                    v-else-if="item.due_at"
                    class="todo-due"
                    :class="{ 'todo-due--overdue': isOverdue(item.due_at) && item.status === 'pending' }"
                    @click.stop="startEditDue(item)"
                  >
                    <n-icon :component="CalendarClearOutline" :size="14" />
                    <span>{{ formatDueTime(item.due_at) }}</span>
                  </div>
                </div>
              </li>
            </ul>
          </section>

          <section class="todo-column todo-column--done">
            <header class="column-head">
              <span class="column-title">{{ t("todos.done") }}</span>
              <n-tag size="small" :bordered="false" type="success">{{ done.length }}</n-tag>
              <IconAction
                :label="t('common.delete')"
                :icon="TrashOutline"
                type="error"
                size="tiny"
                :disabled="!canBatchDeleteDone"
                @click="handleBatchDelete('done')"
              />
            </header>
            <n-empty
              v-if="!done.length && !loading"
              :description="t('todos.emptyDoneShort')"
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
                <span class="todo-drag" :title="t('todos.dragSort')">
                  <n-icon :component="ReorderThreeOutline" :size="22" />
                </span>
                <n-checkbox
                  :checked="item.status === 'done'"
                  @update:checked="(v) => onStatusChange(item, v)"
                />
                <div class="todo-body">
                  <n-text delete class="todo-title">{{ item.title }}</n-text>
                  <n-text v-if="item.note" depth="3" class="todo-note">{{ item.note }}</n-text>
                  <n-text v-if="item.completed_at" depth="3" class="todo-time">
                    {{ formatDoneTime(item.completed_at) }}
                  </n-text>
                  <div
                    v-if="item.due_at"
                    class="todo-due"
                    :class="{ 'todo-due--done': true }"
                    @click.stop="startEditDue(item)"
                  >
                    <n-icon :component="CalendarClearOutline" :size="14" />
                    <span>{{ formatDueTime(item.due_at) }}</span>
                  </div>
                </div>
              </li>
            </ul>
          </section>
        </div>
      </n-spin>
    </n-card>

    <template v-else>
      <div class="add-row add-row--popover">
        <div class="add-row__input-group">
          <n-input
            v-model:value="newTitle"
            :placeholder="t('todos.addPlaceholderEnter')"
            clearable
            size="small"
            @keyup.enter="addTodo"
          />
          <n-tooltip placement="top">
            <template #trigger>
              <n-button
                size="tiny"
                quaternary
                :class="{ 'add-due-btn--active': showDuePicker }"
                class="add-due-btn"
                @click="showDuePicker = !showDuePicker"
              >
                <template #icon><n-icon :component="TimeOutline" :size="16" /></template>
              </n-button>
            </template>
            {{ newDueAt ? t("todos.setDueDateTime") : t("todos.setDueDate") }}
          </n-tooltip>
          <n-button type="primary" size="small" :loading="adding" @click="addTodo">{{ t("todos.add") }}</n-button>
        </div>
        <div v-if="showDuePicker" class="add-row__picker add-row__picker--popover">
          <n-date-picker
            v-model:value="newDueAt"
            type="datetime"
            :placeholder="t('todos.setDueDateTime')"
            clearable
            size="small"
            style="width: 100%"
          />
          <n-tag v-if="newDueAt" closable size="tiny" @close="newDueAt = null" style="margin-top: 4px">
            {{ formatDueTime(new Date(newDueAt).toISOString()) }}
          </n-tag>
        </div>
      </div>

      <n-spin :show="loading" local>
        <div class="todos-panel__body">
          <div class="todos-columns">
            <section class="todo-column todo-column--pending">
              <header class="column-head">
                <span class="column-title">{{ t("todos.pendingColumn") }}</span>
                <n-tag size="small" :bordered="false" type="info">{{ pending.length }}</n-tag>
                <IconAction
                  :label="t('common.delete')"
                  :icon="TrashOutline"
                  type="error"
                  size="tiny"
                  :disabled="!canBatchDeletePending"
                  @click="handleBatchDelete('pending')"
                />
              </header>
              <n-empty
                v-if="!pending.length && !loading"
                :description="t('todos.emptyPendingShort')"
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
                  <span class="todo-drag" :title="t('todos.dragSort')">
                    <n-icon :component="ReorderThreeOutline" :size="19" />
                  </span>
                  <n-checkbox
                    :checked="item.status === 'done'"
                    @update:checked="(v) => onStatusChange(item, v)"
                  />
                  <div class="todo-body">
                    <n-text class="todo-title">{{ item.title }}</n-text>
                    <div
                      v-if="item.due_at"
                      class="todo-due"
                      :class="{ 'todo-due--overdue': isOverdue(item.due_at) && item.status === 'pending' }"
                      @click.stop="startEditDue(item)"
                    >
                      <n-icon :component="CalendarClearOutline" :size="12" />
                      <span>{{ formatDueTime(item.due_at) }}</span>
                    </div>
                  </div>
                </li>
              </ul>
            </section>

            <section class="todo-column todo-column--done">
              <header class="column-head">
                <span class="column-title">{{ t("todos.done") }}</span>
                <n-tag size="small" :bordered="false" type="success">{{ done.length }}</n-tag>
                <IconAction
                  :label="t('common.delete')"
                  :icon="TrashOutline"
                  type="error"
                  size="tiny"
                  :disabled="!canBatchDeleteDone"
                  @click="handleBatchDelete('done')"
                />
              </header>
              <n-empty
                v-if="!done.length && !loading"
                :description="t('todos.emptyDoneShort')"
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
                  <span class="todo-drag" :title="t('todos.dragSort')">
                    <n-icon :component="ReorderThreeOutline" :size="19" />
                  </span>
                  <n-checkbox
                    :checked="item.status === 'done'"
                    @update:checked="(v) => onStatusChange(item, v)"
                  />
                  <div class="todo-body">
                    <n-text delete class="todo-title">{{ item.title }}</n-text>
                    <div
                      v-if="item.due_at"
                      class="todo-due todo-due--done"
                    >
                      <n-icon :component="CalendarClearOutline" :size="12" />
                      <span>{{ formatDueTime(item.due_at) }}</span>
                    </div>
                  </div>
                </li>
              </ul>
            </section>
          </div>
        </div>
      </n-spin>
    </template>

    <AdminFormModal
      v-model:show="showLlmModal"
      :title="t('todos.llmModalTitle')"
      width="min(672px, 92vw)"
    >
      <n-space vertical :size="14">
        <n-radio-group v-model:value="llmMode" size="small">
          <n-radio-button value="parse">{{ t("todos.llmModeParse") }}</n-radio-button>
          <n-radio-button value="adjust">{{ t("todos.llmModeAdjust") }}</n-radio-button>
        </n-radio-group>
        <n-input
          v-model:value="llmText"
          type="textarea"
          :rows="5"
          :placeholder="
            llmMode === 'parse' ? t('todos.llmPlaceholderParse') : t('todos.llmPlaceholderAdjust')
          "
        />
        <n-space>
          <n-button :loading="llmLoading" @click="runLlmPreview">{{ t("todos.preview") }}</n-button>
          <n-button
            type="primary"
            :loading="llmLoading"
            :disabled="!llmPreview?.items?.length"
            @click="applyLlm"
          >
            {{ t("todos.confirmApply") }}
          </n-button>
        </n-space>
        <div v-if="llmPreview?.items?.length" class="llm-preview">
          <n-text depth="3" style="font-size: 14px">{{ llmPreview.message }}</n-text>
          <ul>
            <li v-for="(row, i) in llmPreview.items" :key="i">
              <n-tag v-if="llmPreview.mode === 'adjust'" size="tiny" :bordered="false">#{{ i + 1 }}</n-tag>
              {{ row.title }}
              <n-text v-if="row.note" depth="3"> — {{ row.note }}</n-text>
            </li>
          </ul>
          <n-text v-if="llmPreview.mode === 'adjust'" depth="3" type="warning" style="font-size: 14px">
            {{ t("todos.adjustWarning") }}
          </n-text>
        </div>
      </n-space>
    </AdminFormModal>
  </div>
</template>

<style scoped>
.todos-panel--page {
  max-width: 1320px;
  margin: 0 auto;
}

.todos-panel--popover {
  width: 100%;
  box-sizing: border-box;
}

.todos-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 17px 12px;
  border-bottom: 1px solid var(--platform-border);
  background: linear-gradient(180deg, var(--platform-toolbar-bg) 0%, transparent 100%);
}

.todos-panel__title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: var(--platform-tracking-tight);
}

.todos-panel__actions {
  flex-shrink: 0;
}

.todos-panel__body {
  padding: 12px 14px 14px;
}

.todos-card :deep(.n-card-header) {
  padding-bottom: 10px;
}

.add-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.add-row__input-group {
  display: flex;
  gap: 10px;
  align-items: center;
}

.add-row--popover {
  padding: 12px 14px 0;
}

.add-row :deep(.n-input) {
  flex: 1;
}

.add-row__picker {
  padding: 8px 10px;
  background: var(--platform-bg-elevated, #f8fafb);
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-radius: var(--platform-radius-sm, 10px);
}

.add-row__picker--popover {
  padding: 6px 8px;
}

.add-due-btn {
  flex-shrink: 0;
  color: var(--n-text-color-3) !important;
}

.add-due-btn--active {
  color: var(--platform-accent) !important;
}

.todos-columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.todos-panel--popover .todos-columns {
  gap: 10px;
}

.todo-column {
  min-height: 144px;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-radius: var(--platform-radius-sm, 10px);
  background: rgba(248, 250, 252, 0.6);
  overflow: hidden;
}

.todo-column--pending,
.todo-column--done {
  border-top: 2px solid var(--platform-accent);
}

.column-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
}

.todos-panel--popover .column-head {
  padding: 10px 12px;
}

.column-title {
  font-size: 17px;
  font-weight: 600;
  color: #0f172a;
}

.todos-panel--popover .column-title {
  font-size: 16px;
}

.column-empty {
  padding: 34px 14px;
}

.todos-panel--popover .column-empty {
  padding: 24px 12px;
}

.todo-list {
  list-style: none;
  margin: 0;
  padding: 5px 7px 10px;
  max-height: min(65vh, 672px);
  overflow-y: auto;
}

.todos-panel--popover .todo-list {
  max-height: 240px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 7px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: #fff;
  margin-bottom: 5px;
  transition: background 0.15s, border-color 0.15s;
}

.todos-panel--popover .todo-item {
  gap: 7px;
  padding: 7px 5px;
}

.todo-item:hover {
  border-color: var(--platform-border, rgba(15, 23, 42, 0.1));
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04);
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
  font-size: 17px;
  line-height: 1.45;
}

.todos-panel--popover .todo-title {
  font-size: 16px;
}

.todo-note,
.todo-time {
  display: block;
  font-size: 14px;
  margin-top: 2px;
}

.todo-due {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  margin-top: 4px;
  color: var(--n-text-color-3);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
  transition: background 0.15s;
}

.todo-due:hover {
  background: var(--platform-bg-tertiary, rgba(15, 23, 42, 0.04));
}

.todo-due--overdue {
  color: var(--platform-danger, #d03050) !important;
  font-weight: 500;
}

.todo-due--done {
  text-decoration: line-through;
  opacity: 0.65;
}

.todo-due-edit {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding: 6px;
  background: var(--platform-bg-elevated, #f8fafb);
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-radius: var(--platform-radius-sm, 10px);
}

.todos-panel--popover .todo-due {
  font-size: 12px;
  margin-top: 2px;
}

.llm-preview ul {
  margin: 10px 0 0;
  padding-left: 22px;
  font-size: 16px;
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
