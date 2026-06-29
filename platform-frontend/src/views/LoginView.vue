<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCheckbox,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSpace,
  NIcon,
} from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { useAppPreferences } from "../composables/useAppPreferences";
import { useI18n } from "../composables/useI18n";
import { useAppDisplayName } from "../composables/usePlatformBranding";
import { usePlatformUi } from "../composables/usePlatformUi";
import { loggingOut } from "../utils/sessionEpoch.js";
import { DEFAULT_HOME_ROUTE } from "../utils/postLoginRoute.js";
import { MoonOutline, SunnyOutline, LanguageOutline } from "@vicons/ionicons5";
import PlatformCopyright from "../components/PlatformCopyright.vue";
import PlatformBrandTitle from "../components/PlatformBrandTitle.vue";
import PlatformBrandIcon from "../components/PlatformBrandIcon.vue";
import LoginFeatureScroll from "../components/LoginFeatureScroll.vue";
import { cleanupBlockingUiArtifacts } from "../utils/blockingUiCleanup.js";
import { isBenignNavigationError } from "../api/requestScope.js";
import { LOGIN_FLY_CLONE_CLASS } from "../constants/loginFlyAnimation.js";
import { prefersReducedMotion } from "../utils/mediaQuery.js";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { login, register } = useAuth();
const { isDark, toggleTheme, toggleLocale } = useAppPreferences();
const { t, localeLabel } = useI18n();
const appDisplayName = useAppDisplayName();

onMounted(() => {
  loggingOut.value = false;
  nextTick(() => {
    pageRef.value?.scrollTo({ top: 0, left: 0 });
  });
});

const pageRef = ref(null);

const loading = ref(false);
const exiting = ref(false);
const account = ref("");
const password = ref("");
const loginPanelRef = ref(null);
const registerPanelRef = ref(null);
const loginModalOpen = ref(false);
const registerModalOpen = ref(false);
const regPhone = ref("");
const regEmail = ref("");
const regDisplayName = ref("");
const regPassword = ref("");
const regPassword2 = ref("");
const registering = ref(false);
const flyPanelRef = ref(null);
const termsAccepted = ref(true);

const FLY_DURATION_MS = 420;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function resolveHeaderAvatarPoint() {
  const headerH = 36;
  const fromRight = 8 + 52 + 56 + 72 + 14;
  return {
    x: Math.max(window.innerWidth * 0.55, window.innerWidth - fromRight),
    y: headerH / 2,
  };
}

function resolveCardElement() {
  return flyPanelRef.value ?? loginPanelRef.value ?? registerPanelRef.value ?? null;
}

async function flyLoginCardToHeader() {
  if (prefersReducedMotion()) {
    exiting.value = true;
    await wait(100);
    return;
  }

  const card = resolveCardElement();
  if (!card) {
    exiting.value = true;
    await wait(200);
    return;
  }

  const rect = card.getBoundingClientRect();
  const target = resolveHeaderAvatarPoint();
  const startCx = rect.left + rect.width / 2;
  const startCy = rect.top + rect.height / 2;
  const dx = target.x - startCx;
  const dy = target.y - startCy;
  const scale = 28 / Math.max(rect.width, 1);

  const clone = card.cloneNode(true);
  clone.classList.add(LOGIN_FLY_CLONE_CLASS);
  clone.setAttribute("aria-hidden", "true");
  Object.assign(clone.style, {
    position: "fixed",
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    margin: "0",
    zIndex: "10000",
    pointerEvents: "none",
    transformOrigin: "center center",
    transition: "none",
    overflow: "hidden",
  });
  document.body.appendChild(clone);
  card.style.visibility = "hidden";
  exiting.value = true;
  loginModalOpen.value = false;
  registerModalOpen.value = false;

  await nextTick();
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

  clone.style.transition = `transform ${FLY_DURATION_MS}ms cubic-bezier(0.4, 0, 0.2, 1), opacity ${FLY_DURATION_MS}ms ease, border-radius ${FLY_DURATION_MS}ms ease, box-shadow ${FLY_DURATION_MS}ms ease`;
  clone.style.transform = `translate(${dx}px, ${dy}px) scale(${scale})`;
  clone.style.opacity = "0.12";
  clone.style.borderRadius = "50%";
  clone.style.boxShadow = "0 0 0 1px var(--platform-accent-border)";

  await wait(FLY_DURATION_MS);
  clone.remove();
}

async function navigateAfterAuth() {
  loginModalOpen.value = false;
  registerModalOpen.value = false;
  await nextTick();
  await flyLoginCardToHeader();
  cleanupBlockingUiArtifacts();
  await router.replace(DEFAULT_HOME_ROUTE);
  await nextTick();
  cleanupBlockingUiArtifacts();
}

onBeforeUnmount(() => {
  cleanupBlockingUiArtifacts();
});

async function onSubmit() {
  if (!termsAccepted.value) {
    ui.warning(t("login.termsRequired"));
    return;
  }
  loading.value = true;
  flyPanelRef.value = loginPanelRef.value;
  try {
    await login(account.value.trim(), password.value);
    ui.success(t("login.loginSuccess"));
    await navigateAfterAuth();
  } catch (e) {
    ui.error(e.message || t("login.loginFailed"));
    exiting.value = false;
  } finally {
    loading.value = false;
  }
}

function isValidPhone(value) {
  const digits = String(value || "").replace(/\D/g, "");
  return /^1\d{10}$/.test(digits);
}

async function onRegister() {
  if (registering.value) return;
  const mobile = regPhone.value.trim();
  const name = regDisplayName.value.trim();
  if (!isValidPhone(mobile)) {
    ui.warning(t("login.invalidPhone"));
    return;
  }
  if (name.length < 2) {
    ui.warning(t("login.nameTooShort"));
    return;
  }
  if (regPassword.value.length < 6) {
    ui.warning(t("login.passwordTooShort"));
    return;
  }
  if (regPassword.value !== regPassword2.value) {
    ui.warning(t("login.passwordMismatch"));
    return;
  }
  const email = regEmail.value.trim();
  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    ui.warning(t("login.invalidEmail"));
    return;
  }
  registering.value = true;
  flyPanelRef.value = registerPanelRef.value;
  let authed = false;
  try {
    await register({
      phone: mobile,
      email,
      displayName: name,
      password: regPassword.value,
    });
    authed = true;
    ui.success(t("login.registerSuccess"));
  } catch (e) {
    ui.error(e.message || t("login.registerFailed"));
    exiting.value = false;
    return;
  } finally {
    registering.value = false;
  }
  if (!authed) return;
  try {
    await navigateAfterAuth();
  } catch (e) {
    if (!isBenignNavigationError(e)) {
      exiting.value = false;
    }
    try {
      await router.replace(DEFAULT_HOME_ROUTE);
    } catch (navErr) {
      if (!isBenignNavigationError(navErr)) {
        ui.error(navErr.message || t("login.registerFailed"));
        exiting.value = false;
      }
    }
  }
}

function openLoginModal() {
  if (exiting.value) return;
  registerModalOpen.value = false;
  loginModalOpen.value = true;
}

function openRegisterModal() {
  if (exiting.value) return;
  loginModalOpen.value = false;
  regPhone.value = "";
  regEmail.value = "";
  regDisplayName.value = "";
  regPassword.value = "";
  regPassword2.value = "";
  registerModalOpen.value = true;
}

function onLoginModalUpdate(show) {
  if (!show && (loading.value || exiting.value)) return;
  loginModalOpen.value = show;
}

function onRegisterModalUpdate(show) {
  if (!show && (registering.value || exiting.value)) return;
  registerModalOpen.value = show;
}

watch([loginModalOpen, registerModalOpen], ([loginOpen, registerOpen]) => {
  if (loginOpen || registerOpen) {
    nextTick(() => {
      const card = resolveCardElement();
      if (card) card.style.visibility = "";
    });
  }
});
</script>

<template>
  <div
    ref="pageRef"
    class="login-page"
    :class="{ 'login-page--exit': exiting, 'login-page--scroll': !exiting }"
  >
    <header class="login-header">
      <div class="login-header__inner">
        <a class="login-header__brand" href="#" @click.prevent>
          <PlatformBrandIcon :size="22" class="login-header__logo" />
          <span class="login-header__title platform-text-gradient">{{ t("login.brandName") }}</span>
        </a>

        <div class="login-header__actions">
          <button
            type="button"
            class="login-glass-link login-header__chip login-header__chip--icon"
            :aria-label="isDark ? t('userMenu.lightMode') : t('userMenu.darkMode')"
            @click="toggleTheme"
          >
            <n-icon :size="14" :component="isDark ? SunnyOutline : MoonOutline" />
          </button>
          <span class="login-header__vrule" aria-hidden="true" />
          <button
            type="button"
            class="login-glass-link login-header__chip login-header__chip--locale"
            @click="toggleLocale"
          >
            <n-icon :size="14" :component="LanguageOutline" />
            <span class="login-header__locale-label">{{ localeLabel }}</span>
          </button>
          <span class="login-header__vrule" aria-hidden="true" />
          <button
            type="button"
            class="login-glass-link login-header__chip login-header__chip--text"
            :disabled="exiting"
            @click="openLoginModal"
          >
            {{ t("login.submit") }}
          </button>
          <span class="login-header__vrule" aria-hidden="true" />
          <button
            type="button"
            class="login-glass-link login-header__chip login-header__chip--text login-header__chip--accent"
            :disabled="exiting"
            @click="openRegisterModal"
          >
            {{ t("login.register") }}
          </button>
        </div>
      </div>
    </header>

    <div class="login-page__bg" aria-hidden="true">
      <div class="login-page__orb login-page__orb--1" />
      <div class="login-page__orb login-page__orb--2" />
    </div>

    <main class="login-page__intro">
      <section class="login-showcase__hero login-snap-section">
        <h1 class="login-showcase__platform-title">
          <PlatformBrandTitle tag="span" strong :title="appDisplayName" />
        </h1>
        <p class="login-showcase__intro">{{ t("login.showcaseIntro") }}</p>
        <p class="login-showcase__scroll-hint">{{ t("login.showcaseScrollHint") }}</p>
      </section>
      <LoginFeatureScroll v-if="!exiting" class="login-showcase__scroll" />
    </main>

    <footer class="login-page__copyright">
      <PlatformCopyright compact />
    </footer>

    <n-modal
      :show="loginModalOpen"
      preset="card"
      class="login-auth-modal platform-glass-modal login-glass-panel login-auth-modal--login"
      :style="{ width: 'min(440px, calc(100vw - 32px))' }"
      :mask-closable="!loading && !exiting"
      transform-origin="center"
      @update:show="onLoginModalUpdate"
    >
      <template #header>
        <div class="login-auth-modal__header">
          <PlatformBrandIcon :size="40" class="login-auth-modal__logo" />
          <div class="login-auth-modal__header-text">
            <h2 class="login-auth-modal__title">{{ t("login.title") }}</h2>
            <p class="login-auth-modal__subtitle">{{ t("app.tagline") }}</p>
          </div>
        </div>
      </template>
      <div ref="loginPanelRef" class="login-auth-panel login-auth-panel--login">
        <n-form
          class="login-form login-form--compact login-form--placeholder-only"
          :show-label="false"
          @submit.prevent="onSubmit"
        >
          <n-form-item :show-label="false" :show-feedback="false">
            <n-input
              v-model:value="account"
              :placeholder="t('login.account')"
              autocomplete="username"
            />
          </n-form-item>
          <n-form-item :show-label="false" :show-feedback="false">
            <n-input
              v-model:value="password"
              type="password"
              show-password-on="click"
              :placeholder="t('login.password')"
              autocomplete="current-password"
              @keyup.enter="onSubmit"
            />
          </n-form-item>
          <n-space vertical :size="14" class="login-form__actions" style="width: 100%">
            <n-button
              type="primary"
              block
              class="login-glass-btn login-glass-btn--submit"
              :loading="loading"
              attr-type="submit"
            >
              {{ t("login.submit") }}
            </n-button>
            <label class="login-terms">
              <n-checkbox v-model:checked="termsAccepted" size="small" class="login-terms__checkbox" />
              <span class="login-terms__text">
                {{ t("login.termsPrefix") }}
                <button type="button" class="login-terms__link" @click.stop.prevent>
                  {{ t("login.termsLink") }}
                </button>
              </span>
            </label>
          </n-space>
        </n-form>
      </div>
    </n-modal>

    <n-modal
      :show="registerModalOpen"
      preset="card"
      class="login-auth-modal platform-glass-modal login-glass-panel login-auth-modal--register"
      :style="{ width: 'min(460px, calc(100vw - 32px))' }"
      :mask-closable="!registering && !exiting"
      transform-origin="center"
      @update:show="onRegisterModalUpdate"
    >
      <template #header>
        <div class="login-auth-modal__header">
          <PlatformBrandIcon :size="40" class="login-auth-modal__logo" />
          <div class="login-auth-modal__header-text">
            <h2 class="login-auth-modal__title">{{ t("login.registerTitle") }}</h2>
            <p class="login-auth-modal__subtitle">{{ t("login.registerHint") }}</p>
          </div>
        </div>
      </template>
      <div ref="registerPanelRef" class="login-auth-panel login-auth-panel--register">
        <n-form class="login-register-form login-form--compact" @submit.prevent="onRegister">
          <n-form-item :label="t('login.phone')">
            <n-input v-model:value="regPhone" :placeholder="t('login.phone')" maxlength="11" />
          </n-form-item>
          <n-form-item :label="t('login.email')" required>
            <n-input v-model:value="regEmail" :placeholder="t('login.email')" />
          </n-form-item>
          <n-form-item :label="t('login.displayName')">
            <n-input
              v-model:value="regDisplayName"
              :placeholder="t('login.displayNamePlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('login.password')">
            <n-input
              v-model:value="regPassword"
              type="password"
              show-password-on="click"
              :placeholder="t('login.password')"
            />
          </n-form-item>
          <n-form-item :label="t('login.passwordConfirm')">
            <n-input
              v-model:value="regPassword2"
              type="password"
              show-password-on="click"
              :placeholder="t('login.passwordConfirm')"
              @keyup.enter="onRegister"
            />
          </n-form-item>
          <n-space vertical :size="8" style="width: 100%">
            <n-button
              type="primary"
              block
              class="login-glass-btn login-glass-btn--submit"
              :loading="registering"
              attr-type="submit"
            >
              {{ t("login.registerSubmit") }}
            </n-button>
          </n-space>
        </n-form>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  height: 100dvh;
  max-height: 100dvh;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  -webkit-overflow-scrolling: touch;
  background: transparent;
}

.login-page--scroll {
  scroll-behavior: smooth;
  scroll-snap-type: y proximity;
  scroll-padding-top: 36px;
  scroll-padding-bottom: 48px;
}

.login-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 36px;
  box-sizing: border-box;
  border-bottom: 1px solid var(--platform-border, rgba(148, 163, 184, 0.18));
  background: rgba(255, 255, 255, 0.42);
  backdrop-filter: blur(14px) saturate(150%);
  -webkit-backdrop-filter: blur(14px) saturate(150%);
}

html[data-theme="dark"] .login-header {
  background: rgba(15, 15, 22, 0.72);
  border-bottom-color: var(--platform-accent-border-soft);
}

.login-header__inner {
  width: 100%;
  max-width: none;
  height: 100%;
  margin: 0;
  padding: 0 max(8px, env(safe-area-inset-right, 0px)) 0 max(16px, env(safe-area-inset-left, 0px));
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.login-header__brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  text-decoration: none;
  color: inherit;
}

.login-header__logo {
  flex-shrink: 0;
}

.login-header__title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: -0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.login-header__actions {
  display: flex;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
  height: 100%;
  max-height: 36px;
}

.login-header__chip {
  position: relative;
  z-index: 0;
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: 22px;
  max-height: 22px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
  color: var(--platform-text-secondary);
  cursor: pointer;
  transition:
    color 0.18s ease,
    border-color 0.2s var(--platform-ease-smooth),
    transform 0.18s var(--platform-ease-smooth);
}

.login-header__chip:hover:not(:disabled) {
  color: var(--platform-text);
}

.login-header__chip--icon {
  width: 22px;
  padding: 0;
}

.login-header__chip--locale {
  gap: 5px;
  padding: 0 8px;
}

.login-header__chip :deep(.n-icon) {
  color: inherit;
}

.login-header__chip--accent {
  color: var(--platform-accent);
}

.login-header__chip--accent:hover:not(:disabled) {
  color: color-mix(in srgb, var(--platform-accent) 82%, var(--platform-text));
}

.login-header__chip:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.login-header__vrule {
  flex-shrink: 0;
  width: 1px;
  height: 14px;
  margin: 0 3px;
  background: var(--platform-border, rgba(148, 163, 184, 0.28));
}

html[data-theme="dark"] .login-header__vrule {
  background: var(--platform-accent-border-soft);
}

.login-header__locale-label {
  display: none;
}

.login-page__copyright {
  position: relative;
  z-index: 4;
  padding: 24px 16px 32px;
  pointer-events: none;
}

.login-page--exit {
  pointer-events: none;
}

.login-page--exit .login-page__intro,
.login-page--exit .login-page__bg,
.login-page--exit .login-header,
.login-page--exit :deep(.login-feature-scroll) {
  opacity: 0;
  transition: opacity 0.28s ease;
}

.login-page__bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 0;
}

.login-page__orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(48px);
  opacity: 0.55;
  mix-blend-mode: soft-light;
}

.login-page__orb--1 {
  width: min(42vw, 420px);
  height: min(42vw, 420px);
  top: 8%;
  left: 6%;
  background: radial-gradient(circle, var(--platform-accent-soft-2) 0%, transparent 70%);
}

.login-page__orb--2 {
  width: min(36vw, 360px);
  height: min(36vw, 360px);
  bottom: 10%;
  right: 8%;
  background: radial-gradient(circle, color-mix(in srgb, var(--platform-accent) 28%, transparent) 0%, transparent 70%);
}

.login-page__intro {
  position: relative;
  z-index: 3;
  max-width: 960px;
  margin: 0 auto;
  padding: calc(36px + max(16px, 3vh)) 24px 48px;
  box-sizing: border-box;
}

.login-showcase__hero {
  scroll-snap-align: center;
  scroll-snap-stop: normal;
  min-height: calc(100dvh - 36px);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 0 24px;
  box-sizing: border-box;
}

.login-showcase__platform-title {
  margin: 0 0 14px;
  font-size: clamp(2rem, 5.8vw, 3.35rem);
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.045em;
}

.login-showcase__platform-title :deep(.platform-brand-title--strong) {
  font-weight: 700;
}

.login-showcase__headline {
  margin: 0 0 12px;
  font-size: clamp(1.15rem, 2.6vw, 1.5rem);
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: -0.02em;
  color: var(--platform-text);
}

.login-showcase__headline--vision {
  margin-bottom: 16px;
  font-size: clamp(1.65rem, 4vw, 2.35rem);
  font-weight: 800;
  letter-spacing: -0.04em;
  background: linear-gradient(135deg, var(--platform-text) 0%, var(--platform-accent) 92%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.login-showcase__intro {
  margin: 0 0 24px;
  max-width: 34em;
  font-size: clamp(12px, 1.25vw, 14px);
  font-weight: 400;
  line-height: 1.65;
  color: var(--platform-text-secondary);
}

.login-showcase__scroll-hint {
  margin: 0;
  font-size: 13px;
  letter-spacing: 0.04em;
  color: var(--platform-text-tertiary);
}

.login-showcase__scroll {
  width: 100vw;
  max-width: 100vw;
  margin-left: calc(50% - 50vw);
  box-sizing: border-box;
}

.login-auth-modal__header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 4px 0 2px;
}

.login-auth-modal__logo {
  flex-shrink: 0;
}

.login-auth-modal__header-text {
  min-width: 0;
}

.login-auth-modal__title {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.03em;
  color: var(--platform-text);
}

.login-auth-modal__subtitle {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--platform-text-secondary);
}

.login-auth-panel {
  width: 100%;
}

.login-auth-panel--register {
  overflow: visible;
}

.login-form--compact :deep(.n-form-item) {
  margin-bottom: 18px;
}

.login-auth-panel--login {
  padding: 8px 0 4px;
}

.login-form--placeholder-only :deep(.n-form-item) {
  margin-bottom: 16px;
}

.login-form--placeholder-only :deep(.n-form-item:last-of-type) {
  margin-bottom: 22px;
}

.login-form--placeholder-only :deep(.n-form-item-label) {
  display: none;
}

.login-form--placeholder-only :deep(.n-form-item-blank) {
  min-height: unset;
}

.login-form--compact :deep(.n-form-item-label) {
  padding-bottom: 4px;
  font-size: 13px;
}

.login-auth-panel :deep(.n-input) {
  --n-height: 40px;
  --n-font-size: 14px;
  --n-padding-left: 14px;
  --n-padding-right: 14px;
  --n-border-radius: 8px;
}

.login-auth-panel :deep(.n-input .n-input__input-el::placeholder),
.login-auth-panel :deep(.n-input .n-input__placeholder) {
  color: var(--platform-text-tertiary);
}

.login-glass-btn--submit {
  min-height: 40px !important;
  height: 40px;
  margin-top: 2px;
  font-size: 14px;
  font-weight: 600;
  --n-border-radius: 8px;
  --n-height: 40px;
}

.login-terms {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 4px;
  padding-top: 2px;
  cursor: pointer;
  user-select: none;
}

.login-terms__checkbox {
  flex-shrink: 0;
}

.login-terms__text {
  font-size: 13px;
  line-height: 1.55;
  text-align: center;
  color: var(--platform-text-tertiary);
}

.login-terms__link {
  appearance: none;
  border: none;
  padding: 0;
  margin: 0;
  background: none;
  font: inherit;
  font-size: inherit;
  line-height: inherit;
  color: var(--platform-accent);
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}

.login-terms__link:hover {
  color: color-mix(in srgb, var(--platform-accent) 82%, var(--platform-text));
}

.login-register-form {
  margin-top: 0;
}

.login-form {
  margin-top: 0;
}

@media (min-width: 640px) {
  .login-header__locale-label {
    display: inline;
  }

  .login-header__chip--locale {
    padding: 0 10px;
  }
}

@media (max-width: 639px) {
  .login-header__chip--locale {
    width: 22px;
    padding: 0;
  }

  .login-header__chip--text {
    padding: 0 6px;
  }
}
</style>

<style>
.login-card-fly-clone {
  box-sizing: border-box;
  background: var(--platform-bg-elevated) !important;
  will-change: transform, opacity;
}

.login-glass-panel.platform-glass-modal.n-modal .n-card {
  background: rgba(255, 255, 255, 0.38) !important;
  backdrop-filter: blur(18px) saturate(170%);
  -webkit-backdrop-filter: blur(18px) saturate(170%);
  border: 1px solid rgba(255, 255, 255, 0.48) !important;
  border-radius: 18px !important;
  box-shadow:
    0 20px 56px rgba(91, 120, 200, 0.18),
    0 8px 24px rgba(91, 120, 200, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.65) !important;
}

html[data-theme="dark"] .login-glass-panel.platform-glass-modal.n-modal .n-card {
  background: rgba(22, 22, 32, 0.52) !important;
  border-color: var(--platform-accent-border) !important;
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card-header {
  padding: 28px 32px 8px !important;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card-header .n-card-header__main {
  flex: 1;
  min-width: 0;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card__content {
  padding: 12px 32px 32px !important;
}

.login-auth-modal--login.platform-glass-modal.n-modal .n-card__content {
  padding-top: 16px !important;
}

.login-auth-modal--register.platform-glass-modal.n-modal .n-card__content {
  padding-top: 8px !important;
  max-height: min(72vh, 560px);
  overflow-y: auto;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card {
  overflow: visible;
}

.login-auth-modal .login-glass-btn--submit.n-button {
  min-height: 40px;
  height: 40px;
  font-size: 14px;
}
</style>
