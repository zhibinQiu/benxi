<script setup>
/** 搜索按钮 → 展开输入框（类似文档管理搜索） */
import { nextTick, ref } from "vue";
import { NInput } from "naive-ui";
import { SearchOutline } from "@vicons/ionicons5";
import IconAction from "./IconAction.vue";
import { useI18n } from "../composables/useI18n";

const props = defineProps({
  modelValue: { type: String, default: "" },
  placeholder: { type: String, default: "" },
  /** 输入框宽度 */
  inputWidth: { type: String, default: "240px" },
});

const emit = defineEmits(["update:modelValue", "search", "clear"]);

const { t } = useI18n();
const open = ref(false);
const inputRef = ref(null);

function toggle() {
  open.value = !open.value;
  if (open.value) {
    nextTick(() => inputRef.value?.focus?.());
  } else {
    emit("clear");
  }
}

function onKeyupEnter() {
  emit("search");
}

function onClear() {
  emit("clear");
}

function onUpdateValue(val) {
  emit("update:modelValue", val);
}
</script>

<template>
  <span class="search-toggle">
    <n-input
      v-show="open"
      ref="inputRef"
      :value="modelValue"
      clearable
      :placeholder="placeholder"
      size="small"
      :style="{ width: inputWidth }"
      @update:value="onUpdateValue"
      @keyup.enter="onKeyupEnter"
      @clear="onClear"
    />
    <IconAction
      :label="t('common.search')"
      :icon="SearchOutline"
      :active="open"
      @click="toggle"
    />
  </span>
</template>

<style scoped>
.search-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
