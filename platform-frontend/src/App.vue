<script setup>
import { computed, ref, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
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
import { usePlatformBranding } from "./composables/usePlatformBranding";
import { useLiquidGlassMotion } from "./composables/useLiquidGlassMotion";
import { useI18n } from "./composables/useI18n";
import { createThemeOverrides } from "./utils/platformTheme";
import { shouldSkipAppRouteMotion, shellRouteKey, consumeSkipAfterLoginMotion } from "./utils/routeTransition";
import { routeUsesVideoBackground } from "./utils/shellBackground";
import { onSessionReplaced } from "./utils/sessionGuard";
import PageVideoBackground from "./components/PageVideoBackground.vue";
import AppSessionGuard from "./components/AppSessionGuard.vue";
const { isDark } = useAppPreferences();
const { locale, t } = useI18n();
const { platformAppTitle } = usePlatformBranding();
useLiquidGlassMotion();

const naiveTheme = computed(() => (isDark.value ? darkTheme : null));
const themeOverrides = computed(() => createThemeOverrides(isDark.value));
const naiveLocale = computed(() => (locale.value === "en" ? enUS : zhCN));
const naiveDateLocale = computed(() => (locale.value === "en" ? dateEnUS : dateZhCN));

const router = useRouter();
const route = useRoute();
const appRouteTransition = ref("app-route");
const shellVideoBg = computed(() => routeUsesVideoBackground(route));

router.beforeEach((to, from) => {
  appRouteTransition.value = shouldSkipAppRouteMotion(from.name)
    ? "app-route-instant"
    : "app-route";
});

router.afterEach((to, from) => {
  if (from.name === "login" && to.name !== "login") {
    consumeSkipAfterLoginMotion();
  }
});

watch(
  [locale, platformAppTitle],
  () => {
    document.title = platformAppTitle.value || t("app.name");
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
        <AppSessionGuard />
        <div class="app-shell" :class="{ 'app-shell--video-bg': shellVideoBg }">
          <PageVideoBackground v-if="shellVideoBg" fixed />
          <div v-if="!shellVideoBg" class="app-ambient" aria-hidden="true">
            <span class="app-ambient__orb app-ambient__orb--1" />
            <span class="app-ambient__orb app-ambient__orb--2" />
            <span class="app-ambient__orb app-ambient__orb--3" />
          </div>
          <router-view v-slot="{ Component, route }">
            <Transition
              v-if="appRouteTransition !== 'app-route-instant'"
              :name="appRouteTransition"
            >
              <component :is="Component" :key="shellRouteKey(route)" />
            </Transition>
            <component
              v-else
              :is="Component"
              :key="shellRouteKey(route)"
            />
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

.app-ambient {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.app-ambient__orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(72px);
  opacity: 0.75;
  animation: liquid-orb-drift 36s var(--platform-ease-fluid) infinite;
}

.app-ambient__orb--1 {
  width: min(46vw, 480px);
  height: min(46vw, 480px);
  top: -8%;
  left: -5%;
  background: radial-gradient(circle, var(--platform-accent-soft-2) 0%, transparent 68%);
  animation-duration: 32s;
}

.app-ambient__orb--2 {
  width: min(38vw, 400px);
  height: min(38vw, 400px);
  bottom: -6%;
  right: 4%;
  background: radial-gradient(circle, var(--platform-accent-soft) 0%, transparent 68%);
  animation-duration: 26s;
  animation-delay: -8s;
}

.app-ambient__orb--3 {
  width: min(30vw, 320px);
  height: min(30vw, 320px);
  top: 36%;
  left: 40%;
  background: radial-gradient(circle, var(--liquid-flow-c) 0%, transparent 70%);
  animation: liquid-orb-drift 32s var(--platform-ease-fluid) infinite;
  animation-delay: -12s;
}

.app-shell > .page-video-bg {
  z-index: 0;
}

.app-shell > .app-ambient {
  z-index: 0;
}

.app-shell--video-bg > .app-ambient {
  z-index: 1;
}

.app-shell > :not(.app-ambient):not(.page-video-bg) {
  position: relative;
  z-index: 2;
}
</style>

<style src="./styles/platform.css"></style>
<style src="./styles/platform-typography.css"></style>
<style src="./styles/liquid-glass.css"></style>
<style src="./styles/feature-local-nav.css"></style>
<style src="./styles/menu-liquid-glass.css"></style>
<style src="./styles/subsystem-embed.css"></style>
<style src="./styles/motion.css"></style>
<style src="./styles/video-background.css"></style>
<style src="./styles/platform-ui-glass.css"></style>
