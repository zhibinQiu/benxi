<script setup>
import { computed, onMounted, ref } from "vue";
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NSpace,
  NText } from "naive-ui";
import { updateMe } from "../api/client";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";

const ui = usePlatformUi();
const { t } = useI18n();
const { user, loadUser, hasPerm, isBootstrapAdmin } = useAuth();

const saving = ref(false);

const form = ref({
  display_name: "",
  email: "",
  password: ""});

const showAdminGrantFields = computed(() => hasPerm("admin.user"));

const departmentLabel = computed(() => user.value?.department_name || "—");

const roleLabel = computed(() => {
  const names = user.value?.role_names || [];
  if (names.length) return names.join("、");
  if (user.value?.is_system_admin) return t("profile.roleAdmin");
  return t("profile.roleUser");
});

function syncFormFromUser() {
  form.value = {
    display_name: user.value?.display_name || user.value?.username || "",
    email: user.value?.email || "",
    password: ""};
}

function validateForm() {
  if (!form.value.display_name?.trim()) {
    ui.warning("validation.nameRequired");
    return false;
  }
  if (form.value.display_name.trim().length < 2) {
    ui.warning("validation.nameMinLength");
    return false;
  }
  if (!form.value.email?.trim()) {
    ui.warning("validation.emailRequired");
    return false;
  }
  if (form.value.password && form.value.password.length < 6) {
    ui.warning("validation.passwordOptionalMin");
    return false;
  }
  return true;
}

async function submit() {
  if (!validateForm()) return;
  saving.value = true;
  const payload = {
    display_name: form.value.display_name.trim(),
    email: form.value.email.trim()};
  if (form.value.password) payload.password = form.value.password;
  try {
    await updateMe(payload);
    await loadUser();
    syncFormFromUser();
    ui.success("profile.saved");
  } catch (e) {
    ui.error(e);
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  syncFormFromUser();
});
</script>

<template>
  <n-card class="profile-page">
    <n-form label-placement="left" label-width="88" style="max-width: 624px">
      <n-form-item :label="t('profile.phone')">
        <n-input :value="user?.phone || '—'" disabled />
      </n-form-item>
      <n-form-item :label="t('profile.displayName')" required>
        <n-input
          v-model:value="form.display_name"
          :disabled="isBootstrapAdmin"
          :placeholder="t('profile.displayNamePlaceholder')"
        />
      </n-form-item>
      <n-form-item v-if="isBootstrapAdmin" label="">
        <n-text depth="3">{{ t("profile.bootstrapHint") }}</n-text>
      </n-form-item>
      <n-form-item :label="t('profile.email')" required>
        <n-input
          v-model:value="form.email"
          :placeholder="t('profile.emailPlaceholder')"
        />
      </n-form-item>
      <n-form-item :label="t('profile.newPassword')">
        <n-input
          v-model:value="form.password"
          type="password"
          show-password-on="click"
          :placeholder="t('profile.passwordPlaceholder')"
        />
      </n-form-item>
      <n-form-item :label="t('profile.department')">
        <n-text>{{ departmentLabel }}</n-text>
      </n-form-item>
      <n-form-item :label="t('profile.role')">
        <n-text>{{ roleLabel }}</n-text>
      </n-form-item>
      <n-form-item v-if="showAdminGrantFields" label="">
        <n-text depth="3">{{ t("profile.adminHint") }}</n-text>
      </n-form-item>
      <n-form-item label="">
        <n-space>
          <n-button type="primary" :loading="saving" @click="submit">
            {{ t("common.save") }}
          </n-button>
        </n-space>
      </n-form-item>
    </n-form>
  </n-card>
</template>
