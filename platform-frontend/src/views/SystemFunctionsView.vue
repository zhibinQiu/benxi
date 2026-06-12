<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { encodeReturnLocation } from "../utils/navigationReturn";
import { NCard, NGrid, NGi, NTag, NIcon } from "naive-ui";
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
  StarOutline,
  Star } from "@vicons/ionicons5";
import HintTooltip from "../components/HintTooltip.vue";
import { useFeatureFavorites } from "../composables/useFeatureFavorites";
import { useSystemFeatures } from "../composables/useSystemFeatures";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { isFavorite, toggleFavorite } = useFeatureFavorites();
const { features, loading, loaded, loadSystemFeatures } = useSystemFeatures();
const showLoading = computed(() => loading.value || !loaded.value);

const iconMap = {
  language: LanguageOutline,
  chatbubbles: ChatbubblesOutline,
  mic: MicOutline,
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
  search: SearchOutline};

const CATEGORY_ORDER = ["document", "tools", "carbon"];

const categoryMeta = {
  document: {
    title: "文档",
    hint: "翻译、对比、辅助写作、知识检索与文档生成",
    icon: DocumentTextOutline},
  tools: {
    title: "工具",
    hint: "会议助手、文件内容提取、数据分析、在线 AI 工具等",
    icon: GridOutline},
  carbon: {
    title: "双碳",
    hint: "双碳业务应用与智碳平台等外链入口",
    icon: LeafOutline}};

const DEFAULT_CATEGORY = "tools";

function tagType(f) {
  if (!f.enabled) return "default";
  if (!f.accessible) return "warning";
  return "success";
}

function shouldShowTag(f) {
  const tag = String(f.tag || "").trim();
  return Boolean(tag) && tag !== "可用";
}

const groupedCategories = computed(() => {
  const buckets = Object.fromEntries(CATEGORY_ORDER.map((k) => [k, []]));
  for (const f of features.value) {
    const raw = f.category || DEFAULT_CATEGORY;
    const cat = raw === "external" ? "carbon" : raw;
    if (buckets[cat]) buckets[cat].push(f);
  }
  return CATEGORY_ORDER.map((id) => ({
    id,
    ...categoryMeta[id],
    features: buckets[id]})).filter((c) => c.features.length > 0);
});

onMounted(async () => {
  try {
    await loadSystemFeatures();
  } catch (e) {
    ui.error(e.message);
  }
});

function onFavoriteClick(event, feature) {
  event.stopPropagation();
  toggleFavorite(feature.id, feature);
}

function openFeature(f) {
  if (!f.enabled) {
    ui.info(`「${f.title}」${f.tag || "即将推出"}，敬请期待`);
    return;
  }
  if (!f.accessible) {
    ui.warning("暂无权限，请联系管理员在角色管理中开通");
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
  ui.warning("该功能暂未配置入口");
}
</script>

<template>
  <div class="functions-page feature-page">
    <div class="functions-page__content">
    <header class="functions-page__intro">
      <HintTooltip
        text="按类别选择功能进入；长任务提交后可离开，在后台任务或消息中查看结果"
      />
    </header>

    <template v-if="!showLoading">
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
                  :aria-label="isFavorite(f.id) ? '取消收藏' : '收藏到侧栏'"
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
                  <h3 class="feature-card__title">{{ f.title }}</h3>
                  <n-tag
                    v-if="shouldShowTag(f)"
                    size="tiny"
                    round
                    :bordered="false"
                    :type="tagType(f)"
                    class="feature-card__tag"
                  >
                    {{ f.tag }}
                  </n-tag>
                </div>
                <p class="feature-card__desc">{{ f.description }}</p>
              </div>
            </article>
          </n-gi>
        </n-grid>
      </section>
    </template>

    <n-grid
      v-else
      cols="2 s:3 m:4 xl:5"
      :x-gap="8"
      :y-gap="8"
      responsive="screen"
      class="functions-page__loading"
    >
      <n-gi v-for="i in 10" :key="i">
        <n-card size="small" class="feature-card feature-card--skeleton">
          <div class="skeleton-block skeleton-block--icon" />
          <div class="skeleton-block skeleton-block--title" />
          <div class="skeleton-block skeleton-block--desc" />
        </n-card>
      </n-gi>
    </n-grid>
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
  background: var(--platform-bg-elevated);
  border: 1px solid var(--platform-border);
  box-shadow: var(--platform-shadow-sm);
  cursor: pointer;
  outline: none;
  transition:
    transform 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--cat-accent) 35%, transparent);
  box-shadow:
    var(--platform-shadow),
    0 0 0 1px color-mix(in srgb, var(--cat-accent) 10%, transparent);
}

.feature-card:focus-visible {
  box-shadow:
    0 0 0 2px var(--platform-bg-elevated),
    0 0 0 4px var(--cat-accent);
}

.feature-card--disabled,
.feature-card--locked {
  cursor: not-allowed;
  opacity: 0.62;
  background: var(--platform-bg-secondary);
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
    transform 0.18s var(--platform-ease-smooth, ease);
}

.feature-card__star:hover {
  color: var(--platform-text-secondary);
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
}

.functions-page__loading :deep(> *) {
  display: flex;
}

.feature-card--skeleton {
  min-height: 112px;
  pointer-events: none;
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
