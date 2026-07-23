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
  NPagination,
  NSelect,
  NSpace,
  NIcon } from "naive-ui";
import {
  fetchUsers,
  createUser,
  updateUser,
  fetchDepartments,
  fetchRoles } from "../../api/client";
import { deleteUser, deleteTrialUsers } from "../../api/auth";
import OrgDeptPickerTree from "../../components/OrgDeptPickerTree.vue";
import AdminFormModal from "../../components/AdminFormModal.vue";
import BatchTableToolbar from "../../components/BatchTableToolbar.vue";
import HintTooltip from "../../components/HintTooltip.vue";
import IconAction from "../../components/IconAction.vue";
import { useAuth } from "../../composables/useAuth";
import { useBatchTableSelection } from "../../composables/useBatchTableSelection";
import { LIST_PAGE_SIZE } from "../../constants/listPage.js";
import { deleteSequentially } from "../../utils/batchActions.js";
import { renderIconActionGroup } from "../../utils/tableIconActions.js";

const ui = usePlatformUi();
const { t } = useI18n();
const { user: currentUser } = useAuth();
const loading = ref(false);
const deletingTrial = ref(false);
const users = ref([]);
const page = ref(1);
const pageSize = LIST_PAGE_SIZE;
const total = ref(0);
const displayInfo = computed(() => {
  if (!total.value) return "";
  const start = (page.value - 1) * pageSize + 1;
  const end = Math.min(page.value * pageSize, total.value);
  return `${total.value}条数据中的 ${start}-${end} 条`;
});
const departments = ref([]);
/** 组织树展示用（含各页用户，用于部门选择树中标注成员） */
const orgUsers = ref([]);
const roles = ref([]);

const showModal = ref(false);
const editingId = ref(null);
const saving = ref(false);
const showBatchModal = ref(false);
const batchSaving = ref(false);
const batchForm = ref({
  status: "active",
  department_ids: [],
  role_id: null,
});

const {
  checkedRowKeys,
  selectedRows,
  selectedCount,
  onCheckedRowKeysChange,
  clearSelection,
  selectionColumn,
} = useBatchTableSelection(users);

const BOOTSTRAP_PHONE = "admin";

const emptyForm = () => ({
  phone: "",
  username: "",
  display_name: "",
  password: "",
  email: "",
  status: "active",
  department_ids: [],
  /** 单选：普通成员或系统管理员 */
  role_id: null });

const form = ref(emptyForm());

const isEdit = computed(() => Boolean(editingId.value));

const ASSIGNABLE_ROLE_CODES = ["member", "sys_admin"];

const roleOptions = computed(() =>
  roles.value
    .filter((r) => ASSIGNABLE_ROLE_CODES.includes(r.code))
    .map((r) => ({
      label:
        r.name ||
        (r.code === "sys_admin"
          ? t("admin.users.roleSysAdmin")
          : t("admin.users.roleMember")),
      value: r.id,
    }))
);

const statusOptions = computed(() => [
  { label: t("admin.users.statusActive"), value: "active" },
  { label: t("admin.users.statusDisabled"), value: "disabled" },
]);

function memberRoleId() {
  return roles.value.find((r) => r.code === "member")?.id ?? null;
}

function resolveRoleId(roleIds) {
  const ids = roleIds || [];
  const assignable = roles.value.filter((r) => ASSIGNABLE_ROLE_CODES.includes(r.code));
  const hit = assignable.find((r) => ids.includes(r.id));
  return hit?.id ?? memberRoleId();
}

function userDeptIds(row) {
  if (row?.department_id) return [row.department_id];
  return row?.department_ids || [];
}

function deptLabel(ids) {
  const list = Array.isArray(ids) ? ids : userDeptIds(ids);
  if (!list?.length) return "—";
  const name = departments.value.find((d) => d.id === list[0])?.name;
  return name || "—";
}

function roleLabel(row) {
  if (row?.role_names?.length) {
    return row.role_names.join(t("admin.listSeparator"));
  }
  if (isBootstrapUser(row)) {
    return t("admin.users.roleSysAdmin");
  }
  const ids = row?.role_ids || [];
  if (!ids.length) return "—";
  const names = ids
    .map((id) => roles.value.find((r) => r.id === id)?.name)
    .filter(Boolean);
  return names.length
    ? names.join(t("admin.listSeparator"))
    : t("admin.users.roleCount", { count: ids.length });
}

function isBootstrapUser(row) {
  return String(row?.phone || "") === BOOTSTRAP_PHONE;
}

function canEditUser(row) {
  return Boolean(row) && !isBootstrapUser(row);
}

function canDeleteUser(row) {
  if (!row || isBootstrapUser(row)) return false;
  if (currentUser.value?.id && row.id === currentUser.value.id) return false;
  return true;
}

const editableSelectedRows = computed(() => selectedRows.value.filter(canEditUser));
const deletableSelectedRows = computed(() => selectedRows.value.filter(canDeleteUser));
const canBatchEdit = computed(() => editableSelectedRows.value.length > 0);
const canBatchDelete = computed(() => deletableSelectedRows.value.length > 0);

const columns = computed(() => [
  selectionColumn(),
  {
    title: t("admin.users.displayName"),
    key: "display_name",
    width: 144,
    render: (r) => r.display_name || r.username || "—"},
  {
    title: t("admin.users.department"),
    key: "department_ids",
    ellipsis: { tooltip: true },
    render: (r) => deptLabel(r)},
  {
    title: t("admin.users.role"),
    key: "role_ids",
    ellipsis: { tooltip: true },
    render: (r) => roleLabel(r)},
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
          disabled: !canDeleteUser(row),
          onClick: () => onDelete(row),
        },
      ]),
  },
]);

async function loadAllUsersForOrgTree() {
  const pageSize = 100;
  const first = await fetchUsers({ page: 1, page_size: pageSize });
  let items = first.items || [];
  const totalCount = first.total || items.length;
  for (let p = 2; items.length < totalCount; p += 1) {
    const next = await fetchUsers({ page: p, page_size: pageSize });
    items = items.concat(next.items || []);
    if (!(next.items || []).length) break;
  }
  return items;
}

async function loadMeta() {
  try {
    const [depts, roleList, allUsers] = await Promise.all([
      fetchDepartments().catch(() => []),
      fetchRoles().catch(() => []),
      loadAllUsersForOrgTree().catch(() => []),
    ]);
    departments.value = depts;
    orgUsers.value = allUsers;
    roles.value = roleList.filter((r) => ASSIGNABLE_ROLE_CODES.includes(r.code));
  } catch (e) {
    ui.warning(e.message || t("admin.users.loadMetaFailed"));
  }
}

async function load() {
  loading.value = true;
  try {
    let data = await fetchUsers({ page: page.value, page_size: pageSize });
    if (!data.items.length && data.total > 0 && page.value > 1) {
      page.value -= 1;
      data = await fetchUsers({ page: page.value, page_size: pageSize });
    }
    users.value = data.items;
    total.value = data.total;
    clearSelection();
  } catch (e) {
    ui.error(e.message);
  } finally {
    loading.value = false;
  }
}

function onPageChange(p) {
  page.value = p;
  clearSelection();
  load();
}

function normalizeDepartmentIds(ids) {
  return (ids || []).slice(0, 1).map(String);
}

function openCreate() {
  editingId.value = null;
  form.value = emptyForm();
  form.value.role_id = memberRoleId();
  showModal.value = true;
}

function openEdit(row) {
  editingId.value = row.id;
  form.value = {
    phone: row.phone || "",
    username: row.username || "",
    display_name: row.display_name || "",
    password: "",
    email: row.email || "",
    status: row.status || "active",
    department_ids: normalizeDepartmentIds(userDeptIds(row)),
    role_id: resolveRoleId(row.role_ids),
  };
  showModal.value = true;
}

const editingBootstrap = computed(() => {
  const row = users.value.find((u) => u.id === editingId.value);
  return row ? isBootstrapUser(row) : false;
});

function closeModal() {
  showModal.value = false;
  editingId.value = null;
  form.value = emptyForm();
}

function isValidPhone(value) {
  const digits = String(value || "").replace(/\D/g, "");
  return /^1\d{10}$/.test(digits);
}

function validateForm() {
  if (!isEdit.value && !isValidPhone(form.value.phone)) {
    ui.warning("validation.phoneInvalid");
    return false;
  }
  if (!form.value.display_name?.trim()) {
    ui.warning("validation.nameRequired");
    return false;
  }
  if (!form.value.email?.trim()) {
    ui.warning("validation.emailRequired");
    return false;
  }
  if (form.value.display_name.trim().length < 2) {
    ui.warning("validation.nameMinLength");
    return false;
  }
  if (!isEdit.value) {
    if (!form.value.password || form.value.password.length < 6) {
      ui.warning("validation.passwordMinLength");
      return false;
    }
  } else if (form.value.password && form.value.password.length < 6) {
    ui.warning("validation.passwordOptionalMin");
    return false;
  }
  if (!editingBootstrap.value && !form.value.role_id) {
    ui.warning(t("admin.users.selectRoleRequired"));
    return false;
  }
  return true;
}

async function submit() {
  if (!validateForm()) return;
  saving.value = true;
  const payload = {
    display_name: form.value.display_name.trim(),
    username: form.value.display_name.trim(),
    email: form.value.email.trim(),
    status: form.value.status,
    department_ids: editingBootstrap.value
      ? []
      : normalizeDepartmentIds(form.value.department_ids),
    role_ids: form.value.role_id ? [form.value.role_id] : [],
  };
  if (!isEdit.value) {
    payload.phone = String(form.value.phone).replace(/\D/g, "");
  }
  try {
    if (isEdit.value) {
      const patch = { ...payload };
      if (form.value.password) patch.password = form.value.password;
      await updateUser(editingId.value, patch);
      ui.success(t("admin.users.updated"));
    } else {
      await createUser({ ...payload, password: form.value.password });
      ui.success(t("admin.users.created"));
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
  if (!canDeleteUser(row)) return;
  await ui.confirmDelete({
    title: t("admin.users.deleteTitle"),
    content: t("admin.users.deleteConfirm", { name: row.display_name || row.username || row.phone }),
    onPositive: async () => {
      await deleteUser(row.id);
      ui.success(t("admin.users.deleted"));
      await load();
    },
  });
}

function openBatchEdit() {
  const rows = editableSelectedRows.value;
  if (!rows.length) {
    ui.warning(t("admin.users.batchEditNone"));
    return;
  }
  if (rows.length === 1) {
    openEdit(rows[0]);
    return;
  }
  batchForm.value = {
    status: "active",
    department_ids: [],
    role_id: memberRoleId(),
  };
  showBatchModal.value = true;
}

function closeBatchModal() {
  showBatchModal.value = false;
  batchForm.value = {
    status: "active",
    department_ids: [],
    role_id: null,
  };
}

async function submitBatchEdit() {
  const rows = editableSelectedRows.value;
  if (!rows.length) {
    ui.warning(t("admin.users.batchEditNone"));
    return;
  }
  if (!batchForm.value.role_id) {
    ui.warning(t("admin.users.selectRoleRequired"));
    return;
  }
  batchSaving.value = true;
  const payload = {
    status: batchForm.value.status,
    department_ids: normalizeDepartmentIds(batchForm.value.department_ids),
    role_ids: [batchForm.value.role_id],
  };
  try {
    const { deleted: updated, failed } = await deleteSequentially(rows, (row) =>
      updateUser(row.id, payload)
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
      ui.success(t("admin.users.batchUpdatedMulti", { count: updated }));
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
  const rows = deletableSelectedRows.value;
  if (!rows.length) {
    ui.warning(t("admin.users.batchDeleteNone"));
    return;
  }
  const content =
    rows.length === 1
      ? t("admin.users.batchDeleteContentSingle", {
          name: rows[0].display_name || rows[0].username || rows[0].phone,
        })
      : t("admin.users.batchDeleteContentMulti", { count: rows.length });
  ui.confirmDelete({
    title: t("admin.users.batchDeleteTitle"),
    content,
    onPositive: async () => {
      const { deleted, failed } = await deleteSequentially(rows, (row) => deleteUser(row.id));
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
            ? t("admin.users.batchDeletedMulti", { count: deleted })
            : t("admin.users.deleted")
        );
      }
      clearSelection();
      await load();
    },
  });
}

function handleDeleteTrialUsers() {
  ui.confirmDelete({
    title: t("admin.users.deleteTrialTitle"),
    content: t("admin.users.deleteTrialConfirm"),
    onPositive: async () => {
      deletingTrial.value = true;
      try {
        const data = await deleteTrialUsers();
        const count = data?.deleted_count ?? 0;
        if (count > 0) {
          ui.success(t("admin.users.deleteTrialDone", { count }));
        } else {
          ui.success(t("admin.users.deleteTrialEmpty"));
        }
        clearSelection();
        await load();
      } catch (e) {
        ui.error(e.message);
      } finally {
        deletingTrial.value = false;
      }
    },
  });
}

onMounted(async () => {
  await loadMeta();
  await load();
});
</script>

<template>
  <div class="users-card">
    <div class="admin-list-table">
      <Teleport to="#header-page-tools">
        <n-space align="center" :size="4">
          <IconAction
            :label="t('admin.users.deleteTrial')"
            :icon="TrashOutline"
            type="error"
            :disabled="loading || deletingTrial"
            :loading="deletingTrial"
            @click="handleDeleteTrialUsers"
          />
          <n-button
            quaternary
            circle
            size="small"
            class="header-icon-btn"
            :class="{ 'header-icon-btn--spinning': loading }"
            :aria-label="t('common.refresh')"
            :disabled="loading || deletingTrial"
            @click="load"
          >
            <n-icon :size="14" :component="RefreshOutline" />
          </n-button>
        </n-space>
      </Teleport>
      <div v-if="selectedCount > 0" class="admin-batch-toolbar">
        <n-space align="center" :size="7">
          <IconAction
            :label="t('admin.users.batchEdit')"
            :icon="CreateOutline"
            type="primary"
            :disabled="!canBatchEdit"
            @click="openBatchEdit"
          />
          <BatchTableToolbar
            :count="deletableSelectedRows.length || selectedCount"
            :disabled="!canBatchDelete"
            :icon="TrashOutline"
            action-type="error"
            @action="handleBatchDelete"
          />
        </n-space>
      </div>
      <n-data-table
        :columns="columns"
        :data="users"
        :loading="loading"
        :scroll-x="900"
        :row-key="(row) => row.id"
        :checked-row-keys="checkedRowKeys"
        @update:checked-row-keys="onCheckedRowKeysChange"
      />
    </div>
    <div class="users-table-footer">
      <span class="users-table-footer__info">{{ displayInfo }}</span>
      <div class="users-table-footer__pages">
        <NPagination
          :page="page"
          :page-size="pageSize"
          :item-count="total"
          :page-slot="7"
          @update:page="onPageChange"
        />
      </div>
    </div>
  </div>

  <AdminFormModal
    v-model:show="showModal"
    :title="isEdit ? t('admin.users.edit') : t('admin.users.create')"
    :width="624"
    @after-leave="closeModal"
  >
    <n-form
      class="admin-form-modal__form admin-form-modal__form--compact"
      label-placement="top"
    >
      <div class="admin-form-modal__form-grid">
        <n-form-item v-if="!isEdit" :label="t('admin.users.phone')" required>
          <n-input
            v-model:value="form.phone"
            :placeholder="t('admin.users.phonePlaceholder')"
            maxlength="11"
          />
        </n-form-item>
        <n-form-item v-else :label="t('admin.users.phone')">
          <n-input :value="form.phone" disabled />
        </n-form-item>
        <n-form-item :label="t('admin.users.displayName')" required>
          <n-input
            v-model:value="form.display_name"
            :placeholder="t('admin.users.displayNamePlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="t('admin.users.email')" required>
          <n-input
            v-model:value="form.email"
            :placeholder="t('admin.users.emailPlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="isEdit ? t('admin.users.newPassword') : t('admin.users.password')"
          :required="!isEdit"
        >
          <n-input
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            :placeholder="
              isEdit ? t('admin.users.passwordPlaceholderEdit') : t('admin.users.passwordPlaceholderNew')
            "
          />
        </n-form-item>
        <template v-if="!editingBootstrap">
          <n-form-item :label="t('admin.users.status')">
            <n-select v-model:value="form.status" :options="statusOptions" />
          </n-form-item>
          <n-form-item>
            <template #label>
              <span class="admin-form-modal__label-row">
                {{ t("admin.users.role") }}
                <HintTooltip
                  variant="inline"
                  placement="top"
                  :text="t('admin.users.roleHint')"
                />
              </span>
            </template>
            <n-select
              v-model:value="form.role_id"
              :placeholder="t('admin.users.selectRole')"
              :options="roleOptions"
            />
          </n-form-item>
        </template>
      </div>

      <n-form-item v-if="!editingBootstrap">
        <template #label>
          <span class="admin-form-modal__label-row">
            {{ t("admin.users.department") }}
            <HintTooltip
              variant="inline"
              placement="top"
              :text="t('admin.users.departmentHint')"
            />
          </span>
        </template>
        <OrgDeptPickerTree
          v-model:department-ids="form.department_ids"
          :departments="departments"
          :users="orgUsers"
          :max-height="240"
        />
      </n-form-item>

      <p v-else class="admin-form-modal__hint">
        {{ t("admin.users.bootstrapHint", { phone: BOOTSTRAP_PHONE }) }}
      </p>
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
    :title="t('admin.users.batchEditTitle')"
    :width="624"
    @after-leave="closeBatchModal"
  >
    <n-form
      class="admin-form-modal__form admin-form-modal__form--compact"
      label-placement="top"
    >
      <p class="admin-form-modal__hint">
        {{ t("admin.users.batchEditHint", { count: editableSelectedRows.length }) }}
      </p>
      <div class="admin-form-modal__form-grid">
        <n-form-item :label="t('admin.users.status')">
          <n-select v-model:value="batchForm.status" :options="statusOptions" />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="admin-form-modal__label-row">
              {{ t("admin.users.role") }}
              <HintTooltip
                variant="inline"
                placement="top"
                :text="t('admin.users.roleHint')"
              />
            </span>
          </template>
          <n-select
            v-model:value="batchForm.role_id"
            :placeholder="t('admin.users.selectRole')"
            :options="roleOptions"
          />
        </n-form-item>
      </div>
      <n-form-item>
        <template #label>
          <span class="admin-form-modal__label-row">
            {{ t("admin.users.department") }}
            <HintTooltip
              variant="inline"
              placement="top"
              :text="t('admin.users.departmentHint')"
            />
          </span>
        </template>
        <OrgDeptPickerTree
          v-model:department-ids="batchForm.department_ids"
          :departments="departments"
          :users="orgUsers"
          :max-height="240"
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
.users-card {
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

.users-card :deep(.n-data-table-th),
.users-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.users-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.users-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}

.users-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-top: 1px solid var(--platform-border-strong);
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-tertiary);
}

.users-table-footer__pages :deep(.n-pagination) {
  justify-content: flex-end;
}

.users-table-footer__pages :deep(.n-pagination-item) {
  font-size: var(--platform-font-size-sm);
}
</style>
