<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { NConfigProvider, NMessageProvider, NDialogProvider, zhCN, dateZhCN } from "naive-ui";
import { shouldSkipAppRouteMotion } from "./utils/routeTransition";

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

const router = useRouter();
const appRouteTransition = ref("app-route");

router.beforeEach((to, from) => {
  appRouteTransition.value = shouldSkipAppRouteMotion(from.name)
    ? "app-route-instant"
    : "app-route";
});
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" :theme-overrides="platformTheme">
    <n-message-provider>
      <n-dialog-provider>
        <div class="app-shell">
          <router-view v-slot="{ Component, route }">
            <Transition :name="appRouteTransition">
              <component :is="Component" :key="route.fullPath" />
            </Transition>
          </router-view>
        </div>
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

.app-shell {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
}
</style>

<style src="./styles/platform.css"></style>
<style src="./styles/subsystem-embed.css"></style>
<style src="./styles/motion.css"></style>
