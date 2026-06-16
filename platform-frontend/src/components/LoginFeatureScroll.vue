<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { NIcon } from "naive-ui";
import {
  LanguageOutline,
  ChatbubblesOutline,
  GitCompareOutline,
  DocumentTextOutline,
  MicOutline,
  ScanOutline,
  StatsChartOutline,
  LeafOutline,
  SparklesOutline,
  CreateOutline,
  WalletOutline,
  NewspaperOutline,
  SearchOutline,
  GitNetworkOutline,
  CheckmarkCircleOutline,
  TrendingUpOutline,
  AnalyticsOutline,
} from "@vicons/ionicons5";
import { useAppPreferences } from "../composables/useAppPreferences";
import { messages } from "../locales";

const { locale } = useAppPreferences();

const iconMap = {
  "document-text": DocumentTextOutline,
  search: SearchOutline,
  sparkles: SparklesOutline,
  language: LanguageOutline,
  "git-compare": GitCompareOutline,
  "stats-chart": StatsChartOutline,
  analytics: AnalyticsOutline,
  "trending-up": TrendingUpOutline,
  leaf: LeafOutline,
  wallet: WalletOutline,
  mic: MicOutline,
  scan: ScanOutline,
  "git-network": GitNetworkOutline,
  create: CreateOutline,
  newspaper: NewspaperOutline,
  chatbubbles: ChatbubblesOutline,
  todos: CheckmarkCircleOutline,
};

const iconStyles = {
  "document-text": "linear-gradient(135deg, #60a5fa 0%, #2563eb 100%)",
  search: "linear-gradient(135deg, #c084fc 0%, #7c3aed 100%)",
  sparkles: "linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)",
  language: "linear-gradient(135deg, #22d3ee 0%, #0891b2 100%)",
  "git-compare": "linear-gradient(135deg, #818cf8 0%, #4f46e5 100%)",
  "stats-chart": "linear-gradient(135deg, #34d399 0%, #059669 100%)",
  analytics: "linear-gradient(135deg, #2dd4bf 0%, #0d9488 100%)",
  "trending-up": "linear-gradient(135deg, #fb923c 0%, #ea580c 100%)",
  leaf: "linear-gradient(135deg, #4ade80 0%, #16a34a 100%)",
  wallet: "linear-gradient(135deg, #f472b6 0%, #db2777 100%)",
  mic: "linear-gradient(135deg, #a78bfa 0%, #9333ea 100%)",
  scan: "linear-gradient(135deg, #38bdf8 0%, #0284c7 100%)",
  "git-network": "linear-gradient(135deg, #e879f9 0%, #c026d3 100%)",
  create: "linear-gradient(135deg, #f87171 0%, #dc2626 100%)",
  newspaper: "linear-gradient(135deg, #94a3b8 0%, #475569 100%)",
  chatbubbles: "linear-gradient(135deg, #86efac 0%, #15803d 100%)",
  todos: "linear-gradient(135deg, #fcd34d 0%, #d97706 100%)",
};

const glowColors = {
  "document-text": "rgba(37, 99, 235, 0.45)",
  search: "rgba(124, 58, 237, 0.45)",
  sparkles: "rgba(245, 158, 11, 0.45)",
  language: "rgba(8, 145, 178, 0.45)",
  "git-compare": "rgba(79, 70, 229, 0.45)",
  "stats-chart": "rgba(5, 150, 105, 0.45)",
  analytics: "rgba(13, 148, 136, 0.45)",
  "trending-up": "rgba(234, 88, 12, 0.45)",
  leaf: "rgba(22, 163, 74, 0.45)",
  wallet: "rgba(219, 39, 119, 0.45)",
  mic: "rgba(147, 51, 234, 0.45)",
  scan: "rgba(2, 132, 199, 0.45)",
  "git-network": "rgba(192, 38, 211, 0.45)",
  create: "rgba(220, 38, 38, 0.45)",
  newspaper: "rgba(71, 85, 105, 0.45)",
  chatbubbles: "rgba(21, 128, 61, 0.45)",
  todos: "rgba(217, 119, 6, 0.45)",
};

const sectionEls = ref([]);
const summaryEl = ref(null);

const allCards = computed(() => {
  const list = messages[locale.value]?.login?.showcaseCards;
  return Array.isArray(list) ? list : [];
});

/** 登录页展示 curated 核心功能（排除智能问数） */
const cards = computed(() =>
  allCards.value.filter((card) => card.featureId !== "smart_data_query")
);

const summary = computed(() => messages[locale.value]?.login?.showcaseSummary || null);

const compareLabel = computed(
  () => messages[locale.value]?.login?.showcaseCompareLabel || "Why us"
);

const activeIndex = ref(-1);
const summaryActive = ref(false);
let revealObserver = null;
let activeObserver = null;

function scrollToSection(index) {
  const el = sectionEls.value[index];
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function scrollToSummary() {
  if (summaryEl.value) {
    summaryEl.value.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function resolveIcon(key) {
  return iconMap[key] || SparklesOutline;
}

function resolveIconStyle(key) {
  return iconStyles[key] || iconStyles.sparkles;
}

function resolveGlow(key) {
  return glowColors[key] || glowColors.sparkles;
}

function setSectionRef(el, index) {
  if (el) sectionEls.value[index] = el;
}

function bindObservers() {
  revealObserver?.disconnect();
  activeObserver?.disconnect();

  const sections = sectionEls.value.filter(Boolean);
  if (!sections.length && !summaryEl.value) return;

  revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add(
            entry.target.classList.contains("login-feature-scroll__summary")
              ? "login-feature-scroll__summary--visible"
              : "login-feature-scroll__section--visible"
          );
        }
      });
    },
    { threshold: 0.22, rootMargin: "0px 0px -8% 0px" }
  );

  activeObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        if (entry.target.classList.contains("login-feature-scroll__summary")) {
          summaryActive.value = true;
          return;
        }
        summaryActive.value = false;
        const idx = Number(entry.target.dataset.index);
        if (!Number.isNaN(idx)) activeIndex.value = idx;
      });
    },
    { threshold: 0.52, rootMargin: "-18% 0px -18% 0px" }
  );

  sections.forEach((el) => {
    revealObserver.observe(el);
    activeObserver.observe(el);
  });
  if (summaryEl.value) {
    revealObserver.observe(summaryEl.value);
    activeObserver.observe(summaryEl.value);
  }
}

onMounted(() => nextTick(bindObservers));

onUnmounted(() => {
  revealObserver?.disconnect();
  activeObserver?.disconnect();
});

watch(locale, () => {
  sectionEls.value = [];
  activeIndex.value = -1;
  summaryActive.value = false;
  nextTick(bindObservers);
});

watch(cards, () => {
  sectionEls.value = [];
  activeIndex.value = -1;
  summaryActive.value = false;
  nextTick(bindObservers);
});

watch(summaryEl, () => nextTick(bindObservers));
</script>

<template>
  <div v-if="cards.length" class="login-feature-scroll">
    <nav class="login-feature-scroll__rail" aria-label="Feature sections">
      <button
        v-for="(card, index) in cards"
        :key="`rail-${card.featureId}`"
        type="button"
        class="login-feature-scroll__rail-dot"
        :class="{ 'login-feature-scroll__rail-dot--active': !summaryActive && activeIndex === index }"
        :aria-label="card.title"
        :aria-current="!summaryActive && activeIndex === index ? 'true' : undefined"
        @click="scrollToSection(index)"
      />
      <button
        v-if="summary"
        type="button"
        class="login-feature-scroll__rail-dot login-feature-scroll__rail-dot--summary"
        :class="{ 'login-feature-scroll__rail-dot--active': summaryActive }"
        :aria-label="compareLabel"
        :aria-current="summaryActive ? 'true' : undefined"
        @click="scrollToSummary"
      />
    </nav>

    <div class="login-feature-scroll__head">
      <p class="login-feature-scroll__counter" aria-hidden="true">
        <template v-if="summaryActive && summary">
          {{ compareLabel }}
        </template>
        <template v-else>
          {{ String((activeIndex >= 0 ? activeIndex : 0) + 1).padStart(2, "0") }}
          <span>/</span>
          {{ String(cards.length).padStart(2, "0") }}
        </template>
      </p>
    </div>

    <section
      v-for="(card, index) in cards"
      :key="`${card.featureId}-${index}`"
      :ref="(el) => setSectionRef(el, index)"
      class="login-feature-scroll__section"
      :class="{
        'login-feature-scroll__section--past': activeIndex > index && !summaryActive,
        'login-feature-scroll__section--future': activeIndex < index && !summaryActive,
        'login-feature-scroll__section--active': activeIndex === index && !summaryActive,
      }"
      :data-index="index"
      :style="{ '--section-glow': resolveGlow(card.icon) }"
    >
      <div class="login-feature-scroll__section-bg" aria-hidden="true" />
      <div class="login-feature-scroll__section-sweep" aria-hidden="true" />
      <div class="login-feature-scroll__section-layout">
        <div class="login-feature-scroll__section-main">
          <span class="login-feature-scroll__index">
            {{ String(index + 1).padStart(2, "0") }}
          </span>
          <div class="login-feature-scroll__visual">
            <span
              class="login-feature-scroll__icon-ring"
              :style="{ background: resolveIconStyle(card.icon) }"
            />
            <span
              class="login-feature-scroll__icon"
              :style="{ background: resolveIconStyle(card.icon) }"
            >
              <n-icon :size="36" :component="resolveIcon(card.icon)" />
            </span>
          </div>
          <h2 class="login-feature-scroll__title">{{ card.title }}</h2>
          <p class="login-feature-scroll__desc">{{ card.desc }}</p>
        </div>

        <aside
          v-if="card.pitch || card.value || card.bullets?.length"
          class="login-feature-scroll__pitch"
          :style="{ '--pitch-accent': resolveIconStyle(card.icon) }"
        >
          <p v-if="card.pitch" class="login-feature-scroll__pitch-hook">{{ card.pitch }}</p>
          <p v-if="card.value" class="login-feature-scroll__pitch-value">{{ card.value }}</p>
          <ul v-if="card.bullets?.length" class="login-feature-scroll__pitch-bullets">
            <li v-for="(bullet, bi) in card.bullets" :key="bi">
              <n-icon :size="15" :component="CheckmarkCircleOutline" class="login-feature-scroll__pitch-check" />
              <span>{{ bullet }}</span>
            </li>
          </ul>
        </aside>
      </div>
    </section>

    <section
      v-if="summary"
      ref="summaryEl"
      class="login-feature-scroll__summary"
      :class="{ 'login-feature-scroll__summary--active': summaryActive }"
    >
      <div class="login-feature-scroll__summary-inner">
        <p class="login-feature-scroll__summary-label">{{ compareLabel }}</p>
        <h2 class="login-feature-scroll__summary-title">{{ summary.title }}</h2>
        <p class="login-feature-scroll__summary-subtitle">{{ summary.subtitle }}</p>

        <div class="login-feature-scroll__compare-table">
          <div class="login-feature-scroll__compare-row login-feature-scroll__compare-row--head">
            <span>{{ summary.columns?.aspect }}</span>
            <span>{{ summary.columns?.others }}</span>
            <span>{{ summary.columns?.ours }}</span>
          </div>
          <div
            v-for="(row, ri) in summary.rows"
            :key="ri"
            class="login-feature-scroll__compare-row"
          >
            <span class="login-feature-scroll__compare-aspect">{{ row.aspect }}</span>
            <span class="login-feature-scroll__compare-others">{{ row.others }}</span>
            <span class="login-feature-scroll__compare-ours">{{ row.ours }}</span>
          </div>
        </div>

        <p v-if="summary.closing" class="login-feature-scroll__summary-closing">
          {{ summary.closing }}
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login-feature-scroll {
  position: relative;
  width: 100%;
  margin: 0;
  padding: 0;
}

.login-feature-scroll__rail {
  position: fixed;
  right: max(14px, env(safe-area-inset-right, 0px));
  top: 50%;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
  backdrop-filter: blur(16px) saturate(160%);
  -webkit-backdrop-filter: blur(16px) saturate(160%);
  border: 1px solid rgba(255, 255, 255, 0.35);
  box-shadow: 0 8px 28px rgba(91, 120, 200, 0.12);
  transform: translateY(-50%);
}

html[data-theme="dark"] .login-feature-scroll__rail {
  background: rgba(22, 22, 32, 0.55);
  border-color: rgba(147, 197, 253, 0.14);
}

.login-feature-scroll__rail-dot {
  position: relative;
  width: 8px;
  height: 8px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(148, 163, 184, 0.45);
  cursor: pointer;
  transition:
    transform 0.35s cubic-bezier(0.22, 1, 0.36, 1),
    background 0.35s ease,
    box-shadow 0.35s ease;
}

.login-feature-scroll__rail-dot--summary {
  width: 6px;
  height: 6px;
  margin-top: 4px;
}

.login-feature-scroll__rail-dot--active {
  background: var(--platform-accent);
  box-shadow: 0 0 12px var(--platform-accent-soft, rgba(59, 130, 246, 0.45));
  transform: scale(1.35);
}

.login-feature-scroll__rail-dot--active::after {
  content: "";
  position: absolute;
  inset: -6px;
  border-radius: inherit;
  border: 1px solid var(--platform-accent-border, rgba(59, 130, 246, 0.4));
  animation: login-feature-scroll-ring 1.8s ease-out infinite;
}

.login-feature-scroll__head {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin: 0 0 8px;
  padding: 0 max(48px, env(safe-area-inset-right, 0px)) 0 max(12px, env(safe-area-inset-left, 0px));
}

.login-feature-scroll__hint {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--platform-text-tertiary);
}

.login-feature-scroll__hint-line {
  width: 24px;
  height: 1px;
  background: linear-gradient(90deg, var(--platform-accent), transparent);
  animation: login-feature-scroll-pulse 2.4s ease-in-out infinite;
}

.login-feature-scroll__counter {
  margin: 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.06em;
  color: var(--platform-text-tertiary);
}

.login-feature-scroll__counter span {
  margin: 0 4px;
  opacity: 0.45;
}

.login-feature-scroll__section {
  position: relative;
  min-height: calc(100dvh - 36px);
  display: flex;
  align-items: center;
  scroll-snap-align: start;
  scroll-snap-stop: always;
  isolation: isolate;
  box-sizing: border-box;
  padding: 24px max(48px, env(safe-area-inset-right, 0px)) 24px max(12px, env(safe-area-inset-left, 0px));
}

.login-feature-scroll__section-sweep {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0;
  background: linear-gradient(
    105deg,
    transparent 42%,
    rgba(255, 255, 255, 0.14) 50%,
    transparent 58%
  );
  transform: translateX(-120%);
}

.login-feature-scroll__section--active .login-feature-scroll__section-sweep {
  animation: login-feature-scroll-sweep 0.9s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

.login-feature-scroll__section-layout {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 240px) minmax(0, 1fr);
  gap: clamp(24px, 4vw, 40px);
  width: 100%;
  max-width: min(960px, calc(100vw - 72px));
  padding: 0;
  align-items: center;
  opacity: 0.28;
  filter: blur(10px);
  transform: scale(0.9) translateY(48px);
  transition:
    opacity 0.65s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.75s cubic-bezier(0.22, 1, 0.36, 1),
    filter 0.65s cubic-bezier(0.22, 1, 0.36, 1);
}

.login-feature-scroll__section--past .login-feature-scroll__section-layout {
  transform: scale(0.88) translateY(-56px);
}

.login-feature-scroll__section--future .login-feature-scroll__section-layout {
  transform: scale(0.9) translateY(56px);
}

.login-feature-scroll__section--active .login-feature-scroll__section-layout,
.login-feature-scroll__section--visible.login-feature-scroll__section--active .login-feature-scroll__section-layout {
  opacity: 1;
  filter: blur(0);
  transform: scale(1) translateY(0);
}

.login-feature-scroll__section-main {
  min-width: 0;
}

.login-feature-scroll__pitch {
  min-width: 0;
  padding: 18px 20px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.28);
  backdrop-filter: blur(24px) saturate(170%);
  -webkit-backdrop-filter: blur(24px) saturate(170%);
  border: 1px solid rgba(255, 255, 255, 0.42);
  box-shadow:
    0 12px 36px rgba(91, 120, 200, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    inset 0 0 0 1px rgba(255, 255, 255, 0.08);
  opacity: 0;
  transform: translateX(28px);
  transition:
    opacity 0.85s cubic-bezier(0.22, 1, 0.36, 1) 0.28s,
    transform 0.95s cubic-bezier(0.22, 1, 0.36, 1) 0.28s;
}

html[data-theme="dark"] .login-feature-scroll__pitch {
  background: rgba(22, 22, 32, 0.52);
  border-color: rgba(147, 197, 253, 0.14);
  box-shadow:
    0 12px 36px rgba(0, 0, 0, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.login-feature-scroll__pitch-hook {
  margin: 0 0 12px;
  font-size: clamp(1.15rem, 2.2vw, 1.45rem);
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.03em;
  background: var(--pitch-accent, linear-gradient(135deg, #60a5fa, #2563eb));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.login-feature-scroll__pitch-value {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--platform-text);
}

.login-feature-scroll__summary {
  position: relative;
  min-height: calc(100dvh - 36px);
  display: flex;
  align-items: center;
  scroll-snap-align: start;
  scroll-snap-stop: always;
  box-sizing: border-box;
  padding: 24px max(48px, env(safe-area-inset-right, 0px)) 48px max(12px, env(safe-area-inset-left, 0px));
  opacity: 0.35;
  filter: blur(8px);
  transform: scale(0.92) translateY(40px);
  transition:
    opacity 0.75s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    filter 0.75s cubic-bezier(0.22, 1, 0.36, 1);
}

.login-feature-scroll__summary--visible {
  opacity: 0.35;
  transform: scale(0.92) translateY(40px);
}

.login-feature-scroll__summary--active,
.login-feature-scroll__summary--visible.login-feature-scroll__summary--active {
  opacity: 1;
  filter: blur(0);
  transform: scale(1) translateY(0);
}

.login-feature-scroll__summary-inner {
  width: 100%;
  max-width: min(960px, calc(100vw - 72px));
  padding: 28px 24px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.3);
  backdrop-filter: blur(28px) saturate(170%);
  -webkit-backdrop-filter: blur(28px) saturate(170%);
  border: 1px solid rgba(255, 255, 255, 0.45);
  box-shadow:
    0 16px 48px rgba(91, 120, 200, 0.14),
    inset 0 1px 0 rgba(255, 255, 255, 0.6);
}

html[data-theme="dark"] .login-feature-scroll__summary-inner {
  background: rgba(22, 22, 32, 0.55);
  border-color: rgba(147, 197, 253, 0.14);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.32);
}

.login-feature-scroll__summary-label {
  margin: 0 0 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--platform-accent);
}

.login-feature-scroll__summary-title {
  margin: 0 0 12px;
  font-size: clamp(1.5rem, 3.5vw, 2.25rem);
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.03em;
  color: var(--platform-text);
}

.login-feature-scroll__summary-subtitle {
  margin: 0 0 24px;
  font-size: 15px;
  line-height: 1.65;
  color: var(--platform-text-secondary);
  max-width: 46em;
}

.login-feature-scroll__compare-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.login-feature-scroll__compare-row {
  display: grid;
  grid-template-columns: minmax(88px, 0.9fr) minmax(0, 1.2fr) minmax(0, 1.2fr);
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.55;
  background: rgba(255, 255, 255, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.28);
}

html[data-theme="dark"] .login-feature-scroll__compare-row {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
}

.login-feature-scroll__compare-row--head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--platform-text-tertiary);
  background: transparent;
  border-color: transparent;
  padding-top: 0;
}

.login-feature-scroll__compare-aspect {
  font-weight: 600;
  color: var(--platform-text);
}

.login-feature-scroll__compare-others {
  color: var(--platform-text-tertiary);
}

.login-feature-scroll__compare-ours {
  color: var(--platform-text);
  font-weight: 500;
}

.login-feature-scroll__summary-closing {
  margin: 24px 0 0;
  padding-top: 20px;
  border-top: 1px solid var(--platform-border, rgba(148, 163, 184, 0.22));
  font-size: 15px;
  line-height: 1.65;
  font-weight: 500;
  color: var(--platform-text);
}

.login-feature-scroll__pitch-bullets {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.login-feature-scroll__pitch-bullets li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--platform-text-secondary);
}

.login-feature-scroll__pitch-check {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--platform-accent);
}

.login-feature-scroll__section-inner {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 520px;
  padding: 8px 0 32px;
}

.login-feature-scroll__section-bg {
  position: absolute;
  inset: 0 12% 8% 0;
  border-radius: 28px;
  background: radial-gradient(
    ellipse 72% 58% at 18% 36%,
    var(--section-glow) 0%,
    transparent 68%
  );
  opacity: 0;
  transform: scale(0.92);
  transition:
    opacity 1s cubic-bezier(0.22, 1, 0.36, 1),
    transform 1.2s cubic-bezier(0.22, 1, 0.36, 1);
  pointer-events: none;
}

.login-feature-scroll__section--visible .login-feature-scroll__section-bg {
  opacity: 1;
  transform: scale(1);
}

.login-feature-scroll__section-inner {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 520px;
  padding: 8px 0 32px;
}

.login-feature-scroll__index {
  display: block;
  margin-bottom: 16px;
  font-size: clamp(2.5rem, 6vw, 4rem);
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.06em;
  background: linear-gradient(
    180deg,
    rgba(148, 163, 184, 0.28) 0%,
    rgba(148, 163, 184, 0.06) 100%
  );
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  opacity: 0;
  transform: translateY(24px);
  transition:
    opacity 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.05s,
    transform 0.8s cubic-bezier(0.22, 1, 0.36, 1) 0.05s;
}

.login-feature-scroll__visual {
  position: relative;
  width: 80px;
  height: 80px;
  margin-bottom: 22px;
  opacity: 0;
  transform: translateY(32px) scale(0.88);
  transition:
    opacity 0.75s cubic-bezier(0.22, 1, 0.36, 1) 0.12s,
    transform 0.9s cubic-bezier(0.22, 1, 0.36, 1) 0.12s;
}

.login-feature-scroll__icon-ring {
  position: absolute;
  inset: -16px;
  border-radius: 50%;
  opacity: 0.35;
  filter: blur(18px);
  animation: login-feature-scroll-orbit 6s ease-in-out infinite;
}

.login-feature-scroll__icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  border-radius: 22px;
  color: #fff;
  box-shadow:
    0 16px 40px rgba(15, 23, 42, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
  animation: login-feature-scroll-float 5s ease-in-out infinite;
}

.login-feature-scroll__title {
  margin: 0 0 12px;
  font-size: clamp(1.65rem, 3.8vw, 2.5rem);
  font-weight: 700;
  line-height: 1.12;
  letter-spacing: -0.04em;
  color: var(--platform-text);
  opacity: 0;
  transform: translateY(28px);
  transition:
    opacity 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.2s,
    transform 0.85s cubic-bezier(0.22, 1, 0.36, 1) 0.2s;
}

.login-feature-scroll__desc {
  margin: 0;
  max-width: 38ch;
  font-size: clamp(14px, 1.5vw, 17px);
  line-height: 1.65;
  color: var(--platform-text-secondary);
  opacity: 0;
  transform: translateY(24px);
  transition:
    opacity 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.32s,
    transform 0.85s cubic-bezier(0.22, 1, 0.36, 1) 0.32s;
}

.login-feature-scroll__section--visible .login-feature-scroll__index,
.login-feature-scroll__section--active .login-feature-scroll__index,
.login-feature-scroll__section--visible .login-feature-scroll__visual,
.login-feature-scroll__section--active .login-feature-scroll__visual,
.login-feature-scroll__section--visible .login-feature-scroll__title,
.login-feature-scroll__section--active .login-feature-scroll__title,
.login-feature-scroll__section--visible .login-feature-scroll__desc,
.login-feature-scroll__section--active .login-feature-scroll__desc,
.login-feature-scroll__section--visible .login-feature-scroll__pitch,
.login-feature-scroll__section--active .login-feature-scroll__pitch {
  opacity: 1;
  transform: translateY(0) scale(1);
}

.login-feature-scroll__section--visible .login-feature-scroll__pitch,
.login-feature-scroll__section--active .login-feature-scroll__pitch {
  transform: translateX(0);
}

.login-feature-scroll__section--active .login-feature-scroll__section-bg {
  opacity: 1;
  transform: scale(1.08);
}

@keyframes login-feature-scroll-sweep {
  0% {
    opacity: 0;
    transform: translateX(-120%);
  }
  20% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: translateX(120%);
  }
}

@keyframes login-feature-scroll-ring {
  0% {
    opacity: 0.8;
    transform: scale(0.85);
  }
  100% {
    opacity: 0;
    transform: scale(1.8);
  }
}

@keyframes login-feature-scroll-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

@keyframes login-feature-scroll-orbit {
  0%,
  100% {
    transform: scale(1) rotate(0deg);
    opacity: 0.35;
  }
  50% {
    transform: scale(1.12) rotate(12deg);
    opacity: 0.55;
  }
}

@keyframes login-feature-scroll-pulse {
  0%,
  100% {
    opacity: 0.45;
    transform: scaleX(0.85);
  }
  50% {
    opacity: 1;
    transform: scaleX(1);
  }
}

@media (max-width: 1100px) {
  .login-feature-scroll__section-layout {
    grid-template-columns: 1fr;
    max-width: 100%;
  }

  .login-feature-scroll__pitch {
    transform: translateY(24px);
  }

  .login-feature-scroll__section--visible .login-feature-scroll__pitch,
  .login-feature-scroll__section--active .login-feature-scroll__pitch {
    transform: translateY(0);
  }
}

@media (max-width: 900px) {
  .login-feature-scroll__rail {
    right: 8px;
    padding: 10px 6px;
    gap: 8px;
  }

  .login-feature-scroll__section,
  .login-feature-scroll__summary {
    padding-right: 36px;
  }

  .login-feature-scroll__head {
    padding-right: 36px;
  }
}

@media (max-width: 720px) {
  .login-feature-scroll__rail {
    display: none;
  }

  .login-feature-scroll__section,
  .login-feature-scroll__summary {
    padding-right: 0;
  }

  .login-feature-scroll__head {
    padding-right: 0;
  }
  .login-feature-scroll__compare-row,
  .login-feature-scroll__compare-row--head {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .login-feature-scroll__compare-row--head {
    display: none;
  }

  .login-feature-scroll__compare-aspect {
    font-size: 12px;
    color: var(--platform-accent);
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-feature-scroll__section-layout,
  .login-feature-scroll__summary {
    opacity: 1 !important;
    filter: none !important;
    transform: none !important;
    transition: none !important;
  }

  .login-feature-scroll__section-bg,
  .login-feature-scroll__index,
  .login-feature-scroll__visual,
  .login-feature-scroll__title,
  .login-feature-scroll__desc,
  .login-feature-scroll__pitch,
  .login-feature-scroll__summary {
    opacity: 1 !important;
    transform: none !important;
    transition: none !important;
  }

  .login-feature-scroll__icon,
  .login-feature-scroll__icon-ring,
  .login-feature-scroll__hint-line,
  .login-feature-scroll__section-sweep,
  .login-feature-scroll__rail-dot--active::after {
    animation: none !important;
  }
}
</style>
