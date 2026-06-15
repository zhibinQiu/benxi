<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
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
      label: r.name || (r.code === "sys_admin" ? "系统管理员" : "普通成员"),
      value: r.id,
    }))
);

function memberRoleId() {
  return roles.value.find((r) => r.code === "member")?.id ?? null;
}

function resolveRoleId(roleIds) {
  const ids = roleIds || [];
  const assignable = roles.value.filter((r) => ASSIGNABLE_ROLE_CODES.includes(r.code));
  const hit = assignable.find((r) => ids.includes(r.id));
  return hit?.id ?? memberRoleId();
}

const statusOptions = [
  { label: "正常", value: "active" },
  { label: "禁用", value: "disabled" },
];

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
    return row.role_names.join("、");
  }
  if (isBootstrapUser(row)) {
    return "系统管理员";
  }
  const ids = row?.role_ids || [];
  if (!ids.length) return "—";
  const names = ids
    .map((id) => roles.value.find((r) => r.id === id)?.name)
    .filter(Boolean);
  return names.length ? names.join("、") : `${ids.length} 个`;
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
  { title: "手机号", key: "phone", width: 130, render: (r) => r.phone || "—" },
  {
    title: "姓名",
    key: "display_name",
    width: 120,
    render: (r) => r.display_name || r.username || "—"},
  { title: "邮箱", key: "email", render: (r) => r.email || "—" },
  {
    title: "状态",
    key: "status",
    width: 80,
    render: (r) => (r.status === "active" ? "正常" : "禁用")},
  {
    title: "部门",
    key: "department_ids",
    ellipsis: { tooltip: true },
    render: (r) => deptLabel(r)},
  {
    title: "角色",
    key: "role_ids",
    ellipsis: { tooltip: true },
    render: (r) => roleLabel(r)},
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
    ui.warning(e.message || "加载部门/角色失败");
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
    ui.warning("请输入有效的 11 位手机号");
    return false;
  }
  if (!form.value.display_name?.trim()) {
    ui.warning("姓名必填");
    return false;
  }
  if (!form.value.email?.trim()) {
    ui.warning("邮箱必填");
    return false;
  }
  if (form.value.display_name.trim().length < 2) {
    ui.warning("姓名至少 2 个字符");
    return false;
  }
  if (!isEdit.value) {
    if (!form.value.password || form.value.password.length < 6) {
      ui.warning("密码至少 6 个字符");
      return false;
    }
  } else if (form.value.password && form.value.password.length < 6) {
    ui.warning("新密码至少 6 个字符，留空则不修改");
    return false;
  }
  if (!editingBootstrap.value && !form.value.role_id) {
    ui.warning("请选择角色");
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
      ui.success("用户已更新");
    } else {
      await createUser({ ...payload, password: form.value.password });
      ui.success("用户已创建");
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
  const summary =
    rows.length === 1
      ? `「${rows[0].display_name || rows[0].username || rows[0].phone}」`
      : `选中的 ${rows.length} 个用户`;
  ui.confirmDelete({
    title: "批量删除用户",
    content: `确定删除${summary}？此操作不可恢复。`,
    onPositive: async () => {
      const { deleted, failed } = await deleteSequentially(rows, (row) => deleteUser(row.id));
      if (failed.length) {
        ui.warning(
          `已删除 ${deleted} 个，${failed.length} 个失败：${failed[0].message || "未知错误"}`
        );
      } else {
        ui.success(deleted > 1 ? `已删除 ${deleted} 个用户` : "用户已删除");
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
    <template #header-extra>
      <n-button type="primary" @click="openCreate">新建用户</n-button>
    </template>
    <BatchTableToolbar
      :count="selectedCount"
      :disabled="!canBatchDelete"
      @action="handleBatchDelete"
    />
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
    :title="isEdit ? '编辑用户' : '新建用户'"
    :width="520"
    @after-leave="closeModal"
  >
    <n-form
      class="admin-form-modal__form admin-form-modal__form--compact"
      label-placement="top"
    >
      <div class="admin-form-modal__form-grid">
        <n-form-item v-if="!isEdit" label="手机号" required>
          <n-input
            v-model:value="form.phone"
            placeholder="11 位手机号"
            maxlength="11"
          />
        </n-form-item>
        <n-form-item v-else label="手机号">
          <n-input :value="form.phone" disabled />
        </n-form-item>
        <n-form-item label="姓名" required>
          <n-input
            v-model:value="form.display_name"
            placeholder="不可与他人重复"
          />
        </n-form-item>
        <n-form-item label="邮箱" required>
          <n-input v-model:value="form.email" placeholder="不可与他人重复" />
        </n-form-item>
        <n-form-item :label="isEdit ? '新密码' : '密码'" :required="!isEdit">
          <n-input
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            :placeholder="isEdit ? '留空则不修改' : '至少 6 位'"
          />
        </n-form-item>
        <template v-if="!editingBootstrap">
          <n-form-item label="状态">
            <n-select v-model:value="form.status" :options="statusOptions" />
          </n-form-item>
          <n-form-item>
            <template #label>
              <span class="admin-form-modal__label-row">
                角色
                <HintTooltip
                  variant="inline"
                  placement="top"
                  text="普通成员与系统管理员二选一，不可同时持有多个角色。"
                />
              </span>
            </template>
            <n-select
              v-model:value="form.role_id"
              placeholder="选择角色"
              :options="roleOptions"
            />
          </n-form-item>
        </template>
      </div>

      <n-form-item v-if="!editingBootstrap">
        <template #label>
          <span class="admin-form-modal__label-row">
            部门
            <HintTooltip
              variant="inline"
              placement="top"
              text="每人只能归属一个部门；勾选新部门会自动取消原选择。"
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
        内置管理员（{{ BOOTSTRAP_PHONE }}）不归属部门，角色不可修改。
      </p>
    </n-form>
    <template #footer>
      <n-space :size="10">
        <n-button @click="showModal = false">取消</n-button>
        <n-button type="primary" :loading="saving" @click="submit">
          {{ isEdit ? "保存" : "创建" }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>
</template>
