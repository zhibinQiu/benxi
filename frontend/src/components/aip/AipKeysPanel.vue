<script setup>
import { onMounted, ref } from "vue";
import { NAlert, NButton, NDataTable, NInput, NModal, NSpace } from "naive-ui";
import { AddOutline, CopyOutline, RefreshOutline, TrashOutline } from "@vicons/ionicons5";
import IconAction from "../IconAction.vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { createAipKey, deleteAipKey, fetchAipKeys } from "../../api/aipKeys";
import { renderIconActionGroup } from "../../utils/tableIconActions.js";

const ui = usePlatformUi();
const { t } = useI18n();

const props = defineProps({
  refreshing: { type: Boolean, default: false },
  onRefresh: { type: Function, default: null },
});

const loading = ref(false);
const creating = ref(false);
const rows = ref([]);
const createdSecret = ref("");
const showSecretModal = ref(false);

const columns = [
  {
    title: () => t("admin.agentSkills.aipKeys.colPrefix"),
    key: "key_prefix",
    width: 192,
  },
  {
    title: () => t("admin.agentSkills.aipKeys.colPurpose"),
    key: "purpose",
    ellipsis: { tooltip: true },
  },
  {
    title: () => t("admin.agentSkills.aipKeys.colCreator"),
    key: "created_by_name",
    width: 144,
  },
  {
    title: () => t("admin.agentSkills.aipKeys.colCreatedAt"),
    key: "created_at",
    width: 216,
    render: (row) =>
      row.created_at ? String(row.created_at).replace("T", " ").slice(0, 19) : "",
  },
  {
    title: () => t("common.actions"),
    key: "actions",
    width: 106,
    render: (row) =>
      renderIconActionGroup([
        {
          label: t("common.delete"),
          icon: TrashOutline,
          type: "error",
          onClick: () => onDelete(row),
        },
      ]),
  },
];

async function load() {
  loading.value = true;
  try {
    const data = await fetchAipKeys();
    rows.value = Array.isArray(data) ? data : [];
  } catch (e) {
    ui.error(e?.message || t("admin.agentSkills.aipKeys.loadFailed"));
  } finally {
    loading.value = false;
  }
}

async function onCreate() {
  creating.value = true;
  try {
    const data = await createAipKey("");
    createdSecret.value = data?.secret_key || "";
    showSecretModal.value = Boolean(createdSecret.value);
    if (createdSecret.value) {
      ui.success(t("admin.agentSkills.aipKeys.created"));
    }
    await load();
  } catch (e) {
    ui.error(e?.message || t("admin.agentSkills.aipKeys.createFailed"));
  } finally {
    creating.value = false;
  }
}

async function onDelete(row) {
  await ui.confirmDelete({
    title: t("admin.agentSkills.aipKeys.deleteTitle"),
    content: t("admin.agentSkills.aipKeys.deleteConfirm", { prefix: row.key_prefix }),
    onPositive: async () => {
      await deleteAipKey(row.id);
      ui.success(t("admin.agentSkills.deleted"));
      await load();
    },
  });
}

async function copySecret() {
  if (!createdSecret.value) return;
  try {
    await navigator.clipboard.writeText(createdSecret.value);
    ui.success(t("admin.agentSkills.aipKeys.copied"));
  } catch {
    ui.warning(t("admin.agentSkills.aipKeys.copyManual"));
  }
}

onMounted(load);

defineExpose({ load, openCreate: onCreate, loading });
</script>

<template>
  <div class="aip-keys-panel">
    <div class="aip-keys-card__header">
      <div class="aip-keys-card__title-row">
        <div class="aip-keys-card__title">{{ t('admin.agentSkills.tabAipKeys') }}</div>
        <div class="aip-keys-card__actions">
          <IconAction
            :label="t('admin.agentSkills.aipKeys.create')"
            :icon="AddOutline"
            :loading="creating"
            @click="onCreate"
          />
          <IconAction
            v-if="onRefresh"
            :label="t('common.refresh')"
            :icon="RefreshOutline"
            :loading="refreshing"
            @click="onRefresh"
          />
        </div>
      </div>
      <div class="aip-keys-card__hint">{{ t('admin.agentSkills.aipKeys.usageHint') }}</div>
    </div>
    <div class="aip-keys-card">
      <div class="admin-list-table">
        <NDataTable
          :columns="columns"
          :data="rows"
          :loading="loading"
          :bordered="false"
          size="small"
        />
      </div>
    </div>

    <NModal
      v-model:show="showSecretModal"
      preset="card"
      :title="t('admin.agentSkills.aipKeys.secretTitle')"
      style="width: 672px"
      :mask-closable="false"
      :close-on-esc="false"
    >
      <NAlert type="warning" :bordered="false" style="margin-bottom: 14px">
        {{ t("admin.agentSkills.aipKeys.secretOnceHint") }}
      </NAlert>
      <NInput :value="createdSecret" readonly type="textarea" :rows="3" />
      <NSpace justify="end" style="margin-top: 14px">
        <NButton @click="copySecret">
          <template #icon>
            <n-icon :component="CopyOutline" />
          </template>
          {{ t("admin.agentSkills.aipKeys.copy") }}
        </NButton>
        <NButton type="primary" @click="showSecretModal = false">
          {{ t("admin.agentSkills.aipKeys.secretSaved") }}
        </NButton>
      </NSpace>
    </NModal>
  </div>
</template>

<style scoped>
.aip-keys-panel {
  max-width: 1320px;
}

.aip-keys-card__header {
  margin: 0 0 8px;
  padding-left: 16px;
}

.aip-keys-card__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.aip-keys-card__title {
  font-size: var(--platform-font-size-sm);
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.4;
  flex-shrink: 0;
}

.aip-keys-card__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

.aip-keys-card__hint {
  margin-top: 2px;
  font-size: var(--platform-font-size-sm);
  font-weight: 400;
  color: var(--platform-text-tertiary);
  line-height: 1.4;
}

.aip-keys-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 12px 16px;
  padding-top: 0;
}

.aip-keys-card :deep(.n-data-table-th),
.aip-keys-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.aip-keys-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.aip-keys-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}
</style>
