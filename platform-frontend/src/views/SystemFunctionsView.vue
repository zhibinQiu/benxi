<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
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
} from "@vicons/ionicons5";
import { fetchSystemFeatures } from "../api/client";

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
};

const CATEGORY_ORDER = ["document", "tools", "carbon", "external"];

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

const groupedCategories = computed(() => {
  const buckets = Object.fromEntries(CATEGORY_ORDER.map((k) => [k, []]));
  for (const f of features.value) {
    const cat = f.category || "tools";
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
    message.info("该功能即将推出");
    return;
  }
  if (!f.accessible) {
    message.warning("暂无权限，请联系管理员在角色管理中开通");
    return;
  }
  if (f.route) {
    router.push(f.route);
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
  <div class="functions-page feature-page">
    <n-text depth="2" class="page-hint feature-tip">
      按类别选择功能进入；长任务提交后可离开，在后台任务或消息中查看结果
    </n-text>

    <template v-if="!loading">
      <section
        v-for="cat in groupedCategories"
        :key="cat.id"
        class="category-section"
      >
        <div class="category-head">
          <n-icon :size="20" class="category-icon">
            <component :is="cat.icon" />
          </n-icon>
          <div class="category-titles">
            <n-text strong class="category-title">{{ cat.title }}</n-text>
            <n-text v-if="cat.hint" depth="3" class="category-hint">{{ cat.hint }}</n-text>
          </div>
        </div>

        <n-grid
          cols="1 m:4 l:8"
          :x-gap="12"
          :y-gap="12"
          responsive="screen"
          item-responsive
          class="category-grid"
        >
          <n-gi v-for="f in cat.features" :key="f.id" span="1 m:2 l:1">
            <n-card
              size="small"
              class="feature-card"
              :class="{ disabled: !f.enabled, locked: f.enabled && !f.accessible }"
              hoverable
              @click="openFeature(f)"
            >
              <div class="feature-row">
                <n-icon :size="22" class="feature-icon">
                  <component :is="iconMap[f.icon] || DocumentTextOutline" />
                </n-icon>
                <div class="feature-body">
                  <n-text strong class="feature-title">{{ f.title }}</n-text>
                  <n-text depth="3" class="feature-desc">{{ f.description }}</n-text>
                </div>
                <n-icon
                  v-if="f.enabled && f.accessible && f.external_url"
                  :size="16"
                  class="external-icon"
                  depth="3"
                >
                  <OpenOutline />
                </n-icon>
              </div>
              <n-tag
                size="small"
                :bordered="false"
                :type="f.enabled && f.accessible ? 'success' : f.enabled ? 'warning' : 'default'"
                class="feature-tag"
              >
                {{ f.tag }}
              </n-tag>
            </n-card>
          </n-gi>
        </n-grid>
      </section>
    </template>
  </div>
</template>

<style scoped>
.functions-page {
  width: 100%;
}
.page-hint {
  display: block;
  font-size: 13px;
}
.category-section {
  margin-top: 20px;
}
.category-section:first-of-type {
  margin-top: 12px;
}
.category-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}
.category-icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--n-text-color);
}
.category-titles {
  min-width: 0;
}
.category-title {
  display: block;
  font-size: 15px;
  line-height: 1.35;
}
.category-hint {
  display: block;
  font-size: 12px;
  margin-top: 2px;
}
.category-grid :deep(> *) {
  display: flex;
}
.feature-card {
  cursor: pointer;
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
}
.feature-card :deep(.n-card__content) {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.feature-card.disabled,
.feature-card.locked {
  cursor: not-allowed;
  opacity: 0.6;
}
.feature-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
}
.feature-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--n-text-color);
}
.external-icon {
  flex-shrink: 0;
  margin-top: 4px;
  opacity: 0.55;
}
.feature-body {
  min-width: 0;
  flex: 1;
}
.feature-title {
  font-size: 14px;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: calc(1.35em * 2);
}
.feature-desc {
  font-size: 12px;
  line-height: 1.4;
  margin-top: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: calc(1.4em * 2);
}
.feature-tag {
  margin-top: auto;
  flex-shrink: 0;
}
</style>
