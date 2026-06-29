<script setup>
import { useI18n } from "../composables/useI18n";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import IconAction from "../components/IconAction.vue";
import SubscriptionMonthRangeSlider from "../components/SubscriptionMonthRangeSlider.vue";
import { usePlatformUi } from "../composables/usePlatformUi";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { computed, nextTick, onActivated, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NEmpty,
  NIcon,
  NInput,
  NModal,
  NPagination,
  NSpin,
  NTag,
  NText,
} from "naive-ui";
import { LinkOutline, SearchOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import { fetchSubscriptionItems, ingestSubscriptionUrl } from "../api/client";
import { siteFaviconUrl } from "../utils/siteFavicon.js";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { t, locale, featureDescription } = useI18n();
const { headerExtensionActive } = usePageHeaderExtension();
const headerTeleportReady = ref(false);

const dateLocale = computed(() => (locale.value === "zh" ? "zh-CN" : "en-US"));

const loading = ref(true);
const itemsLoading = ref(false);
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = LIST_PAGE_SIZE;

const ingestUrl = ref("");
const ingesting = ref(false);
const ingestModalOpen = ref(false);

const searchKeyword = ref("");
const createdRange = ref(null);

let searchTimer = null;
let rangeTimer = null;

const hasDateFilter = computed(
  () => Array.isArray(createdRange.value) && createdRange.value.length === 2
);

const pageCount = computed(() =>
  Math.max(1, Math.ceil(total.value / pageSize))
);

const showPager = computed(() => total.value > pageSize);

const resultCountLabel = computed(() => {
  if (!searchKeyword.value.trim() && !hasDateFilter.value) {
    return total.value ? t("subscriptions.resultTotalSaved", { count: total.value }) : "";
  }
  return t("subscriptions.resultTotal", { count: total.value });
});

function fmtSerpDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(dateLocale.value, {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  } catch {
    return "";
  }
}

function siteLabel(item) {
  if (item?.is_wechat) return t("subscriptions.siteWechat");
  return domainFromUrl(item?.link || item?.url) || t("subscriptions.siteWeb");
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
  return siteFaviconUrl(url);
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
    created_to: to ? new Date(to).toISOString() : undefined,
  };
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
      created_to,
    });
    items.value = data.items || [];
    total.value = data.total || 0;
  } catch (e) {
    ui.error(e.message);
  } finally {
    itemsLoading.value = false;
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
  }
}

function scheduleLocalSearch() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    page.value = 1;
    loadItems();
  }, 350);
}

function submitSearch() {
  page.value = 1;
  loadItems();
}

function onPageChange(nextPage) {
  page.value = nextPage;
  loadItems();
}

function scheduleRangeFilter() {
  if (rangeTimer) clearTimeout(rangeTimer);
  rangeTimer = setTimeout(() => {
    page.value = 1;
    loadItems();
  }, 200);
}

function onCreatedRangeChange(next) {
  createdRange.value = next;
  scheduleRangeFilter();
}

watch(searchKeyword, scheduleLocalSearch);

async function onIngest(urlInput) {
  const url = (urlInput || ingestUrl.value).trim();
  if (!url) {
    ui.warning(t("subscriptions.needUrl"));
    return;
  }
  ingesting.value = true;
  try {
    const detail = await ingestSubscriptionUrl(url);
    ui.success(detail.summary ? t("subscriptions.ingestedWithSummary") : t("subscriptions.ingested"));
    ingestUrl.value = "";
    ingestModalOpen.value = false;
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

onMounted(() => {
  reload();
  nextTick(() => {
    headerTeleportReady.value = true;
  });
});

onUnmounted(() => {
  if (searchTimer) clearTimeout(searchTimer);
  if (rangeTimer) clearTimeout(rangeTimer);
  ingestModalOpen.value = false;
});

onActivated(() => {
  loadItems();
});

watch(
  () => route.query.refresh,
  (value) => {
    if (value) {
      loadItems();
    }
  }
);
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <Teleport
      v-if="headerTeleportReady && headerExtensionActive"
      to="#page-header-extension"
    >
      <div class="subscriptions-actions-bar">
        <div class="subscriptions-actions-toolbar">
          <NText depth="3" class="subscriptions-actions-hint">
            {{ featureDescription("knowledge-subscriptions") }}
          </NText>
          <div class="subscriptions-toolbar subscriptions-toolbar--secondary">
            <IconAction
              :label="t('subscriptions.ingest')"
              :icon="LinkOutline"
              type="primary"
              :loading="ingesting"
              @click="ingestModalOpen = true"
            />
          </div>
        </div>
      </div>
    </Teleport>

    <NModal
      v-model:show="ingestModalOpen"
      preset="card"
      :title="t('subscriptions.ingest')"
      class="subscriptions-ingest-modal"
      style="width: min(420px, 92vw)"
      :mask-closable="!ingesting"
      :close-on-esc="!ingesting"
    >
      <div class="subscriptions-ingest-panel">
        <div class="subscriptions-ingest-panel__label">{{ t("subscriptions.ingestLabel") }}</div>
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
          {{ t("subscriptions.ingest") }}
        </NButton>
        <NText depth="3" class="subscriptions-ingest-panel__hint">
          {{ t("subscriptions.ingestHint") }}
        </NText>
      </div>
    </NModal>

    <div class="subscriptions-page">
      <header class="feature-top-strip subscriptions-chrome-head">
        <div class="subscriptions-search-hub feature-local-nav">
          <div class="subscriptions-search-hub__bar">
            <NIcon :size="18" class="subscriptions-search-hub__icon" :component="SearchOutline" />
            <NInput
              v-model:value="searchKeyword"
              :placeholder="t('subscriptions.placeholderLocal')"
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
              {{ t("subscriptions.search") }}
            </NButton>
          </div>

          <SubscriptionMonthRangeSlider
            :model-value="createdRange"
            :locale="dateLocale"
            :label="t('subscriptions.filterDateLabel')"
            :clear-label="t('subscriptions.clear')"
            @update:model-value="onCreatedRangeChange"
          />

          <div class="subscriptions-search-hub__tools">
            <ListRefreshButton :loading="itemsLoading || loading" size="tiny" @click="reload" />

            <NText v-if="resultCountLabel" depth="3" class="subscriptions-search-hub__count">
              {{ resultCountLabel }}
            </NText>
          </div>
        </div>
      </header>

      <div class="subscriptions-body">
        <NSpin :show="itemsLoading || loading" class="list-spin" local>
          <div class="subscriptions-list-scroll">
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
                    {{ t("subscriptions.importedTag") }}
                  </NTag>
                </div>
                <h3 class="serp-result-item__title">{{ a.title }}</h3>
                <p class="serp-result-item__snippet">{{ a.summary || t("subscriptions.noSummary") }}</p>
                <div class="serp-result-item__meta">
                  <NTag
                    v-if="a.is_wechat"
                    size="small"
                    :bordered="false"
                    class="serp-result-item__wechat-tag"
                  >
                    {{ t("subscriptions.wechatTag") }}
                  </NTag>
                  <span v-if="fmtSerpDate(a.created_at || a.publish_at)" class="serp-result-item__date">
                    {{ fmtSerpDate(a.created_at || a.publish_at) }}
                  </span>
                </div>
              </article>
            </div>
            <div v-else-if="!loading" class="subscriptions-empty">
              <NEmpty :description="t('subscriptions.emptyLocal')" />
            </div>
          </div>
        </NSpin>
      </div>

      <footer v-if="showPager" class="subscriptions-footer feature-bottom-strip">
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

.subscriptions-chrome-head {
  flex-shrink: 0;
}

.subscriptions-search-hub {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 8px;
  padding-bottom: 12px;
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
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.subscriptions-ingest-panel__label {
  font-size: 13px;
  color: var(--platform-text-secondary);
}

.subscriptions-ingest-panel__hint {
  font-size: 12px;
  line-height: 1.45;
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
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.subscriptions-empty {
  width: 100%;
  padding: 24px 0;
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
}

.subscriptions-footer__inner {
  width: 100%;
  display: flex;
  justify-content: center;
}

.subscriptions-footer__inner :deep(.n-pagination) {
  flex-wrap: wrap;
  justify-content: center;
}
</style>
