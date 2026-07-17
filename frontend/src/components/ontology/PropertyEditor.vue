<template>
  <div class="property-editor">
    <div v-for="(prop, key, idx) in schema" :key="key" class="prop-row">
      <n-space align="center" style="width: 100%;">
        <n-input v-model:value="propKeys[idx]" size="small" placeholder="属性名" style="width: 120px"
          @update:value="renameKey(idx, $event)" />
        <n-select v-model:value="prop.type" size="small" :options="typeOptions" style="width: 100px" />
        <n-switch v-model:value="prop.required" size="small" />
        <span style="font-size: 12px; color: #888;">必需</span>
        <n-input v-model:value="prop.description" size="small" placeholder="描述" style="flex:1;" />
        <n-button size="small" quaternary type="error" @click="removeProp(key)">
          <template #icon><n-icon><CloseOutline /></n-icon></template>
        </n-button>
      </n-space>
    </div>
    <n-button size="small" class="platform-btn--create" @click="addProp" style="margin-top: 8px;">
      <template #icon><n-icon><AddOutline /></n-icon></template>
      添加属性
    </n-button>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
import { AddOutline, CloseOutline } from "@vicons/ionicons5";

const props = defineProps({
  value: { type: Object, default: () => ({}) },
});

const emit = defineEmits(["update:value"]);

const typeOptions = [
  { label: "字符串", value: "string" },
  { label: "数字", value: "number" },
  { label: "日期", value: "date" },
  { label: "布尔", value: "boolean" },
  { label: "文本", value: "text" },
  { label: "链接", value: "url" },
];

const schema = ref({ ...props.value });
const propKeys = ref(Object.keys(props.value));

watch(
  () => props.value,
  (v) => {
    schema.value = { ...v };
    propKeys.value = Object.keys(v);
  },
  { deep: true }
);

function addProp() {
  const key = "prop_" + Date.now();
  schema.value[key] = { type: "string", required: false, description: "" };
  propKeys.value = Object.keys(schema.value);
  emitChange();
}

function removeProp(key) {
  delete schema.value[key];
  propKeys.value = Object.keys(schema.value);
  emitChange();
}

function renameKey(idx, newKey) {
  const oldKey = propKeys.value[idx];
  if (oldKey === newKey || !newKey) return;
  if (newKey in schema.value && newKey !== oldKey) return;
  const val = schema.value[oldKey];
  delete schema.value[oldKey];
  schema.value[newKey] = val;
  propKeys.value = Object.keys(schema.value);
  emitChange();
}

function emitChange() {
  const result = {};
  for (const key of propKeys.value) {
    if (schema.value[key]) {
      result[key] = { ...schema.value[key] };
    }
  }
  emit("update:value", result);
}
</script>

<style scoped>
.prop-row {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
}
</style>
