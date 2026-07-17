<script setup>
import { computed, onMounted, ref } from "vue";
import {
  NButton,
  NCard,
  NEmpty,
  NModal,
  NScrollbar,
  NSpin,
  NTag,
  NText,
  useDialog,
  useMessage,
} from "naive-ui";
import { AddOutline, TrashOutline } from "@vicons/ionicons5";
import IconAction from "../IconAction.vue";
import { useI18n } from "../../composables/useI18n";
import {
  fetchKnowledgeMounts,
  addKnowledgeMount,
  removeKnowledgeMount,
} from "../../api/agentSkills.js";
import { fetchMountableFolders } from "../../api/knowledge.js";

const props = defineProps({
  agentId: { type: String, required: true },
});

const { t } = useI18n();
const dialog = useDialog();
const message = useMessage();

const loading = ref(false);
const mounts = ref([]);
const pickerOpen = ref(false);
const pickerLoading = ref(false);
/** 平面化后的 {(dataset_id, folder_id) -> label} 映射 */
const folderMap = ref({});

onMounted(() => loadMounts());

async function loadMounts() {
  loading.value = true;
  try {
    const res = await fetchKnowledgeMounts(props.agentId);
    mounts.value = res?.data ?? [];
  } catch (e) {
    message.error("加载挂载列表失败");
  } finally {
    loading.value = false;
  }
}

async function handleRemove(mountId) {
  dialog.warning({
    title: t("admin.agentSkills.removeKnowledgeMount"),
    content: "确定移除该知识库文件夹挂载？",
    positiveText: "确定",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await removeKnowledgeMount(props.agentId, mountId);
        message.success(t("admin.agentSkills.knowledgeMountRemoved"));
        await loadMounts();
      } catch (e) {
        message.error("移除挂载失败");
      }
    },
  });
}

async function openPicker() {
  pickerOpen.value = true;
  pickerLoading.value = true;
  folderMap.value = {};
  try {
    const res = await fetchMountableFolders();
    const folders = res?.data ?? [];
    for (const f of folders) {
      const mountId = f.folder_id || f.virtual_folder_id;
      if (mountId) {
        const key = `${f.dataset_id}::${mountId}`;
        folderMap.value[key] = {
          dataset_id: f.dataset_id,
          folder_id: mountId,
          scope: f.scope,
          label: f.label,
          library_label: f.library_label || "",
          document_count: f.document_count || 0,
        };
      }
    }
  } catch (e) {
    message.error("加载知识库范围树失败");
  } finally {
    pickerLoading.value = false;
  }
}

const folderEntries = computed(() => Object.entries(folderMap.value));

async function handleAddMount(key) {
  const entry = folderMap.value[key];
  if (!entry) return;
  try {
    await addKnowledgeMount(props.agentId, {
      datasetId: entry.dataset_id,
      folderId: entry.folder_id,
      scope: entry.scope,
      label: entry.label,
    });
    message.success(t("admin.agentSkills.knowledgeMountAdded"));
    pickerOpen.value = false;
    await loadMounts();
  } catch (e) {
    message.error(e.message || "挂载失败");
  }
}
</script>

<template>
  <div class="knowledge-mount-manager">
    <div
      style="
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
      "
    >
      <NText depth="3" style="font-size: 13px">
        {{ t("admin.agentSkills.knowledgeMountsHint") }}
      </NText>
      <NButton size="tiny" secondary class="platform-btn--create" @click="openPicker">
        <template #icon><AddOutline /></template>
        {{ t("admin.agentSkills.addKnowledgeMount") }}
      </NButton>
    </div>

    <NSpin :show="loading">
      <div v-if="!mounts.length && !loading" style="padding: 20px 0">
        <NEmpty :description="t('admin.agentSkills.knowledgeMountsEmpty')" />
      </div>
      <div v-else style="display: flex; flex-direction: column; gap: 6px">
        <NCard
          v-for="m in mounts"
          :key="m.id"
          size="small"
          :title="m.label || '文件夹'"
          hoverable
          style="cursor: default"
        >
          <template #header-extra>
            <IconAction
              variant="table"
              type="error"
              :label="t('admin.agentSkills.removeKnowledgeMount')"
              :icon="TrashOutline"
              @click="handleRemove(m.id)"
            />
          </template>
          <div style="display: flex; gap: 6px; flex-wrap: wrap">
            <NTag size="tiny" :bordered="false">{{ m.scope }}</NTag>
            <NTag size="tiny" :bordered="false">
              {{ m.dataset_id?.slice(0, 8) }}…
            </NTag>
          </div>
        </NCard>
      </div>
    </NSpin>

    <!-- 选择知识库文件夹弹窗 -->
    <NModal
      v-model:show="pickerOpen"
      preset="card"
      style="width: 560px"
      :title="t('admin.agentSkills.knowledgeMountPickFolder')"
      :mask-closable="false"
    >
      <NSpin :show="pickerLoading">
        <div v-if="!folderEntries.length && !pickerLoading" style="padding: 20px 0">
          <NEmpty description="暂无可用知识库文件夹" />
        </div>
        <div v-else>
          <NScrollbar style="max-height: 420px">
            <div
              v-for="[key, entry] in folderEntries"
              :key="key"
              style="
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 4px;
                border-bottom: 1px solid var(--n-border-color);
              "
            >
              <div style="flex: 1; min-width: 0">
                <NText style="display: block; font-weight: 500">
                  {{ entry.library_label }} / {{ entry.label }}
                </NText>
                <div style="display: flex; gap: 4px; margin-top: 2px">
                  <NTag size="tiny" :bordered="false">{{ entry.scope }}</NTag>
                  <NTag size="tiny" :bordered="false">
                    {{ entry.document_count }} 文档
                  </NTag>
                </div>
              </div>
              <NButton
                size="tiny"
                type="primary"
                secondary
                class="platform-btn--create"
                @click="handleAddMount(key)"
              >
                {{ t("admin.agentSkills.addKnowledgeMount") }}
              </NButton>
            </div>
          </NScrollbar>
        </div>
      </NSpin>
    </NModal>
  </div>
</template>
