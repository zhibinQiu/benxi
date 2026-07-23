<script setup>
import { computed, onMounted, ref } from "vue";
import { NSwitch, NTooltip } from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { getApiBase } from "../api/http";
import {
  fetchAiHomeOpenApiSettings,
  updateAiHomeOpenApiSettings,
} from "../api/aiHomeOpenApi.js";

const { t } = useI18n();
const ui = usePlatformUi();
const { hasPerm } = useAuth();

const canManage = computed(() => hasPerm("admin.user"));
const loading = ref(false);
const saving = ref(false);
const enabled = ref(false);
const basePath = ref("/api/v1/openai/v1");
const visible = computed(() => canManage.value);

const baseUrl = computed(() => {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const apiBase = getApiBase().replace(/\/$/, "");
  const path = (basePath.value || "/api/v1/openai/v1").replace(/^\//, "");
  return `${origin}${apiBase}/${path}`.replace(/([^:]\/)\/+/g, "$1");
});

const tooltipText = computed(
  () => `${t("aiHome.openApi.hint")} ${baseUrl.value}`
);

async function load() {
  if (!canManage.value) return;
  loading.value = true;
  try {
    const data = await fetchAiHomeOpenApiSettings();
    enabled.value = Boolean(data?.enabled);
    if (data?.base_path) basePath.value = data.base_path;
  } catch (e) {
    ui.error(e?.message || t("aiHome.openApi.loadFailed"));
  } finally {
    loading.value = false;
  }
}

async function onToggle(value) {
  if (!canManage.value || saving.value) return;
  saving.value = true;
  try {
    const data = await updateAiHomeOpenApiSettings(value);
    enabled.value = Boolean(data?.enabled);
    if (data?.base_path) basePath.value = data.base_path;
    ui.success(
      enabled.value ? t("aiHome.openApi.enabledToast") : t("aiHome.openApi.disabledToast")
    );
  } catch (e) {
    ui.error(e?.message || t("aiHome.openApi.saveFailed"));
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <label
    v-if="visible"
    class="ai-home-openapi-toggle"
    :title="tooltipText"
  >
    <n-tooltip trigger="hover" placement="bottom">
      <template #trigger>
        <span class="ai-home-openapi-toggle__label">
          {{ t("aiHome.openApi.title") }}
        </span>
      </template>
      <span class="ai-home-openapi-toggle__tip">{{ tooltipText }}</span>
    </n-tooltip>
    <n-switch
      size="small"
      :value="enabled"
      :loading="loading || saving"
      :disabled="loading"
      @update:value="onToggle"
    />
  </label>
</template>

<style scoped>
.ai-home-openapi-toggle {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 4px 0 8px;
  margin: 0;
  cursor: pointer;
  user-select: none;
}

.ai-home-openapi-toggle__label {
  font-size: 11px;
  color: var(--platform-text-tertiary);
  white-space: nowrap;
  line-height: 1;
}

.ai-home-openapi-toggle:hover .ai-home-openapi-toggle__label {
  color: var(--platform-text-secondary);
}

.ai-home-openapi-toggle__tip {
  max-width: 420px;
  word-break: break-all;
  white-space: normal;
  line-height: 1.4;
}

@media (max-width: 768px) {
  .ai-home-openapi-toggle {
    height: 26px;
    padding: 0 2px 0 4px;
    gap: 4px;
  }
  .ai-home-openapi-toggle__label {
    font-size: 10px;
  }
}
</style>
