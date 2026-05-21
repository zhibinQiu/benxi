<script setup>
import { h, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { NButton, NCard, NDataTable, NTag, useMessage } from "naive-ui";
import { fetchJobs } from "../api/client";

const router = useRouter();
const message = useMessage();
const loading = ref(false);
const items = ref([]);
const page = ref(1);
const total = ref(0);

const TYPE_LABELS = {
  pdf_translate: "PDF 翻译",
  document_index: "文档索引",
  document_parse: "文档解析",
};

const statusType = {
  pending: "default",
  running: "info",
  done: "success",
  failed: "error",
  cancelled: "warning",
};

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
      h(NTag, { type: statusType[row.status] || "default", size: "small" }, () => row.status),
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
    width: 100,
    render: (row) =>
      row.type === "pdf_translate"
        ? h(
            NButton,
            { text: true, type: "primary", size: "small", onClick: () => openJob(row) },
            () => "查看"
          )
        : "—",
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

onMounted(load);
</script>

<template>
  <n-card title="任务中心">
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
