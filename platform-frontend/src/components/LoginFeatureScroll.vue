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
  GlobeOutline,
} from "@vicons/ionicons5";
import { useAppPreferences } from "../composables/useAppPreferences";
import { messages } from "../locales";

const { locale } = useAppPreferences();

const TOTAL_SHOWCASE_PAGES = 6;
const SECTION_ORDER = ["vision", "ontology", "skills", "features", "compare"];

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
  globe: GlobeOutline,
};

const iconStyles = {
  "document-text": "linear-gradient(135deg, #60a5fa 0%, #2563eb 100%)",
  search: "var(--platform-accent-gradient)",
  sparkles: "linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)",
  language: "linear-gradient(135deg, #22d3ee 0%, #0891b2 100%)",
  "git-compare": "linear-gradient(135deg, #818cf8 0%, #4f46e5 100%)",
  "stats-chart": "linear-gradient(135deg, #34d399 0%, #059669 100%)",
  analytics: "linear-gradient(135deg, #2dd4bf 0%, #0d9488 100%)",
  "trending-up": "linear-gradient(135deg, #fb923c 0%, #ea580c 100%)",
  leaf: "linear-gradient(135deg, #4ade80 0%, #16a34a 100%)",
  wallet: "linear-gradient(135deg, #f472b6 0%, #db2777 100%)",
  mic: "var(--platform-accent-gradient)",
  scan: "linear-gradient(135deg, #38bdf8 0%, #0284c7 100%)",
  "git-network": "linear-gradient(135deg, #e879f9 0%, #c026d3 100%)",
  create: "linear-gradient(135deg, #f87171 0%, #dc2626 100%)",
  newspaper: "linear-gradient(135deg, #94a3b8 0%, #475569 100%)",
  chatbubbles: "linear-gradient(135deg, #86efac 0%, #15803d 100%)",
  todos: "linear-gradient(135deg, #fcd34d 0%, #d97706 100%)",
  globe: "linear-gradient(135deg, #38bdf8 0%, #0369a1 100%)",
};

const visionEl = ref(null);
const ontologyEl = ref(null);
const skillsEl = ref(null);
const featuresEl = ref(null);
const summaryEl = ref(null);

const dict = computed(() => messages[locale.value] || messages.zh);

const vision = computed(() => dict.value?.login?.showcaseVision || null);
const ontology = computed(() => dict.value?.login?.showcaseOntology || null);
const skills = computed(() => dict.value?.login?.showcaseSkills || null);
const featuresMeta = computed(() => dict.value?.login?.showcaseFeatures || null);
const summary = computed(() => dict.value?.login?.showcaseSummary || null);

const allCards = computed(() => {
  const list = dict.value?.login?.showcaseCards;
  return Array.isArray(list) ? list : [];
});

const cards = computed(() => allCards.value.slice(0, 16));

const SUMMARY_COMPARE_KEYS = ["dify", "coze", "fastgpt", "openclaw", "ours"];

const compareLabel = computed(
  () => dict.value?.login?.showcaseCompareLabel || "Why us"
);

const railItems = computed(() => {
  const items = [];
  if (vision.value) items.push({ id: "vision", label: vision.value.label, el: () => visionEl.value });
  if (ontology.value) items.push({ id: "ontology", label: ontology.value.label, el: () => ontologyEl.value });
  if (skills.value) items.push({ id: "skills", label: skills.value.label, el: () => skillsEl.value });
  if (cards.value.length) items.push({ id: "features", label: featuresMeta.value?.label || "Features", el: () => featuresEl.value });
  if (summary.value) items.push({ id: "compare", label: compareLabel.value, el: () => summaryEl.value });
  return items;
});

const activeSection = ref(null);

const counterText = computed(() => {
  const idx = SECTION_ORDER.indexOf(activeSection.value);
  const page = idx >= 0 ? idx + 2 : 2;
  return `${String(page).padStart(2, "0")} / ${String(TOTAL_SHOWCASE_PAGES).padStart(2, "0")}`;
});

const counterLabel = computed(() => {
  const item = railItems.value.find((r) => r.id === activeSection.value);
  return item?.label || "";
});

let revealObserver = null;
let activeObserver = null;

function scrollToSection(id) {
  const item = railItems.value.find((r) => r.id === id);
  const el = item?.el?.();
  if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
}

function resolveScrollRoot() {
  return document.querySelector(".login-page");
}

function sectionId(el) {
  return el?.dataset?.section || null;
}

function resolveIcon(key) {
  return iconMap[key] || SparklesOutline;
}

function resolveIconStyle(key) {
  return iconStyles[key] || iconStyles.sparkles;
}

function collectSectionEls() {
  return [visionEl.value, ontologyEl.value, skillsEl.value, featuresEl.value, summaryEl.value].filter(Boolean);
}

function bindObservers() {
  revealObserver?.disconnect();
  activeObserver?.disconnect();

  const sections = collectSectionEls();
  if (!sections.length) return;

  const scrollRoot = resolveScrollRoot();
  const observerOptions = scrollRoot ? { root: scrollRoot } : {};

  revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("login-feature-scroll__page--visible");
        }
      });
    },
    { threshold: 0.08, rootMargin: "0px 0px -4% 0px", ...observerOptions }
  );

  activeObserver = new IntersectionObserver(
    (entries) => {
      let bestId = null;
      let bestRatio = 0;
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const id = sectionId(entry.target);
        if (!id || entry.intersectionRatio <= bestRatio) return;
        if (entry.intersectionRatio >= 0.25) {
          bestRatio = entry.intersectionRatio;
          bestId = id;
        }
      });
      if (bestId) activeSection.value = bestId;
    },
    {
      threshold: [0.25, 0.5, 0.75],
      rootMargin: "-8% 0px -8% 0px",
      ...observerOptions,
    }
  );

  sections.forEach((el) => {
    revealObserver.observe(el);
    activeObserver.observe(el);
  });
}

onMounted(() => nextTick(bindObservers));

onUnmounted(() => {
  revealObserver?.disconnect();
  activeObserver?.disconnect();
});

watch(locale, () => {
  activeSection.value = null;
  nextTick(bindObservers);
});

watch(cards, () => nextTick(bindObservers));
</script>

<template>
  <div v-if="railItems.length" class="login-feature-scroll">
    <nav class="login-feature-scroll__rail" aria-label="Showcase sections">
      <button
        v-for="item in railItems"
        :key="item.id"
        type="button"
        class="login-feature-scroll__rail-dot"
        :class="{ 'login-feature-scroll__rail-dot--active': activeSection === item.id }"
        :aria-label="item.label"
        :aria-current="activeSection === item.id ? 'true' : undefined"
        @click="scrollToSection(item.id)"
      />
    </nav>

    <div class="login-feature-scroll__head">
      <p class="login-feature-scroll__counter" aria-hidden="true">
        <span class="login-feature-scroll__counter-page">{{ counterText }}</span>
        <span v-if="counterLabel" class="login-feature-scroll__counter-label">{{ counterLabel }}</span>
      </p>
    </div>

    <!-- 第 2 页：产品愿景 -->
    <section
      v-if="vision"
      ref="visionEl"
      data-section="vision"
      class="login-feature-scroll__page login-snap-section"
      :class="{ 'login-feature-scroll__page--active': activeSection === 'vision' }"
    >
      <div class="login-feature-scroll__content">
        <p class="login-feature-scroll__page-label">{{ vision.label }}</p>
        <h2 class="login-feature-scroll__page-title">{{ vision.title }}</h2>
        <p v-if="vision.body" class="login-feature-scroll__page-body">{{ vision.body }}</p>
      </div>
    </section>

    <!-- 第 3 页：本体论 -->
    <section
      v-if="ontology"
      ref="ontologyEl"
      data-section="ontology"
      class="login-feature-scroll__page login-snap-section"
      :class="{ 'login-feature-scroll__page--active': activeSection === 'ontology' }"
    >
      <div class="login-feature-scroll__content">
        <p class="login-feature-scroll__page-label">{{ ontology.label }}</p>
        <h2 class="login-feature-scroll__page-title">{{ ontology.title }}</h2>
        <p class="login-feature-scroll__page-body">{{ ontology.body }}</p>
      </div>
    </section>

    <!-- 第 4 页：Agent Skills -->
    <section
      v-if="skills"
      ref="skillsEl"
      data-section="skills"
      class="login-feature-scroll__page login-snap-section"
      :class="{ 'login-feature-scroll__page--active': activeSection === 'skills' }"
    >
      <div class="login-feature-scroll__content">
        <p class="login-feature-scroll__page-label">{{ skills.label }}</p>
        <h2 class="login-feature-scroll__page-title">{{ skills.title }}</h2>
        <p class="login-feature-scroll__page-body">{{ skills.body }}</p>

        <div v-if="skills.applications?.length" class="login-feature-scroll__section-block">
          <p class="login-feature-scroll__block-label">{{ skills.applicationsTitle }}</p>
          <div class="login-feature-scroll__tile-grid login-feature-scroll__tile-grid--3">
            <article v-for="(item, i) in skills.applications" :key="`app-${i}`" class="login-feature-scroll__tile login-feature-scroll__tile--card">
              <header class="login-feature-scroll__card-head">
                <span class="login-feature-scroll__card-icon" :style="{ background: resolveIconStyle(item.icon) }">
                  <n-icon :size="18" :component="resolveIcon(item.icon)" />
                </span>
                <h3 class="login-feature-scroll__tile-title">{{ item.title }}</h3>
              </header>
              <p class="login-feature-scroll__tile-text">{{ item.desc }}</p>
            </article>
          </div>
        </div>

        <div v-if="skills.sharing?.length" class="login-feature-scroll__section-block">
          <p class="login-feature-scroll__block-label">{{ skills.sharingTitle }}</p>
          <div class="login-feature-scroll__tile-grid login-feature-scroll__tile-grid--3">
            <article v-for="(item, i) in skills.sharing" :key="`share-${i}`" class="login-feature-scroll__tile login-feature-scroll__tile--card">
              <header class="login-feature-scroll__card-head">
                <span class="login-feature-scroll__card-icon" :style="{ background: resolveIconStyle(item.icon) }">
                  <n-icon :size="18" :component="resolveIcon(item.icon)" />
                </span>
                <h3 class="login-feature-scroll__tile-title">{{ item.title }}</h3>
              </header>
              <p class="login-feature-scroll__tile-text">{{ item.desc }}</p>
            </article>
          </div>
        </div>
      </div>
    </section>

    <!-- 第 5 页：核心功能 4×4 -->
    <section
      v-if="cards.length"
      ref="featuresEl"
      data-section="features"
      class="login-feature-scroll__page login-feature-scroll__page--features login-snap-section"
      :class="{ 'login-feature-scroll__page--active': activeSection === 'features' }"
    >
      <div class="login-feature-scroll__features-shell">
        <header class="login-feature-scroll__features-head">
          <p class="login-feature-scroll__page-label">{{ featuresMeta?.label }}</p>
          <h2 class="login-feature-scroll__page-title">{{ featuresMeta?.title }}</h2>
          <p v-if="featuresMeta?.subtitle" class="login-feature-scroll__page-subtitle">{{ featuresMeta.subtitle }}</p>
        </header>
        <div class="login-feature-scroll__tile-grid login-feature-scroll__tile-grid--features">
          <article
            v-for="(card, i) in cards"
            :key="`${card.featureId}-${i}`"
            class="login-feature-scroll__tile login-feature-scroll__tile--feature login-feature-scroll__tile--square"
          >
            <span class="login-feature-scroll__card-icon" :style="{ background: resolveIconStyle(card.icon) }">
              <n-icon :size="18" :component="resolveIcon(card.icon)" />
            </span>
            <h3 class="login-feature-scroll__tile-title">{{ card.title }}</h3>
            <p class="login-feature-scroll__tile-text">{{ card.desc }}</p>
          </article>
        </div>
      </div>
    </section>

    <!-- 第 6 页：对比 -->
    <section
      v-if="summary"
      ref="summaryEl"
      data-section="compare"
      class="login-feature-scroll__page login-feature-scroll__page--tall login-snap-section"
      :class="{ 'login-feature-scroll__page--active': activeSection === 'compare' }"
    >
      <div class="login-feature-scroll__glass">
        <p class="login-feature-scroll__page-label">{{ compareLabel }}</p>
        <h2 class="login-feature-scroll__page-title">{{ summary.title }}</h2>
        <p class="login-feature-scroll__page-subtitle">{{ summary.subtitle }}</p>

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

        <p v-if="summary.closing" class="login-feature-scroll__page-footnote">
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
  border-color: var(--platform-accent-border-soft);
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

.login-feature-scroll__counter {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.06em;
  color: var(--platform-text-tertiary);
}

.login-feature-scroll__counter-label {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.login-feature-scroll__page {
  position: relative;
  z-index: 1;
  min-height: calc(100dvh - 36px);
  display: flex;
  align-items: center;
  justify-content: center;
  scroll-snap-align: center;
  scroll-snap-stop: normal;
  box-sizing: border-box;
  padding: 20px max(56px, env(safe-area-inset-right, 0px)) 20px max(56px, env(safe-area-inset-left, 0px));
}

.login-feature-scroll__page--tall {
  min-height: auto;
  align-items: flex-start;
  padding-top: 32px;
  padding-bottom: 48px;
  scroll-snap-align: start;
}

.login-feature-scroll__content,
.login-feature-scroll__glass {
  width: 100%;
  max-width: min(920px, calc(100vw - 112px));
  margin: 0 auto;
  padding: 24px 22px;
  opacity: 0;
  transform: translateY(20px);
  transition:
    opacity 0.5s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}

.login-feature-scroll__content--wide {
  max-width: min(1080px, calc(100vw - 112px));
}

.login-feature-scroll__glass {
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(16px) saturate(165%);
  -webkit-backdrop-filter: blur(16px) saturate(165%);
  border: 1px solid rgba(255, 255, 255, 0.38);
  box-shadow:
    0 16px 48px rgba(91, 120, 200, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.42);
}

html[data-theme="dark"] .login-feature-scroll__glass {
  background: rgba(22, 22, 32, 0.42);
  border-color: var(--platform-accent-border);
  box-shadow:
    0 16px 48px rgba(0, 0, 0, 0.26),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.login-feature-scroll__page--visible .login-feature-scroll__content,
.login-feature-scroll__page--active .login-feature-scroll__content,
.login-feature-scroll__page--visible .login-feature-scroll__glass,
.login-feature-scroll__page--active .login-feature-scroll__glass {
  opacity: 1;
  transform: translateY(0);
}

.login-feature-scroll__page-label {
  margin: 0 0 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--platform-accent);
}

.login-feature-scroll__page-title {
  margin: 0 0 10px;
  font-size: clamp(1.45rem, 3.2vw, 2rem);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.04em;
  color: var(--platform-text);
}

.login-feature-scroll__page-subtitle {
  margin: -2px 0 12px;
  font-size: clamp(13px, 1.4vw, 15px);
  font-weight: 600;
  line-height: 1.45;
  color: var(--platform-text-secondary);
}

.login-feature-scroll__page-body {
  margin: 0;
  font-size: clamp(14px, 1.45vw, 15px);
  line-height: 1.7;
  color: var(--platform-text-secondary);
}

.login-feature-scroll__page-footnote {
  margin: 20px 0 0;
  padding-top: 16px;
  border-top: 1px solid var(--platform-border, rgba(148, 163, 184, 0.2));
  font-size: 14px;
  line-height: 1.65;
  font-weight: 500;
  color: var(--platform-text);
}

.login-feature-scroll__section-block {
  margin-top: 20px;
}

.login-feature-scroll__section-block + .login-feature-scroll__section-block,
.login-feature-scroll__section-block + .login-feature-scroll__tile-grid {
  margin-top: 16px;
}

.login-feature-scroll__page-body + .login-feature-scroll__tile-grid,
.login-feature-scroll__page-body + .login-feature-scroll__bullet-list,
.login-feature-scroll__page-body + .login-feature-scroll__text-list {
  margin-top: 18px;
}

.login-feature-scroll__page-body + .login-feature-scroll__text-block {
  margin-top: 16px;
}

.login-feature-scroll__text-block {
  margin-top: 18px;
}

.login-feature-scroll__text-block + .login-feature-scroll__text-block {
  margin-top: 14px;
}

.login-feature-scroll__text-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.login-feature-scroll__text-list li {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--platform-text-secondary);
}

.login-feature-scroll__text-list--checks li {
  flex-direction: row;
  align-items: flex-start;
  gap: 8px;
}

.login-feature-scroll__text-term {
  font-weight: 700;
  color: var(--platform-text);
}

.login-feature-scroll__text-detail {
  color: var(--platform-text-secondary);
}

.login-feature-scroll__text-list--checks .login-feature-scroll__text-term {
  margin-right: 0.35em;
}

.login-feature-scroll__text-check {
  flex-shrink: 0;
  margin-top: 3px;
  color: var(--platform-accent);
}

.login-feature-scroll__block-label {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--platform-text-tertiary);
}

.login-feature-scroll__block-desc {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--platform-text-secondary);
}

.login-feature-scroll__chain-pills {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 4px;
}

.login-feature-scroll__chain-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--platform-text);
  background: rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(12px) saturate(160%);
  -webkit-backdrop-filter: blur(12px) saturate(160%);
  border: 1px solid rgba(255, 255, 255, 0.32);
  box-shadow:
    0 4px 14px rgba(91, 120, 200, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
}

html[data-theme="dark"] .login-feature-scroll__chain-pill {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--platform-accent-border-soft);
  box-shadow:
    0 4px 14px rgba(0, 0, 0, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.login-feature-scroll__chain-arrow {
  align-self: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--platform-text-tertiary);
  user-select: none;
}

.login-feature-scroll__page-subtitle + .login-feature-scroll__tile-grid--features {
  margin-top: 16px;
}

.login-feature-scroll__tile-grid {
  display: grid;
  gap: 10px;
}

.login-feature-scroll__tile-grid--3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.login-feature-scroll__tile-grid--features {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.login-feature-scroll__section-block + .login-feature-scroll__tile-grid,
.login-feature-scroll__page-body + .login-feature-scroll__tile-grid {
  margin-top: 14px;
}

.login-feature-scroll__tile {
  min-width: 0;
}

.login-feature-scroll__tile--card,
.login-feature-scroll__tile--feature {
  background: rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(16px) saturate(170%);
  -webkit-backdrop-filter: blur(16px) saturate(170%);
  border: 1px solid rgba(255, 255, 255, 0.3);
  box-shadow:
    0 8px 22px rgba(91, 120, 200, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.38);
}

html[data-theme="dark"] .login-feature-scroll__tile--card,
html[data-theme="dark"] .login-feature-scroll__tile--feature {
  background: rgba(255, 255, 255, 0.04);
  border-color: var(--platform-accent-border-soft);
  box-shadow:
    0 8px 22px rgba(0, 0, 0, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.login-feature-scroll__tile--card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border-radius: 16px;
}

.login-feature-scroll__card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.login-feature-scroll__tile--feature {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  border-radius: 14px;
}

.login-feature-scroll__feature-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.login-feature-scroll__feature-head .login-feature-scroll__tile-title {
  margin: 0;
}

.login-feature-scroll__card-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  color: #fff;
  box-shadow:
    0 8px 18px rgba(15, 23, 42, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
}

.login-feature-scroll__tile--feature .login-feature-scroll__card-icon {
  width: 28px;
  height: 28px;
  border-radius: 9px;
}

.login-feature-scroll__tile-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: -0.02em;
  color: var(--platform-text);
}

.login-feature-scroll__tile-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--platform-text-secondary);
}

.login-feature-scroll__tile--feature .login-feature-scroll__tile-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.login-feature-scroll__compare-wrap {
  width: 100%;
  margin-top: 16px;
  overflow-x: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
}

.login-feature-scroll__compare-table {
  width: 100%;
  min-width: 640px;
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
  padding: 11px 10px;
  vertical-align: middle;
}

.login-feature-scroll__compare-table tbody td {
  text-align: center;
}

.login-feature-scroll__compare-table tbody tr {
  background: rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

html[data-theme="dark"] .login-feature-scroll__compare-table tbody tr {
  background: rgba(255, 255, 255, 0.03);
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

@media (max-width: 1100px) {
  .login-feature-scroll__tile-grid--features {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .login-feature-scroll__rail {
    right: 8px;
    padding: 10px 6px;
    gap: 8px;
  }

  .login-feature-scroll__page {
    padding-inline: max(40px, env(safe-area-inset-left, 0px)) max(40px, env(safe-area-inset-right, 0px));
  }

  .login-feature-scroll__head {
    padding-inline: max(40px, env(safe-area-inset-left, 0px)) max(40px, env(safe-area-inset-right, 0px));
  }

  .login-feature-scroll__tile-grid--3,
  .login-feature-scroll__tile-grid--features {
    grid-template-columns: 1fr;
  }

  .login-feature-scroll__chain-pills {
    flex-direction: column;
    align-items: flex-start;
  }

  .login-feature-scroll__chain-arrow {
    flex-direction: column;
    align-items: stretch;
  }

  .login-feature-scroll__chain-arrow {
    align-self: flex-start;
    transform: rotate(90deg);
    margin-left: 12px;
  }
}

@media (max-width: 720px) {
  .login-feature-scroll__rail {
    display: none;
  }

  .login-feature-scroll__page {
    padding-inline: max(16px, env(safe-area-inset-left, 0px)) max(16px, env(safe-area-inset-right, 0px));
  }

  .login-feature-scroll__head {
    padding-inline: max(16px, env(safe-area-inset-left, 0px)) max(16px, env(safe-area-inset-right, 0px));
  }

  .login-feature-scroll__content,
  .login-feature-scroll__content--wide,
  .login-feature-scroll__glass {
    max-width: min(1080px, calc(100vw - 32px));
    padding: 20px 16px;
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
  .login-feature-scroll__content,
  .login-feature-scroll__glass {
    opacity: 1 !important;
    filter: none !important;
    transform: none !important;
    transition: none !important;
  }

  .login-feature-scroll__rail-dot--active::after {
    animation: none !important;
  }
}
</style>
e>
