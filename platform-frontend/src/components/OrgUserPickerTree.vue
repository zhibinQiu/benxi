<script setup>
import { computed } from "vue";
import { NEmpty, NTree } from "naive-ui";
import {
  applyUserPickerCheckChange,
  applyUserPickerKeysDiff,
  buildOrgUserTree,
  defaultExpandedDeptKeys,
  isUserTreeKey,
  treeCheckedKeysFromUserIds,
  treeIndeterminateKeysFromUserIds,
  UNASSIGNED_KEY,
  userPrimaryDeptId,
} from "../utils/orgUserTree";

const props = defineProps({
  departments: { type: Array, default: () => [] },
  users: { type: Array, default: () => [] },
  /** multi：分享勾选；single：单选用户 */
  mode: { type: String, default: "multi" },
  checkedKeys: { type: Array, default: () => [] },
  selectedKey: { type: String, default: null },
  maxHeight: { type: Number, default: 320 },
});

const emit = defineEmits(["update:checkedKeys", "update:selectedKey"]);

const treeData = computed(() =>
  buildOrgUserTree({
    departments: props.departments,
    users: props.users,
  })
);

const hasUsers = computed(() => (props.users || []).length > 0);

const displayCheckedKeys = computed(() =>
  treeCheckedKeysFromUserIds(props.checkedKeys, props.users, props.departments)
);

const indeterminateKeys = computed(() =>
  treeIndeterminateKeysFromUserIds(props.checkedKeys, props.users, props.departments)
);

function onUpdateCheckedKeys(nextKeys, _option, meta) {
  let userIds;
  if (meta?.node && meta?.action) {
    userIds = applyUserPickerCheckChange(
      props.checkedKeys,
      meta,
      props.users,
      props.departments
    );
  } else {
    userIds = applyUserPickerKeysDiff(
      displayCheckedKeys.value,
      nextKeys,
      props.checkedKeys,
      props.users,
      props.departments
    );
  }
  emit("update:checkedKeys", userIds);
}

function onUpdateSelectedKeys(keys) {
  const picked = (keys || []).find(isUserTreeKey);
  emit("update:selectedKey", picked || null);
}

const expandedKeys = computed(() => {
  const keys = defaultExpandedDeptKeys(props.departments);
  if ((props.users || []).some((u) => !userPrimaryDeptId(u))) {
    keys.push(UNASSIGNED_KEY);
  }
  return keys;
});
</script>

<template>
  <n-empty v-if="!hasUsers" description="暂无可选用户" size="small" />
  <n-tree
    v-else-if="mode === 'multi'"
    block-line
    checkable
    :cascade="false"
    selectable
    :data="treeData"
    :default-expanded-keys="expandedKeys"
    :checked-keys="displayCheckedKeys"
    :indeterminate-keys="indeterminateKeys"
    :style="{ maxHeight: `${maxHeight}px`, overflow: 'auto' }"
    @update:checked-keys="onUpdateCheckedKeys"
  />
  <n-tree
    v-else
    block-line
    selectable
    :data="treeData"
    :default-expanded-keys="expandedKeys"
    :selected-keys="selectedKey ? [selectedKey] : []"
    :style="{ maxHeight: `${maxHeight}px`, overflow: 'auto' }"
    @update:selected-keys="onUpdateSelectedKeys"
  />
</template>
