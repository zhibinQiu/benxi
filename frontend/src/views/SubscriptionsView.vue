<script setup>
import { useI18n } from "../composables/useI18n";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onActivated, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NEmpty,
  NIcon,
  NInput,
  NPagination,
  NSpin,
  NTag,
} from "naive-ui";
import { AddOutline, SearchOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import { fetchSubscriptionItems, importSubscriptionItem, ingestSubscriptionUrl } from "../api/client";
import { useAuth } from "../composables/useAuth";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { t } = useI18n();
const { isSystemAdmin } = useAuth();

const loading = ref(false);
const itemsLoading = ref(false);
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = LIST_PAGE_SIZE;

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

async function loadItems() {
  itemsLoading.value = true;
  try {
    const data = await fetchSubscriptionItems({
      page: page.value,
      page_size: pageSize,
      keyword: appliedSearch.value || undefined,
      all_users: isSystemAdmin.value,
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

    <div class="subscriptions-page">
      <div class="subscriptions-toolbar">
        <div class="subscriptions-search-hub__bar">
          <NIcon :size="18" class="subscriptions-search-hub__icon" :component="inputIsUrl ? AddOutline : SearchOutline" />
          <NInput
            v-model:value="searchKeyword"
            :placeholder="t('subscriptions.placeholderUnified')"
            clearable
            size="small"
            class="subscriptions-search-hub__input"
            @keyup.enter="onSmartSubmit"
          />
          <NButton
            type="primary"
            size="small"
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
            <div v-if="items.length" class="subscriptions-card">
              <div class="subscriptions-serp-list" role="list">
              <article
                v-for="a in items"
                :key="a.ref"
                role="listitem"
                class="serp-result-item"
                @click="openItem(a.ref)"
              >
                <h3 class="serp-result-item__title">{{ a.title }}</h3>
                <p class="serp-result-item__snippet">{{ a.summary || t("subscriptions.noSummary") }}</p>
                <div class="serp-result-item__footer">
                <div class="serp-result-item__meta">
                  <span v-if="a.owner_name" class="serp-result-item__owner">{{ a.owner_name }}</span>
                  <span v-if="fmtSerpDate(a.created_at || a.publish_at)" class="serp-result-item__date">
                    {{ fmtSerpDate(a.created_at || a.publish_at) }}
                  </span>
                  <span class="serp-result-item__meta-sep">·</span>
                  <span class="serp-result-item__source-text">
                    <span class="serp-result-item__site">{{ siteLabel(a) }}</span>
                    <span v-if="breadcrumbPath(a.link)" class="serp-result-item__path">
                      › {{ breadcrumbPath(a.link) }}
                    </span>
                  </span>
                </div>
                  <div class="serp-result-item__actions">
                  <NButton
                    v-if="a.imported"
                    size="tiny"
                    secondary
                    disabled
                    class="serp-result-item__import-btn serp-result-item__imported-btn"
                  >
                    {{ t("subscriptions.importedTag") }}
                  </NButton>
                  <NButton
                    v-else
                    size="tiny"
                    secondary
                    :loading="importingRefs.has(a.ref)"
                    class="serp-result-item__import-btn"
                    @click.stop="onImportItem(a.ref)"
                  >
                    {{ t("subscriptions.importBtn") }}
                  </NButton>
                </div>
                </div>
              </article>
            </div>
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
  padding: 8px 16px 0;
}

/* ── Toolbar ── */
.subscriptions-toolbar {
  flex-shrink: 0;
  padding: 20px 0 12px;
}

/* ── Search hub pill ── */
.subscriptions-search-hub__bar {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 600px;
  max-width: 100%;
  flex-shrink: 0;
  min-width: 0;
  padding: 3px 3px 3px 12px;
  border-radius: 1199px;
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
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
  padding-inline: 20px;
}

.subscriptions-search-hub__submit,
.subscriptions-search-hub__submit:focus,
.subscriptions-search-hub__submit:hover,
.subscriptions-search-hub__submit:active {
  border: none !important;
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

.subscriptions-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: var(--platform-card-bg);
  overflow: hidden;
}

.subscriptions-serp-list {
  display: flex;
  flex-direction: column;
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
  padding: 14px 16px;
  margin: 0;
  box-sizing: border-box;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--platform-border);
  transition: background-color 0.18s ease;
}

.serp-result-item:hover {
  background: var(--platform-accent-soft);
}

.serp-result-item:last-child {
  border-bottom: none;
}

.serp-result-item__title {
  margin: 0 0 6px;
  font-size: var(--platform-font-size-lg);
  font-weight: 500;
  line-height: 1.4;
  letter-spacing: -0.01em;
  color: var(--platform-text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color 0.15s ease;
}

.serp-result-item:hover .serp-result-item__title {
  color: var(--platform-accent);
}

.serp-result-item__snippet {
  margin: 0 0 8px;
  font-size: var(--platform-font-size-sm);
  line-height: 1.55;
  color: var(--platform-text-tertiary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Meta row ── */
.serp-result-item__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px 6px;
  font-size: var(--platform-font-size-xs);
  color: var(--platform-text-tertiary);
}

.serp-result-item__owner {
  font-size: var(--platform-font-size-xs);
  color: var(--platform-text-tertiary);
}

.serp-result-item__owner::before {
  content: "@";
  margin-right: 1px;
  opacity: 0.6;
}

.serp-result-item__date {
  font-size: var(--platform-font-size-xs);
  color: var(--platform-text-tertiary);
}

.serp-result-item__meta-sep {
  opacity: 0.35;
  user-select: none;
}

.serp-result-item__source-text {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.serp-result-item__site {
  color: var(--platform-text-quaternary);
}

.serp-result-item__path {
  color: var(--platform-text-quaternary);
}

/* ── Footer: meta + actions in same row ── */
.serp-result-item__footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.serp-result-item__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.18s ease;
}

.serp-result-item:hover .serp-result-item__actions {
  opacity: 1;
}

.serp-result-item__import-btn {
  flex-shrink: 0;
}
.serp-result-item__import-btn:not(:disabled):not(.serp-result-item__imported-btn):hover {
  background: var(--platform-accent-soft);
  border-color: var(--platform-accent-border-soft);
}
.serp-result-item__imported-btn {
  pointer-events: none;
  opacity: 0.5;
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
  font-size: var(--platform-font-size-xs);
  color: var(--platform-text-tertiary);
  user-select: none;
  letter-spacing: 0.04em;
}

.subscriptions-footer__inner :deep(.n-pagination) {
  flex-wrap: wrap;
  justify-content: center;
}

@media (max-width: 768px) {
  .subscriptions-search-hub__bar {
    width: 100%;
    gap: 8px;
    padding: 4px 4px 4px 10px;
  }
  .subscriptions-search-hub__submit {
    padding-inline: 12px;
    font-size: 13px;
  }

  .serp-result-item {
    padding: 12px;
  }
}
</style>
