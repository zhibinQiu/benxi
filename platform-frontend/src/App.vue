<script setup>
import { computed, watch } from "vue";
import { useRoute } from "vue-router";
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  darkTheme,
  zhCN,
  enUS,
  dateZhCN,
  dateEnUS } from "naive-ui";
import { useAppPreferences } from "./composables/useAppPreferences";
import { useAppDisplayName } from "./composables/usePlatformBranding";
import { useI18n } from "./composables/useI18n";
import { createThemeOverrides } from "./utils/platformTheme";
import { PLATFORM_Z } from "./constants/zIndex.js";
import { shellRouteKey } from "./utils/routeTransition";
import { routeUsesVideoBackground } from "./utils/shellBackground";
import PageVideoBackground from "./components/PageVideoBackground.vue";
import AppSessionGuard from "./components/AppSessionGuard.vue";
const { isDark, colorScheme, customPrimaryColor } = useAppPreferences();
const { locale } = useI18n();
const appDisplayName = useAppDisplayName();
const naiveTheme = computed(() => (isDark.value ? darkTheme : null));
const themeOverrides = computed(() =>
  createThemeOverrides(isDark.value, colorScheme.value, customPrimaryColor.value)
);
const naiveLocale = computed(() => (locale.value === "en" ? enUS : zhCN));
const naiveDateLocale = computed(() => (locale.value === "en" ? dateEnUS : dateZhCN));

const route = useRoute();
const shellVideoBg = computed(() => routeUsesVideoBackground(route));

watch(
  [locale, appDisplayName],
  () => {
    document.title = appDisplayName.value;
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
    <n-message-provider :container-style="{ zIndex: PLATFORM_Z.message }">
      <n-dialog-provider>
        <AppSessionGuard />
        <div class="app-shell" :class="{ 'app-shell--video-bg': shellVideoBg }">
          <PageVideoBackground v-if="shellVideoBg" fixed />
          <router-view v-slot="{ Component, route }">
            <component :is="Component" :key="shellRouteKey(route)" />
          </router-view>
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style>
@import "./styles/tokens.css";
@import "./styles/color-schemes.css";

html,
body,
#app {
  margin: 0;
  min-height: 100vh;
  font-family: var(--platform-font);
  font-size: 15px;
  line-height: var(--platform-line-body);
  letter-spacing: var(--platform-tracking-normal);
  font-feature-settings: "kern" 1, "liga" 1, "calt" 1;
  background: var(--platform-bg);
  background-attachment: fixed;
  color: var(--platform-text);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

h1,
h2,
h3,
h4,
.header-title,
.n-card-header__main {
  font-family: var(--platform-font-display);
  letter-spacing: var(--platform-tracking-tight);
  line-height: var(--platform-line-heading);
}

.app-shell {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background: var(--platform-bg);
  background-attachment: fixed;
}

.app-shell--video-bg {
  background: transparent;
}

.app-shell > .page-video-bg {
  z-index: 0;
}

.app-shell > :not(.page-video-bg) {
  position: relative;
  z-index: 1;
}
</style>

<style src="./styles/platform.css"></style>
<style src="./styles/chat-message-media.css"></style>
<style src="./styles/platform-typography.css"></style>
<style src="./styles/liquid-glass.css"></style>
<style src="./styles/feature-local-nav.css"></style>
<style src="./styles/menu-liquid-glass.css"></style>
<style src="./styles/selectable-glass.css"></style>
<style src="./styles/subsystem-embed.css"></style>
<style src="./styles/motion.css"></style>
<style src="./styles/platform-spin.css"></style>
<style src="./styles/video-background.css"></style>
<style src="./styles/platform-ui-glass.css"></style>
<style src="./styles/solid-shell.css"></style>
<style src="./styles/openai-style.css"></style>
