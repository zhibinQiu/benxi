<script setup>
import { onMounted, ref } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NSpace,
  NTag,
  useMessage,
} from "naive-ui";
import { fetchModelSettings } from "../../api/client";

const message = useMessage();
const loading = ref(false);
const settings = ref(null);

async function load() {
  loading.value = true;
  try {
    settings.value = await fetchModelSettings();
  } catch (e) {
    message.error(e.message);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="model-settings-page">
    <n-alert type="info" :bordered="false" class="page-alert">
      {{ settings?.notice || "本页配置暂不生效，实际以服务器环境变量为准。" }}
      <template #header>配置说明</template>
    </n-alert>

    <n-space vertical :size="16" style="margin-top: 16px">
      <n-card title="语言模型（LLM）" size="small" :loading="loading">
        <n-form label-placement="left" label-width="100">
          <n-form-item label="API URL">
            <n-input
              :value="settings?.llm?.base_url || ''"
              placeholder="未配置"
              readonly
            />
          </n-form-item>
          <n-form-item label="模型名称">
            <n-input
              :value="settings?.llm?.model_name || ''"
              placeholder="未配置"
              readonly
            />
          </n-form-item>
          <n-form-item label="SK / API Key">
            <n-input
              :value="
                settings?.llm?.api_key_configured
                  ? settings.llm.api_key_masked
                  : ''
              "
              placeholder="未配置"
              readonly
            />
            <n-tag
              v-if="settings?.llm?.api_key_configured"
              size="small"
              type="success"
              :bordered="false"
              style="margin-left: 8px"
            >
              已配置
            </n-tag>
          </n-form-item>
        </n-form>
      </n-card>

      <n-card title="Embedding 模型" size="small" :loading="loading">
        <n-form label-placement="left" label-width="100">
          <n-form-item label="API URL">
            <n-input
              :value="settings?.embedding?.base_url || ''"
              placeholder="未配置"
              readonly
            />
          </n-form-item>
          <n-form-item label="SK / API Key">
            <n-input
              :value="
                settings?.embedding?.api_key_configured
                  ? settings.embedding.api_key_masked
                  : ''
              "
              placeholder="未配置"
              readonly
            />
            <n-tag
              v-if="settings?.embedding?.api_key_configured"
              size="small"
              type="success"
              :bordered="false"
              style="margin-left: 8px"
            >
              已配置
            </n-tag>
          </n-form-item>
        </n-form>
      </n-card>

      <n-card title="Reranker 模型" size="small" :loading="loading">
        <n-form label-placement="left" label-width="100">
          <n-form-item label="API URL">
            <n-input
              :value="settings?.rerank?.base_url || ''"
              placeholder="未配置"
              readonly
            />
          </n-form-item>
          <n-form-item label="SK / API Key">
            <n-input
              :value="
                settings?.rerank?.api_key_configured
                  ? settings.rerank.api_key_masked
                  : ''
              "
              placeholder="未配置"
              readonly
            />
            <n-tag
              v-if="settings?.rerank?.api_key_configured"
              size="small"
              type="success"
              :bordered="false"
              style="margin-left: 8px"
            >
              已配置
            </n-tag>
          </n-form-item>
        </n-form>
      </n-card>

      <n-space>
        <n-button :loading="loading" @click="load">刷新</n-button>
        <n-tag type="warning" :bordered="false">暂不生效 · 环境变量为准</n-tag>
      </n-space>
    </n-space>
  </div>
</template>

<style scoped>
.model-settings-page {
  max-width: 720px;
}
.page-alert {
  margin-bottom: 0;
}
</style>
