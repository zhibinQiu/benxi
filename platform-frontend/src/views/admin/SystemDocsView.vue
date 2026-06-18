<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NEmpty,
  NIcon,
  NLayout,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NSpin } from "naive-ui";
import { BookOutline } from "@vicons/ionicons5";
import SystemDocContent from "../../components/SystemDocContent.vue";
import { fetchSystemDocCatalog, fetchSystemDocContent } from "../../api/systemDocs.js";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { t } = useI18n();

const catalogLoading = ref(true);
const contentLoading = ref(false);
const catalog = ref([]);
const docTitle = ref("");
const docContent = ref("");
const activePath = ref("");
const contentRef = ref(null);

const menuOptions = computed(() =>
  catalog.value.map((group) => ({
    label: group.title,
    key: group.key,
    type: "group",
    children: (group.children || []).map((item) => ({
      label: item.title,
      key: item.path,
      disabled: !item.available}))}))
);

const defaultPath = computed(() => {
  for (const group of catalog.value) {
    const first = (group.children || []).find((c) => c.available);
    if (first) return first.path;
  }
  return "";
});

async function loadCatalog() {
  catalogLoading.value = true;
  try {
    catalog.value = await fetchSystemDocCatalog();
  } catch (e) {
    ui.error(e.message);
  } finally {
    catalogLoading.value = false;
  }
}

async function loadDoc(path, hash = "") {
  const normalized = String(path || "").trim();
  if (!normalized) return;
  contentLoading.value = true;
  try {
    const data = await fetchSystemDocContent(normalized);
    docTitle.value = data.title;
    docContent.value = data.content;
    activePath.value = data.path;
    router.replace({ query: { ...route.query, doc: data.path } });
    if (hash) {
      await nextTick();
      await new Promise((r) => setTimeout(r, 80));
      contentRef.value?.scrollToHash?.(hash);
    }
  } catch (e) {
    ui.error(e.message);
  } finally {
    contentLoading.value = false;
  }
}

function onMenuSelect(key) {
  loadDoc(String(key));
}

function onDocNavigate({ path, hash }) {
  if (!path) return;
  loadDoc(path, hash || "");
}

onMounted(async () => {
  await loadCatalog();
  const fromQuery = String(route.query.doc || "").trim();
  const initial = fromQuery || defaultPath.value;
  if (initial) await loadDoc(initial);
});

watch(
  () => route.query.doc,
  (next) => {
    const path = String(next || "").trim();
    if (path && path !== activePath.value) loadDoc(path);
  }
);
</script>

<template>
  <div class="system-docs-page admin-page">
    <NSpin :show="catalogLoading">
      <NLayout has-sider class="system-docs-layout">
        <NLayoutSider
          bordered
          collapse-mode="width"
          :collapsed-width="0"
          :width="240"
          :native-scrollbar="false"
          class="system-docs-sider"
        >
          <div class="system-docs-sider__head">
            <NIcon :size="18" :component="BookOutline" />
            <span>{{ t("admin.systemDocs.title") }}</span>
          </div>
          <NMenu
            :value="activePath"
            :options="menuOptions"
            @update:value="onMenuSelect"
          />
        </NLayoutSider>
        <NLayoutContent class="system-docs-main">
          <header v-if="docTitle" class="system-docs-main__head">
            <h1 class="system-docs-main__title">{{ docTitle }}</h1>
          </header>
          <SystemDocContent
            v-if="docContent"
            ref="contentRef"
            :content="docContent"
            :doc-path="activePath"
            :loading="contentLoading"
            @navigate="onDocNavigate"
          />
          <NEmpty
            v-else-if="!catalogLoading && !contentLoading"
            :description="t('admin.systemDocs.noDocs')"
          />
        </NLayoutContent>
      </NLayout>
    </NSpin>
  </div>
</template>

<style scoped>
.system-docs-page {
  height: calc(100vh - 56px - 24px);
  min-height: 420px;
}

.system-docs-layout {
  height: 100%;
  border-radius: var(--platform-radius);
  overflow: hidden;
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
}

.system-docs-sider {
  background: var(--platform-bg-secondary) !important;
}

.system-docs-sider__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--platform-text);
}

.system-docs-main {
  padding: 16px 22px 24px;
  overflow: auto;
  min-width: 0;
}

.system-docs-main__head {
  margin-bottom: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--platform-divider);
}

.system-docs-main__title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: var(--platform-tracking-tight);
  color: var(--platform-text);
}
</style>
