<script setup>
defineOptions({ name: "CarbonNewsView" });

import { computed, ref } from "vue";
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NIcon,
  NInput,
  NPagination,
  NSpin,
  NTag,
} from "naive-ui";
import { ChatbubbleEllipsesOutline, SearchOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { askCarbonNews, crawlCarbonNews } from "../api/client";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { renderMarkdown } from "../utils/markdown.js";
import { openExternal } from "../utils/openExternal.js";

const { t } = useI18n();
const ui = usePlatformUi();

/** 列表每页条数；一次爬取上限 */
const PAGE_SIZE = 8;
const CRAWL_LIMIT = 100;

const crawlKeyword = ref("碳");
const crawling = ref(false);
const items = ref([]);
const totalHits = ref(0);
const lastKeyword = ref("");
const page = ref(1);

const question = ref("");
const asking = ref(false);
const answerMd = ref("");
const sources = ref([]);

const detailOpen = ref(false);
const detailItem = ref(null);

const hasItems = computed(() => items.value.length > 0);
const pageCount = computed(() =>
  Math.max(1, Math.ceil(items.value.length / PAGE_SIZE))
);
const pagedItems = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE;
  return items.value.slice(start, start + PAGE_SIZE);
});
const answerHtml = computed(() =>
  answerMd.value ? renderMarkdown(answerMd.value) : ""
);

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

function fmtDate(raw) {
  if (!raw) return "";
  try {
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return String(raw);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(raw);
  }
}

function snippetOf(item) {
  const body = String(item?.body || "").replace(/\s+/g, " ").trim();
  if (!body) return t("carbonNews.noBody");
  return body.length > 160 ? `${body.slice(0, 157)}…` : body;
}

function openDetail(item) {
  detailItem.value = item;
  detailOpen.value = true;
}

function openSource(url) {
  if (url) openExternal(url);
}

function onPageChange(nextPage) {
  page.value = nextPage;
}

async function onCrawl() {
  const keyword = crawlKeyword.value.trim() || "碳";
  crawling.value = true;
  answerMd.value = "";
  sources.value = [];
  page.value = 1;
  try {
    const data = await crawlCarbonNews({
      keyword,
      limit: CRAWL_LIMIT,
    });
    items.value = data?.items || [];
    totalHits.value = Number(data?.total_hits || items.value.length);
    lastKeyword.value = data?.keyword || keyword;
    if (!items.value.length) {
      ui.warning(t("carbonNews.crawlEmpty"));
    } else {
      ui.success(
        t("carbonNews.crawlDone", {
          count: items.value.length,
          hits: totalHits.value,
        })
      );
    }
  } catch (e) {
    ui.error(e.message || t("carbonNews.crawlFailed"));
  } finally {
    crawling.value = false;
  }
}

async function onAsk() {
  const q = question.value.trim();
  if (!q) return;
  if (!hasItems.value) {
    ui.warning(t("carbonNews.needCrawlFirst"));
    return;
  }
  asking.value = true;
  try {
    const data = await askCarbonNews({
      question: q,
      items: items.value,
    });
    answerMd.value = data?.answer_md || "";
    sources.value = data?.sources || [];
    if (!answerMd.value) {
      ui.warning(t("carbonNews.askEmpty"));
    }
  } catch (e) {
    ui.error(e.message || t("carbonNews.askFailed"));
  } finally {
    asking.value = false;
  }
}
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="carbon-news-page">
      <div class="carbon-news-toolbar">
        <div class="carbon-news-bar">
          <NIcon :size="18" class="carbon-news-bar__icon" :component="SearchOutline" />
          <NInput
            v-model:value="crawlKeyword"
            :placeholder="t('carbonNews.crawlPlaceholder')"
            clearable
            size="small"
            class="carbon-news-bar__input"
            @keyup.enter="onCrawl"
          />
          <NButton
            size="small"
            type="primary"
            class="carbon-news-bar__submit"
            :loading="crawling"
            @click="onCrawl"
          >
            {{ t("carbonNews.crawl") }}
          </NButton>
        </div>

        <div class="carbon-news-bar carbon-news-bar--ask">
          <NIcon
            :size="18"
            class="carbon-news-bar__icon"
            :component="ChatbubbleEllipsesOutline"
          />
          <NInput
            v-model:value="question"
            :placeholder="t('carbonNews.askPlaceholder')"
            clearable
            size="small"
            class="carbon-news-bar__input"
            :disabled="!hasItems"
            @keyup.enter="onAsk"
          />
          <NButton
            size="small"
            class="carbon-news-bar__submit"
            :loading="asking"
            :disabled="!hasItems"
            @click="onAsk"
          >
            {{ t("carbonNews.ask") }}
          </NButton>
        </div>
      </div>

      <div v-if="answerMd" class="carbon-news-answer">
        <div class="carbon-news-answer__title">{{ t("carbonNews.answerTitle") }}</div>
        <div class="carbon-news-answer__body md-rich" v-html="answerHtml" />
        <div v-if="sources.length" class="carbon-news-sources">
          <div class="carbon-news-sources__title">{{ t("carbonNews.sourcesTitle") }}</div>
          <ol class="carbon-news-sources__list">
            <li v-for="s in sources" :key="s.index" class="carbon-news-sources__item">
              <button
                type="button"
                class="carbon-news-sources__link"
                :disabled="!s.url"
                @click="openSource(s.url)"
              >
                [{{ s.index }}] {{ s.title }}
              </button>
              <span class="carbon-news-sources__meta">
                <NTag v-if="s.doc_type" size="tiny" :bordered="false">{{ s.doc_type }}</NTag>
                <span v-if="s.published_at">{{ fmtDate(s.published_at) }}</span>
                <span v-if="s.source">{{ s.source }}</span>
              </span>
            </li>
          </ol>
        </div>
      </div>

      <div class="carbon-news-body">
        <div v-if="lastKeyword" class="carbon-news-meta">
          {{
            t("carbonNews.listMeta", {
              keyword: lastKeyword,
              total: items.length,
              page: page,
              pageCount: pageCount,
              pageSize: PAGE_SIZE,
              hits: totalHits,
            })
          }}
        </div>
        <NSpin :show="crawling" class="list-spin" local>
          <div class="carbon-news-list-scroll">
            <div v-if="pagedItems.length" class="carbon-news-feed" role="list">
              <article
                v-for="(a, idx) in pagedItems"
                :key="`${a.url || a.title}-${(page - 1) * PAGE_SIZE + idx}`"
                role="listitem"
                class="serp-result-item"
                @click="openDetail(a)"
              >
                <div class="serp-result-item__cite">
                  <NTag
                    v-if="a.doc_type"
                    size="tiny"
                    type="info"
                    :bordered="false"
                    class="serp-result-item__type"
                  >
                    {{ a.doc_type }}
                  </NTag>
                  <span class="serp-result-item__site">
                    {{ a.source || domainFromUrl(a.url) || t("carbonNews.siteDefault") }}
                  </span>
                  <span v-if="breadcrumbPath(a.url)" class="serp-result-item__path">
                    › {{ breadcrumbPath(a.url) }}
                  </span>
                </div>
                <h3 class="serp-result-item__title">{{ a.title || t("carbonNews.untitled") }}</h3>
                <p class="serp-result-item__snippet">{{ snippetOf(a) }}</p>
                <div class="serp-result-item__footer">
                  <div class="serp-result-item__meta">
                    <span v-if="fmtDate(a.published_at)" class="serp-result-item__date">
                      {{ fmtDate(a.published_at) }}
                    </span>
                  </div>
                </div>
              </article>
            </div>
            <div v-else-if="!crawling" class="carbon-news-empty">
              <NEmpty :description="t('carbonNews.emptyHint')" />
            </div>
          </div>
        </NSpin>
      </div>

      <footer v-if="items.length" class="carbon-news-footer">
        <div class="carbon-news-footer__inner">
          <div class="carbon-news-page-indicator">{{ page }} / {{ pageCount }}</div>
          <NPagination
            :page="page"
            :page-count="pageCount"
            :page-slot="7"
            @update:page="onPageChange"
          />
        </div>
      </footer>
    </div>

    <NDrawer v-model:show="detailOpen" :width="560" placement="right">
      <NDrawerContent
        :title="detailItem?.title || t('carbonNews.untitled')"
        closable
      >
        <div v-if="detailItem" class="carbon-news-detail">
          <div class="carbon-news-detail__meta">
            <NTag v-if="detailItem.doc_type" size="small" :bordered="false">
              {{ detailItem.doc_type }}
            </NTag>
            <span v-if="detailItem.published_at">{{ fmtDate(detailItem.published_at) }}</span>
            <span v-if="detailItem.source">{{ detailItem.source }}</span>
          </div>
          <NButton
            v-if="detailItem.url"
            size="small"
            quaternary
            class="carbon-news-detail__open"
            @click="openSource(detailItem.url)"
          >
            {{ t("carbonNews.openOriginal") }}
          </NButton>
          <div class="carbon-news-detail__body">
            {{ detailItem.body || t("carbonNews.noBody") }}
          </div>
        </div>
      </NDrawerContent>
    </NDrawer>
  </FeatureSubsystemShell>
</template>

<style scoped>
.carbon-news-page {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 8px 16px 0;
}

.carbon-news-toolbar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 0 12px;
}

.carbon-news-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 720px;
  max-width: 100%;
  padding: 3px 3px 3px 12px;
  border-radius: 1199px;
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
}

.carbon-news-bar__icon {
  flex-shrink: 0;
  color: var(--platform-text-tertiary);
}

.carbon-news-bar__input {
  flex: 1;
  min-width: 0;
}

.carbon-news-bar__input :deep(.n-input) {
  background: transparent !important;
}

.carbon-news-bar__input :deep(.n-input-wrapper) {
  background: transparent !important;
  box-shadow: none !important;
}

.carbon-news-bar__input :deep(.n-input__border),
.carbon-news-bar__input :deep(.n-input__state-border) {
  display: none;
}

.carbon-news-bar__submit {
  flex-shrink: 0;
  padding-inline: 16px;
  border-radius: 1199px;
}

.carbon-news-answer {
  flex-shrink: 0;
  margin-bottom: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
  max-height: 42vh;
  overflow: auto;
}

.carbon-news-answer__title,
.carbon-news-sources__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--platform-text-secondary);
  margin-bottom: 8px;
}

.carbon-news-answer__body {
  font-size: 14px;
  line-height: 1.65;
  color: var(--platform-text);
}

.carbon-news-sources {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--platform-border);
}

.carbon-news-sources__list {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.carbon-news-sources__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.carbon-news-sources__link {
  border: 0;
  background: transparent;
  padding: 0;
  text-align: left;
  color: var(--platform-primary, #2080f0);
  cursor: pointer;
  font-size: 13px;
}

.carbon-news-sources__link:disabled {
  color: var(--platform-text);
  cursor: default;
}

.carbon-news-sources__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.carbon-news-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.carbon-news-meta {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--platform-text-tertiary);
  margin-bottom: 8px;
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

.carbon-news-list-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.carbon-news-feed {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 12px;
}

.serp-result-item {
  padding: 12px 10px;
  border-radius: 10px;
  cursor: pointer;
}

.serp-result-item:hover {
  background: color-mix(in srgb, var(--platform-bg-elevated) 70%, transparent);
}

.serp-result-item__cite {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--platform-text-tertiary);
  margin-bottom: 4px;
}

.serp-result-item__title {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: var(--platform-primary, #1a0dab);
  line-height: 1.35;
}

.serp-result-item__snippet {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--platform-text-secondary);
}

.serp-result-item__footer {
  margin-top: 6px;
}

.serp-result-item__date {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.carbon-news-empty {
  padding: 48px 0;
}

.carbon-news-footer {
  flex-shrink: 0;
  padding: 8px 0 12px;
  border-top: 1px solid var(--platform-border);
}

.carbon-news-footer__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.carbon-news-page-indicator {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.carbon-news-detail__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--platform-text-tertiary);
  margin-bottom: 10px;
}

.carbon-news-detail__open {
  margin-bottom: 12px;
}

.carbon-news-detail__body {
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.7;
  color: var(--platform-text);
}
</style>
