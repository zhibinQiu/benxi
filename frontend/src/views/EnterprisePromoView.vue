<script setup>
import { computed, ref, onMounted, onUnmounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "../composables/useI18n";
import { useAppDisplayName } from "../composables/usePlatformBranding";
import { useAppPreferences } from "../composables/useAppPreferences";
import { NIcon } from "naive-ui";
import {
  SearchOutline,
  AddOutline,
  LayersOutline,
  GitNetworkOutline,
  ShieldCheckmarkOutline,
  DocumentTextOutline,
  ServerOutline,
  RocketOutline,
} from "@vicons/ionicons5";
import PlatformBrandIcon from "../components/PlatformBrandIcon.vue";
import PlatformCopyright from "../components/PlatformCopyright.vue";
import { LanguageOutline } from "@vicons/ionicons5";

const router = useRouter();
const { t, tm, localeLabel } = useI18n();
const appDisplayName = useAppDisplayName();
const { isDark, toggleLocale } = useAppPreferences();

const BASE = import.meta.env.BASE_URL.replace(/\/+$/, "");
const heroBg = `${BASE}/images/bg.jpg`;

const heroBgStyle = computed(() => {
  const gradient = isDark.value
    ? 'linear-gradient(to bottom, rgba(15,15,22,0.78) 0%, rgba(15,15,22,0.85) 70%, rgba(15,15,22,1) 100%)'
    : 'linear-gradient(to bottom, rgba(255,255,255,0.78) 0%, rgba(255,255,255,0.85) 70%, rgba(255,255,255,1) 100%)';
  return {
    backgroundImage: `${gradient}, url(${heroBg})`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
  };
});

const FEATURE_ICONS = [
  SearchOutline,
  AddOutline,
  LayersOutline,
  GitNetworkOutline,
  ShieldCheckmarkOutline,
  DocumentTextOutline,
  ServerOutline,
  RocketOutline,
];

const ARCH_TAG_CLASSES = [
  "promo-arch__layer-tag--orch",
  "promo-arch__layer-tag--skill",
  "promo-arch__layer-tag--retrieval",
  "promo-arch__layer-tag--export",
];

const features = computed(() => {
  const items = tm("promo.detail.features") || [];
  return items.map((item, i) => ({
    icon: FEATURE_ICONS[i] || SearchOutline,
    title: item.title || "",
    body: item.body || "",
  }));
});

const heroStats = computed(() => tm("promo.hero.stats") || []);
const flowSteps = computed(() => tm("promo.flow.steps") || []);
const archLayers = computed(() => {
  const items = tm("promo.arch.layers") || [];
  return items.map((item, i) => ({
    ...item,
    tagClass: ARCH_TAG_CLASSES[i] || "",
  }));
});

const pageRef = ref(null);
let scrollEndTimer = null;

function onPageScroll() {
  const el = pageRef.value;
  if (el) {
    el.classList.toggle("promo-page--scrolling", el.scrollTop > 80);
  }
  clearTimeout(scrollEndTimer);
  scrollEndTimer = setTimeout(() => {}, 140);
}

onMounted(() => {
  nextTick(() => {
    pageRef.value?.scrollTo({ top: 0, left: 0 });
    pageRef.value?.addEventListener("scroll", onPageScroll, { passive: true });
  });
  nextTick(() => bindRevealObservers());
});

onUnmounted(() => {
  pageRef.value?.removeEventListener("scroll", onPageScroll);
  clearTimeout(scrollEndTimer);
  revealObserver?.disconnect();
});

let revealObserver = null;

function bindRevealObservers() {
  revealObserver?.disconnect();
  const sections = document.querySelectorAll(".promo-reveal-section");
  if (!sections.length) return;
  revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("promo-reveal-section--visible");
        }
      });
    },
    { threshold: 0.06, rootMargin: "0px 0px -5% 0px" }
  );
  sections.forEach((el) => revealObserver.observe(el));
}

function navigateToLogin() {
  window.location.href = `${BASE}/login`;
}
</script>

<template>
  <div
    ref="pageRef"
    class="promo-page"
    :class="{ 'promo-page--scrolling': false }"
  >
    <!-- Header -->
    <header class="promo-header">
      <div class="promo-header__inner">
        <a class="promo-header__brand" href="#" @click.prevent>
          <PlatformBrandIcon :size="26" class="promo-header__logo" />
          <span class="promo-header__title">{{ appDisplayName }}</span>
        </a>

        <div class="promo-header__actions">
          <button
            type="button"
            class="promo-glass-link promo-header__chip promo-header__chip--locale"
            @click="toggleLocale"
          >
            <n-icon :size="17" :component="LanguageOutline" />
            <span class="promo-header__locale-label">{{ localeLabel }}</span>
          </button>
          <span class="promo-header__vrule" aria-hidden="true" />
          <button
            type="button"
            class="promo-header__chip promo-header__chip--login"
            @click="navigateToLogin"
          >
            {{ t("promo.header.login") }}
          </button>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="promo-page__main">
      <!-- Hero Section -->
      <section class="promo-hero" :style="heroBgStyle">
        <div class="promo-hero__content">
          <div class="promo-hero__badge-row">
            <span class="promo-hero__badge">{{ t("promo.hero.badge") }}</span>
          </div>
          <h1 class="promo-hero__title">{{ t("promo.hero.title") }}</h1>
          <p class="promo-hero__subtitle">
            {{ t("promo.hero.subtitle") }}
          </p>
          <div class="promo-hero__ctas">
            <button
              type="button"
              class="promo-hero__cta promo-hero__cta--primary"
              @click="navigateToLogin"
            >
              {{ t("promo.hero.ctaPrimary") }}
            </button>
            <a
              href="#feature-detail"
              class="promo-hero__cta promo-hero__cta--secondary"
            >
              {{ t("promo.hero.ctaSecondary") }}
            </a>
          </div>
          <div class="promo-hero__stats">
            <template v-for="(stat, i) in heroStats" :key="i">
              <div v-if="i > 0" class="promo-hero__stat-divider" />
              <div class="promo-hero__stat">
                <span class="promo-hero__stat-value">{{ stat.value }}</span>
                <span class="promo-hero__stat-label">{{ stat.label }}</span>
              </div>
            </template>
          </div>
        </div>
      </section>

      <!-- Feature Detail Section -->
      <section id="feature-detail" class="promo-detail">
        <div class="promo-detail__inner">
          <div class="promo-detail__header">
            <span class="promo-detail__label">{{ t("promo.detail.label") }}</span>
            <h2 class="promo-detail__title">{{ t("promo.detail.title") }}</h2>
            <p class="promo-detail__subtitle">{{ t("promo.detail.subtitle") }}</p>
          </div>

          <div class="promo-detail__grid">
            <div
              v-for="(feature, i) in features"
              :key="i"
              class="promo-detail__card promo-reveal-section"
            >
              <div class="promo-detail__card-icon">
                <n-icon :size="28" :component="feature.icon" />
              </div>
              <h3 class="promo-detail__card-title">{{ feature.title }}</h3>
              <p class="promo-detail__card-body">{{ feature.body }}</p>
            </div>
          </div>
        </div>
      </section>

      <!-- Flow Section -->
      <section class="promo-flow">
        <div class="promo-flow__inner">
          <div class="promo-flow__header">
            <h2 class="promo-flow__title">{{ t("promo.flow.title") }}</h2>
            <p class="promo-flow__subtitle">{{ t("promo.flow.subtitle") }}</p>
          </div>

          <div class="promo-flow__steps">
            <template v-for="(step, i) in flowSteps" :key="i">
              <div v-if="i > 0" class="promo-flow__step-arrow" />
              <div class="promo-flow__step promo-reveal-section">
                <div class="promo-flow__step-number">{{ String(i + 1).padStart(2, '0') }}</div>
                <h3 class="promo-flow__step-title">{{ step.title }}</h3>
                <p class="promo-flow__step-body">{{ step.body }}</p>
              </div>
            </template>
          </div>
        </div>
      </section>

      <!-- Architecture Insight Section -->
      <section class="promo-arch">
        <div class="promo-arch__inner">
          <div class="promo-arch__header">
            <span class="promo-arch__label">{{ t("promo.arch.label") }}</span>
            <h2 class="promo-arch__title">{{ t("promo.arch.title") }}</h2>
            <p class="promo-arch__subtitle">{{ t("promo.arch.subtitle") }}</p>
          </div>

          <div class="promo-arch__layers">
            <div
              v-for="(layer, i) in archLayers"
              :key="i"
              class="promo-arch__layer promo-reveal-section"
            >
              <div class="promo-arch__layer-tag" :class="layer.tagClass">{{ layer.tag }}</div>
              <h3 class="promo-arch__layer-title">{{ layer.title }}</h3>
              <p class="promo-arch__layer-body">{{ layer.body }}</p>
            </div>
          </div>
        </div>
      </section>

      <!-- CTA Section -->
      <section class="promo-cta" :style="{ backgroundImage: `url(${heroBg})` }">
        <div class="promo-cta__content">
          <div class="promo-cta__badge">{{ t("promo.cta.badge") }}</div>
          <h2 class="promo-cta__title">{{ t("promo.cta.title") }}</h2>
          <p class="promo-cta__body">{{ t("promo.cta.body") }}</p>
          <button
            type="button"
            class="promo-cta__btn"
            @click="navigateToLogin"
          >
            {{ t("promo.cta.button") }}
          </button>
        </div>
      </section>
    </main>

    <!-- Footer -->
    <footer class="promo-footer">
      <PlatformCopyright compact />
    </footer>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
</style>

<style scoped>
.promo-page {
  position: relative;
  height: 100dvh;
  max-height: 100dvh;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  -webkit-overflow-scrolling: touch;
  background: #fff;
  font-family: "Inter", ui-sans-serif, -apple-system, BlinkMacSystemFont,
    "Segoe UI", "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
}

html[data-theme="dark"] .promo-page {
  background: #0f0f16;
}

/* ========== Header ========== */
.promo-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 43px;
  box-sizing: border-box;
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  transition: background 0.25s ease, backdrop-filter 0.25s ease;
}

.promo-page--scrolling .promo-header {
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

html[data-theme="dark"] .promo-page--scrolling .promo-header {
  background: rgba(15, 15, 22, 0.82);
  border-bottom-color: var(--platform-accent-border-soft);
}

.promo-header__inner {
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

.promo-header__brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  text-decoration: none;
  color: inherit;
}

.promo-header__logo {
  flex-shrink: 0;
  filter: brightness(0);
  transition: filter 0.25s ease;
}

html[data-theme="dark"] .promo-header__logo {
  filter: brightness(0) invert(1);
}

.promo-page--scrolling .promo-header__logo,
html[data-theme="dark"] .promo-page--scrolling .promo-header__logo {
  filter: none;
}

.promo-header__title {
  font-size: 14px;
  letter-spacing: -0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #000;
}

html[data-theme="dark"] .promo-header__title {
  color: #e8e8ee;
}

.promo-page--scrolling .promo-header__title {
  background-image: var(--platform-accent-gradient);
  background-size: 120% 100%;
  background-position: 0% 50%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  -webkit-text-fill-color: transparent;
}

.promo-header__actions {
  display: flex;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
  height: 100%;
  max-height: 43px;
}

.promo-header__chip {
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

.promo-header__chip:hover:not(:disabled) {
  color: var(--platform-text);
}

.promo-header__chip--icon {
  width: 26px;
  padding: 0;
}

.promo-header__chip--locale {
  gap: 6px;
  padding: 0 10px;
}

.promo-header__chip :deep(.n-icon) {
  color: inherit;
}

.promo-header__vrule {
  flex-shrink: 0;
  width: 1px;
  height: 17px;
  margin: 0 4px;
  background: var(--platform-border, rgba(148, 163, 184, 0.28));
}

html[data-theme="dark"] .promo-header__vrule {
  background: var(--platform-accent-border-soft);
}

.promo-header__chip--login {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  padding: 0 16px;
  border: none;
  border-radius: 999px;
  background: #000;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.2s ease, transform 0.18s cubic-bezier(0.22, 1, 0.36, 1);
  line-height: 1;
  appearance: none;
  box-sizing: border-box;
  white-space: nowrap;
}

.promo-header__chip--login:hover {
  opacity: 0.82;
  transform: translateY(-1px);
}

html[data-theme="dark"] .promo-header__chip--login {
  background: #fff;
  color: #000;
}

.promo-header__locale-label {
  display: none;
}

@media (min-width: 640px) {
  .promo-header__locale-label { display: inline; }
  .promo-header__chip--locale { padding: 0 12px; }
}

@media (max-width: 639px) {
  .promo-header__chip--locale { width: 26px; padding: 0; }
  .promo-header__chip--text { padding: 0 7px; }
}

/* ========== Hero ========== */
.promo-hero {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 80px 29px 60px;
  box-sizing: border-box;
  position: relative;
  background: #fff;
}

.promo-hero__content {
  position: relative;
  z-index: 2;
  max-width: 864px;
  width: 100%;
  text-align: center;
}

.promo-hero__badge-row {
  margin-bottom: 24px;
}

.promo-hero__badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--platform-accent), color-mix(in srgb, var(--platform-accent) 70%, #6366f1));
  color: #fff;
  font-size: 13px;
  letter-spacing: 0.03em;
  box-shadow: 0 4px 14px color-mix(in srgb, var(--platform-accent) 30%, transparent);
}

.promo-hero__title {
  margin: 0 0 20px;
  font-size: clamp(2rem, 5vw, 3.2rem);
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: -0.04em;
  color: #000;
  -webkit-font-smoothing: antialiased;
}

html[data-theme="dark"] .promo-hero__title {
  color: #e8e8ee;
}

.promo-hero__subtitle {
  margin: 0 auto 36px;
  max-width: 34em;
  font-size: clamp(15px, 1.3vw, 18px);
  font-weight: 400;
  line-height: 1.7;
  color: #333;
  -webkit-font-smoothing: antialiased;
}

html[data-theme="dark"] .promo-hero__subtitle {
  color: #b0b0b8;
}

.promo-hero__ctas {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 48px;
}

.promo-hero__cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 48px;
  padding: 0 32px;
  border: none;
  border-radius: 999px;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  text-decoration: none;
  transition:
    transform 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.2s ease,
    background 0.2s ease;
}

.promo-hero__cta--primary {
  background: var(--platform-accent);
  color: #fff;
  box-shadow: 0 8px 24px color-mix(in srgb, var(--platform-accent) 32%, transparent);
}

.promo-hero__cta--primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px color-mix(in srgb, var(--platform-accent) 40%, transparent);
}

.promo-hero__cta--secondary {
  background: rgba(255, 255, 255, 0.16);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  border: 1px solid rgba(0, 0, 0, 0.12);
  color: var(--platform-text);
  box-shadow: 0 5px 17px color-mix(in srgb, var(--platform-accent) 6%, transparent);
}

.promo-hero__cta--secondary:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.24);
}

html[data-theme="dark"] .promo-hero__cta--secondary {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--platform-accent-border-soft);
}

.promo-hero__stats {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
}

.promo-hero__stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 0 36px;
}

.promo-hero__stat-value {
  font-size: clamp(18px, 2.2vw, 26px);
  color: var(--platform-accent);
  letter-spacing: -0.02em;
}

.promo-hero__stat-label {
  font-size: 13px;
  font-weight: 500;
  color: #888;
}

.promo-hero__stat-divider {
  width: 1px;
  height: 40px;
  background: rgba(0, 0, 0, 0.08);
}

html[data-theme="dark"] .promo-hero__stat-divider {
  background: rgba(255, 255, 255, 0.08);
}

/* ========== Feature Detail ========== */
.promo-detail {
  padding: 100px max(100px, env(safe-area-inset-right, 0px)) 120px max(100px, env(safe-area-inset-left, 0px));
  background: #fff;
}

html[data-theme="dark"] .promo-detail {
  background: #0f0f16;
}

.promo-detail__inner {
  max-width: 1200px;
  margin: 0 auto;
}

.promo-detail__header {
  text-align: center;
  margin-bottom: 56px;
}

.promo-detail__label {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent);
  color: var(--platform-accent);
  font-size: 13px;
  letter-spacing: 0.04em;
  margin-bottom: 14px;
}

.promo-detail__title {
  margin: 0 0 12px;
  font-size: clamp(1.6rem, 3.2vw, 2.2rem);
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.03em;
  color: #000;
}

html[data-theme="dark"] .promo-detail__title {
  color: #e8e8ee;
}

.promo-detail__subtitle {
  margin: 0 auto;
  max-width: 30em;
  font-size: 16px;
  line-height: 1.6;
  color: #666;
}

html[data-theme="dark"] .promo-detail__subtitle {
  color: #999;
}

.promo-detail__grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.promo-detail__card {
  padding: 28px 24px;
  border-radius: 14px;
  background: #f8f8fa;
  border: 1px solid #e8e8ee;
  transition:
    transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.25s ease,
    border-color 0.25s ease;
}

html[data-theme="dark"] .promo-detail__card {
  background: #181820;
  border-color: #2a2a36;
}

.promo-detail__card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.06);
  border-color: color-mix(in srgb, var(--platform-accent) 24%, transparent);
}

html[data-theme="dark"] .promo-detail__card:hover {
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2);
  border-color: color-mix(in srgb, var(--platform-accent) 30%, #2a2a36);
}

.promo-detail__card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  margin-bottom: 18px;
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent);
  color: var(--platform-accent);
}

.promo-detail__card-title {
  margin: 0 0 10px;
  font-size: 17px;
  line-height: 1.3;
  color: #000;
}

html[data-theme="dark"] .promo-detail__card-title {
  color: #e0e0e8;
}

.promo-detail__card-body {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #555;
}

html[data-theme="dark"] .promo-detail__card-body {
  color: #999;
}

/* ========== Flow Section ========== */
.promo-flow {
  padding: 60px max(100px, env(safe-area-inset-right, 0px)) 80px max(100px, env(safe-area-inset-left, 0px));
  background: #f5f5f7;
}

html[data-theme="dark"] .promo-flow {
  background: #14141c;
}

.promo-flow__inner {
  max-width: 1100px;
  margin: 0 auto;
}

.promo-flow__header {
  text-align: center;
  margin-bottom: 48px;
}

.promo-flow__title {
  margin: 0 0 10px;
  font-size: clamp(1.5rem, 3vw, 2rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: #000;
}

html[data-theme="dark"] .promo-flow__title {
  color: #e8e8ee;
}

.promo-flow__subtitle {
  margin: 0;
  font-size: 16px;
  color: #777;
}

html[data-theme="dark"] .promo-flow__subtitle {
  color: #999;
}

.promo-flow__steps {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 0;
}

.promo-flow__step {
  flex: 1;
  text-align: center;
  padding: 32px 24px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid #e8e8ee;
  transition:
    transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.25s ease;
}

html[data-theme="dark"] .promo-flow__step {
  background: #1a1a24;
  border-color: #2a2a36;
}

.promo-flow__step:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.05);
}

html[data-theme="dark"] .promo-flow__step:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.promo-flow__step-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, var(--platform-accent), color-mix(in srgb, var(--platform-accent) 70%, #6366f1));
  color: #fff;
  font-size: 18px;
  font-feature-settings: "tnum";
}

.promo-flow__step-title {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 600;
  color: #000;
}

html[data-theme="dark"] .promo-flow__step-title {
  color: #e0e0e8;
}

.promo-flow__step-body {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #666;
}

html[data-theme="dark"] .promo-flow__step-body {
  color: #999;
}

.promo-flow__step-arrow {
  flex-shrink: 0;
  width: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding-top: 50px;
  color: #ccc;
  font-size: 24px;
}

.promo-flow__step-arrow::after {
  content: "→";
  font-weight: 300;
}

html[data-theme="dark"] .promo-flow__step-arrow {
  color: #555;
}

/* ========== Architecture ========== */
.promo-arch {
  padding: 100px max(100px, env(safe-area-inset-right, 0px)) 100px max(100px, env(safe-area-inset-left, 0px));
  background: #fff;
}

html[data-theme="dark"] .promo-arch {
  background: #0f0f16;
}

.promo-arch__inner {
  max-width: 1000px;
  margin: 0 auto;
}

.promo-arch__header {
  text-align: center;
  margin-bottom: 48px;
}

.promo-arch__label {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent);
  color: var(--platform-accent);
  font-size: 13px;
  letter-spacing: 0.04em;
  margin-bottom: 14px;
}

.promo-arch__title {
  margin: 0 0 10px;
  font-size: clamp(1.5rem, 3vw, 2rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: #000;
}

html[data-theme="dark"] .promo-arch__title {
  color: #e8e8ee;
}

.promo-arch__subtitle {
  margin: 0;
  font-size: 16px;
  color: #777;
}

html[data-theme="dark"] .promo-arch__subtitle {
  color: #999;
}

.promo-arch__layers {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.promo-arch__layer {
  padding: 28px 24px;
  border-radius: 14px;
  background: #f8f8fa;
  border: 1px solid #e8e8ee;
  transition:
    transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.25s ease;
}

html[data-theme="dark"] .promo-arch__layer {
  background: #181820;
  border-color: #2a2a36;
}

.promo-arch__layer:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.05);
}

html[data-theme="dark"] .promo-arch__layer:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.promo-arch__layer-tag {
  display: inline-flex;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11px;
  letter-spacing: 0.04em;
  margin-bottom: 14px;
}

.promo-arch__layer-tag--orch {
  background: color-mix(in srgb, #6366f1 12%, transparent);
  color: #6366f1;
}

.promo-arch__layer-tag--skill {
  background: color-mix(in srgb, #10b981 12%, transparent);
  color: #10b981;
}

.promo-arch__layer-tag--retrieval {
  background: color-mix(in srgb, #f59e0b 12%, transparent);
  color: #d97706;
}

.promo-arch__layer-tag--export {
  background: color-mix(in srgb, #8b5cf6 12%, transparent);
  color: #7c3aed;
}

.promo-arch__layer-title {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 600;
  color: #000;
}

html[data-theme="dark"] .promo-arch__layer-title {
  color: #e0e0e8;
}

.promo-arch__layer-body {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #555;
}

html[data-theme="dark"] .promo-arch__layer-body {
  color: #999;
}

/* ========== CTA ========== */
.promo-cta {
  padding: 80px 29px;
  position: relative;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
}

.promo-cta::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.88) 0%,
    rgba(255, 255, 255, 0.95) 50%,
    rgba(255, 255, 255, 1) 100%
  );
  z-index: 0;
}

html[data-theme="dark"] .promo-cta::before {
  background: linear-gradient(
    135deg,
    rgba(15, 15, 22, 0.9) 0%,
    rgba(15, 15, 22, 0.96) 50%,
    rgba(15, 15, 22, 1) 100%
  );
}

.promo-cta__content {
  position: relative;
  z-index: 1;
  max-width: 640px;
  margin: 0 auto;
  text-align: center;
}

.promo-cta__badge {
  display: inline-flex;
  padding: 5px 14px;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--platform-accent), color-mix(in srgb, var(--platform-accent) 70%, #6366f1));
  color: #fff;
  font-size: 12px;
  letter-spacing: 0.04em;
  margin-bottom: 20px;
  box-shadow: 0 4px 14px color-mix(in srgb, var(--platform-accent) 30%, transparent);
}

.promo-cta__title {
  margin: 0 0 16px;
  font-size: clamp(1.5rem, 3vw, 2rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: #000;
}

html[data-theme="dark"] .promo-cta__title {
  color: #e8e8ee;
}

.promo-cta__body {
  margin: 0 0 32px;
  font-size: 16px;
  line-height: 1.7;
  color: #555;
}

html[data-theme="dark"] .promo-cta__body {
  color: #999;
}

.promo-cta__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 50px;
  padding: 0 36px;
  border: none;
  border-radius: 999px;
  background: var(--platform-accent);
  color: #fff;
  font-size: 17px;
  cursor: pointer;
  box-shadow: 0 8px 24px color-mix(in srgb, var(--platform-accent) 32%, transparent);
  transition:
    transform 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.2s ease;
}

.promo-cta__btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px color-mix(in srgb, var(--platform-accent) 40%, transparent);
}

/* ========== Footer ========== */
.promo-footer {
  padding: 24px 19px 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ========== Reveal Animations ========== */
.promo-reveal-section {
  opacity: 0;
  transform: translateY(32px);
  transition:
    opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1),
    transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}

.promo-reveal-section--visible {
  opacity: 1;
  transform: translateY(0);
}

/* ========== Responsive ========== */
@media (max-width: 1024px) {
  .promo-detail__grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .promo-flow__steps {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }

  .promo-flow__step-arrow {
    display: none;
  }
}

@media (max-width: 900px) {
  .promo-detail { padding-inline: 48px; }
  .promo-flow { padding-inline: 48px; }
  .promo-arch { padding-inline: 48px; }
}

@media (max-width: 720px) {
  .promo-detail { padding-inline: 24px; padding-block: 64px; }
  .promo-flow { padding-inline: 24px; }
  .promo-arch { padding-inline: 24px; padding-block: 64px; }

  .promo-detail__grid {
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }

  .promo-arch__layers {
    grid-template-columns: 1fr;
  }

  .promo-hero__stats {
    flex-wrap: wrap;
    gap: 8px;
  }

  .promo-hero__stat {
    padding: 0 20px;
  }

  .promo-hero__stat-divider {
    display: none;
  }
}

@media (max-width: 480px) {
  .promo-hero { padding: 70px 16px 48px; }
  .promo-detail { padding-inline: 14px; padding-block: 48px; }
  .promo-flow { padding-inline: 14px; }
  .promo-arch { padding-inline: 14px; padding-block: 48px; }
  .promo-cta { padding: 48px 16px; }

  .promo-detail__grid {
    grid-template-columns: 1fr;
  }

  .promo-detail__card { padding: 22px 18px; }
  .promo-arch__layer { padding: 22px 18px; }

  .promo-hero__ctas {
    flex-direction: column;
    width: 100%;
  }

  .promo-hero__cta {
    width: 100%;
  }

  .promo-hero__stat {
    padding: 0 14px;
  }

  .promo-header__title { display: none; }
  .promo-header__brand { gap: 0; }
}

@media (max-width: 400px) {
  .promo-hero { min-height: auto; }
}

@media (prefers-reduced-motion: reduce) {
  .promo-reveal-section {
    opacity: 1 !important;
    transform: none !important;
    transition: none !important;
  }
}
</style>
