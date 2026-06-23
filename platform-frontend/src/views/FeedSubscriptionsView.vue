<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { navigateWithReturn } from "../utils/navigationReturn";
import {
  NButton,
  NCard,
  NCheckbox,
  NEmpty,
  NForm,
  NFormItem,
  NGrid,
  NGi,
  NInput,
  NList,
  NListItem,
  NModal,
  NRadio,
  NRadioGroup,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText,
  useDialog } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  createFeedSubscription,
  deleteFeedSubscription,
  fetchFeedEntries,
  fetchFeedPresets,
  fetchFeedSources,
  subscribeFeedPreset,
  syncFeedSubscription } from "../api/client";
import { deleteSequentially } from "../utils/batchActions";
import { withSystemDialogLayer } from "../utils/systemDialog.js";
import { useI18n } from "../composables/useI18n";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import ListRefreshButton from "../components/ListRefreshButton.vue";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const dialog = useDialog();
const { t, locale } = useI18n();

const dateLocale = computed(() => (locale.value === "zh" ? "zh-CN" : "en-US"));

const pageTitle = computed(() => {
  if (route.query.kind === "website") return t("feedSubscriptions.titleWebsite");
  if (route.query.kind === "rss") return t("feedSubscriptions.titleRss");
  return t("feedSubscriptions.titleDefault");
});

const filterKind = computed(() => route.query.kind || null);

const loading = ref(true);
const articlesLoading = ref(false);
const sources = ref([]);
const presets = ref([]);
const articles = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = LIST_PAGE_SIZE;
const filterSourceId = ref(null);

const showAdd = ref(false);
const addForm = ref({ name: "", feed_url: "", kind: "rss", category: "双碳" });
const submitting = ref(false);
const selectedSourceIds = ref([]);

const sourceOptions = computed(() => [
  { label: t("feedSubscriptions.allSources"), value: null },
  ...sources.value.map((s) => ({
    label: `${s.name} (${s.entry_count || 0})`,
    value: s.id})),
]);

const PRESET_CATEGORY_KEYS = {
  国际双碳: "feedSubscriptions.presetIntlCarbon",
  国内政策: "feedSubscriptions.presetDomesticPolicy",
  推荐: "feedSubscriptions.presetRecommended",
};

function presetCategoryLabel(cat) {
  const key = PRESET_CATEGORY_KEYS[cat];
  return key ? t(key) : cat;
}

/** 按 category 分组展示内置源 */
const presetGroups = computed(() => {
  const order = ["国际双碳", "国内政策"];
  const buckets = new Map();
  presets.value.forEach((p, index) => {
    const cat = p.category || "推荐";
    if (!buckets.has(cat)) buckets.set(cat, []);
    buckets.get(cat).push({ ...p, index });
  });
  const keys = [
    ...order.filter((k) => buckets.has(k)),
    ...[...buckets.keys()].filter((k) => !order.includes(k)),
  ];
  return keys.map((label) => ({
    label: presetCategoryLabel(label),
    items: buckets.get(label) || [],
  }));
});

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(dateLocale.value, { hour12: false });
  } catch {
    return iso;
  }
}

async function loadSources() {
  sources.value = await fetchFeedSources({ kind: filterKind.value || undefined });
  selectedSourceIds.value = selectedSourceIds.value.filter((id) =>
    sources.value.some((s) => s.id === id)
  );
}

async function loadPresets() {
  presets.value = await fetchFeedPresets();
}

async function loadArticles() {
  articlesLoading.value = true;
  try {
    const data = await fetchFeedEntries({
      page: page.value,
      page_size: pageSize,
      source_id: filterSourceId.value || undefined,
      kind: filterKind.value || undefined});
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
    await Promise.all([loadSources(), loadPresets(), loadArticles()]);
  } catch (e) {
    ui.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function submitAdd() {
  const name = addForm.value.name?.trim();
  const url = addForm.value.feed_url?.trim();
  if (!name || !url) {
    ui.warning(t("feedSubscriptions.fillNameAndUrl"));
    return;
  }
  submitting.value = true;
  try {
    await createFeedSubscription({
      name,
      feed_url: url,
      kind: addForm.value.kind,
      category: addForm.value.category?.trim() || "双碳"});
    ui.success(t("feedSubscriptions.added"));
    showAdd.value = false;
    addForm.value = {
      name: "",
      feed_url: "",
      kind: filterKind.value === "website" ? "website" : "rss",
      category: "双碳"};
    await reload();
  } catch (e) {
    ui.error(e.message);
  } finally {
    submitting.value = false;
  }
}

async function addPreset(index) {
  try {
    await subscribeFeedPreset(index);
    ui.success(t("feedSubscriptions.presetAdded"));
    await reload();
  } catch (e) {
    ui.error(e.message);
  }
}

async function onSyncSource(source) {
  try {
    const res = await syncFeedSubscription(source.id);
    ui.info(res.message || t("feedSubscriptions.syncDone"));
    await reload();
  } catch (e) {
    ui.error(e.message);
  }
}

const selectedSources = computed(() =>
  sources.value.filter((s) => selectedSourceIds.value.includes(s.id))
);

const canBatchRemove = computed(() => selectedSources.value.length > 0);

function isSourceSelected(id) {
  return selectedSourceIds.value.includes(id);
}

function toggleSourceSelected(id, checked) {
  if (checked) {
    if (!selectedSourceIds.value.includes(id)) {
      selectedSourceIds.value = [...selectedSourceIds.value, id];
    }
  } else {
    selectedSourceIds.value = selectedSourceIds.value.filter((x) => x !== id);
  }
}

function handleBatchRemoveSources() {
  const rows = selectedSources.value;
  if (!rows.length) return;
  const content =
    rows.length === 1
      ? t("feedSubscriptions.batchRemoveContentSingle", { name: rows[0].name })
      : t("feedSubscriptions.batchRemoveContentMulti", { count: rows.length });
  dialog.warning(
    withSystemDialogLayer({
      title: t("feedSubscriptions.batchRemoveTitle"),
      content,
      positiveText: t("feedSubscriptions.remove"),
      negativeText: t("common.cancel"),
      onPositiveClick: async () => {
        const { deleted, failed } = await deleteSequentially(rows, (row) =>
          deleteFeedSubscription(row.id)
        );
        if (filterSourceId.value && selectedSourceIds.value.includes(filterSourceId.value)) {
          filterSourceId.value = null;
        }
        selectedSourceIds.value = [];
        if (failed.length) {
          ui.warning(
            t("feedSubscriptions.batchRemovePartial", {
              deleted,
              failed: failed.length,
              error: failed[0].message || t("chatHistory.unknownError"),
            })
          );
        } else {
          ui.success(
            deleted > 1
              ? t("feedSubscriptions.batchRemoveSuccessMulti", { deleted })
              : t("feedSubscriptions.batchRemoveSuccessSingle")
          );
        }
        await reload();
        return !failed.length;
      },
    })
  );
}

function openEntry(id) {
  navigateWithReturn(
    router,
    {
      name: "feed-entry",
      params: { id },
      query: filterKind.value ? { kind: filterKind.value } : {}},
    route
  );
}

watch(
  () => route.query.kind,
  () => {
    page.value = 1;
    filterSourceId.value = null;
    addForm.value.kind = filterKind.value === "website" ? "website" : "rss";
    reload();
  }
);

onMounted(() => {
  if (filterKind.value === "website") addForm.value.kind = "website";
  reload();
});
</script>

<template>
  <FeatureSubsystemShell fill>
    <NSpin :show="loading">
      <div class="feed-layout">
        <aside class="feed-sidebar">
          <NSpace vertical :size="12">
            <NButton type="primary" block @click="showAdd = true">{{ t("feedSubscriptions.addSubscription") }}</NButton>
            <ListRefreshButton :loading="loading" size="small" @click="reload" />
          </NSpace>

          <template v-for="group in presetGroups" :key="group.label">
            <NText depth="3" class="section-label">{{ group.label }}</NText>
            <NSpace v-if="group.items.length" vertical size="small" class="preset-list">
              <NButton
                v-for="p in group.items"
                :key="p.feed_url"
                block
                tertiary
                size="small"
                @click="addPreset(p.index)"
              >
                {{ p.name }}
              </NButton>
            </NSpace>
          </template>
          <NText v-if="!presets.length" depth="3" style="font-size: 12px">{{ t("feedSubscriptions.noPresets") }}</NText>

          <NText depth="3" class="section-label">{{ t("feedSubscriptions.mySubscriptions") }}</NText>
          <NSpace v-if="sources.length" align="center" :size="8" style="margin-bottom: 8px">
            <NButton
              size="tiny"
              type="error"
              secondary
              :disabled="!canBatchRemove"
              @click="handleBatchRemoveSources"
            >
              {{ t("feedSubscriptions.remove") }}
            </NButton>
            <NText v-if="selectedSourceIds.length" depth="3" style="font-size: 12px">
              {{ t("common.selectedCount", { count: selectedSourceIds.length }) }}
            </NText>
          </NSpace>
          <NList v-if="sources.length" hoverable clickable>
            <NListItem
              v-for="s in sources"
              :key="s.id"
              @click="filterSourceId = s.id; page = 1; loadArticles()"
            >
              <div class="source-row">
                <NCheckbox
                  :checked="isSourceSelected(s.id)"
                  @update:checked="(v) => toggleSourceSelected(s.id, v)"
                  @click.stop
                />
                <div class="source-row-main">
                  <div class="source-name">
                    {{ s.name }}
                    <NTag size="tiny" :bordered="false">{{ s.kind === "website" ? t("feedSubscriptions.kindWebsiteTag") : t("feedSubscriptions.kindRssTag") }}</NTag>
                  </div>
                  <NText depth="3" style="font-size: 12px">{{ t("feedSubscriptions.entryCount", { count: s.entry_count }) }}</NText>
                </div>
                <NSpace size="small">
                  <NButton size="tiny" quaternary @click.stop="onSyncSource(s)">{{ t("feedSubscriptions.sync") }}</NButton>
                </NSpace>
              </div>
            </NListItem>
          </NList>
          <NEmpty v-else :description="t('feedSubscriptions.noSubscriptions')" size="small" />
        </aside>

        <main class="feed-main">
          <NSpace justify="space-between" align="center" style="margin-bottom: 12px">
            <NSelect
              v-model:value="filterSourceId"
              :options="sourceOptions"
              style="width: 260px"
              @update:value="() => { page = 1; loadArticles(); }"
            />
            <NSpace align="center" :size="8">
              <ListRefreshButton :loading="articlesLoading" size="small" @click="reload" />
              <NText depth="3">{{ t("feedSubscriptions.totalEntries", { total, title: pageTitle }) }}</NText>
            </NSpace>
          </NSpace>

          <NSpin :show="articlesLoading">
            <NGrid v-if="articles.length" cols="1 s:2 m:3" :x-gap="16" :y-gap="16">
              <NGi v-for="a in articles" :key="a.id">
                <NCard hoverable class="article-card" @click="openEntry(a.id)">
                  <div class="card-body">
                    <div class="card-title">{{ a.title }}</div>
                    <NText depth="3" class="card-summary" :line-clamp="3">
                      {{ a.summary || t("feedSubscriptions.noSummary") }}
                    </NText>
                    <NSpace justify="space-between" style="margin-top: 8px">
                      <NText depth="3" style="font-size: 12px">{{ a.source_name }}</NText>
                      <NSpace size="small">
                        <NTag v-if="a.imported" size="small" type="success" :bordered="false">{{ t("feedSubscriptions.imported") }}</NTag>
                        <NText depth="3" style="font-size: 12px">{{ fmtTime(a.publish_at) }}</NText>
                      </NSpace>
                    </NSpace>
                  </div>
                </NCard>
              </NGi>
            </NGrid>
            <NEmpty v-else :description="t('feedSubscriptions.emptyArticles')" />
          </NSpin>

          <NSpace v-if="total > pageSize" justify="center" style="margin-top: 16px">
            <NButton :disabled="page <= 1" @click="page--; loadArticles()">{{ t("feedSubscriptions.prevPage") }}</NButton>
            <NText>{{ page }} / {{ Math.ceil(total / pageSize) }}</NText>
            <NButton :disabled="page * pageSize >= total" @click="page++; loadArticles()">{{ t("feedSubscriptions.nextPage") }}</NButton>
          </NSpace>
        </main>
      </div>
    </NSpin>

    <NModal v-model:show="showAdd" preset="card" :title="t('feedSubscriptions.addModalTitle')" style="width: 520px">
      <NForm label-placement="top">
        <NFormItem :label="t('feedSubscriptions.typeLabel')">
          <NRadioGroup v-model:value="addForm.kind">
            <NRadio value="rss">{{ t("feedSubscriptions.kindRss") }}</NRadio>
            <NRadio value="website">{{ t("feedSubscriptions.kindWebsite") }}</NRadio>
          </NRadioGroup>
        </NFormItem>
        <NFormItem :label="t('feedSubscriptions.displayName')">
          <NInput v-model:value="addForm.name" :placeholder="t('feedSubscriptions.namePlaceholder')" />
        </NFormItem>
        <NFormItem :label="addForm.kind === 'website' ? t('feedSubscriptions.websiteUrl') : t('feedSubscriptions.feedUrl')">
          <NInput
            v-model:value="addForm.feed_url"
            :placeholder="
              addForm.kind === 'website'
                ? t('feedSubscriptions.websiteUrlPlaceholder')
                : t('feedSubscriptions.feedUrlPlaceholder')
            "
          />
        </NFormItem>
        <NFormItem :label="t('feedSubscriptions.categoryLabel')">
          <NInput v-model:value="addForm.category" :placeholder="t('feedSubscriptions.categoryPlaceholder')" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showAdd = false">{{ t("common.cancel") }}</NButton>
          <NButton type="primary" :loading="submitting" @click="submitAdd">{{ t("common.confirm") }}</NButton>
        </NSpace>
      </template>
    </NModal>
  </FeatureSubsystemShell>
</template>

<style scoped>
.feed-layout {
  display: flex;
  gap: 20px;
  min-height: 0;
  flex: 1;
}
.feed-sidebar {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid var(--n-border-color);
  padding-right: 16px;
}
.feed-main {
  flex: 1;
  min-width: 0;
}
.section-label {
  display: block;
  margin: 16px 0 8px;
  font-size: 12px;
}
.preset-list {
  margin-bottom: 8px;
}
.source-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.source-row-main {
  flex: 1;
  min-width: 0;
}
.source-name {
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
}
.article-card {
  cursor: pointer;
}
.card-title {
  font-weight: 600;
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
