<script setup>
import { computed, h, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  NButton,
  NDataTable,
  NEmpty,
  NPopconfirm,
  NSpace,
  NSpin,
  NTag,
  NText,
} from "naive-ui";
import { cancelJob, clearJobs, fetchJobs } from "../api/client";
import BatchTableToolbar from "./BatchTableToolbar.vue";
import IconAction from "./IconAction.vue";
import { useBatchTableSelection } from "../composables/useBatchTableSelection";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { deleteSequentially } from "../utils/batchActions";
import { RefreshOutline, TrashOutline } from "@vicons/ionicons5";

const props = defineProps({
  variant: {
    type: String,
    default: "page",
    validator: (v) => v === "page" || v === "popover",
  },
  active: {
    type: Boolean,
    default: true,
  },
});

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
  maintenance: "jobs.types.maintenance",
};

const STATUS_LABELS = {
  pending: "jobs.status.pending",
  running: "jobs.status.running",
  done: "jobs.status.done",
  failed: "jobs.status.failed",
  cancelled: "jobs.status.cancelled",
};

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
  cancelled: "warning",
};

const CANCELLABLE = new Set(["pending", "running"]);

function isCancellable(row) {
  return CANCELLABLE.has(row.status);
}

const {
  checkedRowKeys,
  selectedRows,
  selectedCount,
  onCheckedRowKeysChange,
  clearSelection,
  selectionColumn,
} = useBatchTableSelection(items, { canSelect: isCancellable });

const canBatchCancel = computed(
  () => selectedRows.value.length > 0 && selectedRows.value.every(isCancellable)
);

function openJob(row) {
  if (row.type === "pdf_translate") {
    emit("navigate");
    router.push({ name: "translate", query: { job: row.id } });
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
    width: 120,
    render: (row) => jobTypeLabel(row.type),
  },
  {
    title: t("jobs.columns.status"),
    key: "status",
    width: 100,
    render: (row) =>
      h(
        NTag,
        { type: statusType[row.status] || "default", size: "small" },
        () => jobStatusLabel(row.status)
      ),
  },
  { title: t("jobs.columns.progress"), key: "progress", width: 80, render: (row) => `${row.progress}%` },
  {
    title: t("jobs.columns.document"),
    key: "document_id",
    ellipsis: { tooltip: true },
    render: (row) => row.document_id || "—",
  },
  {
    title: t("jobs.columns.createdAt"),
    key: "created_at",
    width: 180,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
  {
    title: t("jobs.columns.actions"),
    key: "actions",
    width: 80,
    render: (row) => {
      if (row.type !== "pdf_translate") return "—";
      return h(
        NButton,
        { text: true, type: "primary", size: "small", onClick: () => openJob(row) },
        () => t("common.view")
      );
    },
  },
];
});

async function load() {
  loading.value = true;
  try {
    const pageSize = props.variant === "popover" ? 8 : 20;
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

function handleBatchCancel() {
  const rows = selectedRows.value;
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
          failed: failed.length,
        });
      } else {
        ui.success(
          deleted > 1 ? "jobs.messages.cancelledBatch" : "jobs.messages.cancelled",
          { count: deleted }
        );
      }
      clearSelection();
      await load();
    },
  });
}

async function doClear(scope) {
  try {
    const { deleted } = await clearJobs(scope);
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

watch(
  () => props.active,
  (visible) => {
    if (visible) load();
  }
);

onMounted(() => {
  if (props.variant === "page" || props.active) load();
});

defineExpose({ load, refresh: load });
</script>

<template>
  <div :class="['jobs-panel', { 'jobs-panel--popover': variant === 'popover' }]">
    <div v-if="variant === 'popover'" class="jobs-panel__header">
      <n-text strong>{{ t("jobs.title") }}</n-text>
      <n-space :size="4">
        <IconAction :label="t('common.refresh')" :icon="RefreshOutline" size="tiny" @click="load" />
        <n-button text type="primary" size="small" @click="goJobsPage">
          {{ t("jobs.viewAll") }}
        </n-button>
      </n-space>
    </div>

    <n-spin :show="loading">
      <template v-if="variant === 'popover'">
        <div v-if="items.length" class="jobs-panel__list">
          <div v-for="row in items" :key="row.id" class="jobs-panel__item">
            <div class="jobs-panel__item-main">
              <n-space :size="6" align="center">
                <n-tag size="small">{{ jobTypeLabel(row.type) }}</n-tag>
                <n-tag :type="statusType[row.status] || 'default'" size="small">
                  {{ jobStatusLabel(row.status) }}
                </n-tag>
                <span class="jobs-panel__progress">{{ row.progress }}%</span>
              </n-space>
              <div class="jobs-panel__meta">
                {{ new Date(row.created_at).toLocaleString() }}
              </div>
            </div>
            <n-space :size="4" class="jobs-panel__item-actions">
              <n-button
                v-if="row.type === 'pdf_translate'"
                text
                type="primary"
                size="tiny"
                @click="openJob(row)"
              >
                {{ t("common.view") }}
              </n-button>
              <n-popconfirm
                v-if="CANCELLABLE.has(row.status)"
                @positive-click="doCancel(row.id)"
              >
                <template #trigger>
                  <n-button text type="warning" size="tiny">{{ t("batch.cancel") }}</n-button>
                </template>
                {{ t("jobs.confirm.cancelOne") }}
              </n-popconfirm>
            </n-space>
          </div>
        </div>
        <n-empty v-else size="small" :description="t('common.empty')" />
      </template>

      <template v-else>
        <div class="jobs-panel__toolbar">
          <n-space :size="8" align="center" wrap>
            <BatchTableToolbar
              :count="selectedCount"
              :disabled="!canBatchCancel"
              label-key="batch.cancel"
              action-type="warning"
              @action="handleBatchCancel"
            />
            <n-popconfirm @positive-click="doClear('finished')">
              <template #trigger>
                <IconAction :label="t('jobs.clearDone')" :icon="TrashOutline" />
              </template>
              {{ t("jobs.confirm.clearDone") }}
            </n-popconfirm>
            <n-popconfirm @positive-click="doClear('all')">
              <template #trigger>
                <IconAction :label="t('notifications.clearAll')" :icon="TrashOutline" type="default" />
              </template>
              {{ t("jobs.confirm.clearAll") }}
            </n-popconfirm>
          </n-space>
        </div>
        <n-data-table
          :columns="pageColumns"
          :data="items"
          :loading="loading"
          :row-key="(row) => row.id"
          :checked-row-keys="checkedRowKeys"
          @update:checked-row-keys="onCheckedRowKeysChange"
          :pagination="{
            page,
            pageSize: 20,
            itemCount: total,
            onUpdatePage: onPageChange,
          }"
        />
      </template>
    </n-spin>
  </div>
</template>

<style scoped>
.jobs-panel--popover {
  width: min(420px, calc(100vw - 32px));
  padding: 12px 14px;
  background: var(--platform-bg-elevated);
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius);
  box-sizing: border-box;
  box-shadow: var(--platform-shadow-lg);
}

.jobs-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--platform-border);
}

.jobs-panel__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.jobs-panel__toolbar :deep(.batch-table-toolbar) {
  margin-bottom: 0;
}

.jobs-panel__list {
  max-height: 360px;
  overflow-y: auto;
}

.jobs-panel__item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 0;
  border-bottom: 1px solid var(--platform-border);
}

.jobs-panel__item:last-child {
  border-bottom: none;
}

.jobs-panel__item-main {
  min-width: 0;
  flex: 1;
}

.jobs-panel__progress {
  font-size: 12px;
  color: var(--n-text-color-3);
}

.jobs-panel__meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--n-text-color-3);
}

.jobs-panel__item-actions {
  flex-shrink: 0;
}
</style>
