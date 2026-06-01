<script setup>
import { computed, h, onMounted, ref } from "vue";
import {
  NCard,
  NDataTable,
  NButton,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NPopconfirm,
  useMessage,
} from "naive-ui";
import {
  fetchDepartments,
  createDepartment,
  updateDepartment,
  deleteDepartment,
} from "../../api/client";

const message = useMessage();
const loading = ref(false);
const items = ref([]);
const showModal = ref(false);
const editingId = ref(null);
const saving = ref(false);

const emptyForm = () => ({
  name: "",
  parent_id: null,
  sort_order: 0,
});

const form = ref(emptyForm());
const isEdit = computed(() => Boolean(editingId.value));

function deptName(id) {
  if (!id) return "（根）";
  return items.value.find((d) => d.id === id)?.name || "未知部门";
}

const parentOptions = computed(() => {
  const exclude = editingId.value;
  const opts = [{ label: "（根部门）", value: null }];
  for (const d of items.value) {
    if (d.id === exclude) continue;
    opts.push({ label: d.name, value: d.id });
  }
  return opts;
});

const columns = [
  { title: "名称", key: "name" },
  {
    title: "上级部门",
    key: "parent_id",
    render: (r) => deptName(r.parent_id),
  },
  { title: "排序", key: "sort_order", width: 80 },
  {
    title: "操作",
    key: "actions",
    width: 150,
    render(row) {
      return h(NSpace, { size: 8 }, () => [
        h(
          NButton,
          { size: "small", quaternary: true, type: "primary", onClick: () => openEdit(row) },
          { default: () => "编辑" }
        ),
        h(
          NPopconfirm,
          { onPositiveClick: () => removeDept(row) },
          {
            trigger: () =>
              h(NButton, { size: "small", quaternary: true, type: "error" }, { default: () => "删除" }),
            default: () => `确定删除部门「${row.name}」？`,
          }
        ),
      ]);
    },
  },
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

function openCreate() {
  editingId.value = null;
  form.value = emptyForm();
  showModal.value = true;
}

function openEdit(row) {
  editingId.value = row.id;
  form.value = {
    name: row.name,
    parent_id: row.parent_id ?? null,
    sort_order: row.sort_order ?? 0,
  };
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
  editingId.value = null;
  form.value = emptyForm();
}

async function removeDept(row) {
  try {
    await deleteDepartment(row.id);
    message.success("部门已删除");
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

async function submit() {
  if (!form.value.name?.trim()) {
    message.warning("请输入部门名称");
    return;
  }
  saving.value = true;
  const payload = {
    name: form.value.name.trim(),
    parent_id: form.value.parent_id ?? null,
    sort_order: form.value.sort_order ?? 0,
  };
  try {
    if (isEdit.value) {
      await updateDepartment(editingId.value, payload);
      message.success("部门已更新");
    } else {
      await createDepartment(payload);
      message.success("部门已创建");
    }
    closeModal();
    await load();
  } catch (e) {
    message.error(e.message);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <n-card title="部门管理">
    <template #header-extra>
      <n-button type="primary" @click="openCreate">新建部门</n-button>
    </template>
    <n-data-table :columns="columns" :data="items" :loading="loading" />
  </n-card>

  <n-modal
    v-model:show="showModal"
    preset="card"
    :title="isEdit ? '编辑部门' : '新建部门'"
    style="width: 400px"
    @after-leave="closeModal"
  >
    <n-form label-placement="left" label-width="88">
      <n-form-item label="部门名称" required>
        <n-input v-model:value="form.name" placeholder="部门名称" />
      </n-form-item>
      <n-form-item label="上级部门">
        <n-select
          v-model:value="form.parent_id"
          :options="parentOptions"
          clearable
          placeholder="不选则为根部门"
        />
      </n-form-item>
      <n-form-item label="排序">
        <n-input-number v-model:value="form.sort_order" :min="0" class="sort-input" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showModal = false">取消</n-button>
        <n-button type="primary" :loading="saving" @click="submit">
          {{ isEdit ? "保存" : "创建" }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<style scoped>
.sort-input {
  width: 100%;
}
</style>
