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

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();

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
  { label: "全部跟踪号", value: null },
  ...sources.value.map((s) => ({
    label: `${s.name} (${s.article_count || 0})`,
    value: s.id})),
]);

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
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
    ui.warning("请填写公众号名称，并提供文章链接或 Biz 标识");
    return;
  }
  submitting.value = true;
  try {
    await createWechatMpSource({
      name,
      sample_url: url || undefined,
      biz: biz || undefined});
    ui.success("已添加跟踪");
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
    ui.success("已收录");
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
    ui.info(res.message || "同步完成");
    await reload();
  } catch (e) {
    ui.error(e.message);
  }
}

async function onRemoveSource(source) {
  try {
    await deleteWechatMpSource(source.id);
    ui.success("已取消跟踪");
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
            <NButton type="primary" block @click="showAdd = true">添加跟踪</NButton>
            <NButton block tertiary @click="showIngest = true">粘贴链接收录</NButton>
          </NSpace>
          <NText depth="3" style="display: block; margin: 16px 0 8px; font-size: 12px">
            我的跟踪
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
                  <NText depth="3" style="font-size: 12px">{{ s.article_count }} 篇</NText>
                </div>
                <NSpace size="small">
                  <NButton size="tiny" quaternary @click.stop="onSyncSource(s)">同步</NButton>
                  <NButton size="tiny" quaternary type="error" @click.stop="onRemoveSource(s)">
                    移除
                  </NButton>
                </NSpace>
              </div>
            </NListItem>
          </NList>
          <NEmpty v-else description="暂无跟踪，请添加公众号" size="small" />
        </aside>

        <main class="mp-feed-main">
          <NSpace justify="space-between" align="center" style="margin-bottom: 12px">
            <NSelect
              v-model:value="filterSourceId"
              :options="sourceOptions"
              style="width: 240px"
              @update:value="() => { page = 1; loadArticles(); }"
            />
            <NText depth="3">共 {{ total }} 篇</NText>
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
                  <div v-else class="cover cover-placeholder">公众号</div>
                  <div class="card-body">
                    <div class="card-title">{{ a.title }}</div>
                    <NText depth="3" class="card-summary" :line-clamp="2">
                      {{ a.summary || "暂无摘要" }}
                    </NText>
                    <NSpace justify="space-between" align="center" style="margin-top: 8px">
                      <NText depth="3" style="font-size: 12px">{{ a.source_name }}</NText>
                      <NSpace size="small">
                        <NTag v-if="a.imported" size="small" type="success" :bordered="false">
                          已入库
                        </NTag>
                        <NText depth="3" style="font-size: 12px">{{ fmtTime(a.publish_at) }}</NText>
                      </NSpace>
                    </NSpace>
                  </div>
                </NCard>
              </NGi>
            </NGrid>
            <NEmpty v-else description="暂无推文，请添加跟踪或粘贴链接" />
          </NSpin>

          <NSpace v-if="total > pageSize" justify="center" style="margin-top: 16px">
            <NButton :disabled="page <= 1" @click="page--; loadArticles()">上一页</NButton>
            <NText>{{ page }} / {{ Math.ceil(total / pageSize) }}</NText>
            <NButton
              :disabled="page * pageSize >= total"
              @click="page++; loadArticles()"
            >
              下一页
            </NButton>
          </NSpace>
        </main>
      </div>
    </NSpin>

    <NModal v-model:show="showAdd" preset="card" title="添加公众号跟踪" style="width: 520px">
      <NForm label-placement="top">
        <NFormItem label="公众号名称">
          <NInput v-model:value="addForm.name" placeholder="如：碳中和观察" />
        </NFormItem>
        <NFormItem label="示例文章链接（推荐）">
          <NSpace vertical style="width: 100%">
            <NInput
              v-model:value="addForm.sample_url"
              placeholder="在微信中打开文章 → 复制链接（宜含 __biz=）"
            />
            <NButton size="small" @click="onPreviewUrl">解析预览</NButton>
            <NText depth="3" style="font-size: 12px">
              短链可能无法识别，请用微信菜单「复制链接」获取完整 URL
            </NText>
          </NSpace>
        </NFormItem>
        <NFormItem label="公众号 Biz（可选，解析失败时填写）">
          <NInput
            v-model:value="addForm.biz"
            placeholder="链接中 __biz= 后面整段，如 MzA3MjA0ODYzOQ=="
          />
        </NFormItem>
        <NCard v-if="parsePreview" size="small" embedded>
          <div style="font-weight: 600">{{ parsePreview.title }}</div>
          <NText depth="3" style="font-size: 12px">
            {{ parsePreview.account_name || "—" }}
            <template v-if="parsePreview.biz"> · Biz 已识别</template>
          </NText>
        </NCard>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showAdd = false">取消</NButton>
          <NButton type="primary" :loading="submitting" @click="submitAdd">确定</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal v-model:show="showIngest" preset="card" title="粘贴文章链接" style="width: 520px">
      <NInput v-model:value="ingestUrl" placeholder="https://mp.weixin.qq.com/s/..." />
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showIngest = false">取消</NButton>
          <NButton type="primary" :loading="submitting" @click="submitIngest">收录</NButton>
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
