<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NCard, NSpace, NSpin, NTag, NText, useMessage } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { fetchFeedEntry, importFeedEntry } from "../api/client";
import { goBackToEntry } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const message = useMessage();

const loading = ref(true);
const importing = ref(false);
const entry = ref(null);

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

async function load() {
  loading.value = true;
  try {
    entry.value = await fetchFeedEntry(route.params.id);
  } catch (e) {
    message.error(e.message);
    goBackToEntry(router, route, { name: route.meta.backTo || "feed-subscriptions" });
  } finally {
    loading.value = false;
  }
}

async function onImport() {
  importing.value = true;
  try {
    const res = await importFeedEntry(route.params.id, { scope: "personal", sync_knowflow: true });
    message.success(res.knowflow_synced ? "已入文档库并同步知识库" : "已入文档库");
    await load();
  } catch (e) {
    message.error(e.message);
  } finally {
    importing.value = false;
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
          <NTag v-if="entry.imported" type="success" :bordered="false">已入文档库</NTag>
        </NSpace>
        <NCard>
          <h1 class="article-title">{{ entry.title }}</h1>
          <NSpace style="margin: 8px 0 16px">
            <NText depth="3">{{ entry.source_name }}</NText>
            <NText v-if="entry.category" depth="3">· {{ entry.category }}</NText>
            <NText depth="3">· {{ fmtTime(entry.publish_at) }}</NText>
          </NSpace>
          <NSpace style="margin-bottom: 20px">
            <NButton v-if="!entry.imported" type="primary" :loading="importing" @click="onImport">
              导入文档库
            </NButton>
            <NButton v-else tertiary @click="router.push({ name: 'documents' })">打开文档库</NButton>
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
