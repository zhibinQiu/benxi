<script setup>
import { useRouter } from "vue-router";
import { NButton, NIcon } from "naive-ui";
import { ArrowBackOutline } from "@vicons/ionicons5";

const router = useRouter();

function goBack() {
  router.push({ name: "system-functions" });
}
</script>

<template>
  <header class="feature-toolbar">
    <n-button quaternary class="back-btn" @click="goBack">
      <template #icon>
        <n-icon :component="ArrowBackOutline" />
      </template>
      返回
    </n-button>
    <div v-if="$slots.default" class="feature-toolbar-extra">
      <slot />
    </div>
  </header>
</template>

<style scoped>
.feature-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  padding: 4px 0 8px;
  border-bottom: 1px solid var(--platform-border, var(--n-border-color));
}
.back-btn {
  flex-shrink: 0;
}
.feature-toolbar-extra {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}
</style>
