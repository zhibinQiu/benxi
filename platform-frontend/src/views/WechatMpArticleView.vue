<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCard,
  NSpace,
  NSpin,
  NTag,
  NText,
  useMessage,
} from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  DOCUMENT_SCOPE_PERSONAL,
  fetchWechatMpArticle,
  importWechatMpArticle,
} from "../api/client";
import { goBackToEntry } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const message = useMessage();

const loading = ref(true);
const importing = ref(false);
const article = ref(null);

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
    article.value = await fetchWechatMpArticle(route.params.id);
  } catch (e) {
    if (notifyOnError) message.error(e.message);
    if (notifyOnError) {
      goBackToEntry(router, route, { name: route.meta.backTo || "wechat-mp" });
    }
  } finally {
    loading.value = false;
  }
}

async function onImport() {
  importing.value = true;
  try {
    const res = await importWechatMpArticle(route.params.id);
    message.success(
      res.knowflow_synced
        ? "已入「我的」文档库并同步知识库"
        : "已入「我的」文档库",
    );
    await load({ notifyOnError: false });
  } catch (e) {
    message.error(e.message);
  } finally {
    importing.value = false;
  }
}

function openOriginal() {
  if (article.value?.original_url) {
    window.open(article.value.original_url, "_blank", "noopener");
  }
}

onMounted(load);
</script>

<template>
  <FeatureSubsystemShell>
    <NSpin :show="loading">
      <template v-if="article">
        <NSpace align="center" style="margin-bottom: 16px">
          <NButton quaternary @click="goBackToEntry(router, route, { name: route.meta.backTo || 'wechat-mp' })">
            返回列表
          </NButton>
          <NTag v-if="article.imported" type="success" :bordered="false">已入文档库</NTag>
        </NSpace>

        <NCard>
          <h1 class="article-title">{{ article.title }}</h1>
          <NSpace style="margin: 8px 0 16px">
            <NText depth="3">{{ article.source_name }}</NText>
            <NText depth="3">·</NText>
            <NText depth="3">{{ fmtTime(article.publish_at) }}</NText>
          </NSpace>
          <NSpace style="margin-bottom: 20px">
            <NButton
              v-if="!article.imported"
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
                  query: { scope: DOCUMENT_SCOPE_PERSONAL },
                })
              "
            >
              打开「我的」文档库
            </NButton>
            <NButton @click="openOriginal">查看原文</NButton>
          </NSpace>
          <div
            v-if="article.content_html"
            class="article-content"
            v-html="article.content_html"
          />
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
  line-height: 1.35;
}
.article-content {
  line-height: 1.75;
  word-break: break-word;
}
.article-content :deep(img) {
  max-width: 100%;
  height: auto;
}
</style>
