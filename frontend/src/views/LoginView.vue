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
import { loginShowcaseScrolling } from "../utils/loginScrollState.js";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const BASE = import.meta.env.BASE_URL.replace(/\/+$/, "");
const heroBg = `${BASE}/images/bg.jpg`;
const { login, register } = useAuth();
const { isDark, toggleTheme, toggleLocale } = useAppPreferences();
const { t, localeLabel } = useI18n();
const appDisplayName = useAppDisplayName();

const pageRef = ref(null);

let scrollEndTimer = null;

function onPageScroll() {
  loginShowcaseScrolling.value = true;
  const el = pageRef.value;
  if (el) {
    el.classList.toggle("login-page--scrolling", el.scrollTop > 80);
  }
  clearTimeout(scrollEndTimer);
  scrollEndTimer = setTimeout(() => {
    loginShowcaseScrolling.value = false;
  }, 140);
}

onMounted(() => {
  loggingOut.value = false;
  nextTick(() => {
    pageRef.value?.scrollTo({ top: 0, left: 0 });
    pageRef.value?.addEventListener("scroll", onPageScroll, { passive: true });
  });
});

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
  await router.replace(DEFAULT_HOME_ROUTE);
  cleanupBlockingUiArtifacts();
}

onBeforeUnmount(() => {
  pageRef.value?.removeEventListener("scroll", onPageScroll);
  clearTimeout(scrollEndTimer);
  loginShowcaseScrolling.value = false;
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
    :class="{
      'login-page--exit': exiting,
      'login-page--scrolling': loginShowcaseScrolling,
    }"
  >
    <header class="login-header">
      <div class="login-header__inner">
        <a class="login-header__brand" href="#" @click.prevent>
          <PlatformBrandIcon :size="26" class="login-header__logo" />
          <span class="login-header__title platform-text-gradient">{{ t("login.brandName") }}</span>
        </a>

        <div class="login-header__actions">
          <button
            type="button"
            class="login-glass-link login-header__chip login-header__chip--icon"
            :aria-label="isDark ? t('userMenu.lightMode') : t('userMenu.darkMode')"
            @click="toggleTheme"
          >
            <n-icon :size="17" :component="isDark ? SunnyOutline : MoonOutline" />
          </button>
          <span class="login-header__vrule" aria-hidden="true" />
          <button
            type="button"
            class="login-glass-link login-header__chip login-header__chip--locale"
            @click="toggleLocale"
          >
            <n-icon :size="17" :component="LanguageOutline" />
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

    <main class="login-page__main">
      <section class="login-showcase__hero" :style="{ backgroundImage: `url(${heroBg})` }">
        <div class="login-showcase__hero-content">
          <h1 class="login-showcase__platform-title">
            <PlatformBrandTitle tag="span" strong :title="appDisplayName" />
          </h1>
          <p class="login-showcase__intro">{{ t("login.showcaseIntro") }}</p>
          <div class="login-showcase__ctas">
            <button
              type="button"
              class="login-showcase__cta login-showcase__cta--primary"
              :disabled="exiting"
              @click="openLoginModal"
            >
              {{ t("login.submit") }}
            </button>
            <button
              type="button"
              class="login-showcase__cta login-showcase__cta--secondary"
              :disabled="exiting"
              @click="openRegisterModal"
            >
              {{ t("login.register") }}
            </button>
          </div>
        </div>
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
      :style="{ width: 'min(528px, calc(100vw - 38px))' }"
      :mask-closable="!loading && !exiting"
      transform-origin="center"
      @update:show="onLoginModalUpdate"
    >
      <template #header>
        <div class="login-auth-modal__header">
          <PlatformBrandIcon :size="48" class="login-auth-modal__logo" />
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
          <n-space vertical :size="17" class="login-form__actions" style="width: 100%">
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
      :style="{ width: 'min(552px, calc(100vw - 38px))' }"
      :mask-closable="!registering && !exiting"
      transform-origin="center"
      @update:show="onRegisterModalUpdate"
    >
      <template #header>
        <div class="login-auth-modal__header">
          <PlatformBrandIcon :size="48" class="login-auth-modal__logo" />
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
          <n-space vertical :size="10" style="width: 100%">
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

.login-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 43px;
  box-sizing: border-box;
  border-bottom: none;
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

html[data-theme="dark"] .login-header {
  background: transparent;
  border-bottom: none;
}

.login-header__inner {
  width: 100%;
  max-width: none;
  height: 100%;
  margin: 0;
  padding: 0 max(10px, env(safe-area-inset-right, 0px)) 0 max(19px, env(safe-area-inset-left, 0px));
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 19px;
}

.login-header__brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  text-decoration: none;
  color: inherit;
}

.login-header__logo {
  flex-shrink: 0;
}

.login-header__title {
  font-size: 14px;
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
  max-height: 43px;
}

.login-header__chip {
  position: relative;
  z-index: 0;
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: 26px;
  max-height: 26px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  font-size: 14px;
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
  width: 26px;
  padding: 0;
}

.login-header__chip--locale {
  gap: 6px;
  padding: 0 10px;
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
  height: 17px;
  margin: 0 4px;
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
  padding: 29px 19px 38px;
  pointer-events: none;
}

.login-page--exit {
  pointer-events: none;
}

.login-page--exit .login-page__intro,
.login-page--exit .login-header,
.login-page--exit :deep(.login-feature-scroll) {
  opacity: 0;
  transition: opacity 0.28s ease;
}

.login-page__main {
  position: relative;
  z-index: 3;
}

.login-page__main .login-showcase__hero {
  width: 100%;
}

.login-page--scrolling .login-header {
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(17px) saturate(150%);
  -webkit-backdrop-filter: blur(17px) saturate(150%);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

html[data-theme="dark"] .login-page--scrolling .login-header {
  background: rgba(15, 15, 22, 0.82);
  border-bottom-color: var(--platform-accent-border-soft);
}

.login-showcase__hero {
  min-height: calc(100dvh - 43px);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 43px 29px 29px;
  box-sizing: border-box;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  position: relative;
}

.login-showcase__hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0.72) 0%,
    rgba(255, 255, 255, 0.72) 70%,
    rgba(255, 255, 255, 1) 100%
  );
  z-index: 0;
}

html[data-theme="dark"] .login-showcase__hero::before {
  background: linear-gradient(
    to bottom,
    rgba(15, 15, 22, 0.78) 0%,
    rgba(15, 15, 22, 0.78) 70%,
    rgba(15, 15, 22, 1) 100%
  );
}

.login-showcase__hero-content {
  position: relative;
  z-index: 1;
  max-width: 1152px;
  margin: 0 auto;
  width: 100%;
}

.login-showcase__platform-title {
  margin: 0 0 17px;
  font-size: clamp(2rem, 5.8vw, 3.35rem);
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.045em;
}

.login-showcase__platform-title :deep(.platform-brand-title--strong) {
  font-weight: 700;
}

.login-showcase__headline {
  margin: 0 0 14px;
  font-size: clamp(1.15rem, 2.6vw, 1.5rem);
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: -0.02em;
  color: var(--platform-text);
}

.login-showcase__headline--vision {
  margin-bottom: 19px;
  font-size: clamp(1.65rem, 4vw, 2.35rem);
  font-weight: 800;
  letter-spacing: -0.04em;
  background: linear-gradient(135deg, var(--platform-text) 0%, var(--platform-accent) 92%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.login-showcase__intro {
  margin: 0 0 29px;
  max-width: 34em;
  font-size: clamp(14px, 1.25vw, 17px);
  font-weight: 400;
  line-height: 1.65;
  color: var(--platform-text-secondary);
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
  gap: 19px;
  padding: 5px 0 2px;
}

.login-auth-modal__logo {
  flex-shrink: 0;
}

.login-auth-modal__header-text {
  min-width: 0;
}

.login-auth-modal__title {
  margin: 0 0 7px;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.03em;
  color: var(--platform-text);
}

.login-auth-modal__subtitle {
  margin: 0;
  font-size: 16px;
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
  margin-bottom: 22px;
}

.login-auth-panel--login {
  padding: 10px 0 5px;
}

.login-form--placeholder-only :deep(.n-form-item) {
  margin-bottom: 19px;
}

.login-form--placeholder-only :deep(.n-form-item:last-of-type) {
  margin-bottom: 26px;
}

.login-form--placeholder-only :deep(.n-form-item-label) {
  display: none;
}

.login-form--placeholder-only :deep(.n-form-item-blank) {
  min-height: unset;
}

.login-form--compact :deep(.n-form-item-label) {
  padding-bottom: 5px;
  font-size: 16px;
}

.login-auth-panel :deep(.n-input) {
  --n-height: 48px;
  --n-font-size: 17px;
  --n-padding-left: 17px;
  --n-padding-right: 17px;
  --n-border-radius: 10px;
}

.login-auth-panel :deep(.n-input .n-input__input-el::placeholder),
.login-auth-panel :deep(.n-input .n-input__placeholder) {
  color: var(--platform-text-tertiary);
}

.login-glass-btn--submit {
  min-height: 48px !important;
  height: 48px;
  margin-top: 2px;
  font-size: 17px;
  font-weight: 600;
  --n-border-radius: 10px;
  --n-height: 48px;
}

.login-terms {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 5px;
  padding-top: 2px;
  cursor: pointer;
  user-select: none;
}

.login-terms__checkbox {
  flex-shrink: 0;
}

.login-terms__text {
  font-size: 16px;
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

.login-showcase__ctas {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 29px;
}

.login-showcase__cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 46px;
  padding: 0 26px;
  border: none;
  border-radius: 1199px;
  font-size: 16px;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition:
    transform 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.2s ease,
    background 0.2s ease;
  text-decoration: none;
}

.login-showcase__cta--primary {
  background: var(--platform-accent);
  color: #fff;
  box-shadow:
    0 8px 22px color-mix(in srgb, var(--platform-accent) 30%, transparent);
}

.login-showcase__cta--primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow:
    0 12px 28px color-mix(in srgb, var(--platform-accent) 38%, transparent);
}

.login-showcase__cta--secondary {
  background: rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(14px) saturate(160%);
  -webkit-backdrop-filter: blur(14px) saturate(160%);
  border: 1px solid rgba(255, 255, 255, 0.32);
  color: var(--platform-text);
  box-shadow:
    0 5px 17px color-mix(in srgb, var(--platform-accent) 6%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
}

html[data-theme="dark"] .login-showcase__cta--secondary {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--platform-accent-border-soft);
  box-shadow:
    0 5px 17px rgba(0, 0, 0, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.login-showcase__cta--secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.22);
  transform: translateY(-1px);
}

html[data-theme="dark"] .login-showcase__cta--secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.09);
}

.login-showcase__cta:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (max-width: 480px) {
  .login-showcase__ctas {
    flex-direction: column;
    gap: 10px;
  }
  .login-showcase__cta {
    width: 100%;
  }
}

@media (min-width: 640px) {
  .login-header__locale-label {
    display: inline;
  }

  .login-header__chip--locale {
    padding: 0 12px;
  }
}

@media (max-width: 639px) {
  .login-header__chip--locale {
    width: 26px;
    padding: 0;
  }

  .login-header__chip--text {
    padding: 0 7px;
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
  backdrop-filter: blur(22px) saturate(170%);
  -webkit-backdrop-filter: blur(22px) saturate(170%);
  border: 1px solid rgba(255, 255, 255, 0.48) !important;
  border-radius: 22px !important;
  box-shadow:
    0 24px 67px color-mix(in srgb, var(--platform-accent) 18%, transparent),
    0 10px 29px color-mix(in srgb, var(--platform-accent) 8%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.65) !important;
}

html[data-theme="dark"] .login-glass-panel.platform-glass-modal.n-modal .n-card {
  background: rgba(22, 22, 32, 0.52) !important;
  border-color: var(--platform-accent-border) !important;
  box-shadow:
    0 14px 48px rgba(0, 0, 0, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card-header {
  padding: 34px 38px 10px !important;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card-header .n-card-header__main {
  flex: 1;
  min-width: 0;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card__content {
  padding: 14px 38px 38px !important;
}

.login-auth-modal--login.platform-glass-modal.n-modal .n-card__content {
  padding-top: 19px !important;
}

.login-auth-modal--register.platform-glass-modal.n-modal .n-card__content {
  padding-top: 10px !important;
  max-height: min(72vh, 672px);
  overflow-y: auto;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card {
  overflow: visible;
}

.login-auth-modal .login-glass-btn--submit.n-button {
  min-height: 48px;
  height: 48px;
  font-size: 17px;
}
</style>
