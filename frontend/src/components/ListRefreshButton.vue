<script setup>
import { computed } from "vue";
import { RefreshOutline } from "@vicons/ionicons5";
import { useI18n } from "../composables/useI18n";
import IconAction from "./IconAction.vue";

const props = defineProps({
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  size: { type: String, default: "small" },
  /** tooltip / aria-label；默认「刷新」 */
  label: { type: String, default: "" },
  tooltip: { type: String, default: "" },
});

const emit = defineEmits(["click"]);
const { t } = useI18n();

const actionLabel = computed(() => props.label || t("common.refresh"));
const tooltipText = computed(() => props.tooltip || actionLabel.value);
</script>

<template>
  <IconAction
    :label="actionLabel"
    :tooltip="tooltipText"
    :icon="RefreshOutline"
    :size="size"
    :loading="loading"
    :disabled="disabled"
    @click="emit('click', $event)"
  />
</template>
