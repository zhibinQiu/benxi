<script setup>
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { useSubscriptionImportFlow } from "../composables/useSubscriptionImportFlow.js";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NEmpty, NSpin, NTag, NText } from "naive-ui";
import {
  CloudUploadOutline,
  DocumentTextOutline,
  OpenOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import IconAction from "../components/IconAction.vue";
import {
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
const { headerExtensionActive } = usePageHeaderExtension();
const headerTeleportReady = ref(false);

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
  if (!iso) return t("issueReports.emDash");
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

onMounted(() => {
  headerTeleportReady.value = true;
  load();
});

watch(
  () => route.params.ref,
  (ref, prev) => {
    if (ref && ref !== prev) load();
  }
);
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <Teleport
      v-if="headerTeleportReady && headerExtensionActive && item"
      to="#page-header-extension"
    >
      <div class="subscriptions-actions-bar">
        <div class="subscriptions-actions-toolbar">
          <NTag
            v-if="showImportedActions"
            type="success"
            :bordered="false"
            size="small"
          >
            {{ indexing ? t("subscriptionItem.indexing") : t("subscriptionItem.imported") }}
          </NTag>
          <div v-else class="subscription-item-toolbar__spacer" />
          <div class="subscriptions-toolbar subscriptions-toolbar--secondary">
            <IconAction
              v-if="!showImportedActions"
              type="primary"
              :label="t('subscriptionItem.importDoc')"
              :icon="CloudUploadOutline"
              :loading="importing"
              @click="onImport"
            />
            <IconAction
              v-if="showImportedActions && resolvedDocumentId"
              type="primary"
              :label="
                indexing
                  ? t('subscriptionItem.viewDocIndexing')
                  : t('subscriptionItem.viewDoc')
              "
              :icon="DocumentTextOutline"
              :loading="indexing"
              @click="openDocument(resolvedDocumentId)"
            />
            <IconAction
              :label="t('subscriptionItem.viewOriginal')"
              :icon="OpenOutline"
              @click="openOriginal"
            />
            <IconAction
              :label="t('subscriptionItem.delete')"
              :icon="TrashOutline"
              :loading="deleting"
              @click="onDelete"
            />
          </div>
        </div>
      </div>
    </Teleport>

    <div class="subscription-detail-page">
      <NSpin :show="loading" class="detail-spin" local>
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
  padding-top: 14px;
  box-sizing: border-box;
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
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius);
  background: var(--platform-surface);
  box-shadow: var(--platform-shadow);
  max-width: 860px;
  width: 100%;
  margin: 0 auto;
}

.detail-header {
  flex-shrink: 0;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--platform-border);
  background: var(--platform-surface);
}

.detail-body-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 20px 24px 32px;
  box-sizing: border-box;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

.detail-body-scroll::-webkit-scrollbar {
  width: 6px;
}

.detail-body-scroll::-webkit-scrollbar-thumb {
  background: var(--platform-border-strong);
  border-radius: 3px;
}

.wechat-badge {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 2;
  font-size: var(--platform-font-size-xs);
  padding: 3px 9px;
  border-radius: var(--platform-radius-xs);
  line-height: 1.5;
  color: #fff;
  background: var(--platform-accent-gradient);
}

.article-title {
  margin: 0;
  padding-right: 68px;
  font-size: 23px;
  line-height: var(--platform-line-heading);
  font-weight: var(--platform-font-weight-strong);
  letter-spacing: var(--platform-tracking-tight);
  color: var(--platform-text);
}

.article-meta {
  display: block;
  margin-top: 8px;
  font-size: var(--platform-font-size-sm);
  line-height: 1.5;
}

.subscription-item-toolbar__spacer {
  flex: 1;
  min-width: 0;
}
</style>
