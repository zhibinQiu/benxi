<script setup>
import { computed } from "vue";
import { NEmpty, NTree } from "naive-ui";
import {
  buildOrgDeptTree,
  defaultExpandedDeptKeys,
  isDeptTreeKey,
} from "../utils/orgUserTree";

const props = defineProps({
  departments: { type: Array, default: () => [] },
  /** 部门 UUID（0 或 1 个） */
  departmentIds: { type: Array, default: () => [] },
  maxHeight: { type: Number, default: 280 },
});

const emit = defineEmits(["update:departmentIds"]);

const treeData = computed(() => buildOrgDeptTree({ departments: props.departments }));

const hasDepts = computed(() => (props.departments || []).length > 0);

const displayCheckedKeys = computed(() => {
  const id = (props.departmentIds || [])[0];
  return id ? [`dept:${id}`] : [];
});

const expandedKeys = computed(() => defaultExpandedDeptKeys(props.departments));

/** 单选部门：仅保留本次勾选的节点，不级联上级/下级。 */
function onUpdateCheckedKeys(nextKeys, _option, meta) {
  if (meta?.node) {
    const key = String(meta.node.key);
    if (isDeptTreeKey(key)) {
      if (meta.action === "check") {
        emit("update:departmentIds", [key.slice(5)]);
      } else {
        emit("update:departmentIds", []);
      }
      return;
    }
  }

  const prev = new Set(displayCheckedKeys.value.map(String));
  const next = (nextKeys || []).map(String);
  const added = next.filter((k) => !prev.has(k) && isDeptTreeKey(k));
  if (added.length) {
    emit("update:departmentIds", [added[added.length - 1].slice(5)]);
    return;
  }
  const remaining = next.filter(isDeptTreeKey);
  emit("update:departmentIds", remaining.length ? [remaining[0].slice(5)] : []);
}
</script>

<template>
  <n-empty v-if="!hasDepts" description="暂无部门，请先在部门管理中创建" size="small" />
  <n-tree
    v-else
    block-line
    checkable
    :cascade="false"
    :data="treeData"
    :default-expanded-keys="expandedKeys"
    :checked-keys="displayCheckedKeys"
    :style="{ maxHeight: `${maxHeight}px`, overflow: 'auto' }"
    @update:checked-keys="onUpdateCheckedKeys"
  />
</template>
