<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCard,
  NEmpty,
  NForm,
  NFormItem,
  NGrid,
  NGi,
  NInput,
  NList,
  NListItem,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import {
  createWechatMpSource,
  deleteWechatMpSource,
  fetchWechatMpArticles,
  fetchWechatMpSources,
  ingestWechatMpUrl,
  parseWechatMpUrl,
  syncWechatMpSource } from "../api/client";
import { useI18n } from "../composables/useI18n";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { t, locale } = useI18n();

const dateLocale = computed(() => (locale.value === "zh" ? "zh-CN" : "en-US"));

const loading = ref(true);
const articlesLoading = ref(false);
const sources = ref([]);
const articles = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const filterSourceId = ref(null);

const showAdd = ref(false);
const showIngest = ref(false);
const addForm = ref({ name: "", sample_url: "", biz: "" });
const ingestUrl = ref("");
const parsePreview = ref(null);
const submitting = ref(false);

const sourceOptions = computed(() => [
  { label: t("wechatMpFeed.allSources"), value: null },
  ...sources.value.map((s) => ({
    label: `${s.name} (${s.article_count || 0})`,
    value: s.id})),
]);

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(dateLocale.value, { hour12: false });
  } catch {
    return iso;
  }
}

async function loadSources() {
  sources.value = await fetchWechatMpSources();
}

async function loadArticles() {
  articlesLoading.value = true;
  try {
    const data = await fetchWechatMpArticles({
      page: page.value,
      page_size: pageSize,
      source_id: filterSourceId.value || undefined});
    articles.value = data.items || [];
    total.value = data.total || 0;
  } catch (e) {
    ui.error(e.message);
  } finally {
    articlesLoading.value = false;
  }
}

async function reload() {
  loading.value = true;
  try {
    await loadSources();
    await loadArticles();
  } catch (e) {
    ui.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function onPreviewUrl() {
  if (!addForm.value.sample_url?.trim()) return;
  try {
    parsePreview.value = await parseWechatMpUrl(addForm.value.sample_url.trim());
    if (!addForm.value.name && parsePreview.value.account_name) {
      addForm.value.name = parsePreview.value.account_name;
    }
    if (parsePreview.value.biz) {
      addForm.value.biz = parsePreview.value.biz;
    }
  } catch (e) {
    ui.error(e.message);
  }
}

async function submitAdd() {
  const name = addForm.value.name?.trim();
  const url = addForm.value.sample_url?.trim();
  const biz = addForm.value.biz?.trim();
  if (!name || (!url && !biz)) {
    ui.warning(t("wechatMpFeed.fillNameAndBiz"));
    return;
  }
  submitting.value = true;
  try {
    await createWechatMpSource({
      name,
      sample_url: url || undefined,
      biz: biz || undefined});
    ui.success(t("wechatMpFeed.trackingAdded"));
    showAdd.value = false;
    addForm.value = { name: "", sample_url: "", biz: "" };
    parsePreview.value = null;
    await reload();
  } catch (e) {
    ui.error(e.message);
  } finally {
    submitting.value = false;
  }
}

async function submitIngest() {
  const url = ingestUrl.value.trim();
  if (!url) return;
  submitting.value = true;
  try {
    const art = await ingestWechatMpUrl(url);
    ui.success(t("wechatMpFeed.ingested"));
    showIngest.value = false;
    ingestUrl.value = "";
    await reload();
    navigateWithReturn(
      router,
      { name: "wechat-mp-article", params: { id: art.id } },
      route
    );
  } catch (e) {
    ui.error(e.message);
  } finally {
    submitting.value = false;
  }
}

async function onSyncSource(source) {
  try {
    const res = await syncWechatMpSource(source.id);
    ui.info(res.message || t("wechatMpFeed.syncDone"));
    await reload();
  } catch (e) {
    ui.error(e.message);
  }
}

async function onRemoveSource(source) {
  try {
    await deleteWechatMpSource(source.id);
    ui.success(t("wechatMpFeed.trackingRemoved"));
    if (filterSourceId.value === source.id) filterSourceId.value = null;
    await reload();
  } catch (e) {
    ui.error(e.message);
  }
}

function openArticle(id) {
  navigateWithReturn(
    router,
    { name: "wechat-mp-article", params: { id } },
    route
  );
}

onMounted(reload);
</script>

<template>
  <FeatureSubsystemShell fill>
    <NSpin :show="loading">
      <div class="mp-feed-layout">
        <aside class="mp-feed-sidebar">
          <NSpace vertical :size="12">
            <NButton type="primary" block @click="showAdd = true">{{ t("wechatMpFeed.addTracking") }}</NButton>
            <NButton block tertiary @click="showIngest = true">{{ t("wechatMpFeed.pasteLinkIngest") }}</NButton>
          </NSpace>
          <NText depth="3" style="display: block; margin: 16px 0 8px; font-size: 12px">
            {{ t("wechatMpFeed.myTracking") }}
          </NText>
          <NList v-if="sources.length" hoverable clickable>
            <NListItem
              v-for="s in sources"
              :key="s.id"
              @click="filterSourceId = s.id; page = 1; loadArticles()"
            >
              <div class="source-row">
                <div>
                  <div class="source-name">{{ s.name }}</div>
                  <NText depth="3" style="font-size: 12px">{{ t("wechatMpFeed.articleCount", { count: s.article_count }) }}</NText>
                </div>
                <NSpace size="small">
                  <NButton size="tiny" quaternary @click.stop="onSyncSource(s)">{{ t("wechatMpFeed.sync") }}</NButton>
                  <NButton size="tiny" quaternary type="error" @click.stop="onRemoveSource(s)">
                    {{ t("wechatMpFeed.remove") }}
                  </NButton>
                </NSpace>
              </div>
            </NListItem>
          </NList>
          <NEmpty v-else :description="t('wechatMpFeed.noTracking')" size="small" />
        </aside>

        <main class="mp-feed-main">
          <NSpace justify="space-between" align="center" style="margin-bottom: 12px">
            <NSelect
              v-model:value="filterSourceId"
              :options="sourceOptions"
              style="width: 240px"
              @update:value="() => { page = 1; loadArticles(); }"
            />
            <NText depth="3">{{ t("wechatMpFeed.totalArticles", { total }) }}</NText>
          </NSpace>

          <NSpin :show="articlesLoading">
            <NGrid v-if="articles.length" cols="1 s:2 m:3" :x-gap="16" :y-gap="16">
              <NGi v-for="a in articles" :key="a.id">
                <NCard
                  hoverable
                  class="article-card"
                  @click="openArticle(a.id)"
                >
                  <div
                    v-if="a.cover_url"
                    class="cover"
                    :style="{ backgroundImage: `url(${a.cover_url})` }"
                  />
                  <div v-else class="cover cover-placeholder">{{ t("wechatMpFeed.accountPlaceholder") }}</div>
                  <div class="card-body">
                    <div class="card-title">{{ a.title }}</div>
                    <NText depth="3" class="card-summary" :line-clamp="2">
                      {{ a.summary || t("wechatMpFeed.noSummary") }}
                    </NText>
                    <NSpace justify="space-between" align="center" style="margin-top: 8px">
                      <NText depth="3" style="font-size: 12px">{{ a.source_name }}</NText>
                      <NSpace size="small">
                        <NTag v-if="a.imported" size="small" type="success" :bordered="false">
                          {{ t("wechatMpFeed.imported") }}
                        </NTag>
                        <NText depth="3" style="font-size: 12px">{{ fmtTime(a.publish_at) }}</NText>
                      </NSpace>
                    </NSpace>
                  </div>
                </NCard>
              </NGi>
            </NGrid>
            <NEmpty v-else :description="t('wechatMpFeed.emptyArticles')" />
          </NSpin>

          <NSpace v-if="total > pageSize" justify="center" style="margin-top: 16px">
            <NButton :disabled="page <= 1" @click="page--; loadArticles()">{{ t("wechatMpFeed.prevPage") }}</NButton>
            <NText>{{ page }} / {{ Math.ceil(total / pageSize) }}</NText>
            <NButton
              :disabled="page * pageSize >= total"
              @click="page++; loadArticles()"
            >
              {{ t("wechatMpFeed.nextPage") }}
            </NButton>
          </NSpace>
        </main>
      </div>
    </NSpin>

    <NModal v-model:show="showAdd" preset="card" :title="t('wechatMpFeed.addModalTitle')" style="width: 520px">
      <NForm label-placement="top">
        <NFormItem :label="t('wechatMpFeed.accountName')">
          <NInput v-model:value="addForm.name" :placeholder="t('wechatMpFeed.accountNamePlaceholder')" />
        </NFormItem>
        <NFormItem :label="t('wechatMpFeed.sampleUrl')">
          <NSpace vertical style="width: 100%">
            <NInput
              v-model:value="addForm.sample_url"
              :placeholder="t('wechatMpFeed.sampleUrlPlaceholder')"
            />
            <NButton size="small" @click="onPreviewUrl">{{ t("wechatMpFeed.parsePreview") }}</NButton>
            <NText depth="3" style="font-size: 12px">
              {{ t("wechatMpFeed.shortUrlHint") }}
            </NText>
          </NSpace>
        </NFormItem>
        <NFormItem :label="t('wechatMpFeed.bizLabel')">
          <NInput
            v-model:value="addForm.biz"
            :placeholder="t('wechatMpFeed.bizPlaceholder')"
          />
        </NFormItem>
        <NCard v-if="parsePreview" size="small" embedded>
          <div style="font-weight: 600">{{ parsePreview.title }}</div>
          <NText depth="3" style="font-size: 12px">
            {{ parsePreview.account_name || "—" }}
            <template v-if="parsePreview.biz"> · {{ t("wechatMpFeed.bizRecognized") }}</template>
          </NText>
        </NCard>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showAdd = false">{{ t("common.cancel") }}</NButton>
          <NButton type="primary" :loading="submitting" @click="submitAdd">{{ t("common.confirm") }}</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal v-model:show="showIngest" preset="card" :title="t('wechatMpFeed.ingestModalTitle')" style="width: 520px">
      <NInput v-model:value="ingestUrl" :placeholder="t('wechatMpFeed.ingestUrlPlaceholder')" />
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showIngest = false">{{ t("common.cancel") }}</NButton>
          <NButton type="primary" :loading="submitting" @click="submitIngest">{{ t("wechatMpFeed.ingest") }}</NButton>
        </NSpace>
      </template>
    </NModal>
  </FeatureSubsystemShell>
</template>

<style scoped>
.mp-feed-layout {
  display: flex;
  gap: 20px;
  min-height: 0;
  flex: 1;
}
.mp-feed-sidebar {
  width: 260px;
  flex-shrink: 0;
  border-right: 1px solid var(--n-border-color);
  padding-right: 16px;
}
.mp-feed-main {
  flex: 1;
  min-width: 0;
}
.source-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.source-name {
  font-weight: 500;
}
.article-card {
  cursor: pointer;
  overflow: hidden;
}
.cover {
  height: 140px;
  background-size: cover;
  background-position: center;
  background-color: var(--n-color-modal);
}
.cover-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--n-text-color-3);
  font-size: 14px;
}
.card-body {
  padding-top: 10px;
}
.card-title {
  font-weight: 600;
  line-height: 1.4;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-summary {
  font-size: 13px;
}
</style>
