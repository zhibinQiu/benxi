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
  NPopconfirm,
  useMessage,
} from "naive-ui";
import {
  fetchUsers,
  createUser,
  updateUser,
  deleteUser,
  fetchDepartments,
  fetchRoles,
} from "../../api/client";

const message = useMessage();
const loading = ref(false);
const users = ref([]);
const departments = ref([]);
const roles = ref([]);

const showModal = ref(false);
const editingId = ref(null);
const saving = ref(false);

const emptyForm = () => ({
  username: "",
  password: "",
  email: "",
  status: "active",
  department_ids: [],
  role_ids: [],
});

const form = ref(emptyForm());

const isEdit = computed(() => Boolean(editingId.value));

const deptOptions = computed(() =>
  departments.value.map((d) => ({ label: d.name, value: d.id }))
);

const roleOptions = computed(() =>
  roles.value.map((r) => ({ label: `${r.name}（${r.code}）`, value: r.id }))
);

const statusOptions = [
  { label: "正常", value: "active" },
  { label: "禁用", value: "disabled" },
];

function deptLabel(ids) {
  if (!ids?.length) return "—";
  const names = ids
    .map((id) => departments.value.find((d) => d.id === id)?.name)
    .filter(Boolean);
  return names.length ? names.join("、") : `${ids.length} 个`;
}

function roleLabel(ids) {
  if (!ids?.length) return "—";
  const names = ids
    .map((id) => roles.value.find((r) => r.id === id)?.name)
    .filter(Boolean);
  return names.length ? names.join("、") : `${ids.length} 个`;
}

const columns = [
  { title: "用户名", key: "username", width: 120 },
  { title: "邮箱", key: "email", render: (r) => r.email || "—" },
  {
    title: "状态",
    key: "status",
    width: 80,
    render: (r) => (r.status === "active" ? "正常" : "禁用"),
  },
  {
    title: "部门",
    key: "department_ids",
    ellipsis: { tooltip: true },
    render: (r) => deptLabel(r.department_ids),
  },
  {
    title: "角色",
    key: "role_ids",
    ellipsis: { tooltip: true },
    render: (r) => roleLabel(r.role_ids),
  },
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
          { onPositiveClick: () => removeUser(row) },
          {
            trigger: () =>
              h(NButton, { size: "small", quaternary: true, type: "error" }, { default: () => "删除" }),
            default: () => `确定删除用户「${row.username}」？`,
          }
        ),
      ]);
    },
  },
];

async function loadMeta() {
  try {
    const [depts, roleList] = await Promise.all([
      fetchDepartments().catch(() => []),
      fetchRoles().catch(() => []),
    ]);
    departments.value = depts;
    roles.value = roleList;
  } catch (e) {
    message.warning(e.message || "加载部门/角色失败");
  }
}

async function load() {
  loading.value = true;
  try {
    users.value = await fetchUsers();
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
    username: row.username,
    password: "",
    email: row.email || "",
    status: row.status || "active",
    department_ids: [...(row.department_ids || [])],
    role_ids: [...(row.role_ids || [])],
  };
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
  editingId.value = null;
  form.value = emptyForm();
}

function validateForm() {
  if (!form.value.username?.trim()) {
    message.warning("用户名必填");
    return false;
  }
  if (form.value.username.trim().length < 2) {
    message.warning("用户名至少 2 个字符");
    return false;
  }
  if (!isEdit.value) {
    if (!form.value.password || form.value.password.length < 6) {
      message.warning("密码至少 6 个字符");
      return false;
    }
  } else if (form.value.password && form.value.password.length < 6) {
    message.warning("新密码至少 6 个字符，留空则不修改");
    return false;
  }
  return true;
}

async function submit() {
  if (!validateForm()) return;
  saving.value = true;
  const payload = {
    username: form.value.username.trim(),
    email: form.value.email?.trim() || null,
    status: form.value.status,
    department_ids: form.value.department_ids,
    role_ids: form.value.role_ids,
  };
  try {
    if (isEdit.value) {
      const patch = { ...payload };
      if (form.value.password) patch.password = form.value.password;
      await updateUser(editingId.value, patch);
      message.success("用户已更新");
    } else {
      await createUser({ ...payload, password: form.value.password });
      message.success("用户已创建");
    }
    closeModal();
    await load();
  } catch (e) {
    message.error(e.message);
  } finally {
    saving.value = false;
  }
}

async function removeUser(row) {
  try {
    await deleteUser(row.id);
    message.success("用户已删除");
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

onMounted(async () => {
  await loadMeta();
  await load();
});
</script>

<template>
  <n-card title="用户管理">
    <template #header-extra>
      <n-button type="primary" @click="openCreate">新建用户</n-button>
    </template>
    <n-data-table :columns="columns" :data="users" :loading="loading" :scroll-x="900" />
  </n-card>

  <n-modal
    v-model:show="showModal"
    preset="card"
    :title="isEdit ? '编辑用户' : '新建用户'"
    style="width: 520px"
    @after-leave="closeModal"
  >
    <n-form label-placement="left" label-width="88">
      <n-form-item label="用户名" required>
        <n-input v-model:value="form.username" placeholder="登录名" />
      </n-form-item>
      <n-form-item :label="isEdit ? '新密码' : '密码'" :required="!isEdit">
        <n-input
          v-model:value="form.password"
          type="password"
          show-password-on="click"
          :placeholder="isEdit ? '留空则不修改' : '至少 6 位'"
        />
      </n-form-item>
      <n-form-item label="邮箱">
        <n-input v-model:value="form.email" />
      </n-form-item>
      <n-form-item label="状态">
        <n-select v-model:value="form.status" :options="statusOptions" />
      </n-form-item>
      <n-form-item label="部门">
        <n-select
          v-model:value="form.department_ids"
          multiple
          filterable
          clearable
          placeholder="选择所属部门（首个为主部门）"
          :options="deptOptions"
        />
      </n-form-item>
      <n-form-item label="角色">
        <n-select
          v-model:value="form.role_ids"
          multiple
          filterable
          clearable
          placeholder="选择角色以分配权限"
          :options="roleOptions"
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
