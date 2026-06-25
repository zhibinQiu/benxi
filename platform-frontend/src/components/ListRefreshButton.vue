<script setup>
import { computed } from "vue";
import { NButton, NIcon, NTooltip } from "naive-ui";
import { RefreshOutline } from "@vicons/ionicons5";
import { useI18n } from "../composables/useI18n";

const props = defineProps({
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  size: { type: String, default: "small" },
  type: { type: String, default: "default" },
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
  <NTooltip placement="bottom">
    <template #trigger>
      <NButton
        circle
        :quaternary="type !== 'primary'"
        :type="type === 'primary' ? 'primary' : 'default'"
        :size="size"
        :loading="loading"
        :disabled="disabled"
        :aria-label="actionLabel"
        @click="emit('click')"
      >
        <NIcon :component="RefreshOutline" />
      </NButton>
    </template>
    {{ tooltipText }}
  </NTooltip>
</template>
