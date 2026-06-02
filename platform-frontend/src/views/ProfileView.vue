<script setup>
import { computed, onMounted, ref } from "vue";
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NSpace,
  NText,
  useMessage,
} from "naive-ui";
import { updateMe } from "../api/client";
import { useAuth } from "../composables/useAuth";

const message = useMessage();
const { user, loadUser, hasPerm, isBootstrapAdmin } = useAuth();

const saving = ref(false);

const form = ref({
  display_name: "",
  email: "",
  password: "",
});

const showAdminGrantFields = computed(() => hasPerm("admin.user"));

const departmentLabel = computed(() => user.value?.department_name || "—");

const roleLabel = computed(() => {
  const names = user.value?.role_names || [];
  if (names.length) return names.join("、");
  if (user.value?.is_system_admin) return "系统管理员";
  return "普通用户";
});

function syncFormFromUser() {
  form.value = {
    display_name: user.value?.display_name || user.value?.username || "",
    email: user.value?.email || "",
    password: "",
  };
}

function validateForm() {
  if (!form.value.display_name?.trim()) {
    message.warning("姓名必填");
    return false;
  }
  if (form.value.display_name.trim().length < 2) {
    message.warning("姓名至少 2 个字符");
    return false;
  }
  if (!form.value.email?.trim()) {
    message.warning("邮箱必填");
    return false;
  }
  if (form.value.password && form.value.password.length < 6) {
    message.warning("新密码至少 6 个字符，留空则不修改");
    return false;
  }
  return true;
}

async function submit() {
  if (!validateForm()) return;
  saving.value = true;
  const payload = {
    display_name: form.value.display_name.trim(),
    email: form.value.email.trim(),
  };
  if (form.value.password) payload.password = form.value.password;
  try {
    await updateMe(payload);
    await loadUser();
    syncFormFromUser();
    message.success("个人信息已保存");
  } catch (e) {
    message.error(e.message);
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  syncFormFromUser();
});
</script>

<template>
  <n-card title="信息维护">
    <n-form label-placement="left" label-width="88" style="max-width: 520px">
      <n-form-item label="手机号">
        <n-input :value="user?.phone || '—'" disabled />
      </n-form-item>
      <n-form-item label="姓名" required>
        <n-input
          v-model:value="form.display_name"
          :disabled="isBootstrapAdmin"
          placeholder="登录与界面均显示此名称"
        />
      </n-form-item>
      <n-form-item v-if="isBootstrapAdmin" label="">
        <n-text depth="3">系统默认管理员姓名不可在此修改</n-text>
      </n-form-item>
      <n-form-item label="邮箱" required>
        <n-input v-model:value="form.email" placeholder="不可与他人重复" />
      </n-form-item>
      <n-form-item label="新密码">
        <n-input
          v-model:value="form.password"
          type="password"
          show-password-on="click"
          placeholder="留空则不修改"
        />
      </n-form-item>
      <n-form-item label="部门">
        <n-text>{{ departmentLabel }}</n-text>
      </n-form-item>
      <n-form-item label="角色">
        <n-text>{{ roleLabel }}</n-text>
      </n-form-item>
      <n-form-item v-if="showAdminGrantFields" label="">
        <n-text depth="3">
          部门与角色授权请在「系统设置 → 用户管理」中操作
        </n-text>
      </n-form-item>
      <n-form-item label="">
        <n-space>
          <n-button type="primary" :loading="saving" @click="submit">保存</n-button>
        </n-space>
      </n-form-item>
    </n-form>
  </n-card>
</template>
