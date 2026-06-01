<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { navigateWithReturn } from "../utils/navigationReturn";
import { NCard, NGrid, NGi, NIcon, NTag, NText, useMessage } from "naive-ui";
import { NewspaperOutline } from "@vicons/ionicons5";
import { useAuth } from "../composables/useAuth";
import { resolveFeatureIcon } from "../constants/featureIcons";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const { hasPerm } = useAuth();

const BRAND = "#0d9488";
const BRAND_SOFT = "rgba(13, 148, 136, 0.1)";

/** 知识中心 · 订阅类能力（卡片入口） */
const subscriptionItems = [
  {
    id: "wechat_mp_feed",
    title: "微信公众号资讯",
    description:
      "维护公众号跟踪列表，汇总推文卡片浏览，并可将文章导入文档库供检索。",
    icon: "newspaper",
    routeName: "wechat-mp",
    permission: "feature.wechat_mp_feed",
    tag: "可用",
  },
  {
    id: "feed_rss",
    title: "RSS 订阅",
    description: "添加 RSS/Atom 源，自动拉取条目更新，支持导入文档库检索。",
    icon: "stats-chart",
    routeName: "feed-subscriptions",
    routeQuery: { kind: "rss" },
    permission: "feature.feed_subscriptions",
    tag: "可用",
  },
  {
    id: "feed_website",
    title: "双碳网站资讯",
    description:
      "订阅双碳相关网站（自动发现 RSS），汇总政策与市场资讯。",
    icon: "stats-chart",
    routeName: "feed-subscriptions",
    routeQuery: { kind: "website" },
    permission: "feature.feed_subscriptions",
    tag: "可用",
  },
];

const visibleItems = computed(() =>
  subscriptionItems.filter((item) => hasPerm(item.permission))
);

function openItem(item) {
  if (!hasPerm(item.permission)) {
    message.warning("无权限访问该订阅");
    return;
  }
  navigateWithReturn(
    router,
    { name: item.routeName, query: item.routeQuery || {} },
    route
  );
}
</script>

<template>
  <div class="subscriptions-page">
    <div class="page-head">
      <h1 class="page-title">订阅</h1>
      <NText depth="3" class="page-desc">
        管理外部资讯来源，收录内容后可导入文档库与知识问答检索。
      </NText>
    </div>

    <NGrid v-if="visibleItems.length" cols="1 s:2 m:3" :x-gap="16" :y-gap="16">
      <NGi v-for="item in visibleItems" :key="item.id">
        <NCard
          class="sub-card"
          hoverable
          :bordered="false"
          @click="openItem(item)"
        >
          <div class="sub-card-inner">
            <div class="sub-icon" :style="{ background: BRAND_SOFT, color: BRAND }">
              <NIcon :size="28" :component="resolveFeatureIcon(item.icon) || NewspaperOutline" />
            </div>
            <div class="sub-body">
              <div class="sub-title-row">
                <span class="sub-title">{{ item.title }}</span>
                <NTag size="small" type="success" :bordered="false">{{ item.tag }}</NTag>
              </div>
              <NText depth="3" class="sub-desc">{{ item.description }}</NText>
            </div>
          </div>
        </NCard>
      </NGi>
    </NGrid>

    <NCard v-else embedded>
      <NText depth="3">暂无可用订阅项，请联系管理员分配相应功能权限。</NText>
    </NCard>
  </div>
</template>

<style scoped>
.subscriptions-page {
  max-width: 1100px;
}
.page-head {
  margin-bottom: 20px;
}
.page-title {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 600;
}
.page-desc {
  font-size: 14px;
}
.sub-card {
  cursor: pointer;
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}
.sub-card-inner {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.sub-icon {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sub-body {
  flex: 1;
  min-width: 0;
}
.sub-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.sub-title {
  font-weight: 600;
  font-size: 15px;
}
.sub-desc {
  font-size: 13px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
