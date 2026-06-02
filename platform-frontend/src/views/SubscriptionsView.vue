<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCard,
  NDatePicker,
  NEmpty,
  NGi,
  NGrid,
  NInput,
  NSpace,
  NSpin,
  NTag,
  NText,
  useMessage,
} from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { useBoundedScrollHeight } from "../composables/useBoundedScrollHeight";
import { navigateWithReturn } from "../utils/navigationReturn";
import {
  fetchSubscriptionItems,
  ingestSubscriptionUrl,
} from "../api/client";

const route = useRoute();
const router = useRouter();
const message = useMessage();

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

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
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
    message.error(e.message);
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
    message.error(e.message);
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
    message.warning("请粘贴文章链接");
    return;
  }
  ingesting.value = true;
  try {
    const detail = await ingestSubscriptionUrl(url);
    message.success("已收录");
    ingestUrl.value = "";
    await loadItems();
    openItem(detail.ref);
  } catch (e) {
    message.error(e.message);
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
      <NCard size="small" class="subscriptions-ingest">
        <NText depth="3" class="ingest-hint">
          粘贴文章链接即可收录（微信公众号、网站文章等），收录后可在下方搜索与管理。
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

      <NSpace class="subscriptions-toolbar" align="center" wrap :size="12">
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

      <NSpin :show="itemsLoading || loading" class="list-spin">
        <div
          ref="listScrollRef"
          class="subscriptions-list-scroll"
          :style="{ height: `${listScrollHeight}px` }"
        >
          <NGrid v-if="items.length" cols="1 s:2 m:3" :x-gap="16" :y-gap="16">
            <NGi v-for="a in items" :key="a.ref">
              <NCard hoverable class="article-card" @click="openItem(a.ref)">
                <span v-if="a.is_wechat" class="wechat-badge" title="微信公众号">公众号</span>
                <div class="card-title">{{ a.title }}</div>
                <NText depth="3" class="card-summary" :line-clamp="2">
                  {{ a.summary || "暂无摘要" }}
                </NText>
                <NSpace justify="space-between" align="center" class="card-meta">
                  <NTag v-if="a.imported" size="small" type="success" :bordered="false">
                    已入文档库
                  </NTag>
                  <NText depth="3" class="card-time">
                    {{ fmtTime(a.created_at || a.publish_at) }}
                  </NText>
                </NSpace>
              </NCard>
            </NGi>
          </NGrid>
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
  margin-bottom: 12px;
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
  margin-bottom: 12px;
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
  padding-right: 8px;
  box-sizing: border-box;
  -webkit-overflow-scrolling: touch;
}
.subscriptions-pager {
  margin-top: 16px;
  padding-bottom: 12px;
}
.article-card {
  cursor: pointer;
  position: relative;
}
.wechat-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 1;
  font-size: 11px;
  line-height: 1;
  padding: 4px 8px;
  border-radius: 4px;
  color: #fff;
  background: linear-gradient(135deg, #07c160 0%, #06ad56 100%);
  box-shadow: 0 1px 4px rgba(7, 193, 96, 0.35);
}
.card-title {
  font-weight: 600;
  font-size: 14px;
  line-height: 1.4;
  margin-bottom: 6px;
  padding-right: 52px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-summary {
  font-size: 12px;
  line-height: 1.5;
}
.card-meta {
  margin-top: 8px;
}
.card-time {
  font-size: 12px;
}
</style>
