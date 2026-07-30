<script setup>
import {
  NButton,
  NSpace,
  NForm,
  NFormItem,
  NUpload,
  NUploadDragger,
  NTabs,
  NTabPane,
  NProgress,
  NIcon,
} from "naive-ui";
import { CloudUploadOutline } from "@vicons/ionicons5";
import AdminFormModal from "../AdminFormModal.vue";
import DocumentUploadLocationPicker from "../DocumentUploadLocationPicker.vue";
import FileDropZone from "../FileDropZone.vue";
import { useI18n } from "../../composables/useI18n";
import {
  DOCUMENT_UPLOAD_ACCEPT,
  DOCUMENT_UPLOAD_MAX_FILES,
} from "../../constants/documentUpload.js";

const show = defineModel("show", { type: Boolean, default: false });
const uploadMode = defineModel("uploadMode", { type: String, default: "single" });
const createScope = defineModel("createScope", { type: String, required: true });
const createDeptId = defineModel("createDeptId", { type: [String, Number], default: null });
const createOwnerId = defineModel("createOwnerId", { type: [String, Number], default: null });
const createFolderId = defineModel("createFolderId", { type: [String, Number], default: null });
const batchUploadFileList = defineModel("batchUploadFileList", { type: Array, default: () => [] });

defineProps({
  companies: { type: Array, default: () => [] },
  departments: { type: Array, default: () => [] },
  teams: { type: Array, default: () => [] },
  personalOwners: { type: Array, default: () => [] },
  isSystemAdmin: { type: Boolean, default: false },
  uploadFile: { type: Object, default: null },
  creating: { type: Boolean, default: false },
  folders: { type: Array, default: () => [] },
  batchUploadFiles: { type: Array, default: () => [] },
  batchUploading: { type: Boolean, default: false },
  batchProgress: { type: Object, default: () => ({ done: 0, total: 0 }) },
  batchUploadKey: { type: Number, default: 0 },
  uploadMaxMb: { type: Number, default: 0 },
  batchUploadStats: { type: Object, default: () => ({ count: 0, totalSize: 0 }) },
  canSubmitSingleUpload: { type: Boolean, default: false },
  canSubmitUploadLocation: { type: Boolean, default: false },
  formatUploadFileSize: { type: Function, required: true },
});

const emit = defineEmits([
  "folders-changed",
  "single-file-change",
  "batch-file-change",
  "clear-batch-selection",
  "close",
  "submit-single",
  "submit-batch",
]);

const { t } = useI18n();
</script>

<template>
  <AdminFormModal
    v-model:show="show"
    class="documents-upload-modal"
    :title="t('documents.uploadModalTitle')"
    width="min(480px, 94vw)"
  >
    <n-tabs
      v-model:value="uploadMode"
      type="segment"
      size="small"
      class="documents-upload-modal__tabs"
    >
      <n-tab-pane name="single" :tab="t('documents.uploadSingle')" />
      <n-tab-pane name="batch" :tab="t('documents.batchUpload')" />
    </n-tabs>

    <n-form
      class="documents-upload-modal__form admin-form-modal__form admin-form-modal__form--compact"
      label-placement="top"
      @submit.prevent
    >
      <DocumentUploadLocationPicker
        v-model:scope="createScope"
        v-model:dept-id="createDeptId"
        v-model:owner-id="createOwnerId"
        v-model:folder-id="createFolderId"
        :library-folders="folders"
        :companies="companies"
        :departments="departments"
        :teams="teams"
        :personal-owners="personalOwners"
        :is-system-admin="isSystemAdmin"
        @folders-changed="emit('folders-changed')"
      />

      <template v-if="uploadMode === 'single'">
        <n-form-item :label="t('documents.uploadFileLabel')" required>
          <file-drop-zone
            class="documents-upload-modal__file-picker"
            compact
            hide-button
            :accept="DOCUMENT_UPLOAD_ACCEPT"
            :title="t('documents.uploadDropHint')"
            :hint="t('documents.uploadSizeHint', { mb: uploadMaxMb })"
            :file-name="uploadFile?.name || ''"
            :disabled="creating"
            @change="emit('single-file-change', $event)"
          />
        </n-form-item>
      </template>

      <template v-else>
        <n-form-item :label="t('documents.uploadFileLabel')" required>
          <n-upload
            :key="batchUploadKey"
            v-model:file-list="batchUploadFileList"
            multiple
            :accept="DOCUMENT_UPLOAD_ACCEPT"
            :default-upload="false"
            :show-file-list="false"
            @change="emit('batch-file-change', $event)"
          >
            <n-upload-dragger
              class="documents-upload-modal__dropzone"
              :class="{ 'documents-upload-modal__dropzone--ready': batchUploadFiles.length }"
            >
              <div class="documents-upload-modal__dropzone-inner">
                <n-icon
                  :size="28"
                  :component="CloudUploadOutline"
                  class="documents-upload-modal__dropzone-icon"
                />
                <span class="documents-upload-modal__dropzone-title">
                  {{
                    batchUploadFiles.length
                      ? t("documents.uploadBatchSelected", { count: batchUploadStats.count })
                      : t("documents.uploadBatchDropHint", { max: DOCUMENT_UPLOAD_MAX_FILES })
                  }}
                </span>
                <span class="documents-upload-modal__dropzone-meta">
                  <template v-if="batchUploadFiles.length">
                    {{
                      t("documents.uploadBatchSummary", {
                        size: formatUploadFileSize(batchUploadStats.totalSize),
                      })
                    }}
                    ·
                    <n-button
                      text
                      type="primary"
                      size="tiny"
                      :disabled="batchUploading"
                      @click.stop="emit('clear-batch-selection')"
                    >
                      {{ t("documents.uploadReselect") }}
                    </n-button>
                  </template>
                  <template v-else>
                    {{ t("documents.uploadBatchMeta", { mb: uploadMaxMb }) }}
                  </template>
                </span>
              </div>
            </n-upload-dragger>
          </n-upload>
          <n-progress
            v-if="batchUploading && batchProgress.total"
            type="line"
            :percentage="Math.round((batchProgress.done / batchProgress.total) * 100)"
            :show-indicator="true"
            class="documents-upload-modal__batch-progress"
          />
        </n-form-item>
      </template>
    </n-form>

    <p class="documents-upload-modal__footnote">
      {{ t("documents.uploadIndexHint") }}
    </p>

    <template #footer>
      <n-space justify="end" :size="8">
        <n-button :disabled="batchUploading || creating" @click="emit('close')">
          {{ t("common.cancel") }}
        </n-button>
        <n-button
          v-if="uploadMode === 'single'"
          type="primary"
          :loading="creating"
          :disabled="!canSubmitSingleUpload"
          @click="emit('submit-single')"
        >
          {{ t("documents.uploadSubmitSingle") }}
        </n-button>
        <n-button
          v-else
          type="primary"
          :loading="batchUploading"
          :disabled="!batchUploadFiles.length || !canSubmitUploadLocation"
          @click="emit('submit-batch')"
        >
          {{ t("documents.uploadSubmitBatch", { count: batchUploadFiles.length || 0 }) }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>
</template>

<style scoped>
@media (max-width: 768px) {
  .documents-upload-modal.n-modal :deep(.n-card) {
    width: 100vw !important;
    max-width: 100vw !important;
    height: 100vh;
    max-height: 100vh;
    border-radius: 0 !important;
    margin: 0;
  }
  .documents-upload-modal.n-modal :deep(.n-card__content) {
    flex: 1;
    overflow-y: auto;
  }
}
</style>
