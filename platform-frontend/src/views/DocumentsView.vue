<script setup>
import { h, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  NCard,
  NButton,
  NSpace,
  NDataTable,
  NInput,
  NModal,
  NForm,
  NFormItem,
  NUpload,
  useMessage,
} from "naive-ui";
import {
  createDocument,
  fetchDocuments,
  prepareUpload,
  completeUpload,
} from "../api/client";

const router = useRouter();
const message = useMessage();

const loading = ref(false);
const keyword = ref("");
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const items = ref([]);

const showCreate = ref(false);
const createTitle = ref("");
const createDesc = ref("");
const uploadFile = ref(null);
const creating = ref(false);

const columns = [
  { title: "标题", key: "title", ellipsis: { tooltip: true } },
  {
    title: "状态",
    key: "status",
    width: 90,
  },
  {
    title: "更新时间",
    key: "updated_at",
    width: 180,
    render: (row) => new Date(row.updated_at).toLocaleString(),
  },
  {
    title: "操作",
    key: "actions",
    width: 100,
    render: (row) =>
      h(
        NButton,
        {
          text: true,
          type: "primary",
          onClick: () => router.push({ name: "document-detail", params: { id: row.id } }),
        },
        { default: () => "详情" }
      ),
  },
];

async function load() {
  loading.value = true;
  try {
    const data = await fetchDocuments({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    });
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

async function submitCreate() {
  if (!createTitle.value.trim()) {
    message.warning("请输入标题");
    return;
  }
  creating.value = true;
  try {
    const doc = await createDocument({
      title: createTitle.value.trim(),
      description: createDesc.value,
    });
    if (uploadFile.value) {
      const file = uploadFile.value;
      const prep = await prepareUpload(doc.id, file.name, file.type || "application/octet-stream");
      const putRes = await fetch(prep.upload_url, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": file.type || "application/octet-stream" },
      });
      if (!putRes.ok) throw new Error("上传到存储失败");
      await completeUpload(doc.id, {
        version_id: prep.version_id,
        file_size: file.size,
      });
      message.success("文档已创建并上传");
    } else {
      message.success("文档已创建，可在详情页上传文件");
    }
    showCreate.value = false;
    createTitle.value = "";
    createDesc.value = "";
    uploadFile.value = null;
    await load();
    router.push({ name: "document-detail", params: { id: doc.id } });
  } catch (e) {
    message.error(e.message);
  } finally {
    creating.value = false;
  }
}

onMounted(load);
</script>

<template>
  <n-card title="文档库">
    <template #header-extra>
      <n-space>
        <n-input
          v-model:value="keyword"
          placeholder="搜索标题"
          clearable
          style="width: 200px"
          @keyup.enter="load"
        />
        <n-button @click="load">搜索</n-button>
        <n-button type="primary" @click="showCreate = true">新建文档</n-button>
      </n-space>
    </template>

    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :pagination="{
        page: page,
        pageSize: pageSize,
        itemCount: total,
        onUpdatePage: onPageChange,
      }"
    />
  </n-card>

  <n-modal
    v-model:show="showCreate"
    preset="card"
    title="新建文档"
    style="width: 480px"
    :mask-closable="false"
  >
    <n-form>
      <n-form-item label="标题" required>
        <n-input v-model:value="createTitle" placeholder="文档标题" />
      </n-form-item>
      <n-form-item label="说明">
        <n-input v-model:value="createDesc" type="textarea" placeholder="可选" />
      </n-form-item>
      <n-form-item label="文件（可选）">
        <n-upload
          :max="1"
          :default-upload="false"
          @change="(opts) => { uploadFile = opts.fileList[0]?.file ?? null; }"
        >
          <n-button>选择文件</n-button>
        </n-upload>
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showCreate = false">取消</n-button>
        <n-button type="primary" :loading="creating" @click="submitCreate">
          创建
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>
