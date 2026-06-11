<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NDatePicker,
  NEmpty,
  NIcon,
  NInput,
  NPagination,
  NPopover,
  NRadioButton,
  NRadioGroup,
  NSpin,
  NTag,
  NText } from "naive-ui";
import { LinkOutline, SearchOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import WebSearchResultDrawer from "../components/WebSearchResultDrawer.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import {
  fetchSubscriptionItems,
  fetchWebSearchStatus,
  ingestSubscriptionUrl,
  searchSubscriptionWeb } from "../api/client";

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
const ingestPopoverOpen = ref(false);

const searchMode = ref("local");
const searchKeyword = ref("");
const appliedWebQuery = ref("");
const createdRange = ref(null);
const draftCreatedRange = ref(null);
const filterPopoverOpen = ref(false);

const webSearchEnabled = ref(false);
const webItems = ref([]);
const webHasMore = ref(false);
const webSearched = ref(false);

const webDetailOpen = ref(false);
const webDetailItem = ref(null);
const collectingWeb = ref(false);

let searchTimer = null;

const isLocalMode = computed(() => searchMode.value === "local");
const hasDateFilter = computed(
  () => Array.isArray(createdRange.value) && createdRange.value.length === 2
);

const pageCount = computed(() => {
  if (!isLocalMode.value) {
    return Math.max(1, webHasMore.value ? page.value + 1 : page.value);
  }
  return Math.max(1, Math.ceil(total.value / pageSize));
});

const showPager = computed(() => {
  if (!isLocalMode.value) {
    return webSearched.value && (webItems.value.length > 0 || page.value > 1);
  }
  return total.value > pageSize;
});

const resultCountLabel = computed(() => {
  if (!isLocalMode.value) {
    if (!webSearched.value) return "";
    return webItems.value.length ? `约 ${webItems.value.length} 条结果` : "无匹配结果";
  }
  if (!searchKeyword.value.trim() && !hasDateFilter.value) {
    return total.value ? `共 ${total.value} 篇收藏` : "";
  }
  return `共 ${total.value} 篇`;
});

const searchPlaceholder = computed(() =>
  isLocalMode.value ? "搜索已收藏的文章标题或正文" : "搜索互联网内容"
);

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

function fmtFilterRange(range) {
  if (!range || range.length !== 2) return "";
  const fmt = (ts) =>
    new Date(ts).toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit"});
  return `${fmt(range[0])} — ${fmt(range[1])}`;
}

function siteLabel(item) {
  if (item?.is_wechat) return "微信公众号";
  return domainFromUrl(item?.link || item?.url) || "网页";
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
  }
}

async function loadWebSearch() {
  const q = appliedWebQuery.value.trim();
  if (!q) {
    webItems.value = [];
    webHasMore.value = false;
    webSearched.value = false;
    return;
  }
  if (!webSearchEnabled.value) {
    ui.warning("未配置在线搜索服务，请在资源管理中配置 SearXNG");
    return;
  }
  itemsLoading.value = true;
  try {
    const data = await searchSubscriptionWeb({
      q,
      page: page.value,
      page_size: pageSize});
    webItems.value = data.items || [];
    webHasMore.value = !!data.has_more;
    webSearched.value = true;
  } catch (e) {
    ui.error(e.message);
    webItems.value = [];
    webHasMore.value = false;
    webSearched.value = true;
  } finally {
    itemsLoading.value = false;
  }
}

async function reload() {
  loading.value = true;
  try {
    if (isLocalMode.value) {
      await loadItems();
    } else if (appliedWebQuery.value) {
      await loadWebSearch();
    }
  } catch (e) {
    ui.error(e.message);
  } finally {
    loading.value = false;
  }
}

function scheduleLocalSearch() {
  if (!isLocalMode.value) return;
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    page.value = 1;
    loadItems();
  }, 350);
}

function submitSearch() {
  if (isLocalMode.value) {
    page.value = 1;
    loadItems();
    return;
  }
  appliedWebQuery.value = searchKeyword.value.trim();
  if (!appliedWebQuery.value) {
    ui.warning("请输入搜索关键词");
    return;
  }
  page.value = 1;
  loadWebSearch();
}

function onPageChange(nextPage) {
  page.value = nextPage;
  if (isLocalMode.value) {
    loadItems();
  } else {
    loadWebSearch();
  }
}

function openFilterPopover() {
  draftCreatedRange.value = createdRange.value ? [...createdRange.value] : null;
  filterPopoverOpen.value = true;
}

function applyDateFilter() {
  createdRange.value = draftCreatedRange.value;
  filterPopoverOpen.value = false;
  if (isLocalMode.value) {
    page.value = 1;
    loadItems();
  }
}

function clearDateFilter() {
  draftCreatedRange.value = null;
  createdRange.value = null;
  filterPopoverOpen.value = false;
  if (isLocalMode.value) {
    page.value = 1;
    loadItems();
  }
}

watch(searchKeyword, scheduleLocalSearch);

watch(searchMode, (mode) => {
  page.value = 1;
  webDetailOpen.value = false;
  if (mode === "local") {
    loadItems();
    return;
  }
  appliedWebQuery.value = searchKeyword.value.trim();
  if (appliedWebQuery.value) {
    loadWebSearch();
  } else {
    webItems.value = [];
    webHasMore.value = false;
    webSearched.value = false;
  }
});

async function onIngest(urlInput) {
  const url = (urlInput || ingestUrl.value).trim();
  if (!url) {
    ui.warning("请粘贴文章链接");
    return;
  }
  ingesting.value = true;
  try {
    const detail = await ingestSubscriptionUrl(url);
    ui.success(detail.summary ? "已收录并生成摘要" : "已收录");
    ingestUrl.value = "";
    ingestPopoverOpen.value = false;
    searchMode.value = "local";
    searchKeyword.value = "";
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

function openWebDetail(item) {
  webDetailItem.value = item;
  webDetailOpen.value = true;
}

function openWebOriginal() {
  const url = webDetailItem.value?.url;
  if (url) window.open(url, "_blank", "noopener,noreferrer");
}

async function collectWebDetail() {
  const url = webDetailItem.value?.url;
  if (!url) return;
  collectingWeb.value = true;
  try {
    const detail = await ingestSubscriptionUrl(url);
    webDetailOpen.value = false;
    ui.success(detail.summary ? "已收藏并生成摘要" : "已收藏到本地");
    openItem(detail.ref);
  } catch (e) {
    ui.error(e.message);
  } finally {
    collectingWeb.value = false;
  }
}

async function collectWebResult(item, event) {
  event?.stopPropagation?.();
  webDetailItem.value = item;
  await collectWebDetail();
}

async function loadWebSearchStatus() {
  try {
    const data = await fetchWebSearchStatus();
    webSearchEnabled.value = !!data?.enabled;
    if (!webSearchEnabled.value && searchMode.value === "web") {
      searchMode.value = "local";
    }
  } catch {
    webSearchEnabled.value = false;
    searchMode.value = "local";
  }
}

onMounted(async () => {
  await loadWebSearchStatus();
  await reload();
});
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="subscriptions-page">
      <header class="feature-top-strip subscriptions-chrome-head">
        <div class="subscriptions-search-hub feature-local-nav">
          <NRadioGroup v-model:value="searchMode" size="small" class="subscriptions-search-hub__mode">
            <NRadioButton value="web" :disabled="!webSearchEnabled">联网搜索</NRadioButton>
            <NRadioButton value="local">本地收藏</NRadioButton>
          </NRadioGroup>

          <div class="subscriptions-search-hub__bar">
            <NIcon :size="18" class="subscriptions-search-hub__icon" :component="SearchOutline" />
            <NInput
              v-model:value="searchKeyword"
              :placeholder="searchPlaceholder"
              clearable
              class="subscriptions-search-hub__input"
              @keyup.enter="submitSearch"
            />
            <NButton
              type="primary"
              class="subscriptions-search-hub__submit"
              :loading="itemsLoading"
              @click="submitSearch"
            >
              搜索
            </NButton>
          </div>

          <div class="subscriptions-search-hub__tools">
            <NPopover
              v-if="isLocalMode"
              v-model:show="filterPopoverOpen"
              trigger="click"
              placement="bottom-start"
              :show-arrow="false"
            >
              <template #trigger>
                <NButton
                  size="tiny"
                  quaternary
                  :type="hasDateFilter ? 'primary' : 'default'"
                  @click="openFilterPopover"
                >
                  筛选条件
                </NButton>
              </template>
              <div class="subscriptions-filter-panel">
                <div class="subscriptions-filter-panel__label">收录开始 / 结束时间</div>
                <NDatePicker
                  v-model:value="draftCreatedRange"
                  type="daterange"
                  clearable
                  style="width: 100%"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                />
                <div class="subscriptions-filter-panel__actions">
                  <NButton size="small" @click="clearDateFilter">清除</NButton>
                  <NButton size="small" type="primary" @click="applyDateFilter">应用</NButton>
                </div>
              </div>
            </NPopover>

            <NPopover
              v-model:show="ingestPopoverOpen"
              trigger="click"
              placement="bottom-end"
              :show-arrow="false"
            >
              <template #trigger>
                <NButton size="tiny" quaternary class="subscriptions-search-hub__ingest-trigger">
                  <template #icon>
                    <NIcon :component="LinkOutline" />
                  </template>
                  通过链接收录
                </NButton>
              </template>
              <div class="subscriptions-ingest-panel">
                <div class="subscriptions-ingest-panel__label">粘贴文章链接收录到本地</div>
                <NInput
                  v-model:value="ingestUrl"
                  placeholder="https://..."
                  clearable
                  @keyup.enter="onIngest()"
                />
                <NButton
                  type="primary"
                  block
                  :loading="ingesting"
                  style="margin-top: 10px"
                  @click="onIngest()"
                >
                  收录
                </NButton>
                <NText depth="3" class="subscriptions-ingest-panel__hint">
                  支持公众号、网站文章等；收录后自动生成 AI 摘要。
                </NText>
              </div>
            </NPopover>

            <NText v-if="resultCountLabel" depth="3" class="subscriptions-search-hub__count">
              {{ resultCountLabel }}
            </NText>
          </div>

          <div v-if="isLocalMode && hasDateFilter" class="subscriptions-active-filters">
            <NTag size="small" closable :bordered="false" @close="clearDateFilter">
              收录时间：{{ fmtFilterRange(createdRange) }}
            </NTag>
          </div>
        </div>
      </header>

      <div class="subscriptions-body">
        <NSpin :show="itemsLoading || loading" class="list-spin">
          <div class="subscriptions-list-scroll">
            <template v-if="isLocalMode">
              <div v-if="items.length" class="subscriptions-serp-list" role="list">
                <article
                  v-for="a in items"
                  :key="a.ref"
                  role="listitem"
                  class="serp-result-item"
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
                  <p class="serp-result-item__snippet">{{ a.summary || "暂无摘要" }}</p>
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
              <div v-else-if="!loading" class="subscriptions-empty">
                <NEmpty description="暂无收藏，可联网搜索或粘贴链接收录" />
              </div>
            </template>

            <template v-else>
              <div v-if="webItems.length" class="subscriptions-serp-list" role="list">
                <article
                  v-for="(a, idx) in webItems"
                  :key="`${a.url}-${idx}`"
                  role="listitem"
                  class="serp-result-item serp-result-item--web"
                  @click="openWebDetail(a)"
                >
                  <div class="serp-result-item__source">
                    <span class="serp-result-item__favicon" aria-hidden="true">
                      <img
                        v-if="faviconForUrl(a.url)"
                        class="serp-result-item__favicon-img"
                        :src="faviconForUrl(a.url)"
                        alt=""
                        loading="lazy"
                        @error="$event.target.classList.add('is-broken')"
                      />
                      <span class="serp-result-item__favicon-fallback">{{ siteInitial(a) }}</span>
                    </span>
                    <div class="serp-result-item__source-text">
                      <span class="serp-result-item__site">{{ siteLabel(a) }}</span>
                      <span v-if="breadcrumbPath(a.url)" class="serp-result-item__path">
                        › {{ breadcrumbPath(a.url) }}
                      </span>
                    </div>
                  </div>
                  <h3 class="serp-result-item__title">{{ a.title }}</h3>
                  <p class="serp-result-item__snippet">{{ a.snippet || "暂无摘要" }}</p>
                  <div v-if="a.engine" class="serp-result-item__meta">
                    <span class="serp-result-item__date">{{ a.engine }}</span>
                  </div>
                  <div class="serp-result-item__actions" @click.stop>
                    <NButton size="tiny" quaternary @click="openWebDetail(a)">详情</NButton>
                    <NButton
                      size="tiny"
                      type="primary"
                      ghost
                      :loading="collectingWeb && webDetailItem?.url === a.url"
                      @click="collectWebResult(a, $event)"
                    >
                      收藏
                    </NButton>
                  </div>
                </article>
              </div>
              <div v-else-if="!loading && webSearched" class="subscriptions-empty">
                <NEmpty description="未找到相关网页，请换关键词重试" />
              </div>
              <div v-else-if="!loading && !webSearchEnabled" class="subscriptions-empty">
                <NEmpty description="在线搜索未启用，请在资源管理中配置 SearXNG" />
              </div>
              <div v-else-if="!loading" class="subscriptions-empty subscriptions-empty--hero">
                <NIcon :size="42" :component="SearchOutline" class="subscriptions-empty__icon" />
                <p class="subscriptions-empty__title">在上方输入关键词开始搜索</p>
                <p class="subscriptions-empty__desc">联网检索结果可查看详情或收藏到本地</p>
              </div>
            </template>
          </div>
        </NSpin>
      </div>

      <footer v-if="showPager" class="subscriptions-footer feature-local-nav">
        <div class="subscriptions-footer__inner">
          <NPagination
            :page="page"
            :page-count="pageCount"
            :page-slot="7"
            @update:page="onPageChange"
          />
        </div>
      </footer>
    </div>

    <WebSearchResultDrawer
      v-model:show="webDetailOpen"
      :item="webDetailItem"
      :collecting="collectingWeb"
      @collect="collectWebDetail"
      @open-original="openWebOriginal"
    />
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
  --subscriptions-content-max: 680px;
}

.subscriptions-chrome-head {
  flex-shrink: 0;
}

.subscriptions-search-hub {
  width: 100%;
  max-width: var(--subscriptions-content-max);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 8px;
  padding-bottom: 12px;
}

.subscriptions-search-hub__mode {
  align-self: flex-start;
}

.subscriptions-search-hub__bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 6px 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--platform-border);
  background: var(--platform-ui-glass-fill-strong, var(--platform-bg-glass-subtle));
  box-shadow:
    0 1px 3px color-mix(in srgb, var(--platform-text) 8%, transparent),
    inset 0 1px 0 color-mix(in srgb, #fff 35%, transparent);
}

.subscriptions-search-hub__icon {
  flex-shrink: 0;
  color: var(--platform-text-tertiary);
}

.subscriptions-search-hub__input {
  flex: 1;
  min-width: 0;
}

.subscriptions-search-hub__input :deep(.n-input) {
  background: transparent !important;
}

.subscriptions-search-hub__input :deep(.n-input-wrapper) {
  background: transparent !important;
  box-shadow: none !important;
}

.subscriptions-search-hub__input :deep(.n-input__border),
.subscriptions-search-hub__input :deep(.n-input__state-border) {
  display: none;
}

.subscriptions-search-hub__submit {
  flex-shrink: 0;
  border-radius: 999px;
  padding-inline: 20px;
}

.subscriptions-search-hub__tools {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 12px;
  padding-inline: 4px;
}

.subscriptions-search-hub__count {
  margin-left: auto;
  font-size: 13px;
}

.subscriptions-ingest-panel {
  width: min(360px, 78vw);
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 2px;
}

.subscriptions-ingest-panel__label {
  font-size: 13px;
  color: var(--platform-text-secondary);
}

.subscriptions-ingest-panel__hint {
  font-size: 12px;
  line-height: 1.45;
}

.subscriptions-active-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-inline: 4px;
}

.subscriptions-filter-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(320px, 72vw);
  padding: 4px 2px;
}

.subscriptions-filter-panel__label {
  font-size: 13px;
  color: var(--platform-text-secondary);
}

.subscriptions-filter-panel__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.subscriptions-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.list-spin {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.list-spin :deep(.n-spin-container),
.list-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.subscriptions-list-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 0;
  box-sizing: border-box;
  -webkit-overflow-scrolling: touch;
}

.subscriptions-serp-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  max-width: var(--subscriptions-content-max);
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.subscriptions-empty {
  max-width: var(--subscriptions-content-max);
  padding: 24px 0;
}

.subscriptions-empty--hero {
  text-align: center;
  padding: 48px 16px 32px;
  color: var(--platform-text-secondary);
}

.subscriptions-empty__icon {
  color: var(--platform-text-tertiary);
  margin-bottom: 12px;
}

.subscriptions-empty__title {
  margin: 0 0 6px;
  font-size: 16px;
  color: var(--platform-text);
}

.subscriptions-empty__desc {
  margin: 0;
  font-size: 13px;
}

.serp-result-item {
  display: block;
  width: 100%;
  padding: 12px 8px;
  margin: 0 -8px;
  box-sizing: border-box;
  border-radius: 10px;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: none;
  transition: background-color 0.15s ease;
}

.serp-result-item:hover {
  background: color-mix(in srgb, var(--platform-text) 5%, transparent);
}

.serp-result-item--web {
  padding-bottom: 8px;
}

.serp-result-item__actions {
  display: flex;
  gap: 4px;
  margin-top: 4px;
  padding-left: 36px;
}

@media (hover: hover) {
  .serp-result-item__actions {
    opacity: 0;
    transition: opacity 0.15s ease;
  }

  .serp-result-item--web:hover .serp-result-item__actions {
    opacity: 1;
  }
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

.subscriptions-footer {
  flex-shrink: 0;
  padding: 10px 0 14px;
  border-top: 1px solid var(--platform-divider);
}

.subscriptions-footer__inner {
  width: 100%;
  max-width: var(--subscriptions-content-max);
  display: flex;
  justify-content: center;
}

.subscriptions-footer__inner :deep(.n-pagination) {
  flex-wrap: wrap;
  justify-content: center;
}
</style>
