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
const ontologyEl = ref(null);
const summaryEl = ref(null);

const allCards = computed(() => {
  const list = messages[locale.value]?.login?.showcaseCards;
  return Array.isArray(list) ? list : [];
});

const FEATURES_PER_SECTION = 4;
const MAX_SHOWCASE_FEATURES = 12;

/** 登录页展示 curated 核心功能（排除智能问数），每屏 4 项、共 3 屏 */
const cards = computed(() =>
  allCards.value
    .filter((card) => card.featureId !== "smart_data_query")
    .slice(0, MAX_SHOWCASE_FEATURES)
);

const featureSections = computed(() => {
  const list = cards.value;
  const sections = [];
  for (let i = 0; i < list.length; i += FEATURES_PER_SECTION) {
    sections.push(list.slice(i, i + FEATURES_PER_SECTION));
  }
  return sections;
});

function sectionRailLabel(section) {
  return section.map((card) => card.title).join(" · ");
}

function globalCardIndex(pageIndex, cardIndex) {
  return pageIndex * FEATURES_PER_SECTION + cardIndex;
}

const ontology = computed(() => messages[locale.value]?.login?.showcaseOntology || null);

const summary = computed(() => messages[locale.value]?.login?.showcaseSummary || null);

const SUMMARY_COMPARE_KEYS = ["dify", "coze", "fastgpt", "openclaw", "ours"];

const compareLabel = computed(
  () => messages[locale.value]?.login?.showcaseCompareLabel || "Why us"
);

const activeIndex = ref(-1);
const ontologyActive = ref(false);
const summaryActive = ref(false);
let revealObserver = null;
let activeObserver = null;

function scrollToSection(index) {
  const el = sectionEls.value[index];
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function scrollToOntology() {
  if (ontologyEl.value) {
    ontologyEl.value.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function scrollToSummary() {
  if (summaryEl.value) {
    summaryEl.value.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function resolveScrollRoot() {
  return document.querySelector(".login-page");
}

function isTailSectionVisible() {
  const el = summaryEl.value;
  if (!el) return false;
  const root = resolveScrollRoot();
  const rootRect = root?.getBoundingClientRect() ?? {
    top: 0,
    bottom: window.innerHeight,
  };
  const rect = el.getBoundingClientRect();
  return rect.top < rootRect.bottom - 24 && rect.bottom > rootRect.top + 24;
}

function isOntologySection(el) {
  return el?.classList?.contains("login-feature-scroll__ontology");
}

function isSummarySection(el) {
  return el?.classList?.contains("login-feature-scroll__summary");
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
  if (!sections.length && !ontologyEl.value && !summaryEl.value) return;

  const scrollRoot = resolveScrollRoot();
  const observerOptions = scrollRoot ? { root: scrollRoot } : {};

  revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          if (isOntologySection(entry.target)) {
            entry.target.classList.add("login-feature-scroll__ontology--visible");
          } else if (isSummarySection(entry.target)) {
            entry.target.classList.add("login-feature-scroll__summary--visible");
          } else {
            entry.target.classList.add("login-feature-scroll__section--visible");
          }
        }
      });
    },
    { threshold: 0.08, rootMargin: "0px 0px -4% 0px", ...observerOptions }
  );

  activeObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (isOntologySection(entry.target)) {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.03) {
            ontologyActive.value = true;
            summaryActive.value = false;
          } else if (!entry.isIntersecting) {
            ontologyActive.value = false;
          }
          return;
        }
        if (isSummarySection(entry.target)) {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.03) {
            summaryActive.value = true;
            ontologyActive.value = false;
          } else if (!entry.isIntersecting) {
            summaryActive.value = false;
          }
          return;
        }
        if (!entry.isIntersecting || entry.intersectionRatio < 0.35) return;
        if (isTailSectionVisible()) return;
        ontologyActive.value = false;
        summaryActive.value = false;
        const idx = Number(entry.target.dataset.index);
        if (!Number.isNaN(idx)) activeIndex.value = idx;
      });
    },
    {
      threshold: [0, 0.03, 0.1, 0.25, 0.35, 0.52],
      rootMargin: "-12% 0px -12% 0px",
      ...observerOptions,
    }
  );

  sections.forEach((el) => {
    revealObserver.observe(el);
    activeObserver.observe(el);
  });
  if (ontologyEl.value) {
    revealObserver.observe(ontologyEl.value);
    activeObserver.observe(ontologyEl.value);
  }
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
  ontologyActive.value = false;
  summaryActive.value = false;
  nextTick(bindObservers);
});

watch(featureSections, () => {
  sectionEls.value = [];
  activeIndex.value = -1;
  ontologyActive.value = false;
  summaryActive.value = false;
  nextTick(bindObservers);
});

watch([ontologyEl, summaryEl], () => nextTick(bindObservers));
</script>

<template>
  <div v-if="cards.length" class="login-feature-scroll">
    <nav class="login-feature-scroll__rail" aria-label="Feature sections">
      <button
        v-if="ontology"
        type="button"
        class="login-feature-scroll__rail-dot login-feature-scroll__rail-dot--ontology"
        :class="{ 'login-feature-scroll__rail-dot--active': ontologyActive }"
        :aria-label="ontology.title"
        :aria-current="ontologyActive ? 'true' : undefined"
        @click="scrollToOntology"
      />
      <button
        v-for="(section, index) in featureSections"
        :key="`rail-${section.map((card) => card.featureId).join('-')}`"
        type="button"
        class="login-feature-scroll__rail-dot"
        :class="{ 'login-feature-scroll__rail-dot--active': !ontologyActive && !summaryActive && activeIndex === index }"
        :aria-label="sectionRailLabel(section)"
        :aria-current="!ontologyActive && !summaryActive && activeIndex === index ? 'true' : undefined"
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
        <template v-else-if="ontologyActive && ontology">
          {{ ontology.label }}
        </template>
        <template v-else>
          {{ String((activeIndex >= 0 ? activeIndex : 0) + 1).padStart(2, "0") }}
          <span>/</span>
          {{ String(featureSections.length).padStart(2, "0") }}
        </template>
      </p>
    </div>

    <section
      v-if="ontology"
      ref="ontologyEl"
      class="login-feature-scroll__ontology login-snap-section"
      :class="{ 'login-feature-scroll__ontology--active': ontologyActive }"
    >
      <div class="login-feature-scroll__ontology-copy">
        <p class="login-feature-scroll__ontology-label">{{ ontology.label }}</p>
        <h2 class="login-feature-scroll__ontology-title">{{ ontology.title }}</h2>
        <p class="login-feature-scroll__ontology-body">{{ ontology.body }}</p>
      </div>
    </section>

    <section
      v-for="(section, pageIndex) in featureSections"
      :key="`page-${section.map((card) => card.featureId).join('-')}`"
      :ref="(el) => setSectionRef(el, pageIndex)"
      class="login-feature-scroll__section login-snap-section"
      :class="{
        'login-feature-scroll__section--past': activeIndex > pageIndex && !ontologyActive && !summaryActive,
        'login-feature-scroll__section--future': activeIndex < pageIndex && !ontologyActive && !summaryActive,
        'login-feature-scroll__section--active': activeIndex === pageIndex && !ontologyActive && !summaryActive,
      }"
      :data-index="pageIndex"
      :style="{
        '--section-glow': resolveGlow(section[0]?.icon),
        '--section-glow-alt': resolveGlow(section[1]?.icon || section[0]?.icon),
      }"
    >
      <div class="login-feature-scroll__section-bg" aria-hidden="true" />
      <div class="login-feature-scroll__section-sweep" aria-hidden="true" />
      <div class="login-feature-scroll__page-layout">
        <div class="login-feature-scroll__page-glass">
          <div class="login-feature-scroll__features-grid">
            <article
              v-for="(card, cardIndex) in section"
              :key="`${card.featureId}-${cardIndex}`"
              class="login-feature-scroll__feature-card"
              :style="{ '--feature-accent': resolveIconStyle(card.icon) }"
            >
              <header class="login-feature-scroll__feature-head">
                <span class="login-feature-scroll__index">
                  {{ String(globalCardIndex(pageIndex, cardIndex) + 1).padStart(2, "0") }}
                </span>
                <span
                  class="login-feature-scroll__icon"
                  :style="{ background: resolveIconStyle(card.icon) }"
                >
                  <n-icon :size="20" :component="resolveIcon(card.icon)" />
                </span>
                <div class="login-feature-scroll__feature-intro">
                  <h2 class="login-feature-scroll__title">{{ card.title }}</h2>
                  <p class="login-feature-scroll__desc">{{ card.desc }}</p>
                </div>
              </header>

              <div
                v-if="card.pitch || card.bullets?.length"
                class="login-feature-scroll__pitch"
              >
                <p v-if="card.pitch" class="login-feature-scroll__pitch-hook">{{ card.pitch }}</p>
                <ul v-if="card.bullets?.length" class="login-feature-scroll__pitch-bullets">
                  <li v-for="(bullet, bi) in card.bullets.slice(0, 2)" :key="bi">
                    <n-icon :size="13" :component="CheckmarkCircleOutline" class="login-feature-scroll__pitch-check" />
                    <span>{{ bullet }}</span>
                  </li>
                </ul>
              </div>
            </article>
          </div>
        </div>
      </div>
    </section>

    <section
      v-if="summary"
      ref="summaryEl"
      class="login-feature-scroll__summary login-snap-section"
      :class="{ 'login-feature-scroll__summary--active': summaryActive }"
    >
      <div class="login-feature-scroll__summary-inner">
        <p class="login-feature-scroll__summary-label">{{ compareLabel }}</p>
        <h2 class="login-feature-scroll__summary-title">{{ summary.title }}</h2>
        <p class="login-feature-scroll__summary-subtitle">{{ summary.subtitle }}</p>

        <div class="login-feature-scroll__compare-wrap">
          <table class="login-feature-scroll__compare-table">
            <thead>
              <tr>
                <th scope="col" class="login-feature-scroll__compare-feature-col">
                  {{ summary.columns?.feature }}
                </th>
                <th
                  v-for="key in SUMMARY_COMPARE_KEYS"
                  :key="key"
                  scope="col"
                  :class="{ 'login-feature-scroll__compare-ours-col': key === 'ours' }"
                >
                  {{ summary.columns?.[key] }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, ri) in summary.rows" :key="ri">
                <th scope="row" class="login-feature-scroll__compare-feature">{{ row.feature }}</th>
                <td
                  v-for="key in SUMMARY_COMPARE_KEYS"
                  :key="key"
                  :class="{ 'login-feature-scroll__compare-ours-col': key === 'ours' }"
                >
                  <n-icon
                    v-if="row[key]"
                    :size="18"
                    :component="CheckmarkCircleOutline"
                    class="login-feature-scroll__compare-yes"
                  />
                  <span v-else class="login-feature-scroll__compare-no">—</span>
                </td>
              </tr>
            </tbody>
          </table>
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
  z-index: 1;
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

.login-feature-scroll__rail-dot--ontology {
  width: 6px;
  height: 6px;
}

.login-feature-scroll__rail-dot--summary {
  width: 6px;
  height: 6px;
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
  justify-content: center;
  margin: 0 0 8px;
  padding: 0 max(56px, env(safe-area-inset-right, 0px)) 0 max(56px, env(safe-area-inset-left, 0px));
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
  justify-content: center;
  scroll-snap-align: start;
  scroll-snap-stop: normal;
  isolation: isolate;
  box-sizing: border-box;
  padding: 24px max(56px, env(safe-area-inset-right, 0px)) 24px max(56px, env(safe-area-inset-left, 0px));
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

.login-feature-scroll__page-layout {
  position: relative;
  z-index: 1;
  width: min(920px, 100%);
  max-width: min(920px, calc(100vw - 112px));
  margin: 0 auto;
  padding: 0;
  opacity: 0.28;
  filter: blur(10px);
  transform: scale(0.9) translateY(48px);
  transition:
    opacity 0.65s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.75s cubic-bezier(0.22, 1, 0.36, 1),
    filter 0.65s cubic-bezier(0.22, 1, 0.36, 1);
}

.login-feature-scroll__page-glass {
  position: relative;
  padding: 18px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.34);
  backdrop-filter: blur(24px) saturate(170%);
  -webkit-backdrop-filter: blur(24px) saturate(170%);
  border: 1px solid rgba(255, 255, 255, 0.48);
  box-shadow:
    0 16px 48px rgba(91, 120, 200, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.58);
  overflow: hidden;
}

html[data-theme="dark"] .login-feature-scroll__page-glass {
  background: rgba(22, 22, 32, 0.58);
  border-color: rgba(147, 197, 253, 0.14);
  box-shadow:
    0 16px 48px rgba(0, 0, 0, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.login-feature-scroll__features-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  min-width: 0;
}

.login-feature-scroll__feature-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.32);
  opacity: 0;
  transform: translateY(16px);
  transition:
    opacity 0.75s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.85s cubic-bezier(0.22, 1, 0.36, 1);
}

.login-feature-scroll__feature-card:nth-child(2) {
  transition-delay: 0.05s;
}

.login-feature-scroll__feature-card:nth-child(3) {
  transition-delay: 0.1s;
}

.login-feature-scroll__feature-card:nth-child(4) {
  transition-delay: 0.15s;
}

html[data-theme="dark"] .login-feature-scroll__feature-card {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(147, 197, 253, 0.1);
}

.login-feature-scroll__feature-head {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.login-feature-scroll__section--past .login-feature-scroll__page-layout {
  transform: scale(0.88) translateY(-56px);
}

.login-feature-scroll__section--future .login-feature-scroll__page-layout {
  transform: scale(0.9) translateY(56px);
}

.login-feature-scroll__section--active .login-feature-scroll__page-layout,
.login-feature-scroll__section--visible.login-feature-scroll__section--active .login-feature-scroll__page-layout {
  opacity: 1;
  filter: blur(0);
  transform: scale(1) translateY(0);
}

.login-feature-scroll__section--visible .login-feature-scroll__feature-card,
.login-feature-scroll__section--active .login-feature-scroll__feature-card {
  opacity: 1;
  transform: translateY(0);
}

.login-feature-scroll__feature-intro {
  min-width: 0;
}

.login-feature-scroll__pitch {
  min-width: 0;
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.24);
  opacity: 1;
  transform: none;
  transition: none;
}

html[data-theme="dark"] .login-feature-scroll__pitch {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(147, 197, 253, 0.1);
  box-shadow: none;
}

.login-feature-scroll__pitch-hook {
  margin: 0 0 4px;
  font-size: 0.9rem;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.03em;
  background: var(--feature-accent, linear-gradient(135deg, #60a5fa, #2563eb));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.login-feature-scroll__pitch-value {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--platform-text);
}

.login-feature-scroll__summary {
  position: relative;
  z-index: 3;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  width: 100%;
  scroll-snap-align: none;
  scroll-snap-stop: normal;
  box-sizing: border-box;
  padding: calc(36px + 24px) max(56px, env(safe-area-inset-right, 0px)) 96px max(56px, env(safe-area-inset-left, 0px));
}

.login-feature-scroll__summary-inner {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: min(960px, calc(100vw - 72px));
  margin: 0 auto;
  padding: 28px 24px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(20px) saturate(170%);
  -webkit-backdrop-filter: blur(20px) saturate(170%);
  border: 1px solid rgba(255, 255, 255, 0.55);
  box-shadow:
    0 16px 48px rgba(91, 120, 200, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

html[data-theme="dark"] .login-feature-scroll__summary-inner {
  background: rgba(22, 22, 32, 0.88);
  border-color: rgba(147, 197, 253, 0.18);
  box-shadow:
    0 16px 48px rgba(0, 0, 0, 0.36),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.login-feature-scroll__summary-label {
  margin: 0 0 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  text-align: center;
  color: var(--platform-accent);
}

.login-feature-scroll__summary-title {
  margin: 0 0 12px;
  font-size: clamp(1.5rem, 3.5vw, 2.25rem);
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.03em;
  text-align: center;
  color: var(--platform-text);
}

.login-feature-scroll__summary-subtitle {
  margin: 0 auto 24px;
  font-size: 15px;
  line-height: 1.65;
  text-align: center;
  color: var(--platform-text-secondary);
  max-width: 46em;
}

.login-feature-scroll__ontology {
  position: relative;
  z-index: 1;
  min-height: calc(100dvh - 36px);
  display: flex;
  align-items: center;
  justify-content: center;
  scroll-snap-align: start;
  scroll-snap-stop: normal;
  box-sizing: border-box;
  padding: 24px max(56px, env(safe-area-inset-right, 0px)) 24px max(56px, env(safe-area-inset-left, 0px));
}

.login-feature-scroll__ontology-copy {
  width: 100%;
  max-width: min(720px, calc(100vw - 112px));
  margin: 0 auto;
  opacity: 0;
  filter: blur(10px);
  transform: translateY(48px);
  transition:
    opacity 0.65s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.75s cubic-bezier(0.22, 1, 0.36, 1),
    filter 0.65s cubic-bezier(0.22, 1, 0.36, 1);
}

.login-feature-scroll__ontology--visible .login-feature-scroll__ontology-copy,
.login-feature-scroll__ontology--active .login-feature-scroll__ontology-copy {
  opacity: 1;
  filter: blur(0);
  transform: translateY(0);
}

.login-feature-scroll__ontology-label {
  margin: 0 0 14px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--platform-text-tertiary);
}

.login-feature-scroll__ontology-title {
  margin: 0 0 16px;
  font-size: clamp(1.65rem, 3.8vw, 2.5rem);
  font-weight: 700;
  line-height: 1.12;
  letter-spacing: -0.04em;
  color: var(--platform-text);
}

.login-feature-scroll__ontology-body {
  margin: 0;
  font-size: clamp(14px, 1.5vw, 16px);
  line-height: 1.75;
  color: var(--platform-text-secondary);
  max-width: 42em;
}

.login-feature-scroll__compare-wrap {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 100%;
  margin: 0 auto;
  overflow-x: auto;
  overflow-y: visible;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-x pan-y;
}

.login-feature-scroll__compare-table {
  width: 100%;
  min-width: 640px;
  margin: 0 auto;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
  line-height: 1.55;
}

.login-feature-scroll__compare-table thead th {
  padding: 0 10px 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-align: center;
  color: var(--platform-text-tertiary);
  border-bottom: 1px solid var(--platform-border, rgba(148, 163, 184, 0.22));
}

.login-feature-scroll__compare-feature-col {
  text-align: left !important;
}

.login-feature-scroll__compare-table tbody tr + tr th,
.login-feature-scroll__compare-table tbody tr + tr td {
  border-top: 1px solid var(--platform-border, rgba(148, 163, 184, 0.16));
}

.login-feature-scroll__compare-table tbody th,
.login-feature-scroll__compare-table tbody td {
  padding: 12px 10px;
  vertical-align: middle;
}

.login-feature-scroll__compare-table tbody td {
  text-align: center;
}

.login-feature-scroll__compare-table tbody tr {
  background: rgba(255, 255, 255, 0.35);
}

html[data-theme="dark"] .login-feature-scroll__compare-table tbody tr {
  background: rgba(255, 255, 255, 0.04);
}

.login-feature-scroll__compare-table tbody tr:first-child th,
.login-feature-scroll__compare-table tbody tr:first-child td {
  padding-top: 14px;
}

.login-feature-scroll__compare-feature {
  font-weight: 600;
  text-align: left;
  color: var(--platform-text);
  white-space: nowrap;
}

.login-feature-scroll__compare-ours-col {
  background: rgba(99, 102, 241, 0.06);
}

html[data-theme="dark"] .login-feature-scroll__compare-ours-col {
  background: rgba(129, 140, 248, 0.1);
}

.login-feature-scroll__compare-table thead .login-feature-scroll__compare-ours-col {
  color: var(--platform-accent);
}

.login-feature-scroll__compare-yes {
  color: var(--platform-accent);
  vertical-align: middle;
}

.login-feature-scroll__compare-no {
  color: var(--platform-text-tertiary);
  font-size: 14px;
  line-height: 1;
}

.login-feature-scroll__summary-closing {
  margin: 24px auto 0;
  padding-top: 20px;
  border-top: 1px solid var(--platform-border, rgba(148, 163, 184, 0.22));
  font-size: 15px;
  line-height: 1.65;
  font-weight: 500;
  text-align: center;
  color: var(--platform-text);
  max-width: 46em;
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
  gap: 5px;
  font-size: 11px;
  line-height: 1.4;
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
  inset: 0 8% 8% 0;
  border-radius: 28px;
  background:
    radial-gradient(
      ellipse 52% 48% at 22% 38%,
      var(--section-glow) 0%,
      transparent 68%
    ),
    radial-gradient(
      ellipse 52% 48% at 72% 58%,
      var(--section-glow-alt) 0%,
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
  margin: 0;
  font-size: 1.1rem;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.06em;
  background: linear-gradient(
    180deg,
    rgba(148, 163, 184, 0.38) 0%,
    rgba(148, 163, 184, 0.08) 100%
  );
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  opacity: 1;
  transform: none;
  transition: none;
}

.login-feature-scroll__icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  color: #fff;
  flex-shrink: 0;
  box-shadow:
    0 10px 24px rgba(15, 23, 42, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
}

.login-feature-scroll__title {
  margin: 0 0 2px;
  font-size: clamp(1rem, 1.6vw, 1.15rem);
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.03em;
  color: var(--platform-text);
  opacity: 1;
  transform: none;
  transition: none;
}

.login-feature-scroll__desc {
  margin: 0;
  max-width: none;
  font-size: 12px;
  line-height: 1.45;
  color: var(--platform-text-secondary);
  opacity: 1;
  transform: none;
  transition: none;
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
  .login-feature-scroll__page-layout {
    max-width: 100%;
  }

  .login-feature-scroll__features-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .login-feature-scroll__rail {
    right: 8px;
    padding: 10px 6px;
    gap: 8px;
  }

  .login-feature-scroll__section,
  .login-feature-scroll__ontology,
  .login-feature-scroll__summary {
    padding-inline: max(40px, env(safe-area-inset-left, 0px)) max(40px, env(safe-area-inset-right, 0px));
  }

  .login-feature-scroll__head {
    padding-inline: max(40px, env(safe-area-inset-left, 0px)) max(40px, env(safe-area-inset-right, 0px));
  }
}

@media (max-width: 720px) {
  .login-feature-scroll__rail {
    display: none;
  }

  .login-feature-scroll__section,
  .login-feature-scroll__ontology,
  .login-feature-scroll__summary {
    padding-inline: max(16px, env(safe-area-inset-left, 0px)) max(16px, env(safe-area-inset-right, 0px));
  }

  .login-feature-scroll__head {
    padding-inline: max(16px, env(safe-area-inset-left, 0px)) max(16px, env(safe-area-inset-right, 0px));
  }

  .login-feature-scroll__page-layout {
    max-width: min(920px, calc(100vw - 32px));
  }

  .login-feature-scroll__compare-table {
    min-width: 580px;
  }

  .login-feature-scroll__compare-feature {
    white-space: normal;
    font-size: 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-feature-scroll__page-layout,
  .login-feature-scroll__ontology-copy,
  .login-feature-scroll__feature-card {
    opacity: 1 !important;
    filter: none !important;
    transform: none !important;
    transition: none !important;
  }

  .login-feature-scroll__section-bg,
  .login-feature-scroll__index,
  .login-feature-scroll__title,
  .login-feature-scroll__desc,
  .login-feature-scroll__pitch {
    opacity: 1 !important;
    transform: none !important;
    transition: none !important;
  }

  .login-feature-scroll__hint-line,
  .login-feature-scroll__section-sweep,
  .login-feature-scroll__rail-dot--active::after {
    animation: none !important;
  }
}
</style>
