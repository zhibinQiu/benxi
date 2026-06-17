<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { useSubscriptionImportFlow } from "../composables/useSubscriptionImportFlow.js";
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NCard, NSpace, NSpin, NTag, NText } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  DOCUMENT_SCOPE_PERSONAL,
  fetchFeedEntry,
  importFeedEntry } from "../api/client";
import { goBackToEntry } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();

const loading = ref(true);
const entry = ref(null);

const { importing, indexing, documentId, runImport, openDocument } = useSubscriptionImportFlow({
  router,
  route,
  ui,
});

const resolvedDocumentId = computed(
  () => documentId.value || entry.value?.document_id || null
);

const showImportedActions = computed(
  () => Boolean(entry.value?.imported || resolvedDocumentId.value)
);

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
    entry.value = await fetchFeedEntry(route.params.id);
    if (entry.value?.document_id) {
      documentId.value = entry.value.document_id;
    }
  } catch (e) {
    if (notifyOnError) ui.error(e.message);
    if (notifyOnError) {
      goBackToEntry(router, route, { name: route.meta.backTo || "feed-subscriptions" });
    }
  } finally {
    loading.value = false;
  }
}

async function onImport() {
  try {
    await runImport(importFeedEntry, route.params.id);
    await load({ notifyOnError: false });
  } catch {
    /* runImport 已提示 */
  }
}

onMounted(load);
</script>

<template>
  <FeatureSubsystemShell>
    <NSpin :show="loading">
      <template v-if="entry">
        <NSpace align="center" style="margin-bottom: 16px">
          <NButton quaternary @click="goBackToEntry(router, route, { name: route.meta.backTo || 'feed-subscriptions' })">
            返回列表
          </NButton>
          <NTag :bordered="false">{{ entry.source_kind === "website" ? "网站" : "RSS" }}</NTag>
          <NTag v-if="showImportedActions" type="success" :bordered="false">
            {{ indexing ? "索引中" : "已入文档库" }}
          </NTag>
        </NSpace>
        <NCard>
          <h1 class="article-title">{{ entry.title }}</h1>
          <NSpace style="margin: 8px 0 16px">
            <NText depth="3">{{ entry.source_name }}</NText>
            <NText v-if="entry.category" depth="3">· {{ entry.category }}</NText>
            <NText depth="3">· {{ fmtTime(entry.publish_at) }}</NText>
          </NSpace>
          <NSpace style="margin-bottom: 20px">
            <NButton v-if="!showImportedActions" type="primary" :loading="importing" @click="onImport">
              导入文档库
            </NButton>
            <NButton
              v-if="showImportedActions && resolvedDocumentId"
              type="primary"
              :loading="indexing"
              @click="openDocument(resolvedDocumentId)"
            >
              {{ indexing ? "查看文档（索引中）" : "查看文档" }}
            </NButton>
            <NButton
              v-if="showImportedActions"
              tertiary
              @click="
                router.push({
                  name: 'documents',
                  query: { scope: DOCUMENT_SCOPE_PERSONAL }})
              "
            >
              打开「个人级」文档库
            </NButton>
            <NButton v-if="entry.link" tag="a" :href="entry.link" target="_blank" rel="noopener">
              查看原文
            </NButton>
          </NSpace>
          <div v-if="entry.content_html" class="article-content" v-html="entry.content_html" />
          <NText v-else depth="3">暂无正文，请查看原文链接</NText>
        </NCard>
      </template>
    </NSpin>
  </FeatureSubsystemShell>
</template>

<style scoped>
.article-title {
  margin: 0;
  font-size: 22px;
}
.article-content {
  line-height: 1.75;
  word-break: break-word;
}
.article-content :deep(img) {
  max-width: 100%;
}
</style>
