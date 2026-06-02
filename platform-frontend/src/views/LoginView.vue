<script setup>
import { nextTick, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NSpace,
  NText,
  useMessage,
} from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { useAppPreferences } from "../composables/useAppPreferences";
import { useI18n } from "../composables/useI18n";
import { markSkipMotionAfterLogin } from "../utils/routeTransition";
import { publicAsset } from "../utils/appBase";
import { MoonOutline, SunnyOutline, LanguageOutline } from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import PlatformCopyright from "../components/PlatformCopyright.vue";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const { login, register } = useAuth();
const { isDark, toggleTheme, toggleLocale } = useAppPreferences();
const { t, localeLabel } = useI18n();

const account = ref("15963564658");
const password = ref("admin123");
const loading = ref(false);
const exiting = ref(false);
const loginCardRef = ref(null);

const cardFlipped = ref(false);
const regPhone = ref("");
const regEmail = ref("");
const regDisplayName = ref("");
const regPassword = ref("");
const regPassword2 = ref("");
const registering = ref(false);

const FLY_DURATION_MS = 420;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 主界面顶栏头像大致位置（与 MainLayout 右侧用户区对齐） */
function resolveHeaderAvatarPoint() {
  const headerH = 52;
  const fromRight = 20 + 52 + 8 + 56 + 8 + 88 + 8 + 14;
  return {
    x: Math.max(window.innerWidth * 0.55, window.innerWidth - fromRight),
    y: headerH / 2,
  };
}

function resolveCardElement() {
  return loginCardRef.value ?? null;
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

  await nextTick();
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

  clone.style.transition = `transform ${FLY_DURATION_MS}ms cubic-bezier(0.4, 0, 0.2, 1), opacity ${FLY_DURATION_MS}ms ease, border-radius ${FLY_DURATION_MS}ms ease, box-shadow ${FLY_DURATION_MS}ms ease`;
  clone.style.transform = `translate(${dx}px, ${dy}px) scale(${scale})`;
  clone.style.opacity = "0.12";
  clone.style.borderRadius = "50%";
  clone.style.boxShadow = "0 0 0 1px rgba(13, 148, 136, 0.25)";

  await wait(FLY_DURATION_MS);
  clone.remove();
}

async function navigateAfterAuth() {
  await flyLoginCardToHeader();
  const redirect = route.query.redirect || { name: "ai-home" };
  markSkipMotionAfterLogin();
  await router.push(redirect);
}

async function onSubmit() {
  loading.value = true;
  try {
    await login(account.value.trim(), password.value);
    message.success("登录成功");
    await navigateAfterAuth();
  } catch (e) {
    message.error(e.message || "登录失败");
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
    message.warning("请输入有效的 11 位手机号");
    return;
  }
  if (name.length < 2) {
    message.warning("姓名至少 2 个字符");
    return;
  }
  if (regPassword.value.length < 6) {
    message.warning("密码至少 6 个字符");
    return;
  }
  if (regPassword.value !== regPassword2.value) {
    message.warning("两次输入的密码不一致");
    return;
  }
  const email = regEmail.value.trim();
  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    message.warning("请输入有效的邮箱");
    return;
  }
  registering.value = true;
  try {
    await register({
      phone: mobile,
      email,
      displayName: name,
      password: regPassword.value,
    });
    message.success("注册成功，已自动登录");
    await navigateAfterAuth();
  } catch (e) {
    message.error(e.message || "注册失败");
  } finally {
    registering.value = false;
  }
}

function flipToRegister() {
  if (loading.value || registering.value || exiting.value) return;
  regPhone.value = "";
  regEmail.value = "";
  regDisplayName.value = "";
  regPassword.value = "";
  regPassword2.value = "";
  cardFlipped.value = true;
}

function flipToLogin() {
  if (registering.value || exiting.value) return;
  cardFlipped.value = false;
}
</script>

<template>
  <div class="login-page" :class="{ 'login-page--exit': exiting }">
    <div class="login-page__bg" aria-hidden="true">
      <div class="login-page__orb login-page__orb--1" />
      <div class="login-page__orb login-page__orb--2" />
      <div class="login-page__orb login-page__orb--3" />
      <div class="login-page__grid" />
    </div>

    <div class="login-page__layout">
      <div class="login-preferences">
        <n-button quaternary circle size="small" :aria-label="isDark ? t('userMenu.lightMode') : t('userMenu.darkMode')" @click="toggleTheme">
          <n-icon :size="18" :component="isDark ? SunnyOutline : MoonOutline" />
        </n-button>
        <n-button quaternary size="small" @click="toggleLocale">
          <n-icon :size="16" :component="LanguageOutline" style="margin-right: 4px" />
          {{ localeLabel }}
        </n-button>
      </div>
      <aside class="login-showcase">
        <div class="login-showcase__inner">
          <img :src="publicAsset('logo.svg')" :alt="t('app.name')" class="login-showcase__logo" />
          <h1 class="login-showcase__title">{{ t("login.showcaseTitle") }}</h1>
          <p class="login-showcase__tagline">{{ t("login.showcaseTagline") }}</p>
          <ul class="login-showcase__points">
            <li>{{ t("login.point1") }}</li>
            <li>{{ t("login.point2") }}</li>
            <li>{{ t("login.point3") }}</li>
          </ul>
        </div>
      </aside>

      <main class="login-main">
        <div
          ref="loginCardRef"
          class="login-flip"
          :class="{ 'login-flip--flipped': cardFlipped }"
        >
          <div class="login-flip__inner">
            <div class="login-flip__face login-flip__face--front">
              <n-card class="login-card" size="large">
                <template #header>
                  <span class="login-title">{{ t("login.title") }}</span>
                </template>
                <n-form class="login-form" @submit.prevent="onSubmit">
                  <n-form-item :label="t('login.account')">
                    <n-input
                      v-model:value="account"
                      :placeholder="t('login.account')"
                    />
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
                  <n-space vertical :size="10" style="width: 100%">
                    <n-button type="primary" block :loading="loading" attr-type="submit">
                      {{ t("login.submit") }}
                    </n-button>
                    <n-button
                      block
                      quaternary
                      :disabled="loading || exiting"
                      @click="flipToRegister"
                    >
                      {{ t("login.register") }}
                    </n-button>
                    <n-text depth="3" class="login-footnote">
                      {{ t("login.footnote") }}
                    </n-text>
                  </n-space>
                </n-form>
              </n-card>
            </div>

            <div class="login-flip__face login-flip__face--back">
              <n-card class="login-card" size="large">
                <template #header>
                  <span class="login-title">{{ t("login.registerTitle") }}</span>
                </template>
                <n-text depth="3" class="login-register-hint">
                  {{ t("login.registerHint") }}
                </n-text>
                <n-form class="login-register-form" @submit.prevent="onRegister">
                  <n-form-item :label="t('login.phone')">
                    <n-input
                      v-model:value="regPhone"
                      :placeholder="t('login.phone')"
                      maxlength="11"
                    />
                  </n-form-item>
                  <n-form-item :label="t('login.email')" required>
                    <n-input
                      v-model:value="regEmail"
                      :placeholder="t('login.email')"
                    />
                  </n-form-item>
                  <n-form-item :label="t('login.displayName')">
                    <n-input
                      v-model:value="regDisplayName"
                      :placeholder="t('login.displayName')"
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
                    <n-button type="primary" block :loading="registering" attr-type="submit">
                      {{ t("login.registerSubmit") }}
                    </n-button>
                    <n-button
                      block
                      quaternary
                      :disabled="registering || exiting"
                      @click="flipToLogin"
                    >
                      {{ t("login.backToLogin") }}
                    </n-button>
                  </n-space>
                </n-form>
              </n-card>
            </div>
          </div>
        </div>
      </main>
    </div>
    <footer class="login-page__copyright">
      <PlatformCopyright compact />
    </footer>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background: var(--platform-bg);
}

.login-page__copyright {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2;
  pointer-events: none;
}

.login-preferences {
  position: absolute;
  top: 16px;
  right: 20px;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 4px;
}

.login-page--exit {
  pointer-events: none;
}

.login-page--exit .login-page__layout,
.login-page--exit .login-page__bg {
  opacity: 0;
  transition: opacity 0.28s ease;
}

.login-page__bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.login-page__orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(72px);
}

.login-page__orb--1 {
  width: min(48vw, 480px);
  height: min(48vw, 480px);
  top: -8%;
  left: -6%;
  background: radial-gradient(circle, var(--platform-accent-soft-2) 0%, transparent 70%);
}

.login-page__orb--2 {
  width: min(40vw, 400px);
  height: min(40vw, 400px);
  bottom: -6%;
  right: 4%;
  background: radial-gradient(circle, var(--platform-accent-soft) 0%, transparent 70%);
}

.login-page__orb--3 {
  width: min(32vw, 320px);
  height: min(32vw, 320px);
  top: 42%;
  left: 38%;
  background: radial-gradient(circle, var(--platform-divider) 0%, transparent 70%);
}

.login-page__grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--platform-divider) 1px, transparent 1px),
    linear-gradient(90deg, var(--platform-divider) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse 90% 80% at 50% 40%, #000 15%, transparent 100%);
}

.login-page__layout {
  position: relative;
  z-index: 1;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px;
  box-sizing: border-box;
  gap: 32px;
}

.login-showcase {
  display: none;
  flex: 1;
  min-width: 0;
}

.login-showcase__inner {
  max-width: 420px;
}

.login-showcase__logo {
  width: 56px;
  height: 56px;
  margin-bottom: 20px;
}

.login-showcase__title {
  margin: 0 0 10px;
  font-size: clamp(1.75rem, 3vw, 2.25rem);
  font-weight: 700;
  line-height: 1.25;
  color: var(--platform-text);
  letter-spacing: -0.03em;
}

.login-showcase__tagline {
  margin: 0 0 28px;
  font-size: 15px;
  color: var(--platform-text-secondary);
  line-height: 1.6;
}

.login-showcase__points {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.login-showcase__points li {
  position: relative;
  padding-left: 18px;
  font-size: 14px;
  color: var(--platform-text-secondary);
  line-height: 1.5;
}

.login-showcase__points li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.55em;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--platform-accent);
}

.login-main {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  max-width: 400px;
}

.login-flip {
  width: 100%;
  max-width: 400px;
  perspective: 1200px;
}

.login-flip__inner {
  display: grid;
  transform-style: preserve-3d;
  transition: transform 0.55s cubic-bezier(0.4, 0, 0.2, 1);
}

.login-flip--flipped .login-flip__inner {
  transform: rotateY(180deg);
}

.login-flip__face {
  grid-area: 1 / 1;
  width: 100%;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.login-flip__face--back {
  transform: rotateY(180deg);
}

.login-card {
  width: 100%;
  border: 1px solid var(--platform-border);
  box-shadow: var(--platform-shadow-lg);
}

@media (prefers-reduced-motion: reduce) {
  .login-flip__inner {
    transition: none;
  }
}

.login-card :deep(.n-card-header) {
  padding-bottom: 4px;
}

.login-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--platform-text);
  letter-spacing: -0.02em;
}

.login-form {
  margin-top: 4px;
}

.login-footnote {
  display: block;
  font-size: 12px;
  line-height: 1.55;
  text-align: center;
  color: var(--platform-text-tertiary);
}

.login-register-hint {
  display: block;
  font-size: 12px;
  line-height: 1.55;
  margin-bottom: 16px;
}

.login-register-form {
  margin-top: 0;
}

@media (min-width: 900px) {
  .login-showcase {
    display: block;
  }

  .login-main {
    flex: 0 0 400px;
    max-width: none;
    justify-content: flex-end;
  }
}

@media (max-width: 899px) {
  .login-page__layout {
    padding: 20px 16px;
  }
}
</style>

<style>
.login-card-fly-clone {
  box-sizing: border-box;
  background: var(--platform-bg-elevated) !important;
  will-change: transform, opacity;
}
</style>
