<script setup>
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { useSubscriptionImportFlow } from "../composables/useSubscriptionImportFlow.js";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NEmpty, NSpace, NSpin, NTag, NText } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  DOCUMENT_SCOPE_PERSONAL,
  deleteSubscriptionItem,
  fetchSubscriptionItem,
  importSubscriptionItem,
} from "../api/client";
import { resolveArticleBody } from "../utils/articleContent";
import { goBackToEntry } from "../utils/navigationReturn";
import { openExternal } from "../utils/openExternal.js";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { t, locale } = useI18n();

const loading = ref(true);
const deleting = ref(false);
const item = ref(null);

const { importing, indexing, documentId, runImport, openDocument } = useSubscriptionImportFlow({
  router,
  route,
  ui,
});

const articleBody = computed(() => resolveArticleBody(item.value));

const resolvedDocumentId = computed(
  () => documentId.value || item.value?.document_id || null
);

const showImportedActions = computed(
  () => Boolean(item.value?.imported || resolvedDocumentId.value)
);

const dateLocale = computed(() => (locale.value === "zh" ? "zh-CN" : "en-US"));

function fmtTime(iso) {
  if (!iso) return t("carbonTrading.emDash");
  try {
    return new Date(iso).toLocaleString(dateLocale.value, { hour12: false });
  } catch {
    return iso;
  }
}

async function load({ notifyOnError = true } = {}) {
  loading.value = true;
  try {
    item.value = await fetchSubscriptionItem(route.params.ref);
    if (item.value?.document_id) {
      documentId.value = item.value.document_id;
    }
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
  try {
    await runImport(importSubscriptionItem, route.params.ref);
    await load({ notifyOnError: false });
  } catch {
    /* runImport 已提示 */
  }
}

function openOriginal() {
  const url = item.value?.link;
  if (url) openExternal(url);
}

async function onDelete() {
  deleting.value = true;
  try {
    await deleteSubscriptionItem(route.params.ref);
    ui.success(t("subscriptionItem.deleted"));
    router.push({
      name: "knowledge-subscriptions",
      query: { refresh: String(Date.now()) },
    });
  } catch (e) {
    ui.error(e.message);
  } finally {
    deleting.value = false;
  }
}

onMounted(load);

watch(
  () => route.params.ref,
  (ref, prev) => {
    if (ref && ref !== prev) load();
  }
);
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="subscription-detail-page">
      <NSpin :show="loading" class="detail-spin">
        <div v-if="item" class="detail-layout">
          <div class="detail-panel">
            <header class="detail-header">
              <span v-if="item.is_wechat" class="wechat-badge" :title="t('subscriptionItem.wechatTitle')">
                {{ t("subscriptionItem.wechatBadge") }}
              </span>
              <h1 class="article-title">{{ item.title }}</h1>
              <NText depth="3" class="article-meta">
                {{
                  t("subscriptionItem.collectedAt", {
                    time: fmtTime(item.created_at || item.publish_at),
                  })
                }}
                <template v-if="item.author"> · {{ item.author }}</template>
              </NText>
              <NSpace class="detail-actions" align="center">
                <NTag v-if="showImportedActions" type="success" :bordered="false">
                  {{ indexing ? t("subscriptionItem.indexing") : t("subscriptionItem.imported") }}
                </NTag>
                <NButton
                  v-if="!showImportedActions"
                  type="primary"
                  :loading="importing"
                  @click="onImport"
                >
                  {{ t("subscriptionItem.importDoc") }}
                </NButton>
                <NButton
                  v-if="showImportedActions && resolvedDocumentId"
                  type="primary"
                  :loading="indexing"
                  @click="openDocument(resolvedDocumentId)"
                >
                  {{
                    indexing
                      ? t("subscriptionItem.viewDocIndexing")
                      : t("subscriptionItem.viewDoc")
                  }}
                </NButton>
                <NButton
                  v-if="showImportedActions"
                  tertiary
                  @click="
                    router.push({
                      name: 'documents',
                      query: { scope: DOCUMENT_SCOPE_PERSONAL },
                    })
                  "
                >
                  {{ t("subscriptionItem.openPersonalDocs") }}
                </NButton>
                <NButton @click="openOriginal">{{ t("subscriptionItem.viewOriginal") }}</NButton>
                <NButton type="error" secondary :loading="deleting" @click="onDelete">
                  {{ t("subscriptionItem.delete") }}
                </NButton>
              </NSpace>
            </header>

            <div class="detail-body-scroll">
              <div
                v-if="articleBody.mode !== 'empty'"
                class="article-content article-html"
                v-html="articleBody.body"
              />
              <NText v-else depth="3">{{ t("subscriptionItem.emptyBody") }}</NText>
            </div>
          </div>
        </div>
        <NEmpty v-else-if="!loading" :description="t('subscriptionItem.notFound')" />
      </NSpin>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.subscription-detail-page {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.detail-spin {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.detail-spin :deep(.n-spin-container),
.detail-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.detail-layout {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.detail-panel {
  flex: 1;
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
  flex: 1;
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
