<script setup>
import { computed } from "vue";
import { NSpace } from "naive-ui";
import { TrashOutline } from "@vicons/ionicons5";
import { useI18n } from "../composables/useI18n";
import IconAction from "./IconAction.vue";

const props = defineProps({
  count: { type: Number, default: 0 },
  disabled: { type: Boolean, default: true },
  labelKey: { type: String, default: "batch.delete" },
  actionType: { type: String, default: "error" },
  icon: { type: [Object, Function], default: () => TrashOutline }});

defineEmits(["action"]);

const { t } = useI18n();
const label = computed(() => t(props.labelKey));
</script>

<template>
  <div class="batch-table-toolbar">
    <n-space align="center" :size="10">
      <IconAction
        :label="label"
        :icon="icon"
        :type="actionType"
        :disabled="disabled"
        @click="$emit('action')"
      />
      <span v-if="count > 0" class="batch-table-toolbar__hint">
        {{ t("batch.selected", { count }) }}
      </span>
    </n-space>
  </div>
</template>
