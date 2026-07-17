<script setup>
import { ref } from "vue";
import { NDrawer, NDrawerContent, NSpace, NTag, NText } from "naive-ui";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { fetchRoutingAgentsMd, fetchRoutingSkillsMd } from "../../api/agentSkills.js";
import {
  readRoutingCatalogCache,
  writeRoutingCatalogCache,
} from "../../utils/agentSkillsRoutingCatalogCache.js";

const ui = usePlatformUi();
const { t } = useI18n();

const open = ref(false);
const catalogType = ref("");
const catalogText = ref("");
const loading = ref(false);

async function fetchCatalog(filename) {
  const data =
    filename === "agents.md" ? await fetchRoutingAgentsMd() : await fetchRoutingSkillsMd();
  const text = data?.text || "";
  writeRoutingCatalogCache(filename, text);
  return text;
}

async function openCatalog(filename) {
  catalogType.value = filename;
  open.value = true;

  const cached = readRoutingCatalogCache(filename);
  if (cached) {
    catalogText.value = cached;
    loading.value = false;
    void fetchCatalog(filename)
      .then((text) => {
        if (open.value && catalogType.value === filename) {
          catalogText.value = text;
        }
      })
      .catch(() => {});
    return;
  }

  loading.value = true;
  catalogText.value = "";
  try {
    catalogText.value = await fetchCatalog(filename);
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.routingCatalogLoadFailed"));
  } finally {
    loading.value = false;
  }
}

async function refreshIfOpen() {
  if (!open.value || !catalogType.value) return;
  loading.value = true;
  try {
    catalogText.value = await fetchCatalog(catalogType.value);
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.routingCatalogLoadFailed"));
  } finally {
    loading.value = false;
  }
}

defineExpose({ openCatalog, refreshIfOpen, loading, catalogType });
</script>

<template>
  <NDrawer v-model:show="open" :width="720" placement="right">
    <NDrawerContent :title="catalogType" closable :native-scrollbar="false">
      <NSpace vertical :size="12">
        <NSpace align="center" :size="8">
          <NTag size="small" :bordered="false" type="info">
            {{ t("admin.agentSkills.routingCatalogReadonlyTag") }}
          </NTag>
          <NText depth="3">
            {{
              catalogType === "agents.md"
                ? t("admin.agentSkills.routingCatalogAgentsHint")
                : t("admin.agentSkills.routingCatalogSkillsHint")
            }}
          </NText>
        </NSpace>
        <div v-if="loading && !catalogText">{{ t("common.loading") }}</div>
        <pre v-else class="skill-preview routing-catalog-drawer__body">{{ catalogText }}</pre>
      </NSpace>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.routing-catalog-drawer__body {
  max-height: calc(100vh - 180px);
  overflow: auto;
  margin: 0;
}
.skill-preview {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: var(--platform-font-size-base);
  line-height: 1.5;
  max-height: 576px;
  overflow: auto;
}
</style>
