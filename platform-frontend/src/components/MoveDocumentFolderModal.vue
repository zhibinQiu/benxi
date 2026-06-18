<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, ref, watch } from "vue";
import { NForm, NFormItem, NSelect, NButton, NSpace } from "naive-ui";
import { fetchKbFolders, moveDocument } from "../api/client";
import { ORG_SCOPES } from "../constants/documentScope";
import AdminFormModal from "./AdminFormModal.vue";

const props = defineProps({
  show: { type: Boolean, default: false },
  documentId: { type: String, default: "" },
  /** 批量移动时传入多个文档 ID */
  documentIds: { type: Array, default: () => [] },
  /** 文档分级（用于判断是否支持文件夹） */
  scope: { type: String, default: "" },
  /** 列出目标文件夹时优先使用当前文档库 Tab 的分级 */
  folderScope: { type: String, default: "" },
  deptId: { type: String, default: null },
  folderDeptId: { type: String, default: null },
  currentFolderId: { type: String, default: null },
  documentTitle: { type: String, default: "" },
});

const emit = defineEmits(["update:show", "moved"]);

const moveIds = computed(() => {
  if (props.documentIds?.length) return props.documentIds.map(String);
  if (props.documentId) return [String(props.documentId)];
  return [];
});

const isBatch = computed(() => moveIds.value.length > 1);

const modalTitle = computed(() => {
  if (isBatch.value) return `批量移动 · ${moveIds.value.length} 份文档`;
  if (props.documentTitle) return `移动文档 · ${props.documentTitle}`;
  return "移动文档";
});

const ui = usePlatformUi();
const loading = ref(false);
const saving = ref(false);
const targetFolder = ref(null);

const UNCATEGORIZED = "__uncategorized__";

const effectiveScope = computed(
  () => props.folderScope || props.scope || "personal"
);

const effectiveDeptId = computed(() =>
  ORG_SCOPES.includes(effectiveScope.value)
    ? props.folderDeptId || props.deptId
    : null
);

const supportsFolders = computed(() =>
  ["company", "department", "team", "personal"].includes(effectiveScope.value)
);

const folderOptions = ref([]);

async function loadOptions() {
  if (!supportsFolders.value) {
    folderOptions.value = [];
    return;
  }
  loading.value = true;
  try {
    const params = { scope: effectiveScope.value };
    if (effectiveScope.value !== "personal" && effectiveDeptId.value) {
      params.dept_id = effectiveDeptId.value;
    }
    const data = await fetchKbFolders(params);
    const opts = (data.items || [])
      .filter((f) => f.kind !== "shared")
      .map((f) => ({
        label: f.name,
        value: f.virtual_id === UNCATEGORIZED || !f.id ? UNCATEGORIZED : String(f.id),
      }));
    folderOptions.value = opts;
    if (props.currentFolderId) {
      targetFolder.value = String(props.currentFolderId);
    } else {
      targetFolder.value = UNCATEGORIZED;
    }
  } catch (e) {
    ui.error(e.message);
    folderOptions.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  () => [
    props.show,
    props.documentId,
    effectiveScope.value,
    effectiveDeptId.value,
  ],
  ([visible]) => {
    if (visible) loadOptions();
  },
  { immediate: true }
);

async function submit() {
  if (!moveIds.value.length || targetFolder.value == null) return;
  saving.value = true;
  try {
    const folder_id =
      targetFolder.value === UNCATEGORIZED ? null : targetFolder.value;
    let lastDoc = null;
    for (const id of moveIds.value) {
      lastDoc = await moveDocument(id, { folder_id });
    }
    ui.success(
      isBatch.value ? `已移动 ${moveIds.value.length} 份文档` : "文档已移动"
    );
    emit("update:show", false);
    emit("moved", lastDoc);
  } catch (e) {
    ui.error(e.message);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <AdminFormModal
    :show="show"
    :title="modalTitle"
    :width="420"
    @update:show="(v) => emit('update:show', v)"
  >
    <p v-if="!supportsFolders" class="admin-form-modal__hint">
      该文档分级不支持文件夹。
    </p>
    <n-form v-else class="admin-form-modal__form" label-placement="top">
      <n-form-item label="目标文件夹" required>
        <n-select
          v-model:value="targetFolder"
          :options="folderOptions"
          :loading="loading"
          placeholder="选择文件夹"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end" :size="10">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button
          type="primary"
          :loading="saving"
          :disabled="!supportsFolders || targetFolder == null"
          @click="submit"
        >
          移动
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>
</template>
