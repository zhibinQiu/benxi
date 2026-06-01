<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { encodeReturnLocation } from "../utils/navigationReturn";
import { NCard, NGrid, NGi, NText, NTag, NIcon, useMessage } from "naive-ui";
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
} from "@vicons/ionicons5";
import { fetchSystemFeatures } from "../api/client";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const features = ref([]);
const loading = ref(true);

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
};

const CATEGORY_ORDER = ["document", "tools", "carbon", "external"];

const SYSTEM_GREEN = "#0d9488";
const SYSTEM_GREEN_SOFT = "rgba(13, 148, 136, 0.1)";

const categoryMeta = {
  document: {
    title: "文档类",
    hint: "翻译、问答、对比、辅助写作与文档生成",
    icon: DocumentTextOutline,
  },
  tools: {
    title: "常用工具类",
    hint: "会议、识别与在线 AI 外链",
    icon: GridOutline,
  },
  carbon: {
    title: "双碳应用类",
    hint: "双碳业务智能应用",
    icon: LeafOutline,
  },
  external: {
    title: "外链",
    hint: "智碳相关系统入口（部分为平台内嵌）",
    icon: OpenOutline,
  },
};

const DEFAULT_CATEGORY = "tools";

function tagType(f) {
  if (!f.enabled) return "default";
  if (!f.accessible) return "warning";
  return "success";
}

const groupedCategories = computed(() => {
  const buckets = Object.fromEntries(CATEGORY_ORDER.map((k) => [k, []]));
  for (const f of features.value) {
    const cat = f.category || DEFAULT_CATEGORY;
    if (buckets[cat]) buckets[cat].push(f);
  }
  return CATEGORY_ORDER.map((id) => ({
    id,
    ...categoryMeta[id],
    features: buckets[id],
  })).filter((c) => c.features.length > 0);
});

onMounted(async () => {
  try {
    features.value = await fetchSystemFeatures();
  } catch (e) {
    message.error(e.message);
  } finally {
    loading.value = false;
  }
});

function openFeature(f) {
  if (!f.enabled) {
    message.info(`「${f.title}」${f.tag || "即将推出"}，敬请期待`);
    return;
  }
  if (!f.accessible) {
    message.warning("暂无权限，请联系管理员在角色管理中开通");
    return;
  }
  if (f.route) {
    const encoded = encodeReturnLocation(route);
    router.push({
      path: f.route,
      query: encoded ? { return: encoded } : {},
    });
    return;
  }
  if (f.external_url) {
    window.open(f.external_url, "_blank", "noopener,noreferrer");
    return;
  }
  message.warning("该功能暂未配置入口");
}
</script>

<template>
  <div
    class="functions-page feature-page"
    :style="{ '--cat-accent': SYSTEM_GREEN, '--cat-accent-soft': SYSTEM_GREEN_SOFT }"
  >
    <header class="functions-page__intro">
      <n-text depth="2" class="page-hint feature-tip">
        按类别选择功能进入；长任务提交后可离开，在后台任务或消息中查看结果
      </n-text>
    </header>

    <template v-if="!loading">
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
            <p v-if="cat.hint" class="category-block__hint">{{ cat.hint }}</p>
          </div>
        </header>

        <n-grid
          cols="2 s:3 m:4 xl:5"
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
                'feature-card--locked': f.enabled && !f.accessible,
              }"
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
                <n-tag
                  size="tiny"
                  round
                  :bordered="false"
                  :type="tagType(f)"
                  class="feature-card__tag"
                >
                  {{ f.tag }}
                </n-tag>
              </div>
              <h3 class="feature-card__title">{{ f.title }}</h3>
              <p class="feature-card__desc">{{ f.description }}</p>
              <div class="feature-card__footer">
                <span class="feature-card__action">
                  {{
                    !f.enabled
                      ? f.tag || "即将推出"
                      : !f.accessible
                        ? "暂无权限"
                        : f.external_url
                          ? "外链"
                          : "进入"
                  }}
                </span>
                <n-icon
                  v-if="f.enabled && f.accessible && f.external_url"
                  :size="12"
                  class="feature-card__external"
                >
                  <OpenOutline />
                </n-icon>
                <span v-else class="feature-card__arrow" aria-hidden="true">→</span>
              </div>
            </article>
          </n-gi>
        </n-grid>
      </section>
    </template>

    <n-grid
      v-else
      cols="2 s:3 m:4 xl:5"
      :x-gap="10"
      :y-gap="10"
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
</template>

<style scoped>
.functions-page {
  width: 100%;
  max-width: 1280px;
}

.functions-page__intro {
  margin-bottom: 10px;
}

.page-hint {
  display: block;
  font-size: 13px;
  line-height: 1.55;
}

.category-block {
  margin-top: 22px;
}

.category-block:first-of-type {
  margin-top: 4px;
}

.category-block__head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
  padding: 0 0 8px 10px;
  border-left: 3px solid var(--cat-accent, #0d9488);
}

.category-block__icon {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--cat-accent, #0d9488);
  background: var(--cat-accent-soft, rgba(13, 148, 136, 0.1));
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
  color: #0f172a;
}

.category-block__hint {
  margin: 3px 0 0;
  font-size: 11px;
  line-height: 1.4;
  color: #64748b;
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
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  padding: 10px 11px 9px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
  cursor: pointer;
  outline: none;
  transition:
    transform 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--cat-accent, #0d9488) 35%, transparent);
  box-shadow:
    0 4px 14px rgba(15, 23, 42, 0.07),
    0 0 0 1px color-mix(in srgb, var(--cat-accent, #0d9488) 10%, transparent);
}

.feature-card:focus-visible {
  box-shadow:
    0 0 0 2px #fff,
    0 0 0 4px var(--cat-accent, #0d9488);
}

.feature-card--disabled,
.feature-card--locked {
  cursor: not-allowed;
  opacity: 0.62;
  background: #f8fafc;
}

.feature-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 6px;
}

.feature-card__icon {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--cat-accent, #0d9488);
  background: var(--cat-accent-soft, rgba(13, 148, 136, 0.1));
  transition: transform 0.2s ease;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) .feature-card__icon {
  transform: scale(1.04);
}

.feature-card__tag {
  flex-shrink: 0;
  max-width: 48%;
  transform: scale(0.92);
  transform-origin: top right;
}

.feature-card__title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  color: #0f172a;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.feature-card__desc {
  margin: 3px 0 0;
  flex: 1;
  font-size: 11px;
  line-height: 1.4;
  color: #64748b;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.feature-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed rgba(15, 23, 42, 0.06);
}

.feature-card__action {
  font-size: 11px;
  font-weight: 500;
  color: var(--cat-accent, #0d9488);
}

.feature-card__arrow {
  font-size: 12px;
  line-height: 1;
  color: var(--cat-accent, #0d9488);
  opacity: 0.85;
  transition: transform 0.2s ease;
}

.feature-card:hover:not(.feature-card--disabled):not(.feature-card--locked) .feature-card__arrow {
  transform: translateX(3px);
}

.feature-card__external {
  flex-shrink: 0;
  color: var(--cat-accent, #0d9488);
  opacity: 0.75;
}

.functions-page__loading {
  margin-top: 4px;
}

.functions-page__loading :deep(> *) {
  display: flex;
}

.feature-card--skeleton {
  min-height: 96px;
  pointer-events: none;
  border-style: dashed;
}

.skeleton-block {
  border-radius: 6px;
  background: linear-gradient(
    90deg,
    rgba(15, 23, 42, 0.06) 25%,
    rgba(15, 23, 42, 0.1) 50%,
    rgba(15, 23, 42, 0.06) 75%
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
    padding: 9px 10px 8px;
  }
}
</style>
