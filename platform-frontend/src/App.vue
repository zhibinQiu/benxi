<script setup>
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  darkTheme,
  zhCN,
  enUS,
  dateZhCN,
  dateEnUS,
} from "naive-ui";
import { useAppPreferences } from "./composables/useAppPreferences";
import { useI18n } from "./composables/useI18n";
import { createThemeOverrides } from "./utils/platformTheme";
import { shouldSkipAppRouteMotion } from "./utils/routeTransition";

const { isDark } = useAppPreferences();
const { locale, t } = useI18n();

const naiveTheme = computed(() => (isDark.value ? darkTheme : null));
const themeOverrides = computed(() => createThemeOverrides(isDark.value));
const naiveLocale = computed(() => (locale.value === "en" ? enUS : zhCN));
const naiveDateLocale = computed(() => (locale.value === "en" ? dateEnUS : dateZhCN));

const router = useRouter();
const appRouteTransition = ref("app-route");

router.beforeEach((to, from) => {
  appRouteTransition.value = shouldSkipAppRouteMotion(from.name)
    ? "app-route-instant"
    : "app-route";
});

watch(
  locale,
  () => {
    document.title = t("app.name");
  },
  { immediate: true }
);
</script>

<template>
  <n-config-provider
    :theme="naiveTheme"
    :locale="naiveLocale"
    :date-locale="naiveDateLocale"
    :theme-overrides="themeOverrides"
  >
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
@import "./styles/tokens.css";

html,
body,
#app {
  margin: 0;
  min-height: 100vh;
  font-family: var(--platform-font);
  background: var(--platform-bg);
  color: var(--platform-text);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
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
