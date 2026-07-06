<script setup>
import { NButton, NSpace, NText } from "naive-ui";
import { AddOutline, DownloadOutline } from "@vicons/ionicons5";
import ListRefreshButton from "../ListRefreshButton.vue";
import IconAction from "../IconAction.vue";
import { useI18n } from "../../composables/useI18n";

defineProps({
  activeTab: { type: String, required: true },
  refreshing: { type: Boolean, default: false },
  routingCatalogLoading: { type: Boolean, default: false },
  routingCatalogType: { type: String, default: "" },
});

const emit = defineEmits(["refresh", "open-routing-catalog", "connect-external-agent", "create-aip-key"]);

const { t } = useI18n();
</script>

<template>
  <div class="agent-skills-toolbar">
    <NText depth="3" class="agent-skills-toolbar__hint">
      {{ t(`admin.agentSkills.toolbarHint.${activeTab}`) }}
    </NText>
    <NSpace align="center" :size="10" class="agent-skills-toolbar__actions">
      <NButton
        v-if="activeTab === 'agents'"
        quaternary
        size="small"
        class="routing-catalog-link"
        :loading="routingCatalogLoading && routingCatalogType === 'agents.md'"
        @click="emit('open-routing-catalog', 'agents.md')"
      >
        agents.md
      </NButton>
      <NButton
        v-if="activeTab === 'skills'"
        quaternary
        size="small"
        class="routing-catalog-link"
        :loading="routingCatalogLoading && routingCatalogType === 'skills.md'"
        @click="emit('open-routing-catalog', 'skills.md')"
      >
        skills.md
      </NButton>
      <ListRefreshButton :loading="refreshing" @click="emit('refresh')" />
      <IconAction
        v-if="activeTab === 'agents'"
        type="primary"
        :label="t('admin.agentSkills.connectExternalAgent')"
        :icon="DownloadOutline"
        @click="emit('connect-external-agent')"
      />
      <IconAction
        v-if="activeTab === 'aip-keys'"
        type="primary"
        :label="t('admin.agentSkills.aipKeys.create')"
        :icon="AddOutline"
        @click="emit('create-aip-key')"
      />
    </NSpace>
  </div>
</template>

<style scoped>
.agent-skills-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px 19px;
  width: 100%;
  min-width: 0;
}
.agent-skills-toolbar__hint {
  flex: 1;
  min-width: 0;
  font-size: 16px;
  line-height: 1.45;
}
.agent-skills-toolbar__actions {
  flex-shrink: 0;
  margin-left: auto;
}
</style>
