<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { encodeReturnLocation } from "../utils/navigationReturn";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import { categoryAccentStyle, FEATURE_CATEGORY_ACCENTS } from "../constants/categoryAccents.js";
import { NEmpty, NGrid, NGi, NSpin, NTag, NIcon } from "naive-ui";

const BASE = import.meta.env.BASE_URL.replace(/\/+$/, "");
const functionsBg = `${BASE}/images/bg.jpg`;
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
  GridOutline,
  HardwareChipOutline,
  CreateOutline,
  NewspaperOutline,
  SearchOutline,
  GitNetworkOutline,
  ExtensionPuzzleOutline,
  StarOutline,
  Star,
  VolumeHighOutline,
} from "@vicons/ionicons5";
import HintTooltip from "../components/HintTooltip.vue";
import { useFeatureFavorites } from "../composables/useFeatureFavorites";
import { useI18n } from "../composables/useI18n";
import { useSystemFeatures } from "../composables/useSystemFeatures";
import { openExternal } from "../utils/openExternal.js";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { featureLabel, t, tm, featureTagLabel } = useI18n();
const { isFavorite, toggleFavorite } = useFeatureFavorites();
const { features, loading, loaded, loadError, loadSystemFeatures } = useSystemFeatures();
const showLoading = computed(
  () => loading.value || (!loaded.value && !loadError.value)
);
const showEmpty = computed(
  () => !loading.value && loaded.value && groupedCategories.value.length === 0
);

const iconMap = {
  language: LanguageOutline,
  chatbubbles: ChatbubblesOutline,
  mic: MicOutline,
  "volume-high": VolumeHighOutline,
  scan: ScanOutline,
  "git-compare": GitCompareOutline,
  "document-text": DocumentTextOutline,
  "stats-chart": StatsChartOutline,
  leaf: LeafOutline,
  sparkles: SparklesOutline,
  "hardware-chip": HardwareChipOutline,
  create: CreateOutline,
  newspaper: NewspaperOutline,
  search: SearchOutline,
  "git-network": GitNetworkOutline,
  "extension-puzzle": ExtensionPuzzleOutline,
};

const CATEGORY_ORDER = ["document", "tools", "ai"];

const CATEGORY_ACCENTS = FEATURE_CATEGORY_ACCENTS;

function categoryAccentStyleFor(categoryId) {
  return categoryAccentStyle(categoryId, CATEGORY_ACCENTS);
}

/** 功能 id → 展示分类（与后端 plugin.category 对齐，避免缓存或未重启时仍落在旧分组） */
const FEATURE_CATEGORY_OVERRIDES = {
  ai_home: "tools",
};

/** 功能 id → 路由名（避免 path/redirect 循环） */
const FEATURE_ROUTE_NAMES = {
  ai_home: "ai-home",
  knowledge_search: "knowledge-search",
  report_generation: "report-generation",
};

const categoryMeta = computed(() =>
  Object.fromEntries(
    CATEGORY_ORDER.map((id) => [
      id,
      {
        title: t(`systemFunctionsPage.categories.${id}.title`),
        hint: t(`systemFunctionsPage.categories.${id}.hint`),
        icon:
          id === "document"
            ? DocumentTextOutline
            : id === "tools"
              ? GridOutline
              : LeafOutline,
      },
    ])
  )
);

const DEFAULT_CATEGORY = "tools";

function resolveFeatureCategory(feature) {
  const raw =
    FEATURE_CATEGORY_OVERRIDES[feature.id] || feature.category || DEFAULT_CATEGORY;
  if (raw === "external" || raw === "carbon" || raw === "ai") return "ai";
  return raw;
}

function tagType(f) {
  if (!f.enabled) return "default";
  if (!f.accessible) return "warning";
  return "success";
}

function shouldShowTag(f) {
  const tag = String(f.tag || "").trim();
  const available = t("systemFunctionsPage.tags.available");
  return Boolean(tag) && tag !== available && tag !== "可用";
}

function displayTag(f) {
  return featureTagLabel(f.tag, f.tag);
}

const groupedCategories = computed(() => {
  const buckets = Object.fromEntries(CATEGORY_ORDER.map((k) => [k, []]));
  for (const f of features.value) {
    let cat = resolveFeatureCategory(f);
    if (!buckets[cat]) cat = DEFAULT_CATEGORY;
    buckets[cat].push(f);
  }
  const bySortOrder = (a, b) => {
    const ao = Number(a.sort_order);
    const bo = Number(b.sort_order);
    const aOrder = Number.isFinite(ao) ? ao : 999;
    const bOrder = Number.isFinite(bo) ? bo : 999;
    if (aOrder !== bOrder) return aOrder - bOrder;
    return String(a.title || a.id).localeCompare(String(b.title || b.id), "zh-CN");
  };
  return CATEGORY_ORDER.map((id) => ({
    id,
    ...categoryMeta.value[id],
    features: buckets[id].sort((a, b) => {
      if (Boolean(b.enabled) !== Boolean(a.enabled)) {
        return Number(b.enabled) - Number(a.enabled);
      }
      return bySortOrder(a, b);
    }),
  })).filter((c) => c.features.length > 0);
});

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
  <div class="functions-page feature-page" :style="{ backgroundImage: `url(${functionsBg})`, backgroundSize: 'cover', backgroundPosition: 'center', backgroundAttachment: 'fixed' }">
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
      <section
        v-for="cat in groupedCategories"
        :key="cat.id"
        class="category-block"
        :style="categoryAccentStyleFor(cat.id)"
      >
        <header class="category-block__head">
          <div class="category-block__icon">
            <n-icon :size="18">
              <component :is="cat.icon" />
            </n-icon>
          </div>
          <div class="category-block__text">
            <div class="category-block__row">
              <h2 class="category-block__title">{{ cat.title }}</h2>
            </div>
          </div>
        </header>

        <n-grid
          cols="2 s:3 m:4 l:5 xl:6"
          :x-gap="10"
          :y-gap="10"
          responsive="screen"
          class="category-grid"
        >
          <n-gi
            v-for="(f, fi) in cat.features"
            :key="f.id"
            class="feature-card-wrap"
            :style="{ '--enter-delay': `${Math.min(fi, 10) * 28}ms` }"
          >
            <article
              class="feature-card"
              :class="{
                'feature-card--disabled': !f.enabled,
                'feature-card--locked': f.enabled && !f.accessible}"
              role="button"
              tabindex="0"
              @click="openFeature(f)"
              @keydown.enter.prevent="openFeature(f)"
              @keydown.space.prevent="openFeature(f)"
            >
              <div class="feature-card__icon" aria-hidden="true">
                <n-icon :size="20">
                  <component :is="iconMap[f.icon] || DocumentTextOutline" />
                </n-icon>
              </div>
              <div class="feature-card__body">
                <div class="feature-card__title-row">
                  <h3 class="feature-card__title">{{ featureTitle(f) }}</h3>
                  <n-tag
                    v-if="shouldShowTag(f)"
                    size="tiny"
                    round
                    :bordered="false"
                    :type="tagType(f)"
                    class="feature-card__tag"
                  >
                    {{ displayTag(f) }}
                  </n-tag>
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
                <n-icon :size="18">
                  <component :is="isFavorite(f.id) ? Star : StarOutline" />
                </n-icon>
              </button>
            </article>
          </n-gi>
        </n-grid>
      </section>
    </template>

    <n-spin v-else :show="true" size="large" class="functions-page__loading" local>
      <n-grid
        cols="2 s:3 m:4 l:5 xl:6"
        :x-gap="10"
        :y-gap="10"
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
    </n-spin>
    </div>
  </div>
</template>

<style scoped>
.functions-page {
  position: relative;
  width: 100%;
  flex: 1;
  min-height: 100%;
  --feature-card-height: 112px;
  --cat-accent: var(--platform-accent);
  --cat-accent-soft: var(--platform-accent-soft);
}




.functions-page__content {
  position: relative;
  z-index: 1;
  flex: 1;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 10px 24px 14px;
  box-sizing: border-box;
}

.functions-page__intro {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0;
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

.category-block__head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
  padding: 0 0 7px 7px;
  border-left: 4px solid var(--cat-accent, var(--platform-accent));
}

.category-block__icon {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--cat-accent, var(--platform-accent));
  background: var(--cat-accent-soft, var(--platform-accent-soft));
}


.category-block__text {
  min-width: 0;
  flex: 1;
}

.category-block__row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.category-block__title {
  margin: 0;
  font-size: var(--platform-font-size-base);
  font-weight: var(--platform-font-weight-medium);
  line-height: 1.35;
  color: var(--platform-text);
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
    transform: translateY(12px);
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
  padding: 12px 38px 12px 14px;
  border-radius: var(--platform-radius-sm, 12px);
  cursor: pointer;
  outline: none;
  overflow: hidden;
  isolation: isolate;
  transition:
    transform 0.22s var(--platform-ease-smooth, cubic-bezier(0.22, 1, 0.36, 1)),
    box-shadow 0.22s var(--platform-ease-smooth, ease),
    border-color 0.22s var(--platform-ease-smooth, ease);
}


.feature-card:not(.feature-card--disabled):not(.feature-card--locked)::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  z-index: 0;
  background: linear-gradient(
    160deg,
    color-mix(in srgb, var(--cat-accent) 6%, transparent) 0%,
    transparent 52%
  );
}

.feature-card:not(.feature-card--disabled):not(.feature-card--locked) > * {
  position: relative;
  z-index: 1;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) {
  transform: translateY(-2px);
  border-color: color-mix(
    in srgb,
    var(--cat-accent) 32%,
    var(--platform-border)
  ) !important;
  box-shadow:
    var(--platform-shadow),
    0 0 0 1px color-mix(in srgb, var(--cat-accent) 8%, transparent) !important;
}

.feature-card:focus-visible {
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--platform-bg) 72%, transparent),
    0 0 0 5px var(--cat-accent) !important;
}


.feature-card__star {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 29px;
  height: 29px;
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
  background: var(--platform-ui-glass-fill-subtle, rgba(255, 255, 255, 0.22));
  transform: scale(1.08);
}

.feature-card__star--active {
  color: var(--platform-accent);
}

.feature-card__star--active:hover {
  color: var(--platform-accent-hover);
  background: var(--platform-accent-soft);
}

.feature-card__star:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--platform-bg-elevated), 0 0 0 5px var(--cat-accent);
}

.feature-card__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  gap: 4px;
}

.feature-card__title-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  min-height: calc(var(--platform-font-size-base) * 1.4);
}

.feature-card__icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  align-self: center;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--cat-accent, var(--platform-accent));
  background: var(--cat-accent-soft, var(--platform-accent-soft));
  transition: transform 0.2s ease;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) .feature-card__icon {
  transform: scale(1.04);
}

.feature-card__tag {
  flex-shrink: 0;
  max-width: 48%;
  transform: scale(0.92);
  transform-origin: center right;
}

.feature-card__title {
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: var(--platform-font-size-base);
  font-weight: var(--platform-font-weight-medium);
  line-height: 1.4;
  color: var(--platform-text);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color 0.2s ease;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) .feature-card__title {
  color: color-mix(in srgb, var(--cat-accent) 28%, var(--platform-text));
}

.feature-card__desc {
  margin: 0;
  min-height: calc(11px * 1.5);
  font-size: 11px;
  font-weight: var(--platform-font-weight-normal);
  line-height: 1.5;
  color: var(--platform-text-secondary);
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
  padding: 12px 14px;
  background: var(--platform-ui-glass-fill-subtle) !important;
  border: 1px solid var(--platform-ui-glass-border) !important;
  backdrop-filter: saturate(165%) blur(calc(var(--platform-glass-blur) * 0.75));
  -webkit-backdrop-filter: saturate(165%) blur(calc(var(--platform-glass-blur) * 0.75));
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
  border-radius: 10px;
  flex-shrink: 0;
}



.skeleton-block--title {
  height: 14px;
  width: 72%;
}

.skeleton-block--desc {
  height: 12px;
  width: 92%;
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
    --feature-card-height: 108px;
  }

  .feature-card {
    gap: 10px;
    padding: 10px 34px 10px 12px;
  }

  .feature-card__icon {
    width: 36px;
    height: 36px;
  }
}
</style>
