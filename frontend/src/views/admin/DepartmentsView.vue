<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { CreateOutline, RefreshOutline, TrashOutline } from "@vicons/ionicons5";
import { computed, onMounted, ref } from "vue";
import {
  NDataTable,
  NButton,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NIcon } from "naive-ui";
import {
  fetchDepartments,
  createDepartment,
  updateDepartment,
  deleteDepartment } from "../../api/client";
import AdminFormModal from "../../components/AdminFormModal.vue";
import BatchTableToolbar from "../../components/BatchTableToolbar.vue";
import HintTooltip from "../../components/HintTooltip.vue";
import IconAction from "../../components/IconAction.vue";
import { useBatchTableSelection } from "../../composables/useBatchTableSelection";
import { deleteSequentially } from "../../utils/batchActions.js";
import { renderIconActionGroup } from "../../utils/tableIconActions.js";

const ui = usePlatformUi();
const { t } = useI18n();
const loading = ref(false);
const items = ref([]);
const showModal = ref(false);
const editingId = ref(null);
const saving = ref(false);
const showBatchModal = ref(false);
const batchSaving = ref(false);
const batchParentId = ref(null);

const {
  checkedRowKeys,
  selectedRows,
  selectedCount,
  onCheckedRowKeysChange,
  clearSelection,
  selectionColumn,
} = useBatchTableSelection(items);

const emptyForm = () => ({
  name: "",
  parent_id: null});

const form = ref(emptyForm());
const isEdit = computed(() => Boolean(editingId.value));
const canBatchEdit = computed(() => selectedCount.value > 0);
const canBatchDelete = computed(() => selectedCount.value > 0);

function deptName(id) {
  if (!id) return t("admin.departments.root");
  return items.value.find((d) => d.id === id)?.name || t("admin.departments.unknownDept");
}

const parentOptions = computed(() => {
  const exclude = new Set();
  if (editingId.value) exclude.add(editingId.value);
  if (showBatchModal.value) {
    for (const row of selectedRows.value) exclude.add(row.id);
  }
  const opts = [{ label: t("admin.departments.rootDept"), value: null }];
  for (const d of items.value) {
    if (exclude.has(d.id)) continue;
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
    width: 136,
    render: (row) =>
      renderIconActionGroup([
        {
          label: t("common.edit"),
          icon: CreateOutline,
          type: "primary",
          onClick: () => openEdit(row),
        },
        {
          label: t("common.delete"),
          icon: TrashOutline,
          type: "error",
          onClick: () => onDelete(row),
        },
      ]),
  },
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

async function onDelete(row) {
  await ui.confirmDelete({
    title: t("admin.departments.deleteTitle"),
    content: t("admin.departments.deleteConfirm", { name: row.name }),
    onPositive: async () => {
      await deleteDepartment(row.id);
      ui.success(t("admin.departments.deleted"));
      await load();
    },
  });
}

function openBatchEdit() {
  const rows = selectedRows.value;
  if (!rows.length) return;
  if (rows.length === 1) {
    openEdit(rows[0]);
    return;
  }
  batchParentId.value = null;
  showBatchModal.value = true;
}

function closeBatchModal() {
  showBatchModal.value = false;
  batchParentId.value = null;
}

async function submitBatchEdit() {
  const rows = selectedRows.value;
  if (!rows.length) return;
  batchSaving.value = true;
  const payload = { parent_id: batchParentId.value ?? null };
  try {
    const { deleted: updated, failed } = await deleteSequentially(rows, (row) =>
      updateDepartment(row.id, payload)
    );
    if (failed.length) {
      ui.warning(
        t("admin.batchDeletePartial", {
          success: updated,
          failed: failed.length,
          error: failed[0].message || t("admin.unknownError"),
        })
      );
    } else {
      ui.success(t("admin.departments.batchUpdatedMulti", { count: updated }));
    }
    closeBatchModal();
    clearSelection();
    await load();
  } catch (e) {
    ui.error(e.message);
  } finally {
    batchSaving.value = false;
  }
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
    },
  });
}

onMounted(load);
</script>

<template>
  <div class="dept-card">
    <div class="admin-list-table">
      <Teleport to="#header-page-tools">
        <n-button
          quaternary
          circle
          size="small"
          class="header-icon-btn"
          :class="{ 'header-icon-btn--spinning': loading }"
          :aria-label="t('common.refresh')"
          :disabled="loading"
          @click="load"
        >
          <n-icon :size="14" :component="RefreshOutline" />
        </n-button>
      </Teleport>
      <div v-if="selectedCount > 0" class="admin-batch-toolbar">
        <n-space align="center" :size="7">
          <IconAction
            :label="t('admin.departments.batchEdit')"
            :icon="CreateOutline"
            type="primary"
            :disabled="!canBatchEdit"
            @click="openBatchEdit"
          />
          <BatchTableToolbar
            :count="selectedCount"
            :disabled="!canBatchDelete"
            :icon="TrashOutline"
            action-type="error"
            @action="handleBatchDelete"
          />
        </n-space>
      </div>
      <n-data-table
        :columns="columns"
        :data="items"
        :loading="loading"
        :row-key="(row) => row.id"
        :checked-row-keys="checkedRowKeys"
        @update:checked-row-keys="onCheckedRowKeysChange"
      />
    </div>
  </div>

  <AdminFormModal
    v-model:show="showModal"
    :title="isEdit ? t('admin.departments.edit') : t('admin.departments.create')"
    :width="552"
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
      <n-space :size="12">
        <n-button @click="showModal = false">{{ t("common.cancel") }}</n-button>
        <n-button type="primary" :loading="saving" @click="submit">
          {{ isEdit ? t("common.save") : t("common.create") }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>

  <AdminFormModal
    v-model:show="showBatchModal"
    :title="t('admin.departments.batchEditTitle')"
    :width="552"
    @after-leave="closeBatchModal"
  >
    <n-form
      class="admin-form-modal__form admin-form-modal__form--compact"
      label-placement="top"
    >
      <p class="admin-form-modal__hint">
        {{ t("admin.departments.batchEditHint", { count: selectedCount }) }}
      </p>
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
          v-model:value="batchParentId"
          :options="parentOptions"
          clearable
          :placeholder="t('admin.departments.parentOptional')"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space :size="12">
        <n-button @click="showBatchModal = false">{{ t("common.cancel") }}</n-button>
        <n-button type="primary" :loading="batchSaving" @click="submitBatchEdit">
          {{ t("common.save") }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>
</template>

<style scoped>
.dept-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 12px 16px;
  padding-top: 0;
}

.admin-batch-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 0 4px;
}

.dept-card :deep(.n-data-table-th),
.dept-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.dept-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.dept-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}
</style>
