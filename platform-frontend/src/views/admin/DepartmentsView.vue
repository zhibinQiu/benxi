<script setup>
import { onMounted, ref } from "vue";
import {
  NCard,
  NDataTable,
  NButton,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NSpace,
  useMessage,
} from "naive-ui";
import { fetchDepartments, createDepartment } from "../../api/client";

const message = useMessage();
const loading = ref(false);
const items = ref([]);
const showCreate = ref(false);
const name = ref("");

const columns = [
  { title: "名称", key: "name" },
  {
    title: "上级部门",
    key: "parent_id",
    render: (r) => r.parent_id || "（根）",
  },
  { title: "排序", key: "sort_order", width: 80 },
];

async function load() {
  loading.value = true;
  try {
    items.value = await fetchDepartments();
  } catch (e) {
    message.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function submit() {
  if (!name.value.trim()) {
    message.warning("请输入部门名称");
    return;
  }
  try {
    await createDepartment({ name: name.value.trim(), parent_id: null });
    message.success("部门已创建");
    showCreate.value = false;
    name.value = "";
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

onMounted(load);
</script>

<template>
  <n-card title="部门管理">
    <template #header-extra>
      <n-button type="primary" @click="showCreate = true">新建部门</n-button>
    </template>
    <n-data-table :columns="columns" :data="items" :loading="loading" />
  </n-card>

  <n-modal v-model:show="showCreate" preset="card" title="新建部门" style="width: 360px">
    <n-form>
      <n-form-item label="部门名称" required>
        <n-input v-model:value="name" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showCreate = false">取消</n-button>
        <n-button type="primary" @click="submit">创建</n-button>
      </n-space>
    </template>
  </n-modal>
</template>
