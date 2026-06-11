<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NSpace, NSpin, NTag, NText } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  DOCUMENT_SCOPE_PERSONAL,
  deleteSubscriptionItem,
  fetchSubscriptionItem,
  importSubscriptionItem } from "../api/client";
import { resolveArticleBody } from "../utils/articleContent";
import { goBackToEntry } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();

const loading = ref(true);
const importing = ref(false);
const deleting = ref(false);
const item = ref(null);

const articleBody = computed(() => resolveArticleBody(item.value));

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

async function load({ notifyOnError = true } = {}) {
  loading.value = true;
  try {
    item.value = await fetchSubscriptionItem(route.params.ref);
  } catch (e) {
    if (notifyOnError) ui.error(e.message);
    if (notifyOnError) {
      goBackToEntry(router, route, { name: "knowledge-subscriptions" });
    }
  } finally {
    loading.value = false;
  }
}

async function onImport() {
  importing.value = true;
  try {
    const res = await importSubscriptionItem(route.params.ref);
    ui.success(
      res.knowflow_synced
        ? "已入「个人级」文档库并同步知识库"
        : "已入「个人级」文档库",
    );
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e.message);
  } finally {
    importing.value = false;
  }
}

function openOriginal() {
  const url = item.value?.link;
  if (url) window.open(url, "_blank", "noopener");
}

async function onDelete() {
  deleting.value = true;
  try {
    await deleteSubscriptionItem(route.params.ref);
    ui.success("已删除");
    goBackToEntry(router, route, { name: "knowledge-subscriptions" });
  } catch (e) {
    ui.error(e.message);
  } finally {
    deleting.value = false;
  }
}

onMounted(load);
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="subscription-detail-page">
      <NSpin :show="loading" class="detail-spin">
        <div v-if="item" class="detail-layout">
          <div class="detail-panel">
            <header class="detail-header">
              <span v-if="item.is_wechat" class="wechat-badge" title="微信公众号">公众号</span>
              <h1 class="article-title">{{ item.title }}</h1>
              <NText depth="3" class="article-meta">
                收录于 {{ fmtTime(item.created_at || item.publish_at) }}
                <template v-if="item.author"> · {{ item.author }}</template>
              </NText>
              <NSpace class="detail-actions" align="center">
                <NTag v-if="item.imported" type="success" :bordered="false">已入文档库</NTag>
                <NButton
                  v-if="!item.imported"
                  type="primary"
                  :loading="importing"
                  @click="onImport"
                >
                  导入文档库
                </NButton>
                <NButton
                  v-else
                  tertiary
                  @click="
                    router.push({
                      name: 'documents',
                      query: { scope: DOCUMENT_SCOPE_PERSONAL }})
                  "
                >
                  打开「个人级」文档库
                </NButton>
                <NButton @click="openOriginal">查看原文</NButton>
                <NButton type="error" secondary :loading="deleting" @click="onDelete">
                  删除
                </NButton>
              </NSpace>
            </header>

            <div class="detail-body-scroll">
              <div
                v-if="articleBody.mode !== 'empty'"
                class="article-content article-html"
                v-html="articleBody.body"
              />
              <NText v-else depth="3">暂无正文，请查看原文链接</NText>
            </div>
          </div>
        </div>
      </NSpin>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.subscription-detail-page {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-spin {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-spin :deep(.n-spin-container),
.detail-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-layout {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-panel {
  flex: 1 1 0;
  height: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-radius: var(--platform-radius, 10px);
  background: var(--platform-surface, #fff);
  box-shadow: var(--platform-shadow, 0 1px 2px rgba(15, 23, 42, 0.06));
}

.detail-header {
  flex-shrink: 0;
  padding: 20px 22px 16px;
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  background: var(--platform-surface, #fff);
}

.detail-body-scroll {
  flex: 1 1 0;
  height: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 18px 22px 28px;
  box-sizing: border-box;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

.wechat-badge {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 2;
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 4px;
  color: #fff;
  background: var(--platform-accent-gradient);
}

.article-title {
  margin: 0;
  padding-right: 56px;
  font-size: 22px;
  line-height: 1.35;
  font-weight: 600;
}

.article-meta {
  display: block;
  margin: 8px 0 14px;
  font-size: 13px;
}

.detail-actions {
  flex-wrap: wrap;
}
</style>
