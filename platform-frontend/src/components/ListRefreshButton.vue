<script setup>
import { NButton, NIcon } from "naive-ui";
import { RefreshOutline } from "@vicons/ionicons5";
import { useI18n } from "../composables/useI18n";

defineProps({
  loading: { type: Boolean, default: false },
  size: { type: String, default: "small" },
  quaternary: { type: Boolean, default: true },
  text: { type: Boolean, default: false },
});

const emit = defineEmits(["click"]);
const { t } = useI18n();
</script>

<template>
  <NButton
    :quaternary="quaternary"
    :text="text"
    :size="size"
    :loading="loading"
    @click="emit('click')"
  >
    <template #icon>
      <NIcon :component="RefreshOutline" />
    </template>
    {{ t("common.refresh") }}
  </NButton>
</template>
