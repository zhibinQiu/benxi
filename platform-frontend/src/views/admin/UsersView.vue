<script setup>
import { h, onMounted, ref } from "vue";
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
import { fetchUsers, createUser } from "../../api/client";

const message = useMessage();
const loading = ref(false);
const users = ref([]);
const showCreate = ref(false);
const form = ref({
  username: "",
  password: "",
  display_name: "",
  email: "",
});

const columns = [
  { title: "用户名", key: "username" },
  { title: "显示名", key: "display_name" },
  { title: "邮箱", key: "email", render: (r) => r.email || "—" },
  { title: "状态", key: "status", width: 90 },
  {
    title: "部门数",
    key: "department_ids",
    width: 80,
    render: (r) => (r.department_ids?.length || 0),
  },
];

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

async function submit() {
  if (!form.value.username || !form.value.password) {
    message.warning("用户名和密码必填");
    return;
  }
  try {
    await createUser({
      username: form.value.username,
      password: form.value.password,
      display_name: form.value.display_name || form.value.username,
      email: form.value.email || null,
    });
    message.success("用户已创建");
    showCreate.value = false;
    form.value = { username: "", password: "", display_name: "", email: "" };
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

onMounted(load);
</script>

<template>
  <n-card title="用户管理">
    <template #header-extra>
      <n-button type="primary" @click="showCreate = true">新建用户</n-button>
    </template>
    <n-data-table :columns="columns" :data="users" :loading="loading" />
  </n-card>

  <n-modal v-model:show="showCreate" preset="card" title="新建用户" style="width: 420px">
    <n-form>
      <n-form-item label="用户名" required>
        <n-input v-model:value="form.username" />
      </n-form-item>
      <n-form-item label="密码" required>
        <n-input v-model:value="form.password" type="password" show-password-on="click" />
      </n-form-item>
      <n-form-item label="显示名">
        <n-input v-model:value="form.display_name" />
      </n-form-item>
      <n-form-item label="邮箱">
        <n-input v-model:value="form.email" />
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
