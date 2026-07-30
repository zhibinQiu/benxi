<script setup>
import { h } from "vue";
import { NEmpty, NIcon } from "naive-ui";
import { CreateOutline, TrashOutline } from "@vicons/ionicons5";
import KbFolderCard from "../KbFolderCard.vue";
import KbFolderCreateCard from "../KbFolderCreateCard.vue";
import PlatformSpin from "../PlatformSpin.vue";
import { useI18n } from "../../composables/useI18n";

defineProps({
  loading: { type: Boolean, default: false },
  folders: { type: Array, default: () => [] },
  canManageFolders: { type: Boolean, default: false },
});

const emit = defineEmits([
  "prefetch-folder",
  "open-folder",
  "menu-select",
  "create-folder",
]);

const { t } = useI18n();

function folderTooltip(folder) {
  const parts = [];
  if (folder.description) parts.push(folder.description);
  parts.push(t("documents.folderDocCount", { count: folder.document_count ?? 0 }));
  if (folder.is_system && folder.system_hint) parts.push(folder.system_hint);
  return parts.join("\n");
}

function folderMenuOptions(folder) {
  if (!folder.can_manage || !folder.id || folder.is_system) return [];
  return [
    {
      label: t("common.edit"),
      key: "edit",
      icon: () => h(NIcon, null, { default: () => h(CreateOutline) }),
    },
    {
      label: t("common.delete"),
      key: "delete",
      icon: () => h(NIcon, null, { default: () => h(TrashOutline) }),
    },
  ];
}
</script>

<template>
  <PlatformSpin :show="loading" class="documents-view-spin" local>
    <n-empty
      v-if="!folders.length && !canManageFolders"
      :description="t('documents.emptyFolders')"
    />
    <div v-else class="kb-folder-explorer">
      <div
        v-for="(folder, folderIdx) in folders"
        :key="folder.virtual_id || folder.id"
        class="kb-folder-explorer__cell"
        :style="{ '--folder-i': folderIdx }"
        @mouseenter="emit('prefetch-folder', folder)"
      >
        <KbFolderCard
          :folder="folder"
          :title="folderTooltip(folder)"
          :card-key="folder.virtual_id || folder.id || `f-${folderIdx}`"
          :menu-options="folderMenuOptions(folder)"
          @open="(f) => emit('open-folder', f)"
          @menu-select="(key, f) => emit('menu-select', key, f)"
        />
      </div>
      <div
        v-if="canManageFolders"
        class="kb-folder-explorer__cell"
        :style="{ '--folder-i': folders.length }"
      >
        <KbFolderCreateCard @create="emit('create-folder')" />
      </div>
    </div>
  </PlatformSpin>
</template>

<style scoped>
@media (max-width: 768px) {
  .kb-folder-explorer {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)) !important;
    gap: 10px;
    padding: 8px 0 16px;
  }
  .kb-folder-explorer__cell {
    max-width: 100%;
  }
  .kb-folder-explorer__cell > * {
    max-width: 100%;
  }
  .kb-folder-create-card {
    padding: 8px 6px 10px;
  }
}

@media (max-width: 400px) {
  .kb-folder-explorer {
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 8px;
    padding: 6px 0 12px;
  }
}
</style>
