<script setup>
import { ref } from "vue";
import { useI18n } from "../../composables/useI18n";
import UsersView from "./UsersView.vue";
import DepartmentsView from "./DepartmentsView.vue";

const { t } = useI18n();
const activeTab = ref("users");
</script>

<template>
  <div class="org-management">
    <n-tabs v-model:value="activeTab" type="line" animated>
      <n-tab-pane name="users" :tab="t('routes.admin-users')">
        <UsersView />
      </n-tab-pane>
      <n-tab-pane name="departments" :tab="t('routes.admin-departments')">
        <DepartmentsView />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<style scoped>
.org-management {
  padding: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  height: 100%;
  box-sizing: border-box;
}
.org-management :deep(.n-tabs) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.org-management :deep(.n-tabs .n-tabs-tab-panes) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.org-management :deep(.n-tab-pane) {
  height: auto;
  min-height: 100%;
}
</style>
