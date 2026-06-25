<script setup>
import { AddOutline, TimeOutline } from "@vicons/ionicons5";
import { NButton, NIcon } from "naive-ui";
import IconAction from "./IconAction.vue";
import { useI18n } from "../composables/useI18n.js";

defineProps({
  disabled: { type: Boolean, default: false },
});

defineEmits(["history", "new-chat"]);

const { t } = useI18n();
</script>

<template>
  <IconAction
    :label="t('chat.history')"
    :icon="TimeOutline"
    :disabled="disabled"
    @click="$emit('history')"
  />
  <n-button
    size="small"
    quaternary
    class="chat-session-toolbar__new"
    @click="$emit('new-chat')"
  >
    <template #icon>
      <n-icon :component="AddOutline" />
    </template>
    {{ t("chat.newChat") }}
  </n-button>
</template>
