<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { encodeReturnLocation } from "../utils/navigationReturn";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import { NEmpty, NGrid, NGi, NIcon, NTabs, NTabPane } from "naive-ui";

import {
  StarOutline,
  Star,
  GridOutline,
} from "@vicons/ionicons5";
import HintTooltip from "../components/HintTooltip.vue";
import PlatformSpin from "../components/PlatformSpin.vue";
import {
  SIDEBAR_DEDICATED_FEATURE_IDS,
  useFeatureFavorites,
} from "../composables/useFeatureFavorites";
import { useI18n } from "../composables/useI18n";
import { useSystemFeatures } from "../composables/useSystemFeatures";
import { resolveFeatureIcon } from "../constants/featureIcons.js";
import { openExternal } from "../utils/openExternal.js";

/** Tab 语义色：双碳偏绿、文档偏蓝、系统跟平台主色 */
const TAB_CARD_ACCENTS = Object.freeze({
  carbon: Object.freeze({
    accent: "#0D8A6A",
    soft: "rgba(13, 138, 106, 0.14)",
  }),
  document: Object.freeze({
    accent: "#005A9E",
    soft: "rgba(0, 90, 158, 0.12)",
  }),
  system: Object.freeze({
    accent: "var(--platform-accent)",
    soft: "var(--platform-accent-soft)",
  }),
});

function tabCardAccentStyle(tabId) {
  const entry = TAB_CARD_ACCENTS[tabId] || TAB_CARD_ACCENTS.system;
  return {
    "--card-accent": entry.accent,
    "--card-accent-soft": entry.soft,
  };
}

function featureIconOf(feature) {
  return resolveFeatureIcon(feature?.icon) || GridOutline;
}

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { featureLabel, t, featureTagLabel } = useI18n();
const { isFavorite, toggleFavorite } = useFeatureFavorites();
const { features, loading, loaded, loadError, loadSystemFeatures } = useSystemFeatures();
const showLoading = computed(
  () => loading.value || (!loaded.value && !loadError.value)
);

/** Tab 分类：双碳 / 文档 / 系统 */
const TAB_ORDER = ["carbon", "document", "system"];

/** 双碳、文档固定归属；其余进系统（本析 AI 平台 v1 优先） */
const CARBON_FEATURE_IDS = [
  "carbon_assistant",
  "carbon_qa",
  "carbon_news",
  "smart_data_query",
];
const DOCUMENT_FEATURE_IDS = [
  "pdf_translate",
  "report_generation",
  "ocr",
  "knowledge_search",
  "subscriptions",
  "doc_compare",
];
const SYSTEM_PREFERRED_FIRST = ["carbon_ai_v1", "smart_forecast", "auto_ml", "data_analysis"];

const CARBON_ID_SET = new Set(CARBON_FEATURE_IDS);
const DOCUMENT_ID_SET = new Set(DOCUMENT_FEATURE_IDS);

const TAB_STORAGE_KEY = "platform:system-functions-tab";

function readStoredTab() {
  const fromQuery = String(route.query.tab || "").trim();
  if (TAB_ORDER.includes(fromQuery)) return fromQuery;
  try {
    const raw = sessionStorage.getItem(TAB_STORAGE_KEY);
    if (TAB_ORDER.includes(raw)) return raw;
  } catch {
    /* ignore */
  }
  return "carbon";
}

const activeTab = ref(readStoredTab());

watch(activeTab, (tab) => {
  try {
    sessionStorage.setItem(TAB_STORAGE_KEY, tab);
  } catch {
    /* ignore */
  }
  if (route.query.tab !== tab) {
    router.replace({ query: { ...route.query, tab } }).catch(() => {});
  }
});

/** 功能 id → 路由名（避免 path/redirect 循环） */
const FEATURE_ROUTE_NAMES = {
  knowledge_search: "knowledge-search",
  report_generation: "report-generation",
  subscriptions: "knowledge-subscriptions",
  todos: "notes",
  auto_ml: "auto-ml",
  carbon_news: "carbon-news",
};

/** 不在功能列表中显示：已有独立侧栏入口的功能 + 内部入口 */
const HIDDEN_FEATURE_IDS = new Set([
  ...SIDEBAR_DEDICATED_FEATURE_IDS,
  "carbon_platform",
]);

function displayTag(f) {
  return featureTagLabel(f.tag, f.tag);
}

function bySortOrder(a, b) {
  const ao = Number(a.sort_order);
  const bo = Number(b.sort_order);
  const aOrder = Number.isFinite(ao) ? ao : 999;
  const bOrder = Number.isFinite(bo) ? bo : 999;
  if (aOrder !== bOrder) return aOrder - bOrder;
  return String(a.title || a.id).localeCompare(String(b.title || b.id), "zh-CN");
}

function sortFeatures(list, preferredOrder = []) {
  const rank = new Map(preferredOrder.map((id, i) => [id, i]));
  return [...list].sort((a, b) => {
    if (Boolean(b.enabled) !== Boolean(a.enabled)) {
      return Number(b.enabled) - Number(a.enabled);
    }
    const ar = rank.has(a.id) ? rank.get(a.id) : 1000;
    const br = rank.has(b.id) ? rank.get(b.id) : 1000;
    if (ar !== br) return ar - br;
    return bySortOrder(a, b);
  });
}

function resolveFeatureTab(featureId) {
  if (CARBON_ID_SET.has(featureId)) return "carbon";
  if (DOCUMENT_ID_SET.has(featureId)) return "document";
  return "system";
}

const visibleFeatures = computed(() =>
  features.value.filter((f) => !HIDDEN_FEATURE_IDS.has(f.id))
);

const tabBuckets = computed(() => {
  const buckets = { carbon: [], document: [], system: [] };
  for (const f of visibleFeatures.value) {
    buckets[resolveFeatureTab(f.id)].push(f);
  }
  return {
    carbon: sortFeatures(buckets.carbon, CARBON_FEATURE_IDS),
    document: sortFeatures(buckets.document, DOCUMENT_FEATURE_IDS),
    system: sortFeatures(buckets.system, SYSTEM_PREFERRED_FIRST),
  };
});

const featureTabs = computed(() =>
  TAB_ORDER.map((id) => ({
    id,
    title: t(`systemFunctionsPage.categories.${id}.title`),
    features: tabBuckets.value[id],
  })).filter((tab) => tab.features.length > 0)
);

const showEmpty = computed(
  () => !loading.value && loaded.value && featureTabs.value.length === 0
);

watch(
  featureTabs,
  (tabs) => {
    if (!tabs.length) return;
    if (!tabs.some((tab) => tab.id === activeTab.value)) {
      activeTab.value = tabs[0].id;
    }
  },
  { immediate: true }
);

async function refreshFeatures() {
  try {
    await loadSystemFeatures(true);
  } catch (e) {
    ui.error(e.message || loadError.value || t("systemFunctionsPage.loadFailed"));
  }
}

onMounted(() => {
  refreshFeatures();
});

function onFavoriteClick(event, feature) {
  event.stopPropagation();
  toggleFavorite(feature.id, feature);
}

function featureTitle(f) {
  return featureLabel(f.id, "title", f.title);
}

function featureDescription(f) {
  return featureLabel(f.id, "description", f.description);
}

function openFeature(f) {
  if (!f.enabled) {
    ui.info(t("systemFunctionsPage.comingSoon", { title: featureTitle(f), tag: displayTag(f) }));
    return;
  }
  if (!f.accessible) {
    ui.warning(t("systemFunctionsPage.noPermission"));
    return;
  }
  const encoded = encodeReturnLocation(route);
  const query = encoded ? { return: encoded } : {};
  /** 优先按功能 id 走路由名，避免 path 与 redirect 别名冲突 */
  const byId = FEATURE_ROUTE_NAMES[f.id];
  if (byId) {
    router.push({ name: byId, query });
    return;
  }
  if (f.route) {
    router.push({ path: f.route, query });
    return;
  }
  if (f.external_url) {
    openExternal(f.external_url);
    return;
  }
  ui.warning(t("systemFunctionsPage.noEntry"));
}
</script>

<template>
  <div class="functions-page feature-page">
    <div class="functions-page__content">
    <header class="functions-page__intro">
      <HintTooltip :text="t('systemFunctionsPage.introHint')" />
    </header>

    <n-empty
      v-if="showEmpty && !loadError"
      class="functions-page__empty"
      :description="t('systemFunctionsPage.emptyDescription')"
    >
      <template #extra>
        <ListRefreshButton :label="t('systemFunctionsPage.reload')" @click="refreshFeatures" />
      </template>
    </n-empty>

    <n-empty
      v-else-if="loadError && !showLoading"
      class="functions-page__empty"
      :description="loadError"
    >
      <template #extra>
        <ListRefreshButton
          :label="t('systemFunctionsPage.reload')"
          @click="refreshFeatures"
        />
      </template>
    </n-empty>

    <template v-else-if="!showLoading">
      <n-tabs
        v-model:value="activeTab"
        type="line"
        size="small"
        class="functions-page__tabs"
        animated
      >
        <n-tab-pane
          v-for="tab in featureTabs"
          :key="tab.id"
          :name="tab.id"
          :tab="tab.title"
        >
          <section class="category-block" :style="tabCardAccentStyle(tab.id)">
            <n-grid
              cols="2 s:3 m:4 l:5 xl:6"
              :x-gap="12"
              :y-gap="12"
              responsive="screen"
              class="category-grid"
            >
              <n-gi
                v-for="(f, fi) in tab.features"
                :key="f.id"
                class="feature-card-wrap"
                :style="{ '--enter-delay': `${Math.min(fi, 10) * 28}ms` }"
              >
                <article
                  class="feature-card"
                  :class="{
                    'feature-card--disabled': !f.enabled,
                    'feature-card--locked': f.enabled && !f.accessible,
                  }"
                  role="button"
                  tabindex="0"
                  @click="openFeature(f)"
                  @keydown.enter.prevent="openFeature(f)"
                  @keydown.space.prevent="openFeature(f)"
                >
                  <span class="feature-card__glow" aria-hidden="true" />
                  <div class="feature-card__icon" aria-hidden="true">
                    <n-icon :size="18">
                      <component :is="featureIconOf(f)" />
                    </n-icon>
                  </div>
                  <div class="feature-card__body">
                    <div class="feature-card__title-row">
                      <h3 class="feature-card__title">{{ featureTitle(f) }}</h3>
                    </div>
                    <p class="feature-card__desc">{{ featureDescription(f) }}</p>
                  </div>
                  <button
                    type="button"
                    class="feature-card__star"
                    :class="{ 'feature-card__star--active': isFavorite(f.id) }"
                    :aria-label="isFavorite(f.id) ? t('systemFunctionsPage.favoriteRemove') : t('systemFunctionsPage.favoriteAdd')"
                    :aria-pressed="isFavorite(f.id)"
                    @click="onFavoriteClick($event, f)"
                  >
                    <n-icon :size="14">
                      <component :is="isFavorite(f.id) ? Star : StarOutline" />
                    </n-icon>
                  </button>
                </article>
              </n-gi>
            </n-grid>
          </section>
        </n-tab-pane>
      </n-tabs>
    </template>

    <PlatformSpin v-else :show="true" size="large" class="functions-page__loading" local>
      <n-grid
        cols="2 s:3 m:4 l:5 xl:6"
        :x-gap="12"
        :y-gap="12"
        responsive="screen"
      >
        <n-gi v-for="i in 10" :key="i" class="feature-card-wrap">
          <article class="feature-card feature-card--skeleton" aria-hidden="true">
            <div class="feature-card__icon skeleton-block skeleton-block--icon" />
            <div class="feature-card__body">
              <div class="skeleton-block skeleton-block--title" />
              <div class="skeleton-block skeleton-block--desc" />
            </div>
          </article>
        </n-gi>
      </n-grid>
    </PlatformSpin>
    </div>
  </div>
</template>

<style scoped>
.functions-page {
  position: relative;
  width: 100%;
  flex: 1;
  min-height: 100%;
  isolation: isolate;
  --feature-card-height: 96px;
  --cat-accent: var(--platform-accent);
  --cat-accent-soft: var(--platform-accent-soft);
  --card-accent: var(--platform-accent);
  --card-accent-soft: var(--platform-accent-soft);
}

.functions-page__content {
  position: relative;
  z-index: 1;
  flex: 1;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0 24px 14px;
  box-sizing: border-box;
  background: transparent;
}

.functions-page__tabs,
.functions-page__tabs :deep(.n-tabs-nav),
.functions-page__tabs :deep(.n-tabs-pane-wrapper),
.functions-page__tabs :deep(.n-tab-pane),
.functions-page__tabs :deep(.n-tabs-scroll-padding),
.functions-page .category-block,
.functions-page .category-grid,
.functions-page__loading {
  background: transparent !important;
}

.functions-page__tabs :deep(.n-tabs-nav) {
  background: color-mix(in srgb, var(--platform-bg) 78%, transparent) !important;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.functions-page__tabs :deep(.n-tabs-pane-wrapper),
.functions-page__tabs :deep(.n-tab-pane) {
  background-color: transparent !important;
}

.functions-page__intro {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0;
}

.functions-page__tabs {
  margin-top: 4px;
  margin-bottom: 4px;
}

.category-grid {
  width: 100%;
}

.functions-page__empty {
  margin: 58px auto;
  max-width: 504px;
}

.category-block {
  margin-top: 14px;
}

.category-block:first-of-type {
  margin-top: 0;
}

.category-grid :deep(> *) {
  display: flex;
  align-items: stretch;
}

.feature-card-wrap {
  display: flex;
  width: 100%;
  height: 100%;
  animation: feature-card-in 0.34s cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: var(--enter-delay, 0ms);
}

@keyframes feature-card-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.feature-card {
  position: relative;
  flex: 1;
  width: 100%;
  height: var(--feature-card-height);
  min-height: var(--feature-card-height);
  max-height: var(--feature-card-height);
  box-sizing: border-box;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 12px;
  padding: 12px 14px 12px 12px;
  border-radius: var(--platform-card-radius);
  outline: none;
  cursor: pointer;
  overflow: hidden;
  isolation: isolate;
  transition: var(--platform-card-transition);
  border: 1px solid var(--platform-card-border-color);
  background: var(--platform-card-bg);
  box-shadow: var(--platform-card-shadow);
  backdrop-filter: var(--platform-glass-filter);
  -webkit-backdrop-filter: var(--platform-glass-filter);
}

/* 顶部高光条 */
.feature-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  z-index: 0;
  pointer-events: none;
  background: linear-gradient(
    90deg,
    transparent 4%,
    color-mix(in srgb, var(--platform-bg-elevated) 70%, transparent) 28%,
    color-mix(in srgb, var(--card-accent) 35%, transparent) 52%,
    color-mix(in srgb, var(--platform-bg-elevated) 55%, transparent) 78%,
    transparent 96%
  );
  opacity: 0.55;
  transition: opacity 0.22s ease;
}

/* 角部光晕（悬停显现） */
.feature-card__glow {
  position: absolute;
  top: -40%;
  right: -18%;
  width: 72%;
  height: 110%;
  border-radius: 50%;
  pointer-events: none;
  z-index: 0;
  background: radial-gradient(
    circle at center,
    color-mix(in srgb, var(--card-accent) 22%, transparent) 0%,
    transparent 68%
  );
  opacity: 0;
  transform: scale(0.86);
  transition:
    opacity 0.28s var(--platform-ease-smooth, ease),
    transform 0.28s var(--platform-ease-smooth, ease);
}

.feature-card__icon,
.feature-card__body,
.feature-card__star {
  position: relative;
  z-index: 1;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) {
  border-color: color-mix(in srgb, var(--card-accent) 38%, var(--platform-card-hover-border-color)) !important;
  box-shadow:
    var(--platform-glass-highlight, 0 0 0 1px transparent),
    0 2px 4px color-mix(in srgb, var(--card-accent) 8%, transparent),
    0 14px 32px color-mix(in srgb, var(--card-accent) 12%, rgba(15, 23, 42, 0.06)) !important;
  transform: translateY(-3px) !important;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked)::before {
  opacity: 0.9;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) .feature-card__glow {
  opacity: 1;
  transform: scale(1);
}

.feature-card:focus-visible {
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--platform-bg) 72%, transparent),
    0 0 0 5px var(--card-accent) !important;
}

.feature-card--disabled,
.feature-card--locked {
  cursor: not-allowed;
  opacity: 0.62;
}

.feature-card--disabled:hover,
.feature-card--locked:hover {
  transform: none;
}

.feature-card__icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 11px;
  color: var(--card-accent);
  background:
    linear-gradient(
      145deg,
      color-mix(in srgb, var(--card-accent-soft) 88%, var(--platform-bg-elevated)) 0%,
      color-mix(in srgb, var(--card-accent-soft) 65%, var(--platform-bg-tertiary)) 100%
    );
  border: 1px solid color-mix(in srgb, var(--card-accent) 16%, transparent);
  box-shadow:
    inset 0 1px 0 color-mix(in srgb, var(--platform-bg-elevated) 55%, transparent),
    0 1px 2px color-mix(in srgb, var(--card-accent) 8%, transparent);
  transition:
    transform 0.22s var(--platform-ease-smooth, ease),
    box-shadow 0.22s var(--platform-ease-smooth, ease),
    border-color 0.22s ease,
    color 0.22s ease;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) .feature-card__icon {
  transform: translateY(-1px) scale(1.05);
  border-color: color-mix(in srgb, var(--card-accent) 28%, transparent);
  box-shadow:
    inset 0 1px 0 color-mix(in srgb, var(--platform-bg-elevated) 65%, transparent),
    0 4px 12px color-mix(in srgb, var(--card-accent) 18%, transparent);
}

.feature-card__star {
  position: absolute !important;
  top: 6px !important;
  right: 6px !important;
  z-index: 2;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: var(--platform-radius-xs, 7px);
  background: transparent;
  color: var(--platform-text-quaternary);
  cursor: pointer;
  transition:
    color 0.18s ease,
    background 0.18s ease,
    transform 0.18s var(--platform-ease-smooth, ease);
}

.feature-card__star:hover {
  color: var(--platform-text-secondary);
  background: color-mix(in srgb, var(--platform-bg) 70%, transparent);
  transform: scale(1.08);
}

.feature-card__star--active {
  color: var(--card-accent);
}

.feature-card__star--active:hover {
  color: var(--card-accent);
  background: var(--card-accent-soft);
}

.feature-card__star:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--platform-bg-elevated), 0 0 0 5px var(--card-accent);
}

.feature-card__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  min-height: 0;
  gap: 4px;
}

.feature-card__title-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  padding-right: 18px;
  min-height: calc(var(--platform-font-size-base) * 1.35);
}

.feature-card__title {
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: var(--platform-font-size-sm);
  font-weight: 500;
  letter-spacing: 0.01em;
  line-height: 1.4;
  color: var(--platform-text);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color 0.2s ease;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) .feature-card__title {
  color: var(--card-accent);
}

.feature-card__desc {
  margin: 0;
  min-height: calc(1em * 1.4);
  font-size: var(--platform-font-size-sm);
  font-weight: var(--platform-font-weight-normal);
  line-height: 1.4;
  color: var(--platform-text-tertiary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.functions-page__loading {
  margin-top: 5px;
  min-height: 384px;
}

.functions-page__loading :deep(.n-spin-container) {
  min-height: 384px;
}

.functions-page__loading :deep(.n-spin-content) {
  width: 100%;
}

.feature-card--skeleton {
  height: var(--feature-card-height);
  min-height: var(--feature-card-height);
  max-height: var(--feature-card-height);
  pointer-events: none;
  flex-direction: row;
  align-items: center;
  gap: 12px;
  padding: 12px 14px 12px 12px;
  background: var(--platform-bg-tertiary) !important;
  border: 1px solid transparent !important;
}

.feature-card--skeleton::before,
.feature-card--skeleton .feature-card__glow {
  display: none;
}

.skeleton-block {
  border-radius: 7px;
  background: linear-gradient(
    90deg,
    var(--platform-divider) 25%,
    var(--platform-border) 50%,
    var(--platform-divider) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.2s ease-in-out infinite;
}

.skeleton-block--icon {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  flex-shrink: 0;
}

.skeleton-block--title {
  height: 14px;
  width: 72%;
}

.skeleton-block--desc {
  height: 12px;
  width: 92%;
  margin-top: 4px;
}

@keyframes skeleton-shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

@media (max-width: 640px) {
  .functions-page {
    --feature-card-height: 90px;
  }

  .functions-page__content {
    padding: 8px 12px 14px;
  }

  .feature-card {
    gap: 10px;
    padding: 10px 12px 10px 10px;
  }

  .feature-card__icon {
    width: 36px;
    height: 36px;
    border-radius: 10px;
  }

  .feature-card__star {
    top: 3px;
    right: 3px;
    width: 20px;
    height: 20px;
  }

  .category-block__head {
    margin-bottom: 8px;
  }

  /* 隐藏介绍提示按钮 */
  .functions-page__intro {
    display: none;
  }

  /* 空状态消息更紧凑 */
  .functions-page__empty {
    margin: 32px auto;
    max-width: 90vw;
  }

  /* 网格列数调整为 2 列 */
  .category-grid :deep(.n-grid) {
    grid-template-columns: repeat(2, 1fr) !important;
  }
}

@media (max-width: 400px) {
  .functions-page {
    --feature-card-height: 86px;
  }

  .functions-page__content {
    padding: 4px 8px 12px;
  }

  .feature-card {
    gap: 8px;
    padding: 8px 10px 8px 8px;
  }

  .feature-card__icon {
    width: 32px;
    height: 32px;
    border-radius: 9px;
  }

  .feature-card__title {
    font-size: 13px;
  }

  .feature-card__desc {
    font-size: 12px;
  }

  .feature-card__star {
    top: 2px;
    right: 2px;
    width: 18px;
    height: 18px;
  }

  .category-block__title {
    font-size: 15px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .feature-card,
  .feature-card__icon,
  .feature-card__glow,
  .feature-card__title {
    transition: none !important;
  }

  .feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) {
    transform: none !important;
  }

  .feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) .feature-card__icon {
    transform: none;
  }

  .feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) .feature-card__glow {
    transform: none;
  }
}
</style>
