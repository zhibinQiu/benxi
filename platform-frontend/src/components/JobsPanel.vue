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
  useDialog,
  useMessage,
} from "naive-ui";
import { cancelJob, clearJobs, fetchJobs } from "../api/client";
import BatchTableToolbar from "./BatchTableToolbar.vue";
import { useBatchTableSelection } from "../composables/useBatchTableSelection";
import { deleteSequentially } from "../utils/batchActions";

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
const message = useMessage();
const dialog = useDialog();
const loading = ref(false);
const items = ref([]);
const page = ref(1);
const total = ref(0);

const TYPE_LABELS = {
  pdf_translate: "PDF 翻译",
  delete_document: "删除文档",
  document_index: "文档索引",
  document_parse: "文档解析",
  maintenance: "维护任务",
};

const STATUS_LABELS = {
  pending: "等待中",
  running: "运行中",
  done: "已完成",
  failed: "失败",
  cancelled: "已终止",
};

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

const pageColumns = computed(() => [
  selectionColumn(),
  {
    title: "类型",
    key: "type",
    width: 120,
    render: (row) => TYPE_LABELS[row.type] || row.type,
  },
  {
    title: "状态",
    key: "status",
    width: 100,
    render: (row) =>
      h(
        NTag,
        { type: statusType[row.status] || "default", size: "small" },
        () => STATUS_LABELS[row.status] || row.status
      ),
  },
  { title: "进度", key: "progress", width: 80, render: (row) => `${row.progress}%` },
  {
    title: "文档",
    key: "document_id",
    ellipsis: { tooltip: true },
    render: (row) => row.document_id || "—",
  },
  {
    title: "创建时间",
    key: "created_at",
    width: 180,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
  {
    title: "错误",
    key: "error_message",
    ellipsis: { tooltip: true },
    render: (row) => row.error_message || "—",
  },
  {
    title: "操作",
    key: "actions",
    width: 80,
    render: (row) => {
      if (row.type !== "pdf_translate") return "—";
      return h(
        NButton,
        { text: true, type: "primary", size: "small", onClick: () => openJob(row) },
        () => "查看"
      );
    },
  },
]);

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
    message.error(e.message);
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
    message.success("任务已终止");
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

function handleBatchCancel() {
  const rows = selectedRows.value;
  if (!rows.length) return;
  const summary = rows.length === 1 ? "该任务" : `选中的 ${rows.length} 个任务`;
  dialog.warning({
    title: "批量终止任务",
    content: `确定终止${summary}？进行中的翻译将停止。`,
    positiveText: "终止",
    negativeText: "取消",
    onPositiveClick: async () => {
      const { deleted, failed } = await deleteSequentially(rows, (row) => cancelJob(row.id));
      if (failed.length) {
        message.warning(
          `已终止 ${deleted} 个，${failed.length} 个失败：${failed[0].message || "未知错误"}`
        );
      } else {
        message.success(deleted > 1 ? `已终止 ${deleted} 个任务` : "任务已终止");
      }
      clearSelection();
      await load();
      return !failed.length;
    },
  });
}

async function doClear(scope) {
  try {
    const { deleted } = await clearJobs(scope);
    message.success(deleted ? `已清理 ${deleted} 条任务` : "没有可清理的任务");
    page.value = 1;
    await load();
  } catch (e) {
    message.error(e.message);
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
      <n-text strong>后台任务</n-text>
      <n-space :size="6">
        <n-button text type="primary" size="small" @click="load">刷新</n-button>
        <n-button text type="primary" size="small" @click="goJobsPage">查看全部</n-button>
      </n-space>
    </div>

    <n-spin :show="loading">
      <template v-if="variant === 'popover'">
        <div v-if="items.length" class="jobs-panel__list">
          <div v-for="row in items" :key="row.id" class="jobs-panel__item">
            <div class="jobs-panel__item-main">
              <n-space :size="6" align="center">
                <n-tag size="small">{{ TYPE_LABELS[row.type] || row.type }}</n-tag>
                <n-tag :type="statusType[row.status] || 'default'" size="small">
                  {{ STATUS_LABELS[row.status] || row.status }}
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
                查看
              </n-button>
              <n-popconfirm
                v-if="CANCELLABLE.has(row.status)"
                @positive-click="doCancel(row.id)"
              >
                <template #trigger>
                  <n-button text type="warning" size="tiny">终止</n-button>
                </template>
                确定终止该任务？
              </n-popconfirm>
            </n-space>
          </div>
        </div>
        <n-empty v-else size="small" description="暂无后台任务" />
      </template>

      <template v-else>
        <div class="jobs-panel__toolbar">
          <n-space :size="8" align="center" wrap>
            <BatchTableToolbar
              :count="selectedCount"
              :disabled="!canBatchCancel"
              label="终止"
              @action="handleBatchCancel"
            />
            <n-popconfirm @positive-click="doClear('finished')">
              <template #trigger>
                <n-button size="small">清理已完成</n-button>
              </template>
              将删除所有已完成、失败或已取消的任务记录，确定继续？
            </n-popconfirm>
            <n-popconfirm @positive-click="doClear('all')">
              <template #trigger>
                <n-button size="small" secondary>清空全部</n-button>
              </template>
              将删除除「运行中」外的全部任务记录，确定继续？
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
  background: var(--n-color);
  border-radius: var(--n-border-radius);
  box-sizing: border-box;
}

.jobs-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--n-divider-color);
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
  border-bottom: 1px solid var(--n-divider-color);
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
