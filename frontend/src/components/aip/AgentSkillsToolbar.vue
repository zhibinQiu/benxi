<script setup>
import { NText } from "naive-ui";
import { useI18n } from "../../composables/useI18n";

defineProps({
  activeTab: { type: String, required: true },
});

const { t } = useI18n();
</script>

<template>
  <div class="agent-skills-toolbar">
    <NText depth="3" class="agent-skills-toolbar__hint">
      {{ t(`admin.agentSkills.toolbarHint.${activeTab}`) }}
    </NText>
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
  font-size: var(--platform-font-size-sm);
  line-height: 1.35;
}
</style>
