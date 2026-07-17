<script setup>
import { onMounted, ref } from "vue";
import { NButton, NCard, NInput, NSpace } from "naive-ui";
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
  <NCard size="small">
    <div v-if="loading" class="agent-card-grid--skeleton">
      <div class="mcp-card--skeleton" style="max-width: 600px">
        <div class="skeleton-line skeleton-line--title" />
        <div class="skeleton-line skeleton-line--desc skeleton-line--short" />
      </div>
    </div>
    <template v-else>
      <div class="memory-tab-panel__input-backdrop">
        <div class="memory-tab-panel__input-backdrop-title">
          <span>{{ t("admin.agentSkills.memoryTitle") }}</span>
        </div>
        <NInput
          v-model:value="content"
          type="textarea"
          :rows="14"
          :placeholder="t('admin.agentSkills.memoryPlaceholder')"
        />
      </div>
      <p class="memory-tab-panel__hint">{{ t("admin.agentSkills.memoryHint") }}</p>
      <NSpace style="margin-top: 14px" :size="10">
        <NButton quaternary :loading="saving" @click="save">
          {{ t("common.save") }}
        </NButton>
        <NButton quaternary @click="wipe">
          {{ t("admin.agentSkills.memoryClear") }}
        </NButton>
      </NSpace>
    </template>
  </NCard>
</template>

<style scoped>
.memory-tab-panel__input-backdrop {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius);
  background: #fff;
  padding: 16px;
  margin-bottom: 12px;
}

.memory-tab-panel__input-backdrop-title {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  font-size: var(--platform-font-size-base);
  font-weight: 600;
  color: var(--platform-text-primary);
}

.memory-tab-panel__hint {
  margin: 0 0 14px;
  font-size: var(--platform-font-size-sm);
  line-height: 1.5;
  color: var(--platform-text-tertiary);
}
</style>
