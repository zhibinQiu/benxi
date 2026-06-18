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
  fetchUsers,
  createUser,
  updateUser,
  deleteUser,
  fetchDepartments,
  fetchRoles } from "../../api/client";
import OrgDeptPickerTree from "../../components/OrgDeptPickerTree.vue";
import BatchTableToolbar from "../../components/BatchTableToolbar.vue";
import AdminFormModal from "../../components/AdminFormModal.vue";
import HintTooltip from "../../components/HintTooltip.vue";
import { useAuth } from "../../composables/useAuth";
import { useBatchTableSelection } from "../../composables/useBatchTableSelection";
import { deleteSequentially } from "../../utils/batchActions";

const ui = usePlatformUi();
const { t } = useI18n();
const { user: currentUser } = useAuth();
const loading = ref(false);
const users = ref([]);
const departments = ref([]);
const roles = ref([]);

const showModal = ref(false);
const editingId = ref(null);
const saving = ref(false);

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

function canSelectUser(row) {
  if (isBootstrapUser(row)) return false;
  if (row.id === currentUser.value?.id) return false;
  return true;
}

const {
  checkedRowKeys,
  selectedRows,
  selectedCount,
  onCheckedRowKeysChange,
  clearSelection,
  selectionColumn} = useBatchTableSelection(users, { canSelect: canSelectUser });

const canBatchDelete = computed(
  () => selectedRows.value.length > 0 && selectedRows.value.every(canSelectUser)
);

const columns = computed(() => [
  selectionColumn(),
  {
    title: t("admin.users.phone"),
    key: "phone",
    width: 130,
    render: (r) => r.phone || "—"},
  {
    title: t("admin.users.displayName"),
    key: "display_name",
    width: 120,
    render: (r) => r.display_name || r.username || "—"},
  { title: t("admin.users.email"), key: "email", render: (r) => r.email || "—" },
  {
    title: t("admin.users.status"),
    key: "status",
    width: 80,
    render: (r) =>
      r.status === "active"
        ? t("admin.users.statusActive")
        : t("admin.users.statusDisabled")},
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
    width: 80,
    render(row) {
      return h(
        NButton,
        { size: "small", quaternary: true, type: "primary", onClick: () => openEdit(row) },
        { default: () => t("common.edit") }
      );
    }},
]);

async function loadMeta() {
  try {
    const [depts, roleList] = await Promise.all([
      fetchDepartments().catch(() => []),
      fetchRoles().catch(() => []),
    ]);
    departments.value = depts;
    roles.value = roleList.filter((r) => ASSIGNABLE_ROLE_CODES.includes(r.code));
  } catch (e) {
    ui.warning(e.message || t("admin.users.loadMetaFailed"));
  }
}

async function load() {
  loading.value = true;
  try {
    users.value = await fetchUsers();
    clearSelection();
  } catch (e) {
    ui.error(e.message);
  } finally {
    loading.value = false;
  }
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

function handleBatchDelete() {
  const rows = selectedRows.value;
  if (!rows.length) return;
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
          deleted > 1 ? t("admin.users.batchDeletedMulti", { count: deleted }) : t("admin.users.deleted")
        );
      }
      clearSelection();
      await load();
      return !failed.length;
    },
  });
}

onMounted(async () => {
  await loadMeta();
  await load();
});
</script>

<template>
  <n-card class="admin-page">
    <div class="admin-table-toolbar">
      <BatchTableToolbar
        :count="selectedCount"
        :disabled="!canBatchDelete"
        @action="handleBatchDelete"
      />
      <n-button type="primary" @click="openCreate">{{ t("admin.users.create") }}</n-button>
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
  </n-card>

  <AdminFormModal
    v-model:show="showModal"
    :title="isEdit ? t('admin.users.edit') : t('admin.users.create')"
    :width="520"
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
          :max-height="140"
        />
      </n-form-item>

      <p v-else class="admin-form-modal__hint">
        {{ t("admin.users.bootstrapHint", { phone: BOOTSTRAP_PHONE }) }}
      </p>
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
