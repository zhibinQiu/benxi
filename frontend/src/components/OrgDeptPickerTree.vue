<script setup>
import { computed, ref } from "vue";
import { NEmpty, NTree } from "naive-ui";
import {
  buildOrgDeptAssignTree,
  buildOrgDeptTree,
  isDeptTreeKey,
  isMembersGroupKey,
  isUserTreeKey } from "../utils/orgUserTree";

const props = defineProps({
  departments: { type: Array, default: () => [] },
  /** 传入时在树下展示「部门成员」，仅供辨认，不可作为部门勾选 */
  users: { type: Array, default: () => [] },
  /** 部门 UUID（0 或 1 个） */
  departmentIds: { type: Array, default: () => [] },
  maxHeight: { type: Number, default: 336 }});

const emit = defineEmits(["update:departmentIds"]);

const expandedKeys = ref([]);

const showMembers = computed(() => (props.users || []).length > 0);

const treeData = computed(() =>
  showMembers.value
    ? buildOrgDeptAssignTree({
        departments: props.departments,
        users: props.users,
      })
    : buildOrgDeptTree({ departments: props.departments })
);

const hasDepts = computed(() => (props.departments || []).length > 0);

const displayCheckedKeys = computed(() => {
  const id = (props.departmentIds || [])[0];
  return id ? [`dept:${id}`] : [];
});

function isSelectableDeptKey(key) {
  return isDeptTreeKey(key);
}

/** 单选部门：仅真实部门节点可勾选，成员与用户节点一律忽略。 */
function onUpdateCheckedKeys(nextKeys, _option, meta) {
  if (meta?.node) {
    const key = String(meta.node.key);
    if (isUserTreeKey(key) || isMembersGroupKey(key)) {
      return;
    }
    if (isSelectableDeptKey(key)) {
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
  const added = next.filter(
    (k) => !prev.has(k) && isSelectableDeptKey(k)
  );
  if (added.length) {
    emit("update:departmentIds", [added[added.length - 1].slice(5)]);
    return;
  }
  const remaining = next.filter(isSelectableDeptKey);
  emit("update:departmentIds", remaining.length ? [remaining[0].slice(5)] : []);
}

function nodeProps({ option }) {
  if (isUserTreeKey(option.key)) {
    return { class: "org-tree-node--user" };
  }
  if (isMembersGroupKey(option.key)) {
    return { class: "org-tree-node--members-group" };
  }
  return { class: "org-tree-node--dept" };
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
    :checked-keys="displayCheckedKeys"
    :expanded-keys="expandedKeys"
    :node-props="nodeProps"
    :style="{ maxHeight: `${maxHeight}px`, overflow: 'auto' }"
    @update:checked-keys="onUpdateCheckedKeys"
    @update:expanded-keys="expandedKeys = $event"
  />
</template>

<style scoped>
:deep(.org-tree-node--user .n-tree-node-content__text) {
  color: var(--n-text-color-3);
  font-size: 16px;
}

:deep(.org-tree-node--members-group .n-tree-node-content__text) {
  color: var(--n-text-color-3);
  font-size: 14px;
  font-style: italic;
}
</style>
