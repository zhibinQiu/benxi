<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCard,
  NDatePicker,
  NEmpty,
  NInput,
  NSpace,
  NSpin,
  NTag,
  NText } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { useBoundedScrollHeight } from "../composables/useBoundedScrollHeight";
import { navigateWithReturn } from "../utils/navigationReturn";
import {
  fetchSubscriptionItems,
  ingestSubscriptionUrl } from "../api/client";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();

const loading = ref(true);
const itemsLoading = ref(false);
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;

const ingestUrl = ref("");
const ingesting = ref(false);

const searchKeyword = ref("");
const createdRange = ref(null);

const { anchorRef: listScrollRef, scrollHeight: listScrollHeight, remeasure } =
  useBoundedScrollHeight(16);

let searchTimer = null;

function fmtSerpDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric"});
  } catch {
    return "";
  }
}

function siteLabel(item) {
  if (item?.is_wechat) return "微信公众号";
  return domainFromUrl(item?.link) || "网页";
}

function domainFromUrl(url) {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./i, "");
  } catch {
    return "";
  }
}

function breadcrumbPath(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    const path = `${u.pathname}${u.search}` || "/";
    if (path === "/") return "";
    return path.length > 56 ? `${path.slice(0, 53)}…` : path;
  } catch {
    return "";
  }
}

function faviconForUrl(url) {
  const domain = domainFromUrl(url);
  if (!domain) return "";
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`;
}

function siteInitial(item) {
  const label = siteLabel(item);
  return label.charAt(0).toUpperCase() || "?";
}

function rangeToQuery(range) {
  if (!range || !Array.isArray(range) || range.length !== 2) {
    return { created_from: undefined, created_to: undefined };
  }
  const [from, to] = range;
  return {
    created_from: from ? new Date(from).toISOString() : undefined,
    created_to: to ? new Date(to).toISOString() : undefined};
}

async function loadItems() {
  itemsLoading.value = true;
  try {
    const { created_from, created_to } = rangeToQuery(createdRange.value);
    const data = await fetchSubscriptionItems({
      page: page.value,
      page_size: pageSize,
      keyword: searchKeyword.value.trim() || undefined,
      created_from,
      created_to});
    items.value = data.items || [];
    total.value = data.total || 0;
  } catch (e) {
    ui.error(e.message);
  } finally {
    itemsLoading.value = false;
    remeasure();
  }
}

async function reload() {
  loading.value = true;
  try {
    await loadItems();
  } catch (e) {
    ui.error(e.message);
  } finally {
    loading.value = false;
    remeasure();
  }
}

function scheduleSearch() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    page.value = 1;
    loadItems();
  }, 350);
}

watch(searchKeyword, scheduleSearch);
watch(createdRange, () => {
  page.value = 1;
  loadItems();
});

async function onIngest() {
  const url = ingestUrl.value.trim();
  if (!url) {
    ui.warning("请粘贴文章链接");
    return;
  }
  ingesting.value = true;
  try {
    const detail = await ingestSubscriptionUrl(url);
    ui.success(detail.summary ? "已收录并生成摘要" : "已收录");
    ingestUrl.value = "";
    await loadItems();
    openItem(detail.ref);
  } catch (e) {
    ui.error(e.message);
  } finally {
    ingesting.value = false;
  }
}

function openItem(ref) {
  navigateWithReturn(
    router,
    { name: "subscription-item", params: { ref } },
    route
  );
}

onMounted(reload);
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="subscriptions-page">
      <div class="feature-top-strip">
      <NCard size="small" class="subscriptions-ingest feature-local-nav">
        <NText depth="3" class="ingest-hint">
          粘贴文章链接即可收录（微信公众号、网站文章等）；收录后将自动生成 AI 摘要，并可在下方搜索与管理。
        </NText>
        <NSpace align="center">
          <NInput
            v-model:value="ingestUrl"
            placeholder="粘贴文章 URL，回车收录"
            clearable
            class="ingest-input"
            @keyup.enter="onIngest"
          />
          <NButton type="primary" :loading="ingesting" @click="onIngest">
            收录
          </NButton>
        </NSpace>
      </NCard>

      <NSpace class="subscriptions-toolbar feature-local-nav" align="center" wrap :size="12">
        <NInput
          v-model:value="searchKeyword"
          placeholder="搜索标题或正文"
          clearable
          class="search-input"
        />
        <NDatePicker
          v-model:value="createdRange"
          type="daterange"
          clearable
          start-placeholder="收录开始"
          end-placeholder="收录结束"
        />
        <NText depth="3">共 {{ total }} 篇</NText>
      </NSpace>
      </div>

      <NSpin :show="itemsLoading || loading" class="list-spin">
        <div
          ref="listScrollRef"
          class="subscriptions-list-scroll"
          :style="{ height: `${listScrollHeight}px` }"
        >
          <div v-if="items.length" class="subscriptions-serp-list" role="list">
            <article
              v-for="a in items"
              :key="a.ref"
              role="listitem"
              class="serp-result-item glass-float-panel"
              @click="openItem(a.ref)"
            >
              <div class="serp-result-item__source">
                <span class="serp-result-item__favicon" aria-hidden="true">
                  <img
                    v-if="faviconForUrl(a.link)"
                    class="serp-result-item__favicon-img"
                    :src="faviconForUrl(a.link)"
                    alt=""
                    loading="lazy"
                    @error="$event.target.classList.add('is-broken')"
                  />
                  <span class="serp-result-item__favicon-fallback">{{ siteInitial(a) }}</span>
                </span>
                <div class="serp-result-item__source-text">
                  <span class="serp-result-item__site">{{ siteLabel(a) }}</span>
                  <span v-if="breadcrumbPath(a.link)" class="serp-result-item__path">
                    › {{ breadcrumbPath(a.link) }}
                  </span>
                </div>
                <NTag
                  v-if="a.imported"
                  size="small"
                  type="success"
                  :bordered="false"
                  class="serp-result-item__imported"
                >
                  已入文档库
                </NTag>
              </div>
              <h3 class="serp-result-item__title">{{ a.title }}</h3>
              <p class="serp-result-item__snippet">
                {{ a.summary || "暂无摘要" }}
              </p>
              <div class="serp-result-item__meta">
                <NTag
                  v-if="a.is_wechat"
                  size="small"
                  :bordered="false"
                  class="serp-result-item__wechat-tag"
                >
                  公众号
                </NTag>
                <span v-if="fmtSerpDate(a.created_at || a.publish_at)" class="serp-result-item__date">
                  {{ fmtSerpDate(a.created_at || a.publish_at) }}
                </span>
              </div>
            </article>
          </div>
          <NEmpty v-else-if="!loading" description="暂无收录，请粘贴链接或调整筛选条件" />

          <NSpace v-if="total > pageSize" justify="center" class="subscriptions-pager">
            <NButton :disabled="page <= 1" @click="page--; loadItems()">上一页</NButton>
            <NText>{{ page }} / {{ Math.ceil(total / pageSize) }}</NText>
            <NButton :disabled="page * pageSize >= total" @click="page++; loadItems()">
              下一页
            </NButton>
          </NSpace>
        </div>
      </NSpin>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.subscriptions-page {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.subscriptions-ingest {
  flex-shrink: 0;
  margin-bottom: 0;
}
.ingest-hint {
  display: block;
  margin-bottom: 10px;
  font-size: 13px;
}
.ingest-input {
  flex: 1;
  min-width: 280px;
}
.subscriptions-toolbar {
  flex-shrink: 0;
}
.search-input {
  width: min(360px, 100%);
}
.list-spin {
  flex: 1;
  min-height: 0;
}
.list-spin :deep(.n-spin-container),
.list-spin :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
}
.subscriptions-list-scroll {
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 16px 12px;
  box-sizing: border-box;
  -webkit-overflow-scrolling: touch;
}

.subscriptions-serp-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 4px 0 8px;
  box-sizing: border-box;
}

.serp-result-item {
  display: block;
  width: 100%;
  padding: 14px 18px;
  box-sizing: border-box;
  border-radius: var(--platform-radius);
  text-align: left;
}

.serp-result-item__source {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin-bottom: 6px;
}

.serp-result-item__favicon {
  position: relative;
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  overflow: hidden;
  background: var(--platform-bg-muted, color-mix(in srgb, var(--platform-text) 6%, transparent));
  display: flex;
  align-items: center;
  justify-content: center;
}

.serp-result-item__favicon-img {
  width: 18px;
  height: 18px;
  object-fit: contain;
}

.serp-result-item__favicon-fallback {
  font-size: 12px;
  font-weight: 600;
  color: var(--platform-text-secondary);
  line-height: 1;
}

.serp-result-item__favicon-img.is-broken {
  display: none;
}

.serp-result-item__favicon:has(.serp-result-item__favicon-img:not(.is-broken)) .serp-result-item__favicon-fallback {
  display: none;
}

.serp-result-item__source-text {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.serp-result-item__site {
  color: var(--platform-text);
}

.serp-result-item__path {
  color: var(--platform-text-tertiary);
}

html[data-theme="light"] .serp-result-item__site {
  color: #202124;
}

html[data-theme="light"] .serp-result-item__path {
  color: #5f6368;
}

.serp-result-item__imported {
  flex-shrink: 0;
}

.serp-result-item__title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 400;
  line-height: 1.3;
  letter-spacing: -0.01em;
  color: var(--platform-accent);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color 0.15s ease;
}

html[data-theme="light"] .serp-result-item__title {
  color: #1a0dab;
}

.serp-result-item:hover .serp-result-item__title {
  text-decoration: underline;
  color: var(--platform-accent-hover);
}

html[data-theme="light"] .serp-result-item:hover .serp-result-item__title {
  color: #681da8;
}

.serp-result-item__snippet {
  margin: 0;
  font-size: 14px;
  line-height: 1.58;
  color: var(--platform-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

html[data-theme="light"] .serp-result-item__snippet {
  color: #4d5156;
}

.serp-result-item__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.serp-result-item__wechat-tag {
  background: var(--platform-accent-soft) !important;
  color: var(--platform-accent) !important;
}

.serp-result-item__date {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.subscriptions-pager {
  margin-top: 20px;
  padding-bottom: 12px;
  width: 100%;
}
</style>
