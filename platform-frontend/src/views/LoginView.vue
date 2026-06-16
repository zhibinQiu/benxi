<script setup>
import { nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCheckbox,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSpace,
  NText,
} from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { useAppPreferences } from "../composables/useAppPreferences";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { loggingOut } from "../utils/sessionEpoch.js";
import { publicAsset } from "../utils/appBase";
import { MoonOutline, SunnyOutline, LanguageOutline } from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import PlatformCopyright from "../components/PlatformCopyright.vue";
import PlatformBrandTitle from "../components/PlatformBrandTitle.vue";
import LoginFeatureScroll from "../components/LoginFeatureScroll.vue";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { login, register } = useAuth();
const { isDark, toggleTheme, toggleLocale } = useAppPreferences();
const { t, localeLabel } = useI18n();

onMounted(() => {
  loggingOut.value = false;
});

const loading = ref(false);
const exiting = ref(false);
const account = ref("admin");
const password = ref("admin123");
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
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
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
  clone.classList.add("login-card-fly-clone");
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
  await flyLoginCardToHeader();
  const redirect = route.query.redirect || { name: "ai-home" };
  await router.push(redirect);
}

async function onSubmit() {
  if (!termsAccepted.value) {
    ui.warning(t("login.termsRequired"));
    return;
  }
  loading.value = true;
  flyPanelRef.value = loginPanelRef.value;
  try {
    await login(account.value.trim(), password.value);
    ui.success("登录成功");
    await navigateAfterAuth();
  } catch (e) {
    ui.error(e.message || "登录失败");
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
  const mobile = regPhone.value.trim();
  const name = regDisplayName.value.trim();
  if (!isValidPhone(mobile)) {
    ui.warning("请输入有效的 11 位手机号");
    return;
  }
  if (name.length < 2) {
    ui.warning("姓名至少 2 个字符");
    return;
  }
  if (regPassword.value.length < 6) {
    ui.warning("密码至少 6 个字符");
    return;
  }
  if (regPassword.value !== regPassword2.value) {
    ui.warning("两次输入的密码不一致");
    return;
  }
  const email = regEmail.value.trim();
  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    ui.warning("请输入有效的邮箱");
    return;
  }
  registering.value = true;
  flyPanelRef.value = registerPanelRef.value;
  try {
    await register({
      phone: mobile,
      email,
      displayName: name,
      password: regPassword.value,
    });
    ui.success("注册成功，已自动登录");
    await navigateAfterAuth();
  } catch (e) {
    ui.error(e.message || "注册失败");
  } finally {
    registering.value = false;
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
  <div class="login-page" :class="{ 'login-page--exit': exiting, 'login-page--scroll': !exiting }">
    <header class="login-header">
      <div class="login-header__inner">
        <a class="login-header__brand" href="#" @click.prevent>
          <img :src="publicAsset('logo.svg')" :alt="t('login.brandName')" class="login-header__logo" />
          <span class="login-header__title">{{ t("login.brandName") }}</span>
        </a>

        <div class="login-header__actions">
          <button
            type="button"
            class="login-glass-link login-header__chip login-header__chip--icon"
            :aria-label="isDark ? t('userMenu.lightMode') : t('userMenu.darkMode')"
            @click="toggleTheme"
          >
            <n-icon :size="16" :component="isDark ? SunnyOutline : MoonOutline" />
          </button>
          <span class="login-header__vrule" aria-hidden="true" />
          <button
            type="button"
            class="login-glass-link login-header__chip login-header__chip--locale"
            @click="toggleLocale"
          >
            <n-icon :size="15" :component="LanguageOutline" />
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
      <section class="login-showcase__hero">
        <h1 class="login-showcase__platform-title">
          <PlatformBrandTitle tag="span" strong :title="t('login.showcaseBadge')" />
        </h1>
        <p class="login-showcase__headline">{{ t("login.showcaseHeadline") }}</p>
        <p class="login-showcase__subheadline">{{ t("login.showcaseSubheadline") }}</p>
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
      :title="t('login.title')"
      class="login-auth-modal platform-glass-modal login-glass-panel"
      :style="{ width: 'min(380px, calc(100vw - 32px))' }"
      :mask-closable="!loading && !exiting"
      transform-origin="center"
      @update:show="onLoginModalUpdate"
    >
      <div ref="loginPanelRef" class="login-auth-panel">
        <n-form class="login-form login-form--compact" size="small" @submit.prevent="onSubmit">
          <n-form-item :label="t('login.account')">
            <n-input v-model:value="account" :placeholder="t('login.account')" />
          </n-form-item>
          <n-form-item :label="t('login.password')">
            <n-input
              v-model:value="password"
              type="password"
              show-password-on="click"
              :placeholder="t('login.password')"
              @keyup.enter="onSubmit"
            />
          </n-form-item>
          <n-space vertical :size="8" style="width: 100%">
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
      :title="t('login.registerTitle')"
      class="login-auth-modal platform-glass-modal login-glass-panel"
      :style="{ width: 'min(400px, calc(100vw - 32px))' }"
      :mask-closable="!registering && !exiting"
      transform-origin="center"
      @update:show="onRegisterModalUpdate"
    >
      <div ref="registerPanelRef" class="login-auth-panel login-auth-panel--register">
        <n-form class="login-register-form login-form--compact" size="small" @submit.prevent="onRegister">
          <n-text depth="3" class="login-register-hint">
            {{ t("login.registerHint") }}
          </n-text>
          <n-form-item :label="t('login.phone')">
            <n-input v-model:value="regPhone" :placeholder="t('login.phone')" maxlength="11" />
          </n-form-item>
          <n-form-item :label="t('login.email')" required>
            <n-input v-model:value="regEmail" :placeholder="t('login.email')" />
          </n-form-item>
          <n-form-item :label="t('login.displayName')">
            <n-input v-model:value="regDisplayName" :placeholder="t('login.displayName')" />
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
  min-height: 100vh;
  overflow-x: hidden;
  overflow-y: auto;
  background: transparent;
}

.login-page--scroll {
  scroll-snap-type: y mandatory;
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
  backdrop-filter: blur(20px) saturate(160%);
  -webkit-backdrop-filter: blur(20px) saturate(160%);
}

html[data-theme="dark"] .login-header {
  background: rgba(15, 15, 22, 0.72);
  border-bottom-color: rgba(147, 197, 253, 0.1);
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
  gap: 10px;
  min-width: 0;
  text-decoration: none;
  color: inherit;
}

.login-header__logo {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
}

.login-header__title {
  font-size: 14px;
  font-weight: 600;
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
  height: 26px;
  max-height: 26px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  font-size: 13px;
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
  background: rgba(147, 197, 253, 0.16);
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
  filter: blur(72px);
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
  background: radial-gradient(circle, rgba(139, 92, 246, 0.28) 0%, transparent 70%);
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
  scroll-snap-align: start;
  scroll-snap-stop: always;
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

.login-showcase__subheadline {
  margin: 0 0 20px;
  max-width: 36em;
  font-size: clamp(14px, 1.6vw, 16px);
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

.login-auth-panel {
  width: 100%;
}

.login-auth-panel--register {
  overflow: visible;
}

.login-form--compact :deep(.n-form-item) {
  margin-bottom: 10px;
}

.login-form--compact :deep(.n-form-item-label) {
  padding-bottom: 2px;
  font-size: 13px;
}

.login-auth-panel :deep(.n-input) {
  --n-height: 40px;
  --n-font-size: 14px;
  --n-padding-left: 12px;
  --n-padding-right: 12px;
}

.login-glass-btn--submit {
  min-height: 42px !important;
  margin-top: 4px;
}

.login-terms {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 2px;
  cursor: pointer;
  user-select: none;
}

.login-terms__checkbox {
  flex-shrink: 0;
  margin-top: 1px;
}

.login-terms__text {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  line-height: 1.55;
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

.login-register-hint {
  display: block;
  font-size: 12px;
  line-height: 1.5;
  margin-bottom: 10px;
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
    width: 26px;
    padding: 0;
  }

  .login-header__chip--text {
    padding: 0 8px;
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
  backdrop-filter: blur(32px) saturate(190%);
  -webkit-backdrop-filter: blur(32px) saturate(190%);
  border: 1px solid rgba(255, 255, 255, 0.48) !important;
  box-shadow:
    0 12px 40px rgba(91, 120, 200, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.65) !important;
}

html[data-theme="dark"] .login-glass-panel.platform-glass-modal.n-modal .n-card {
  background: rgba(22, 22, 32, 0.52) !important;
  border-color: rgba(147, 197, 253, 0.18) !important;
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card-header {
  padding: 14px 16px 0 !important;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card-header .n-card-header__main {
  font-size: 15px;
  font-weight: 600;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card__content {
  padding: 12px 16px 16px !important;
}

.login-auth-modal.platform-glass-modal.n-modal .n-card {
  overflow: visible;
}

.login-auth-modal .login-glass-btn--submit.n-button {
  min-height: 42px;
  font-size: 14px;
}
</style>
