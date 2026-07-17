<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { CreateOutline, RefreshOutline } from "@vicons/ionicons5";
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
  updateDepartment } from "../../api/client";
import AdminFormModal from "../../components/AdminFormModal.vue";
import HintTooltip from "../../components/HintTooltip.vue";
import { renderIconAction } from "../../utils/tableIconActions.js";

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
  { title: t("admin.departments.name"), key: "name" },
  {
    title: t("admin.departments.parent"),
    key: "parent_id",
    render: (r) => deptName(r.parent_id)},
  {
    title: t("common.actions"),
    key: "actions",
    width: 86,
    render: (row) =>
      renderIconAction({
        label: t("common.edit"),
        icon: CreateOutline,
        type: "primary",
        onClick: () => openEdit(row),
      }),
  },
]);

async function load() {
  loading.value = true;
  try {
    items.value = await fetchDepartments();
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
      <n-data-table
        :columns="columns"
        :data="items"
        :loading="loading"
        :row-key="(row) => row.id"
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
</template>

<style scoped>
.dept-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 12px 16px;
  padding-top: 0;
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
