<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { computed, h, onMounted, ref } from "vue";
import {
  NCard,
  NDataTable,
  NButton,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace } from "naive-ui";
import {
  fetchDepartments,
  createDepartment,
  updateDepartment,
  deleteDepartment } from "../../api/client";
import BatchTableToolbar from "../../components/BatchTableToolbar.vue";
import AdminFormModal from "../../components/AdminFormModal.vue";
import HintTooltip from "../../components/HintTooltip.vue";
import { useBatchTableSelection } from "../../composables/useBatchTableSelection";
import { deleteSequentially } from "../../utils/batchActions";
import ListRefreshButton from "../../components/ListRefreshButton.vue";
import { LIST_PAGE_SIZE } from "../../constants/listPage.js";

const ui = usePlatformUi();
const { t } = useI18n();
const loading = ref(false);
const items = ref([]);
const showModal = ref(false);
const editingId = ref(null);
const saving = ref(false);

const emptyForm = () => ({
  name: "",
  parent_id: null});

const form = ref(emptyForm());
const isEdit = computed(() => Boolean(editingId.value));

const {
  checkedRowKeys,
  selectedRows,
  selectedCount,
  onCheckedRowKeysChange,
  clearSelection,
  selectionColumn} = useBatchTableSelection(items);

const canBatchDelete = computed(() => selectedRows.value.length > 0);

function deptName(id) {
  if (!id) return t("admin.departments.root");
  return items.value.find((d) => d.id === id)?.name || t("admin.departments.unknownDept");
}

const parentOptions = computed(() => {
  const exclude = editingId.value;
  const opts = [{ label: t("admin.departments.rootDept"), value: null }];
  for (const d of items.value) {
    if (d.id === exclude) continue;
    opts.push({ label: d.name, value: d.id });
  }
  return opts;
});

const columns = computed(() => [
  selectionColumn(),
  { title: t("admin.departments.name"), key: "name" },
  {
    title: t("admin.departments.parent"),
    key: "parent_id",
    render: (r) => deptName(r.parent_id)},
  {
    title: t("common.actions"),
    key: "actions",
    width: 80,
    render(row) {
      return h(
        NButton,
        { size: "small", quaternary: true, type: "primary", onClick: () => openEdit(row) },
        { default: () => t("common.edit") }
      );
    }},
]);

async function load() {
  loading.value = true;
  try {
    items.value = await fetchDepartments();
    clearSelection();
  } catch (e) {
    ui.error(e.message);
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
    parent_id: row.parent_id ?? null};
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
  const content =
    rows.length === 1
      ? t("admin.departments.batchDeleteContentSingle", { name: rows[0].name })
      : t("admin.departments.batchDeleteContentMulti", { count: rows.length });
  ui.confirmDelete({
    title: t("admin.departments.batchDeleteTitle"),
    content,
    onPositive: async () => {
      const { deleted, failed } = await deleteSequentially(rows, (row) =>
        deleteDepartment(row.id)
      );
      if (failed.length) {
        ui.warning(
          t("admin.batchDeletePartial", {
            success: deleted,
            failed: failed.length,
            error: failed[0].message || t("admin.unknownError"),
          })
        );
      } else {
        ui.success(
          deleted > 1
            ? t("admin.departments.batchDeletedMulti", { count: deleted })
            : t("admin.departments.deleted")
        );
      }
      clearSelection();
      await load();
      return !failed.length;
    },
  });
}

async function submit() {
  if (!form.value.name?.trim()) {
    ui.warning(t("admin.departments.nameRequired"));
    return;
  }
  saving.value = true;
  const payload = {
    name: form.value.name.trim(),
    parent_id: form.value.parent_id ?? null};
  try {
    if (isEdit.value) {
      await updateDepartment(editingId.value, payload);
      ui.success(t("admin.departments.updated"));
    } else {
      await createDepartment(payload);
      ui.success(t("admin.departments.created"));
    }
    closeModal();
    await load();
  } catch (e) {
    ui.error(e.message);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <n-card class="admin-page">
    <div class="admin-table-toolbar">
      <BatchTableToolbar
        :count="selectedCount"
        :disabled="!canBatchDelete"
        @action="handleBatchDelete"
      />
      <ListRefreshButton :loading="loading" @click="load" />
      <n-button type="primary" @click="openCreate">{{ t("admin.departments.create") }}</n-button>
    </div>
    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :row-key="(row) => row.id"
      :checked-row-keys="checkedRowKeys"
      :pagination="{ pageSize: LIST_PAGE_SIZE }"
      @update:checked-row-keys="onCheckedRowKeysChange"
    />
  </n-card>

  <AdminFormModal
    v-model:show="showModal"
    :title="isEdit ? t('admin.departments.edit') : t('admin.departments.create')"
    :width="460"
    @after-leave="closeModal"
  >
    <n-form
      class="admin-form-modal__form admin-form-modal__form--compact"
      label-placement="top"
    >
      <div class="admin-form-modal__form-grid">
        <n-form-item :label="t('admin.departments.deptName')" required>
          <n-input
            v-model:value="form.name"
            :placeholder="t('admin.departments.deptNamePlaceholder')"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="admin-form-modal__label-row">
              {{ t("admin.departments.parent") }}
              <HintTooltip
                variant="inline"
                placement="top"
                :text="t('admin.departments.parentHint')"
              />
            </span>
          </template>
          <n-select
            v-model:value="form.parent_id"
            :options="parentOptions"
            clearable
            :placeholder="t('admin.departments.parentOptional')"
          />
        </n-form-item>
      </div>
    </n-form>
    <template #footer>
      <n-space :size="10">
        <n-button @click="showModal = false">{{ t("common.cancel") }}</n-button>
        <n-button type="primary" :loading="saving" @click="submit">
          {{ isEdit ? t("common.save") : t("common.create") }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>
</template>
