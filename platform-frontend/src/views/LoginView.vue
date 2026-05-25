<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NCard,
  NForm,
  NFormItem,
  NInput,
  NButton,
  NSpace,
  NText,
  useMessage,
} from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { PLATFORM_APP_NAME } from "../constants/platform";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const { login } = useAuth();

const username = ref("admin");
const password = ref("admin123");
const loading = ref(false);

async function onSubmit() {
  loading.value = true;
  try {
    await login(username.value, password.value);
    message.success("登录成功");
    const redirect = route.query.redirect || "/system/functions";
    router.push(redirect);
  } catch (e) {
    message.error(e.message || "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <n-card class="login-card" size="large">
      <template #header>
        <div class="login-brand">
          <img src="/logo.svg" :alt="PLATFORM_APP_NAME" class="login-logo" />
          <span class="login-title">{{ PLATFORM_APP_NAME }}</span>
        </div>
      </template>
      <n-text depth="2">智碳AI能力统一入口</n-text>
      <n-form style="margin-top: 24px" @submit.prevent="onSubmit">
        <n-form-item label="用户名">
          <n-input v-model:value="username" placeholder="admin" />
        </n-form-item>
        <n-form-item label="密码">
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            @keyup.enter="onSubmit"
          />
        </n-form-item>
        <n-space vertical :size="12" style="width: 100%">
          <n-button type="primary" block :loading="loading" attr-type="submit">
            登录
          </n-button>
          <n-text depth="3" style="font-size: 12px">
            默认账号见 platform/.env（BOOTSTRAP_ADMIN_*）
          </n-text>
        </n-space>
      </n-form>
    </n-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #eef2ff 0%, #f5f6f8 50%, #e8f4f8 100%);
}
.login-card {
  width: 400px;
  max-width: calc(100vw - 32px);
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.login-logo {
  width: 40px;
  height: 40px;
}
.login-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1a1a2e;
}
</style>
