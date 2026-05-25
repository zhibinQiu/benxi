<script setup>
import { NConfigProvider, NMessageProvider, NDialogProvider, zhCN, dateZhCN } from "naive-ui";

const platformTheme = {
  common: {
    primaryColor: "#0d9488",
    primaryColorHover: "#14b8a6",
    primaryColorPressed: "#0f766e",
    primaryColorSuppl: "#2dd4bf",
    bodyColor: "#f1f5f9",
    cardColor: "#ffffff",
    borderRadius: "10px",
    borderRadiusSmall: "8px",
    fontWeightStrong: "600",
  },
  Card: {
    borderRadius: "10px",
    paddingMedium: "14px 16px",
    titleFontSizeMedium: "14px",
  },
  Button: {
    borderRadiusMedium: "8px",
    borderRadiusSmall: "6px",
  },
};
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" :theme-overrides="platformTheme">
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
  background: #f1f5f9;
  color: #0f172a;
  -webkit-font-smoothing: antialiased;
}
</style>

<style src="./styles/platform.css"></style>
