<script setup>
import { h, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { NButton, NCard, NDataTable, NPopconfirm, NSpace, NTag, useMessage } from "naive-ui";
import { cancelJob, clearJobs, fetchJobs } from "../api/client";

const router = useRouter();
const message = useMessage();
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

function openJob(row) {
  if (row.type === "pdf_translate") {
    router.push({ name: "translate", query: { job: row.id } });
  }
}

const columns = [
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
    width: 140,
    render: (row) => {
      const buttons = [];
      if (row.type === "pdf_translate") {
        buttons.push(
          h(
            NButton,
            { text: true, type: "primary", size: "small", onClick: () => openJob(row) },
            () => "查看"
          )
        );
      }
      if (CANCELLABLE.has(row.status)) {
        buttons.push(
          h(
            NPopconfirm,
            {
              onPositiveClick: () => doCancel(row.id),
            },
            {
              trigger: () =>
                h(
                  NButton,
                  { text: true, type: "warning", size: "small" },
                  () => "终止"
                ),
              default: () => "确定终止该任务？进行中的翻译将停止。",
            }
          )
        );
      }
      if (!buttons.length) return "—";
      return h(NSpace, { size: 4, align: "center" }, () => buttons);
    },
  },
];

async function load() {
  loading.value = true;
  try {
    const data = await fetchJobs({ page: page.value });
    items.value = data.items;
    total.value = data.total;
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

onMounted(load);
</script>

<template>
  <n-card title="任务中心">
    <template #header-extra>
      <n-space :size="8">
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
    </template>
    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :pagination="{
        page,
        pageSize: 20,
        itemCount: total,
        onUpdatePage: onPageChange,
      }"
    />
  </n-card>
</template>
