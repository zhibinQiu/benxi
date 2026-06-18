<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { encodeReturnLocation } from "../utils/navigationReturn";
import { NButton, NCard, NEmpty, NGrid, NGi, NSpin, NTag, NIcon } from "naive-ui";
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
  OpenOutline,
  HardwareChipOutline,
  CreateOutline,
  WalletOutline,
  NewspaperOutline,
  SearchOutline,
  GitNetworkOutline,
  StarOutline,
  Star,
  VolumeHighOutline,
} from "@vicons/ionicons5";
import HintTooltip from "../components/HintTooltip.vue";
import { useFeatureFavorites } from "../composables/useFeatureFavorites";
import { useI18n } from "../composables/useI18n";
import { useSystemFeatures } from "../composables/useSystemFeatures";

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
  wallet: WalletOutline,
  newspaper: NewspaperOutline,
  search: SearchOutline,
  "git-network": GitNetworkOutline};

const CATEGORY_ORDER = ["document", "tools", "ai"];

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
              : SparklesOutline,
      },
    ])
  )
);

const DEFAULT_CATEGORY = "tools";

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
    const raw = f.category || DEFAULT_CATEGORY;
    let cat = raw === "external" || raw === "carbon" || raw === "ai" ? "ai" : raw;
    if (!buckets[cat]) cat = DEFAULT_CATEGORY;
    buckets[cat].push(f);
  }
  return CATEGORY_ORDER.map((id) => ({
    id,
    ...categoryMeta.value[id],
    features: buckets[id].sort((a, b) => Number(b.enabled) - Number(a.enabled)),
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
  if (f.route) {
    const encoded = encodeReturnLocation(route);
    router.push({
      path: f.route,
      query: encoded ? { return: encoded } : {}});
    return;
  }
  if (f.external_url) {
    window.open(f.external_url, "_blank", "noopener,noreferrer");
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
        <n-button size="small" @click="refreshFeatures">{{ t("systemFunctionsPage.reload") }}</n-button>
      </template>
    </n-empty>

    <n-empty
      v-else-if="loadError && !showLoading"
      class="functions-page__empty"
      :description="loadError"
    >
      <template #extra>
        <n-button size="small" type="primary" @click="refreshFeatures">{{ t("systemFunctionsPage.reload") }}</n-button>
      </template>
    </n-empty>

    <template v-else-if="!showLoading">
      <section v-for="cat in groupedCategories" :key="cat.id" class="category-block">
        <header class="category-block__head">
          <div class="category-block__icon">
            <n-icon :size="15">
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
          cols="2 s:3 m:4 xl:5"
          :x-gap="8"
          :y-gap="8"
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
              <div class="feature-card__top">
                <div class="feature-card__icon" aria-hidden="true">
                  <n-icon :size="17">
                    <component :is="iconMap[f.icon] || DocumentTextOutline" />
                  </n-icon>
                </div>
                <button
                  type="button"
                  class="feature-card__star"
                  :class="{ 'feature-card__star--active': isFavorite(f.id) }"
                  :aria-label="isFavorite(f.id) ? t('systemFunctionsPage.favoriteRemove') : t('systemFunctionsPage.favoriteAdd')"
                  :aria-pressed="isFavorite(f.id)"
                  @click="onFavoriteClick($event, f)"
                >
                  <n-icon :size="15">
                    <component :is="isFavorite(f.id) ? Star : StarOutline" />
                  </n-icon>
                </button>
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
            </article>
          </n-gi>
        </n-grid>
      </section>
    </template>

    <n-spin v-else :show="true" size="large" class="functions-page__loading">
      <n-grid
        cols="2 s:3 m:4 xl:5"
        :x-gap="8"
        :y-gap="8"
        responsive="screen"
      >
        <n-gi v-for="i in 10" :key="i">
          <n-card size="small" class="feature-card feature-card--skeleton">
            <div class="skeleton-block skeleton-block--icon" />
            <div class="skeleton-block skeleton-block--title" />
            <div class="skeleton-block skeleton-block--desc" />
          </n-card>
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
  max-width: 1280px;
  --cat-accent: var(--platform-accent);
  --cat-accent-soft: var(--platform-accent-soft);
}

.functions-page__content {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 8px 10px 10px;
  box-sizing: border-box;
}

.functions-page__intro {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0;
}

.functions-page__empty {
  margin: 48px auto;
  max-width: 420px;
}

.category-block {
  margin-top: 12px;
}

.category-block:first-of-type {
  margin-top: 0;
}

.category-block__head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 8px;
  padding: 0 0 6px 6px;
  border-left: 3px solid var(--cat-accent, var(--platform-accent));
}

.category-block__icon {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
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
  gap: 8px;
  flex-wrap: wrap;
}

.category-block__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
}

.category-grid :deep(> *) {
  display: flex;
}

.feature-card-wrap {
  display: flex;
  width: 100%;
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
  flex: 1;
  width: 100%;
  min-height: 112px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  padding: 12px 14px;
  border-radius: var(--platform-radius-sm, 10px);
  cursor: pointer;
  outline: none;
  overflow: hidden;
  transition:
    transform 0.22s var(--platform-ease-smooth, cubic-bezier(0.22, 1, 0.36, 1)),
    box-shadow 0.22s var(--platform-ease-smooth, ease),
    border-color 0.22s var(--platform-ease-smooth, ease);
}

.feature-card:not(.feature-card--disabled):not(.feature-card--locked) {
  background: var(--platform-ui-glass-fill, var(--platform-bg-glass)) !important;
  border: 1px solid var(--platform-ui-glass-border, var(--platform-glass-border)) !important;
  box-shadow: var(--platform-ui-layer-shadow, var(--platform-glass-shadow)) !important;
  backdrop-filter: saturate(var(--platform-glass-saturate)) blur(var(--platform-glass-blur));
  -webkit-backdrop-filter: saturate(var(--platform-glass-saturate)) blur(var(--platform-glass-blur));
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) {
  transform: translateY(-2px);
  border-color: color-mix(
    in srgb,
    var(--cat-accent) 38%,
    var(--platform-ui-glass-border, var(--platform-glass-border))
  ) !important;
  box-shadow:
    var(--platform-ui-layer-shadow, var(--platform-glass-shadow)),
    0 10px 28px color-mix(in srgb, var(--cat-accent) 10%, transparent) !important;
}

.feature-card:focus-visible {
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--platform-bg) 72%, transparent),
    0 0 0 4px var(--cat-accent) !important;
}

.feature-card--disabled,
.feature-card--locked {
  cursor: not-allowed;
  opacity: 0.55;
  background: var(--platform-ui-glass-fill-subtle, var(--platform-bg-glass-subtle)) !important;
  border: 1px solid var(--platform-ui-glass-border, var(--platform-border)) !important;
  box-shadow: none !important;
  backdrop-filter: saturate(120%) blur(calc(var(--platform-glass-blur) * 0.65));
  -webkit-backdrop-filter: saturate(120%) blur(calc(var(--platform-glass-blur) * 0.65));
}

.feature-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 6px;
}

.feature-card__star {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin: -2px -2px 0 0;
  padding: 0;
  border: none;
  border-radius: var(--platform-radius-xs, 6px);
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
  color: #e8a317;
}

.feature-card__star:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--platform-bg-elevated), 0 0 0 4px var(--cat-accent);
}

.feature-card__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.feature-card__title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.feature-card__icon {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--cat-accent, var(--platform-accent));
  background: color-mix(in srgb, var(--cat-accent-soft, var(--platform-accent-soft)) 68%, transparent);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.42),
    0 2px 8px color-mix(in srgb, var(--cat-accent) 14%, transparent);
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
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.feature-card__desc {
  margin: 4px 0 0;
  margin-top: auto;
  font-size: 11px;
  line-height: 1.45;
  color: var(--platform-text-tertiary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.functions-page__loading {
  margin-top: 4px;
  min-height: 320px;
}

.functions-page__loading :deep(.n-spin-container) {
  min-height: 320px;
}

.functions-page__loading :deep(.n-spin-content) {
  width: 100%;
}

.feature-card--skeleton {
  min-height: 112px;
  pointer-events: none;
  background: var(--platform-ui-glass-fill-subtle, var(--platform-bg-glass-subtle)) !important;
  border: 1px solid var(--platform-ui-glass-border, var(--platform-border)) !important;
  backdrop-filter: saturate(var(--platform-glass-saturate)) blur(var(--platform-glass-blur));
  -webkit-backdrop-filter: saturate(var(--platform-glass-saturate)) blur(var(--platform-glass-blur));
}

.skeleton-block {
  border-radius: 6px;
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
  width: 30px;
  height: 30px;
  border-radius: 8px;
  margin-bottom: 6px;
}

.skeleton-block--title {
  height: 12px;
  width: 68%;
  margin-bottom: 6px;
}

.skeleton-block--desc {
  height: 10px;
  width: 88%;
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
  .feature-card {
    padding: 10px 11px;
  }
}
</style>
