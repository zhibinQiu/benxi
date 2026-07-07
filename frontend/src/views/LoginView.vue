<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
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
import SlideCaptcha from "../components/SlideCaptcha.vue";
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
const { login, register, trialLogin } = useAuth();
const { isDark, toggleTheme, toggleLocale } = useAppPreferences();
const { t, tm, localeLabel } = useI18n();
const appDisplayName = useAppDisplayName();

const socialLinks = computed(() => (tm("login.showcaseFooter.social") || []).filter(s => s.icon !== 'xiaohongshu'));

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

const captchaToken = ref("");
const captchaRegisterToken = ref("");

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

async function onTrial() {
  if (exiting.value) return;
  loading.value = true;
  try {
    await trialLogin();
    ui.success(t("login.trialSuccess"));
    await navigateAfterAuth();
  } catch (e) {
    ui.error(e.message || t("login.trialFailed"));
    exiting.value = false;
  } finally {
    loading.value = false;
  }
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
  if (!captchaToken.value) {
    ui.warning(t("login.captchaRequired"));
    return;
  }
  loading.value = true;
  flyPanelRef.value = loginPanelRef.value;
  try {
    await login(account.value.trim(), password.value, captchaToken.value);
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
  if (!captchaRegisterToken.value) {
    ui.warning(t("login.captchaRequired"));
    return;
  }
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
      captchaToken: captchaRegisterToken.value,
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
  captchaToken.value = "";
  loginModalOpen.value = true;
}

function openRegisterModal() {
  if (exiting.value) return;
  loginModalOpen.value = false;
  captchaRegisterToken.value = "";
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

function openTermsPage() {
  window.open("/terms", "_blank");
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
            class="login-glass-link login-header__chip login-header__chip--text login-header__chip--accent"
            :disabled="exiting || loading"
            @click="onTrial"
          >
            {{ t("login.getStarted") }}
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
      <div class="login-page__social-inline">
        <template v-for="(item, i) in socialLinks" :key="`sl-${i}`">
          <a :href="item.url" target="_blank" rel="noopener noreferrer" class="login-page__social-link" :title="item.label">
            <!-- Bilibili -->
            <svg v-if="item.icon === 'bilibili'" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M17.813 4.653h.854c1.51.054 2.769.578 3.773 1.574 1.004.995 1.524 2.249 1.56 3.76v7.36c-.036 1.51-.556 2.769-1.56 3.773s-2.262 1.524-3.773 1.56H5.333c-1.51-.036-2.769-.556-3.773-1.56S.036 18.858 0 17.347v-7.36c.036-1.511.556-2.765 1.56-3.76 1.004-.996 2.262-1.52 3.773-1.574h.774l-1.174-1.12a1.234 1.234 0 0 1-.373-.906c0-.356.124-.658.373-.907l.027-.027c.267-.24.573-.36.92-.36.347 0 .653.12.92.36L9.653 4.44c.284.284.426.596.426.933 0 .338-.142.654-.426.947l-.187.16h4.773l-.16-.16c-.267-.293-.4-.605-.4-.934 0-.328.133-.64.4-.933l2.733-2.734c.267-.24.573-.36.92-.36.347 0 .653.12.92.36l.027.027c.249.249.373.551.373.907 0 .355-.124.657-.373.906zM6.667 16.347c.712 0 1.32-.247 1.827-.74.506-.493.76-1.1.76-1.82 0-.712-.254-1.32-.76-1.826s-1.115-.76-1.827-.76c-.711 0-1.319.254-1.826.76-.508.507-.761 1.114-.761 1.826 0 .72.253 1.327.76 1.82.508.493 1.116.74 1.827.74z"/></svg>
            <!-- YouTube -->
            <svg v-else-if="item.icon === 'youtube'" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
            <!-- GitHub -->
            <svg v-else-if="item.icon === 'github'" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/></svg>
          <!-- 抖音 -->
          <svg v-else-if="item.icon === 'douyin'" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></svg>
        </a>
          </template>
        </div>
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
          <div class="login-form__captcha">
            <SlideCaptcha v-model="captchaToken" />
          </div>
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
                <button type="button" class="login-terms__link" @click.stop.prevent="openTermsPage">
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
          <div class="login-form__captcha">
            <SlideCaptcha v-model="captchaRegisterToken" />
          </div>
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

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
</style>
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
  font-family: "Inter", ui-sans-serif, -apple-system, BlinkMacSystemFont,
    "Segoe UI", "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
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
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-page__social-inline {
  position: absolute;
  left: 19px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  gap: 18px;
  pointer-events: auto;
}

.login-page__social-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #000;
  text-decoration: none;
  transition: color 0.15s ease;
}

.login-page__social-link:hover {
  color: var(--platform-accent);
}

html[data-theme="dark"] .login-page__social-link {
  color: #e0e0e8;
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
  background-size: 120%;
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
  font-size: clamp(1.8rem, 4.8vw, 2.8rem);
  font-weight: 600;
  line-height: 1.1;
  letter-spacing: -0.04em;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

.login-showcase__platform-title :deep(.platform-brand-title--strong) {
  font-weight: 600;
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
  font-size: clamp(14px, 1.15vw, 16px);
  font-weight: 400;
  line-height: 1.6;
  color: #000;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
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
  margin-bottom: 14px;
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

.login-form__captcha {
  margin-bottom: 14px;
  width: 100%;
  display: flex;
  justify-content: center;
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

@media (max-width: 480px) {
  .login-header__title {
    display: none;
  }

  .login-header__brand {
    gap: 0;
  }

  .login-showcase__hero {
    padding: 54px 14px 19px;
  }

  .login-showcase__intro {
    margin-bottom: 22px;
    max-width: 100%;
  }

  .login-page__copyright {
    flex-direction: column;
    gap: 14px;
    padding: 19px 14px 24px;
    align-items: center;
  }

  .login-page__social-inline {
    position: static;
    transform: none;
    justify-content: center;
    gap: 14px;
  }
}

@media (max-width: 400px) {
  .login-showcase__hero {
    min-height: auto;
    padding-top: 60px;
    padding-bottom: 24px;
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
