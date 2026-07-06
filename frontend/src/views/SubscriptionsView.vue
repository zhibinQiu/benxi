<script setup>
import { useI18n } from "../composables/useI18n";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import { usePlatformUi } from "../composables/usePlatformUi";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { computed, onActivated, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NEmpty,
  NIcon,
  NInput,
  NPagination,
  NSpin,
  NSwitch,
  NTag,
} from "naive-ui";
import { AddOutline, SearchOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import { fetchSubscriptionItems, importSubscriptionItem, ingestSubscriptionUrl } from "../api/client";
import { siteFaviconUrl } from "../utils/siteFavicon.js";
import { useAuth } from "../composables/useAuth";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { t } = useI18n();
const { headerExtensionActive } = usePageHeaderExtension();
const { isSystemAdmin } = useAuth();

const loading = ref(false);
const itemsLoading = ref(false);
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = LIST_PAGE_SIZE;
const viewAllUsers = ref(false);

const appliedSearch = ref("");

const ingesting = ref(false);
const importingRefs = ref(new Set());

function onImportItem(ref) {
  importingRefs.value = new Set([...importingRefs.value, ref]);
  importSubscriptionItem(ref)
    .then(() => {
      const item = items.value.find((a) => a.ref === ref);
      if (item) item.imported = true;
    })
    .catch((e) => {
      ui.error(e.message);
    })
    .finally(() => {
      const next = new Set(importingRefs.value);
      next.delete(ref);
      importingRefs.value = next;
    });
}

const searchKeyword = ref("");

const trimmedInput = computed(() => searchKeyword.value.trim());

function looksLikeUrl(text) {
  if (!text) return false;
  const lower = text.toLowerCase();
  if (/^https?:\/\//i.test(lower)) return true;
  if (/^www\./i.test(lower)) return true;
  if (/^[a-z0-9]([a-z0-9-]*[a-z0-9])?\.[a-z]{2,}/i.test(lower) && !/\s/.test(lower)) return true;
  return false;
}

const inputIsUrl = computed(() => looksLikeUrl(trimmedInput.value));

const smartButtonLabel = computed(() =>
  inputIsUrl.value
    ? t("subscriptions.ingest")
    : t("subscriptions.searchOrIngest")
);

const pageCount = computed(() =>
  Math.max(1, Math.ceil(total.value / pageSize))
);

const resultCountLabel = computed(() => {
  if (itemsLoading.value) return "";
  if (appliedSearch.value) {
    return t("subscriptions.resultsForKeyword", {
      keyword: appliedSearch.value,
      count: total.value,
    });
  }
  return t("subscriptions.resultTotal", { count: total.value });
});

function fmtSerpDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
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

async function loadItems() {
  itemsLoading.value = true;
  try {
    const data = await fetchSubscriptionItems({
      page: page.value,
      page_size: pageSize,
      keyword: appliedSearch.value || undefined,
      all_users: isSystemAdmin.value && viewAllUsers.value,
    });
    items.value = data.items || [];
    total.value = data.total || 0;
  } catch (e) {
    ui.error(e.message);
  } finally {
    itemsLoading.value = false;
    loading.value = false;
  }
}

function submitSearch() {
  const keyword = searchKeyword.value.trim();
  appliedSearch.value = keyword;
  page.value = 1;
  loading.value = true;
  loadItems();
}

async function onSmartSubmit() {
  const text = trimmedInput.value;
  if (!text) return;
  if (inputIsUrl.value) {
    ingesting.value = true;
    try {
      const url = /^https?:\/\//i.test(text) ? text : `https://${text}`;
      const detail = await ingestSubscriptionUrl(url);
      ui.success(detail.summary ? t("subscriptions.ingestedWithSummary") : t("subscriptions.ingested"));
      searchKeyword.value = "";
      await loadItems();
      openItem(detail.ref);
    } catch (e) {
      ui.error(e.message);
    } finally {
      ingesting.value = false;
    }
  } else {
    submitSearch();
  }
}

function onPageChange(nextPage) {
  page.value = nextPage;
  loadItems();
}

function onViewAllUsersChange(val) {
  viewAllUsers.value = val;
  page.value = 1;
  loading.value = true;
  loadItems();
}

function openItem(ref) {
  navigateWithReturn(
    router,
    { name: "subscription-item", params: { ref } },
    route
  );
}

onMounted(() => {
  loadItems();
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
    <Teleport v-if="headerExtensionActive" to="#page-header-extension">
      <div class="subscriptions-actions-bar">
        <div class="subscriptions-actions-toolbar">
          <div class="subscriptions-toolbar__count">
            <NIcon :size="16" :component="SearchOutline" class="subscriptions-toolbar__icon" />
            <span class="subscriptions-toolbar__hint">{{ resultCountLabel }}</span>
          </div>
          <div v-if="isSystemAdmin" class="subscriptions-toolbar__admin-toggle">
            <span class="subscriptions-toolbar__admin-label">{{ t("subscriptions.viewAllUsers") }}</span>
            <NSwitch v-model:value="viewAllUsers" @update:value="onViewAllUsersChange" />
          </div>
        </div>
      </div>
    </Teleport>

    <div class="subscriptions-page">
      <div class="subscriptions-hero">
        <h2 class="subscriptions-hero__title">{{ t("subscriptions.heroTitle") }}</h2>
      </div>

      <div class="subscriptions-toolbar">
        <div class="subscriptions-search-hub__bar">
          <NIcon :size="22" class="subscriptions-search-hub__icon" :component="inputIsUrl ? AddOutline : SearchOutline" />
          <NInput
            v-model:value="searchKeyword"
            :placeholder="t('subscriptions.placeholderUnified')"
            clearable
            class="subscriptions-search-hub__input"
            @keyup.enter="onSmartSubmit"
          />
          <NButton
            type="primary"
            class="subscriptions-search-hub__submit"
            :loading="itemsLoading || ingesting"
            @click="onSmartSubmit"
          >
            {{ smartButtonLabel }}
          </NButton>
        </div>
      </div>

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
                  <NButton
                    v-else
                    size="tiny"
                    quaternary
                    type="primary"
                    :loading="importingRefs.has(a.ref)"
                    class="serp-result-item__import-btn"
                    @click.stop="onImportItem(a.ref)"
                  >
                    {{ t("subscriptions.importBtn") }}
                  </NButton>
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
                  <NTag
                    v-if="a.owner_name"
                    size="small"
                    :bordered="false"
                    class="serp-result-item__owner-tag"
                  >
                    {{ a.owner_name }}
                  </NTag>
                  <span v-if="fmtSerpDate(a.created_at || a.publish_at)" class="serp-result-item__date">
                    {{ fmtSerpDate(a.created_at || a.publish_at) }}
                  </span>
                </div>
              </article>
            </div>
            <div v-else-if="!loading && !itemsLoading" class="subscriptions-empty">
              <NEmpty :description="t('subscriptions.emptySearch')" />
            </div>
          </div>
        </NSpin>
      </div>

      <footer v-if="items.length" class="subscriptions-footer">
        <div class="subscriptions-footer__inner">
          <div class="subscriptions-page-indicator">{{ page }} / {{ pageCount }}</div>
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
  padding-top: 8px;
}

/* ── Toolbar ── */
.subscriptions-toolbar {
  flex-shrink: 0;
  padding: 0 0 12px;
}

.subscriptions-toolbar__count {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  white-space: nowrap;
}

.subscriptions-toolbar__icon {
  flex-shrink: 0;
  color: var(--platform-text-tertiary);
}

.subscriptions-toolbar__hint {
  font-size: 14px;
  color: var(--platform-text-tertiary);
  white-space: nowrap;
}

.subscriptions-toolbar__admin-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.subscriptions-toolbar__admin-label {
  font-size: 14px;
  color: var(--platform-text-secondary);
  white-space: nowrap;
}

/* ── Hero title ── */
.subscriptions-hero {
  flex-shrink: 0;
  padding: 36px 4px 24px;
}

.subscriptions-hero__title {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
  letter-spacing: var(--platform-tracking-tight, -0.014em);
}


/* ── Search hub pill ── */
.subscriptions-search-hub__bar {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 600px;
  flex-shrink: 0;
  min-width: 0;
  padding: 5px 5px 5px 14px;
  border-radius: 1199px;
  border: 1px solid var(--platform-border);
  background: var(--platform-ui-glass-fill-strong, var(--platform-bg-glass-subtle));
  box-shadow:
    0 1px 4px color-mix(in srgb, var(--platform-text) 8%, transparent),
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
  border-radius: 1199px;
  padding-inline: 24px;
}

/* ── Body ── */
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
  padding: 5px 0;
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
  padding: 29px 0;
}

/* ── Result items ── */
.serp-result-item {
  display: block;
  width: 100%;
  padding: 10px 10px;
  margin: 0 -10px;
  box-sizing: border-box;
  border-radius: 12px;
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
  margin-bottom: 5px;
}

.serp-result-item__favicon {
  position: relative;
  flex-shrink: 0;
  width: 31px;
  height: 31px;
  border-radius: 50%;
  overflow: hidden;
  background: var(--platform-bg-muted, color-mix(in srgb, var(--platform-text) 6%, transparent));
  display: flex;
  align-items: center;
  justify-content: center;
}

.serp-result-item__favicon-img {
  width: 22px;
  height: 22px;
  object-fit: contain;
}

.serp-result-item__favicon-fallback {
  font-size: 14px;
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
  font-size: 14px;
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
  font-size: 18px;
  font-weight: 500;
  line-height: 1.35;
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
  line-height: 1.55;
  color: var(--platform-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
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
  font-size: 14px;
  color: var(--platform-text-tertiary);
}

.serp-result-item__import-btn {
  flex-shrink: 0;
}

.serp-result-item__owner-tag {
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent) !important;
  color: var(--platform-accent) !important;
}

/* ── Footer ── */
.subscriptions-footer {
  flex-shrink: 0;
  padding: 12px 0 17px;
}

.subscriptions-footer__inner {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.subscriptions-page-indicator {
  flex-shrink: 0;
  font-size: 14px;
  color: var(--platform-text-tertiary);
  user-select: none;
  letter-spacing: 0.04em;
}

.subscriptions-footer__inner :deep(.n-pagination) {
  flex-wrap: wrap;
  justify-content: center;
}
</style>
