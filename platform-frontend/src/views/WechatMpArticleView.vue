<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { useSubscriptionImportFlow } from "../composables/useSubscriptionImportFlow.js";
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCard,
  NSpace,
  NSpin,
  NTag,
  NText } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  DOCUMENT_SCOPE_PERSONAL,
  fetchWechatMpArticle,
  importWechatMpArticle } from "../api/client";
import { goBackToEntry } from "../utils/navigationReturn";
import { useI18n } from "../composables/useI18n";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { t, locale } = useI18n();

const dateLocale = computed(() => (locale.value === "zh" ? "zh-CN" : "en-US"));

const loading = ref(true);
const article = ref(null);

const { importing, indexing, documentId, runImport, openDocument } = useSubscriptionImportFlow({
  router,
  route,
  ui,
});

const resolvedDocumentId = computed(
  () => documentId.value || article.value?.document_id || null
);

const showImportedActions = computed(
  () => Boolean(article.value?.imported || resolvedDocumentId.value)
);

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(dateLocale.value, { hour12: false });
  } catch {
    return iso;
  }
}

async function load({ notifyOnError = true } = {}) {
  loading.value = true;
  try {
    article.value = await fetchWechatMpArticle(route.params.id);
    if (article.value?.document_id) {
      documentId.value = article.value.document_id;
    }
  } catch (e) {
    if (notifyOnError) ui.error(e.message);
    if (notifyOnError) {
      goBackToEntry(router, route, { name: route.meta.backTo || "wechat-mp" });
    }
  } finally {
    loading.value = false;
  }
}

async function onImport() {
  try {
    await runImport(importWechatMpArticle, route.params.id);
    await load({ notifyOnError: false });
  } catch {
    /* runImport 已提示 */
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
            {{ t("wechatMpArticle.backToList") }}
          </NButton>
          <NTag v-if="showImportedActions" type="success" :bordered="false">
            {{ indexing ? t("wechatMpArticle.indexing") : t("wechatMpArticle.imported") }}
          </NTag>
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
              v-if="!showImportedActions"
              type="primary"
              :loading="importing"
              @click="onImport"
            >
              {{ t("wechatMpArticle.importToLibrary") }}
            </NButton>
            <NButton
              v-if="showImportedActions && resolvedDocumentId"
              type="primary"
              :loading="indexing"
              @click="openDocument(resolvedDocumentId)"
            >
              {{ indexing ? t("wechatMpArticle.viewDocumentIndexing") : t("wechatMpArticle.viewDocument") }}
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
              {{ t("wechatMpArticle.openPersonalLibrary") }}
            </NButton>
            <NButton @click="openOriginal">{{ t("wechatMpArticle.viewOriginal") }}</NButton>
          </NSpace>
          <div
            v-if="article.content_html"
            class="article-content"
            v-html="article.content_html"
          />
          <NText v-else depth="3">{{ t("wechatMpArticle.noContent") }}</NText>
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
