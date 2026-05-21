<script setup>
import { NConfigProvider, NMessageProvider, NDialogProvider, zhCN, dateZhCN } from "naive-ui";
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style>
html,
body,
#app {
  margin: 0;
  min-height: 100vh;
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  background: #f5f6f8;
}
</style>
