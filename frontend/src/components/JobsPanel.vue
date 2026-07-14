<script setup>
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  NButton,
  NDataTable,
  NEmpty,
  NIcon,
  NSpace,
  NSpin,
  NTag,
  NTooltip } from "naive-ui";
import { batchDeleteJobs, cancelJob, clearJobs, fetchJobs } from "../api/client";
import { useBatchTableSelection } from "../composables/useBatchTableSelection";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { deleteSequentially } from "../utils/batchActions";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import ListTableFooter from "./ListTableFooter.vue";
import {
  ListOutline,
  RefreshOutline,
  StopCircleOutline,
  TrashOutline } from "@vicons/ionicons5";

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
const ui = usePlatformUi();
const { t, locale } = useI18n();
const loading = ref(false);
const items = ref([]);
const page = ref(1);
const total = ref(0);

const TYPE_LABELS = {
  pdf_translate: "jobs.types.pdf_translate",
  delete_document: "jobs.types.delete_document",
  document_index: "jobs.types.document_index",
  document_parse: "jobs.types.document_parse",
  subscription_import: "jobs.types.subscription_import",
  maintenance: "jobs.types.maintenance"};

const STATUS_LABELS = {
  pending: "jobs.status.pending",
  running: "jobs.status.running",
  done: "jobs.status.done",
  failed: "jobs.status.failed",
  cancelled: "jobs.status.cancelled"};

function jobTypeLabel(type) {
  const key = TYPE_LABELS[type];
  return key ? t(key) : type;
}

function jobStatusLabel(status) {
  const key = STATUS_LABELS[status];
  return key ? t(key) : status;
}

const statusType = {
  pending: "default",
  running: "info",
  done: "success",
  failed: "error",
  cancelled: "warning"};

const CANCELLABLE = new Set(["pending", "running"]);
const CLEARABLE = new Set(["done", "failed", "cancelled"]);

function isParsingDocumentIndex(row) {
  return row.type === "document_index" && Boolean(row.payload?.awaiting_parse);
}

function isJobEffectivelyDone(row) {
  return row.status === "done" || (row.progress ?? 0) >= 100;
}

function displayJobStatus(row) {
  if (isJobEffectivelyDone(row)) return "done";
  if (isParsingDocumentIndex(row)) return "running";
  return row.status;
}

function displayJobProgress(row) {
  if (isJobEffectivelyDone(row)) return 100;
  return row.progress ?? 0;
}

function isCancellable(row) {
  if (isJobEffectivelyDone(row)) return false;
  return CANCELLABLE.has(row.status) || isParsingDocumentIndex(row);
}

function isClearable(row) {
  return CLEARABLE.has(row.status);
}

function canSelectJob(row) {
  return isCancellable(row) || isClearable(row);
}

const {
  checkedRowKeys,
  selectedRows,
  selectedCount,
  onCheckedRowKeysChange,
  clearSelection,
  selectionColumn} = useBatchTableSelection(items, { canSelect: canSelectJob });

const cancellableSelectedRows = computed(() => selectedRows.value.filter(isCancellable));
const clearableSelectedRows = computed(() => selectedRows.value.filter(isClearable));

const canBatchCancel = computed(() => cancellableSelectedRows.value.length > 0);

const canBatchDelete = computed(() => clearableSelectedRows.value.length > 0);

function documentTitle(row) {
  const payload = row?.payload || {};
  const title = payload.document_title || payload.title;
  if (title) return title;
  return row.document_id || "—";
}

function openJob(row) {
  if (row.type === "pdf_translate") {
    emit("navigate");
    router.push({ name: "translate", query: { job: row.id } });
    return;
  }
  if (row.type === "document_index" && row.document_id) {
    emit("navigate");
    router.push({ name: "document-detail", params: { id: row.document_id } });
  }
}

function goJobsPage() {
  emit("navigate");
  router.push({ name: "jobs" });
}

const pageColumns = computed(() => {
  locale.value;
  return [
  selectionColumn(),
  {
    title: t("jobs.columns.type"),
    key: "type",
    width: 144,
    render: (row) => jobTypeLabel(row.type)},
  {
    title: t("jobs.columns.status"),
    key: "status",
    width: 120,
    render: (row) => {
      const status = displayJobStatus(row);
      return h(
        NTag,
        { type: statusType[status] || "default", size: "small" },
        () => jobStatusLabel(status)
      );
    }},
  {
    title: t("jobs.columns.progress"),
    key: "progress",
    width: 96,
    render: (row) => `${displayJobProgress(row)}%` },
  {
    title: t("jobs.columns.document"),
    key: "document_id",
    ellipsis: { tooltip: true },
    render: (row) => documentTitle(row)},
  {
    title: t("jobs.columns.createdAt"),
    key: "created_at",
    width: 216,
    render: (row) => new Date(row.created_at).toLocaleString()},
  {
    title: t("jobs.columns.actions"),
    key: "actions",
    width: 96,
    render: (row) => {
      if (!["pdf_translate", "document_index"].includes(row.type)) return "—";
      return h(
        NButton,
        { text: true, type: "primary", size: "small", onClick: () => openJob(row) },
        () => t("common.view")
      );
    }},
];
});

async function load() {
  loading.value = true;
  try {
    const pageSize = LIST_PAGE_SIZE;
    const data = await fetchJobs({ page: page.value, page_size: pageSize });
    items.value = data.items;
    total.value = data.total;
    clearSelection();
    emit("updated", data);
  } catch (e) {
    ui.error(e);
  } finally {
    loading.value = false;
  }
}

function onPageChange(p) {
  page.value = p;
  load();
}

async function doCancel(jobId) {
  try {
    await cancelJob(jobId);
    ui.success("jobs.messages.cancelled");
    await load();
  } catch (e) {
    ui.error(e);
  }
}

function confirmCancelJob(jobId) {
  ui.confirmAction({
    title: t("batch.cancel"),
    content: t("jobs.confirm.cancelOne"),
    positiveText: t("batch.cancel"),
    onPositive: () => doCancel(jobId)});
}

function handleBatchDelete() {
  const rows = clearableSelectedRows.value;
  if (!rows.length) return;
  const skipped = selectedRows.value.length - rows.length;
  ui.confirmDelete({
    title: t("common.batchDelete"),
    content:
      skipped > 0
        ? t("jobs.confirm.deleteBatchPartial", { count: rows.length, skipped })
        : t("jobs.confirm.deleteBatch", { count: rows.length }),
    onPositive: async () => {
      const { deleted, requested } = await batchDeleteJobs(rows.map((row) => row.id));
      if (!deleted) {
        ui.warning("jobs.messages.nothingToClear");
        return;
      }
      ui.success("jobs.messages.cleared", { count: deleted });
      if (deleted < requested) {
        ui.warning("messages.batchDeletedPartial", {
          success: deleted,
          failed: requested - deleted});
      }
      clearSelection();
      await load();
    }});
}

function handleBatchCancel() {
  const rows = cancellableSelectedRows.value;
  if (!rows.length) return;
  ui.confirmAction({
    title: t("batch.cancel"),
    content: t("jobs.confirm.cancelBatch", { count: rows.length }),
    positiveText: t("batch.cancel"),
    onPositive: async () => {
      const { deleted, failed } = await deleteSequentially(rows, (row) => cancelJob(row.id));
      if (failed.length) {
        ui.warning("messages.batchDeletedPartial", {
          success: deleted,
          failed: failed.length});
      } else {
        ui.success(
          deleted > 1 ? "jobs.messages.cancelledBatch" : "jobs.messages.cancelled",
          { count: deleted }
        );
      }
      clearSelection();
      await load();
    }});
}

async function doClearFinished() {
  try {
    const { deleted } = await clearJobs("finished");
    ui.success(
      deleted ? "jobs.messages.cleared" : "jobs.messages.nothingToClear",
      { count: deleted || 0 }
    );
    page.value = 1;
    await load();
  } catch (e) {
    ui.error(e);
  }
}

let progressPollTimer = null;

function stopProgressPoll() {
  if (progressPollTimer) {
    clearInterval(progressPollTimer);
    progressPollTimer = null;
  }
}

function maybeStartProgressPoll() {
  stopProgressPoll();
  if (!props.active) return;
  const hasActive = items.value.some(
    (j) =>
      !isJobEffectivelyDone(j) &&
      (["pending", "running"].includes(j.status) || isParsingDocumentIndex(j))
  );
  if (!hasActive) return;
  progressPollTimer = setInterval(() => {
    if (!props.active || document.hidden) {
      return;
    }
    load();
  }, 5000);
}

watch(
  () => props.active,
  (visible) => {
    if (visible) {
      load().then(maybeStartProgressPoll);
    } else {
      stopProgressPoll();
    }
  }
);

watch(items, () => {
  if (props.active) maybeStartProgressPoll();
});

onMounted(() => {
  if (props.variant === "page" || props.active) load();
});

onBeforeUnmount(stopProgressPoll);

defineExpose({ load, refresh: load });
</script>

<template>
  <div :class="['jobs-panel', { 'jobs-panel--popover': variant === 'popover' }]">
    <header v-if="variant === 'popover'" class="jobs-panel__header">
      <strong class="platform-text-gradient jobs-panel__title">
        {{ t("jobs.title") }}
      </strong>
      <div class="jobs-panel__actions panel-header-actions">
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
              :aria-label="t('jobs.viewAll')"
              @click="goJobsPage"
            >
              <n-icon :size="19" :component="ListOutline" />
            </button>
          </template>
          {{ t("jobs.viewAll") }}
        </n-tooltip>
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="panel-header-btn panel-header-btn--danger"
              :aria-label="t('jobs.clearDone')"
              @click="doClearFinished"
            >
              <n-icon :size="19" :component="TrashOutline" />
            </button>
          </template>
          {{ t("jobs.clearDone") }}
        </n-tooltip>
      </div>
    </header>

    <n-spin :show="loading" local>
      <template v-if="variant === 'popover'">
        <div class="jobs-panel__body">
        <div v-if="items.length" class="jobs-panel__list">
          <div v-for="row in items" :key="row.id" class="jobs-panel__item">
            <div class="jobs-panel__item-main">
              <n-space :size="7" align="center">
                <n-tag size="small">{{ jobTypeLabel(row.type) }}</n-tag>
                <n-tag :type="statusType[displayJobStatus(row)] || 'default'" size="small">
                  {{ jobStatusLabel(displayJobStatus(row)) }}
                </n-tag>
                <span class="jobs-panel__progress">{{ displayJobProgress(row) }}%</span>
              </n-space>
              <div class="jobs-panel__meta">
                {{ documentTitle(row) }} · {{ new Date(row.created_at).toLocaleString() }}
              </div>
            </div>
            <n-space :size="5" class="jobs-panel__item-actions">
              <n-button
                v-if="['pdf_translate', 'document_index'].includes(row.type)"
                text
                type="primary"
                size="tiny"
                @click="openJob(row)"
              >
                {{ t("common.view") }}
              </n-button>
              <n-button
                v-if="isCancellable(row)"
                text
                type="warning"
                size="tiny"
                @click="confirmCancelJob(row.id)"
              >
                {{ t("batch.cancel") }}
              </n-button>
            </n-space>
          </div>
        </div>
        <n-empty v-else size="small" :description="t('common.empty')" />
        </div>
      </template>

      <template v-else>
        <div class="admin-list-table">
          <div class="jobs-panel__table-body">
            <div class="jobs-panel__toolbar">
              <div class="jobs-panel__toolbar-group">
                <button
                  type="button"
                  class="jobs-toolbar-btn jobs-toolbar-btn--cancel"
                  :disabled="!canBatchCancel"
                  :aria-label="t('batch.cancel')"
                  @click="handleBatchCancel"
                >
                  <n-icon :size="19" :component="StopCircleOutline" />
                  <span>{{ t("batch.cancel") }}</span>
                  <span v-if="cancellableSelectedRows.length > 0 && canBatchCancel" class="jobs-toolbar-btn__badge">
                    {{ cancellableSelectedRows.length }}
                  </span>
                </button>
                <button
                  type="button"
                  class="jobs-toolbar-btn jobs-toolbar-btn--clear"
                  :disabled="!canBatchDelete"
                  :aria-label="t('common.delete')"
                  @click="handleBatchDelete"
                >
                  <n-icon :size="19" :component="TrashOutline" />
                  <span>{{ t("common.delete") }}</span>
                  <span v-if="clearableSelectedRows.length > 0 && canBatchDelete" class="jobs-toolbar-btn__badge">
                    {{ clearableSelectedRows.length }}
                  </span>
                </button>
              </div>
              <n-tooltip placement="bottom">
                <template #trigger>
                  <button
                    type="button"
                    class="jobs-toolbar-btn jobs-toolbar-btn--icon"
                    :aria-label="t('common.refresh')"
                    :disabled="loading"
                    @click="load"
                  >
                    <n-icon :size="19" :component="RefreshOutline" />
                  </button>
                </template>
                {{ t("common.refresh") }}
              </n-tooltip>
              <button
                type="button"
                class="jobs-toolbar-btn jobs-toolbar-btn--clear-done"
                :aria-label="t('jobs.clearDone')"
                @click="doClearFinished"
              >
                <n-icon :size="19" :component="TrashOutline" />
                <span>{{ t("jobs.clearDone") }}</span>
              </button>
            </div>
            <n-data-table
              :columns="pageColumns"
              :data="items"
              :loading="loading"
              :row-key="(row) => row.id"
              :checked-row-keys="checkedRowKeys"
              :pagination="false"
              @update:checked-row-keys="onCheckedRowKeysChange"
            />
          </div>
          <ListTableFooter
            :page="page"
            :page-size="LIST_PAGE_SIZE"
            :item-count="total"
            @update:page="onPageChange"
          />
        </div>
      </template>
    </n-spin>
  </div>
</template>

<style scoped>
.jobs-panel--popover {
  width: 100%;
  box-sizing: border-box;
}

.jobs-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 16px 10px;
  border-bottom: 1px solid var(--platform-border);
  background: linear-gradient(
    180deg,
    var(--platform-toolbar-bg) 0%,
    transparent 100%
  );
}

.jobs-panel__title {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: var(--platform-tracking-tight);
}

.jobs-panel__actions {
  flex-shrink: 0;
}

.jobs-panel__body {
  max-height: 432px;
  overflow-y: auto;
  padding: 8px 16px 14px;
}

.jobs-panel__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.jobs-panel__toolbar-group {
  display: inline-flex;
  align-items: center;
  gap: 0;
  padding: 4px;
  border-radius: var(--platform-radius-sm);
  background: var(--platform-bg-elevated-solid);
  border: 1px solid var(--platform-border);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.jobs-toolbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 38px;
  padding: 0 14px;
  border: none;
  border-radius: calc(var(--platform-radius-sm) - 2px);
  background: transparent;
  color: var(--platform-text-secondary);
  font-size: 16px;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition:
    transform 0.15s var(--platform-ease-smooth),
    background-color 0.15s ease,
    color 0.15s ease,
    box-shadow 0.15s ease;
}

.jobs-toolbar-btn:not(:disabled):hover {
  background: var(--platform-toolbar-bg);
  color: var(--platform-text);
}

.jobs-toolbar-btn:not(:disabled):active {
  transform: translateY(0);
}

.jobs-toolbar-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.jobs-toolbar-btn--cancel:not(:disabled) {
  color: var(--platform-caution);
}

.jobs-toolbar-btn--cancel:not(:disabled):hover {
  color: var(--platform-caution);
  background: var(--platform-caution-soft);
}

.jobs-toolbar-btn--clear-done:not(:disabled) {
  color: var(--platform-danger);
}

.jobs-toolbar-btn--clear-done:not(:disabled):hover {
  color: var(--platform-danger);
  background: var(--platform-danger-soft);
}

.jobs-toolbar-btn--icon {
  width: 38px;
  padding: 0;
  justify-content: center;
}

.jobs-toolbar-btn__badge {
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 1199px;
  font-size: 13px;
  font-weight: 600;
  line-height: 22px;
  text-align: center;
  background: color-mix(in srgb, var(--platform-caution-soft) 88%, var(--platform-caution) 12%);
  color: var(--platform-caution);
}

.jobs-panel__item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 8px;
  margin: 0 -8px;
  border-radius: var(--platform-radius-sm);
  border-bottom: 1px solid var(--platform-border);
  transition:
    background-color 0.2s ease,
    box-shadow 0.2s ease;
}

.jobs-panel__item:last-child {
  border-bottom: none;
}

.jobs-panel__item:hover {
  background: var(--platform-toolbar-bg);
}

.jobs-panel__item-main {
  min-width: 0;
  flex: 1;
}

.jobs-panel__progress {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.jobs-panel__meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--platform-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.jobs-panel__item-actions {
  flex-shrink: 0;
}
</style>
