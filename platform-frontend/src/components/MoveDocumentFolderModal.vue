<script setup>
import { computed, ref, watch } from "vue";
import { NModal, NForm, NFormItem, NSelect, NButton, NSpace, useMessage } from "naive-ui";
import { fetchKbFolders, moveDocument } from "../api/client";

const props = defineProps({
  show: { type: Boolean, default: false },
  documentId: { type: String, default: "" },
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

const message = useMessage();
const loading = ref(false);
const saving = ref(false);
const targetFolder = ref(null);

const UNCATEGORIZED = "__uncategorized__";

const effectiveScope = computed(
  () => props.folderScope || props.scope || "personal"
);

const effectiveDeptId = computed(() =>
  effectiveScope.value === "department"
    ? props.folderDeptId || props.deptId
    : null
);

const supportsFolders = computed(() =>
  ["company", "department", "personal"].includes(effectiveScope.value)
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
    if (effectiveScope.value === "department" && effectiveDeptId.value) {
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
    message.error(e.message);
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
  if (!props.documentId || targetFolder.value == null) return;
  saving.value = true;
  try {
    const folder_id =
      targetFolder.value === UNCATEGORIZED ? null : targetFolder.value;
    const doc = await moveDocument(props.documentId, { folder_id });
    message.success("文档已移动");
    emit("update:show", false);
    emit("moved", doc);
  } catch (e) {
    message.error(e.message);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="documentTitle ? `移动文档 · ${documentTitle}` : '移动文档'"
    style="width: 420px"
    :mask-closable="false"
    @update:show="(v) => emit('update:show', v)"
  >
    <p v-if="!supportsFolders" style="margin: 0; color: #666; font-size: 13px">
      该文档分级不支持文件夹。
    </p>
    <n-form v-else>
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
      <n-space justify="end">
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
  </n-modal>
</template>
