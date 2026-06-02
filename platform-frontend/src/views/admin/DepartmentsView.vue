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
  NSelect,
  NSpace,
  useDialog,
  useMessage,
} from "naive-ui";
import {
  fetchDepartments,
  createDepartment,
  updateDepartment,
  deleteDepartment,
} from "../../api/client";
import BatchTableToolbar from "../../components/BatchTableToolbar.vue";
import { useBatchTableSelection } from "../../composables/useBatchTableSelection";
import { deleteSequentially } from "../../utils/batchActions";

const message = useMessage();
const dialog = useDialog();
const loading = ref(false);
const items = ref([]);
const showModal = ref(false);
const editingId = ref(null);
const saving = ref(false);

const emptyForm = () => ({
  name: "",
  parent_id: null,
});

const form = ref(emptyForm());
const isEdit = computed(() => Boolean(editingId.value));

const {
  checkedRowKeys,
  selectedRows,
  selectedCount,
  onCheckedRowKeysChange,
  clearSelection,
  selectionColumn,
} = useBatchTableSelection(items);

const canBatchDelete = computed(() => selectedRows.value.length > 0);

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

const columns = computed(() => [
  selectionColumn(),
  { title: "名称", key: "name" },
  {
    title: "上级部门",
    key: "parent_id",
    render: (r) => deptName(r.parent_id),
  },
  {
    title: "操作",
    key: "actions",
    width: 80,
    render(row) {
      return h(
        NButton,
        { size: "small", quaternary: true, type: "primary", onClick: () => openEdit(row) },
        { default: () => "编辑" }
      );
    },
  },
]);

async function load() {
  loading.value = true;
  try {
    items.value = await fetchDepartments();
    clearSelection();
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
  };
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
  editingId.value = null;
  form.value = emptyForm();
}

function handleBatchDelete() {
  const rows = selectedRows.value;
  if (!rows.length) return;
  const summary =
    rows.length === 1 ? `「${rows[0].name}」` : `选中的 ${rows.length} 个部门`;
  dialog.warning({
    title: "批量删除部门",
    content: `确定删除${summary}？`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      const { deleted, failed } = await deleteSequentially(rows, (row) =>
        deleteDepartment(row.id)
      );
      if (failed.length) {
        message.warning(
          `已删除 ${deleted} 个，${failed.length} 个失败：${failed[0].message || "未知错误"}`
        );
      } else {
        message.success(deleted > 1 ? `已删除 ${deleted} 个部门` : "部门已删除");
      }
      clearSelection();
      await load();
      return !failed.length;
    },
  });
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
  <n-card class="admin-page">
    <template #header-extra>
      <n-button type="primary" @click="openCreate">新建部门</n-button>
    </template>
    <BatchTableToolbar
      :count="selectedCount"
      :disabled="!canBatchDelete"
      @action="handleBatchDelete"
    />
    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :row-key="(row) => row.id"
      :checked-row-keys="checkedRowKeys"
      @update:checked-row-keys="onCheckedRowKeysChange"
    />
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
