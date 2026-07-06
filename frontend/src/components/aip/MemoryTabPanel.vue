<script setup>
import { onMounted, ref } from "vue";
import { NButton, NCard, NInput, NSpace, NText } from "naive-ui";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { clearAgentMemory, fetchAgentMemory, updateAgentMemory } from "../../api/agentSkills.js";

const ui = usePlatformUi();
const { t } = useI18n();

const content = ref("");
const loading = ref(false);
const saving = ref(false);

async function load() {
  loading.value = true;
  try {
    const data = await fetchAgentMemory();
    content.value = data?.content || "";
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.loadFailed"));
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  try {
    const data = await updateAgentMemory(content.value);
    content.value = data?.content || "";
    ui.success(t("admin.agentSkills.saved"));
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    saving.value = false;
  }
}

function wipe() {
  ui.confirmDelete({
    title: t("admin.agentSkills.memoryClearTitle"),
    content: t("admin.agentSkills.memoryClearConfirm"),
    onPositive: async () => {
      try {
        await clearAgentMemory();
        content.value = "";
        ui.success(t("admin.agentSkills.memoryCleared"));
      } catch (e) {
        ui.error(e.message || t("admin.agentSkills.saveFailed"));
      }
    },
  });
}

onMounted(load);

defineExpose({ load, loading });
</script>

<template>
  <NCard size="small" :title="t('admin.agentSkills.memoryTitle')">
    <NText depth="3" style="display: block; margin-bottom: 14px">
      {{ t("admin.agentSkills.memoryHint") }}
    </NText>
    <div v-if="loading" class="agent-card-grid--skeleton">
      <div class="mcp-card--skeleton" style="max-width: 600px">
        <div class="skeleton-line skeleton-line--title" />
        <div class="skeleton-line skeleton-line--desc skeleton-line--short" />
      </div>
    </div>
    <template v-else>
      <NInput
        v-model:value="content"
        type="textarea"
        :rows="16"
        :placeholder="t('admin.agentSkills.memoryPlaceholder')"
      />
      <NSpace style="margin-top: 14px" :size="10">
        <NButton type="primary" :loading="saving" @click="save">
          {{ t("common.save") }}
        </NButton>
        <NButton type="error" quaternary @click="wipe">
          {{ t("admin.agentSkills.memoryClear") }}
        </NButton>
      </NSpace>
    </template>
  </NCard>
</template>
