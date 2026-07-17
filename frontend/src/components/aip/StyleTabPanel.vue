<script setup>
import { computed, onMounted, ref } from "vue";
import { NButton, NCard, NInput, NSelect, NSpace, NText, NTag } from "naive-ui";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import {
  fetchAgentProfileFile,
  fetchAgentProfiles,
  updateAgentProfileFile,
} from "../../api/agentSkills.js";
import { formatAgentDisplayName } from "../../utils/agentDisplay.js";
import { normalizeBuiltinAgent } from "../../utils/agentSkillsHelpers.js";

const ui = usePlatformUi();
const { t } = useI18n();

const agents = ref([]);
const loading = ref(false);
const styleLoading = ref(false);
const saving = ref(false);

const selectedAgentId = ref("");
const styleContent = ref("");
const styleDirty = ref(false);

const agentOptions = computed(() =>
  agents.value.map((a) => ({
    label: formatAgentDisplayName(a.title) || a.id,
    value: a.id,
    disabled: !a.enabled,
  }))
);

const selectedAgent = computed(() =>
  agents.value.find((a) => a.id === selectedAgentId.value)
);

const selectedAgentTitle = computed(() => {
  if (!selectedAgent.value) return "";
  return formatAgentDisplayName(selectedAgent.value.title) || selectedAgent.value.id;
});

async function loadAgents() {
  loading.value = true;
  try {
    const rows = (await fetchAgentProfiles()) || [];
    agents.value = rows.map(normalizeBuiltinAgent);
    // 默认选中第一个内置智能体
    if (!selectedAgentId.value && agents.value.length) {
      selectedAgentId.value = agents.value[0].id;
    }
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.loadFailed"));
  } finally {
    loading.value = false;
  }
}

async function loadStyle(agentId) {
  if (!agentId) return;
  styleLoading.value = true;
  styleContent.value = "";
  styleDirty.value = false;
  try {
    const file = await fetchAgentProfileFile(agentId, "STYLE.md");
    styleContent.value = file?.text || "";
  } catch (e) {
    styleContent.value = "";
  } finally {
    styleLoading.value = false;
  }
}

async function saveStyle() {
  if (!selectedAgentId.value) return;
  saving.value = true;
  try {
    await updateAgentProfileFile(selectedAgentId.value, "STYLE.md", styleContent.value);
    styleDirty.value = false;
    ui.success(t("admin.agentSkills.saved"));
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    saving.value = false;
  }
}

function clearStyle() {
  styleContent.value = "";
  styleDirty.value = true;
}

function onAgentChange(agentId) {
  styleDirty.value = false;
  loadStyle(agentId);
}

onMounted(async () => {
  await loadAgents();
  if (selectedAgentId.value) {
    await loadStyle(selectedAgentId.value);
  }
});

defineExpose({
  async load({ foreground = false } = {}) {
    await loadAgents();
    if (selectedAgentId.value) {
      await loadStyle(selectedAgentId.value);
    }
  },
  loading,
});
</script>

<template>
  <div class="style-tab-panel">
    <NCard size="small">

      <div v-if="loading" class="agent-card-grid--skeleton">
        <div class="mcp-card--skeleton" style="max-width: 600px">
          <div class="skeleton-line skeleton-line--title" />
          <div class="skeleton-line skeleton-line--desc skeleton-line--short" />
        </div>
      </div>
      <template v-else>
        <div class="style-tab-panel__agent-picker">
          <NSelect
            v-model:value="selectedAgentId"
            :placeholder="t('admin.agentSkills.selectAgent')"
            :options="agentOptions"
            filterable
            style="max-width: 380px"
            @update:value="onAgentChange"
          />
          <NTag v-if="selectedAgent" size="small" :bordered="false" type="info">
            {{ selectedAgent.enabled ? t("admin.agentSkills.statusRunning") : t("admin.agentSkills.disabledAgent") }}
          </NTag>
        </div>

        <NText v-if="selectedAgentId" depth="3" class="style-tab-panel__file-name">
          STYLE.md — {{ selectedAgentTitle }}
        </NText>

        <div v-if="styleLoading" class="style-tab-panel__loading">
          <div class="skeleton-line skeleton-line--desc" />
          <div class="skeleton-line skeleton-line--desc" />
          <div class="skeleton-line skeleton-line--desc skeleton-line--short" />
        </div>
        <template v-else-if="selectedAgentId">
          <NInput
            :key="selectedAgentId"
            v-model:value="styleContent"
            type="textarea"
            :rows="18"
            :placeholder="t('admin.agentSkills.stylePlaceholder')"
            @update:value="styleDirty = true"
          />
          <NSpace style="margin-top: 14px" :size="10">
            <NButton quaternary :loading="saving" @click="saveStyle">
              {{ t("common.save") }}
            </NButton>
            <NButton quaternary @click="clearStyle">
              {{ t("common.clear") }}
            </NButton>
          </NSpace>
        </template>
        <NText v-else depth="3">
          {{ t("admin.agentSkills.styleNoAgent") }}
        </NText>
      </template>
    </NCard>
  </div>
</template>

<style scoped>
.style-tab-panel {
  max-width: 800px;
}

.style-tab-panel__agent-picker {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}

.style-tab-panel__file-name {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
}

.style-tab-panel__loading {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
