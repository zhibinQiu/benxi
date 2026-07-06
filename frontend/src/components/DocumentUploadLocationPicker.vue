<script setup>
import { computed, ref, watch } from "vue";
import { NFormItem, NSelect, NButton, NInput, NSpace } from "naive-ui";
import { fetchKbFolders, createKbFolder } from "../api/documents.js";
import { ORG_SCOPES } from "../constants/documentScope";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";

const props = defineProps({
  libraryFolders: { type: Array, default: () => [] },
  companies: { type: Array, default: () => [] },
  departments: { type: Array, default: () => [] },
  teams: { type: Array, default: () => [] },
  personalOwners: { type: Array, default: () => [] },
  isSystemAdmin: { type: Boolean, default: false },
  scope: { type: String, default: "personal" },
  deptId: { type: [String, Number, null], default: null },
  ownerId: { type: [String, Number, null], default: null },
  folderId: { type: String, default: "__uncategorized__" },
});

const emit = defineEmits([
  "update:scope",
  "update:deptId",
  "update:ownerId",
  "update:folderId",
  "folders-changed",
]);

const { t, scopeLabel } = useI18n();
const ui = usePlatformUi();

const VIRTUAL_UNCATEGORIZED = "__uncategorized__";

const loading = ref(false);
const kbFolders = ref([]);
const canManageFolders = ref(false);
const showInlineCreate = ref(false);
const newFolderName = ref("");
const creatingFolder = ref(false);
let loadFoldersGeneration = 0;

const creatableScopes = computed(() =>
  props.libraryFolders.filter(
    (f) => f.can_create && f.scope !== "all" && f.scope !== "shared"
  )
);

const scopeOptions = computed(() =>
  creatableScopes.value.map((f) => ({
    label: f.label || scopeLabel(f.scope),
    value: f.scope,
  }))
);

const orgUnits = computed(() => {
  if (props.scope === "company") return props.companies;
  if (props.scope === "team") return props.teams;
  if (props.scope === "department") return props.departments;
  return [];
});

const showOrgPicker = computed(
  () =>
    ORG_SCOPES.includes(props.scope) &&
    orgUnits.value.length > (props.isSystemAdmin ? 0 : 1)
);

const showOwnerPicker = computed(
  () =>
    props.scope === "personal" &&
    props.isSystemAdmin &&
    props.personalOwners.length > 1
);

const ownerOptions = computed(() =>
  props.personalOwners.map((o) => ({ label: o.name, value: o.id }))
);

const deptOptions = computed(() =>
  orgUnits.value.map((d) => ({ label: d.name, value: d.id }))
);

const folderOptions = computed(() =>
  kbFolders.value
    .filter((f) => f.kind !== "shared")
    .map((f) => ({
      label: f.name,
      value:
        f.virtual_id === VIRTUAL_UNCATEGORIZED || !f.id
          ? VIRTUAL_UNCATEGORIZED
          : String(f.id),
    }))
);

function orgUnitsForScope(scope) {
  if (scope === "company") return props.companies;
  if (scope === "team") return props.teams;
  if (scope === "department") return props.departments;
  return [];
}

function ensureDeptForScope(scope) {
  if (!ORG_SCOPES.includes(scope)) {
    emit("update:deptId", null);
    return;
  }
  const units = orgUnitsForScope(scope);
  if (!units.length) {
    emit("update:deptId", null);
    return;
  }
  const current = props.deptId;
  if (current && units.some((u) => String(u.id) === String(current))) return;
  emit("update:deptId", units[0].id);
}

async function loadFolders(preferredFolderId = null) {
  if (!props.scope || props.scope === "all" || props.scope === "shared") {
    kbFolders.value = [];
    canManageFolders.value = false;
    return;
  }
  if (ORG_SCOPES.includes(props.scope) && !props.deptId) {
    kbFolders.value = [];
    canManageFolders.value = false;
    return;
  }
  loading.value = true;
  const gen = ++loadFoldersGeneration;
  try {
    const params = { scope: props.scope };
    if (ORG_SCOPES.includes(props.scope) && props.deptId) {
      params.dept_id = props.deptId;
    }
    if (props.scope === "personal" && props.isSystemAdmin && props.ownerId) {
      params.owner_id = props.ownerId;
    }
    const data = await fetchKbFolders(params);
    if (gen !== loadFoldersGeneration) return;
    kbFolders.value = data.items || [];
    canManageFolders.value = !!data.can_manage_folders;
    const validIds = kbFolders.value
      .filter((f) => f.kind !== "shared")
      .map((f) =>
        f.virtual_id === VIRTUAL_UNCATEGORIZED || !f.id
          ? VIRTUAL_UNCATEGORIZED
          : String(f.id)
      );
    const keepId = preferredFolderId ?? props.folderId;
    if (keepId && !validIds.includes(String(keepId))) {
      emit("update:folderId", VIRTUAL_UNCATEGORIZED);
    }
  } catch (e) {
    ui.error(e);
    kbFolders.value = [];
    canManageFolders.value = false;
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.scope, props.deptId, props.ownerId],
  () => {
    loadFolders();
  },
  { immediate: true }
);

function onScopeChange(scope) {
  emit("update:scope", scope);
  ensureDeptForScope(scope);
  if (scope !== "personal") {
    emit("update:ownerId", null);
  }
  emit("update:folderId", VIRTUAL_UNCATEGORIZED);
  showInlineCreate.value = false;
  newFolderName.value = "";
}

async function submitCreateFolder() {
  const name = newFolderName.value.trim();
  if (!name) {
    ui.warning("validation.folderNameRequired");
    return;
  }
  if (ORG_SCOPES.includes(props.scope) && !props.deptId) {
    ui.warning("validation.selectDepartment");
    return;
  }
  creatingFolder.value = true;
  try {
    const payload = { name, description: "", scope: props.scope };
    if (ORG_SCOPES.includes(props.scope) && props.deptId) {
      payload.dept_id = props.deptId;
    }
    if (props.scope === "personal" && props.isSystemAdmin && props.ownerId) {
      payload.owner_id = props.ownerId;
    }
    const folder = await createKbFolder(payload);
    const createdId = folder?.id ? String(folder.id) : null;
    if (createdId && folder?.name) {
      kbFolders.value = [
        ...kbFolders.value.filter((item) => String(item?.id || "") !== createdId),
        {
          id: folder.id,
          name: folder.name,
          description: folder.description || "",
          kind: folder.kind || "normal",
          virtual_id: null,
        },
      ];
      emit("update:folderId", createdId);
    }
    ui.success("documents.messages.folderCreated");
    showInlineCreate.value = false;
    newFolderName.value = "";
    await loadFolders(createdId);
    emit("folders-changed");
  } catch (e) {
    ui.error(e);
  } finally {
    creatingFolder.value = false;
  }
}
</script>

<template>
  <div class="doc-upload-location">
    <n-form-item :label="t('documents.uploadTargetScope')" required>
      <n-select
        :value="scope"
        :options="scopeOptions"
        :placeholder="t('documents.uploadScopePlaceholder')"
        @update:value="onScopeChange"
      />
    </n-form-item>

    <n-form-item
      v-if="showOrgPicker"
      :label="t('documents.uploadDeptLabel')"
      required
    >
      <n-select
        :value="deptId"
        :options="deptOptions"
        :placeholder="t('documents.deptSelectPlaceholder')"
        @update:value="(v) => emit('update:deptId', v)"
      />
    </n-form-item>

    <n-form-item
      v-if="showOwnerPicker"
      :label="t('documents.uploadOwnerLabel')"
    >
      <n-select
        :value="ownerId"
        :options="ownerOptions"
        :placeholder="t('documents.ownerSelectPlaceholder')"
        @update:value="(v) => emit('update:ownerId', v)"
      />
    </n-form-item>

    <n-form-item :label="t('documents.uploadFolderLabel')" required>
      <n-space vertical :size="10" style="width: 100%">
        <n-select
          :value="folderId"
          :options="folderOptions"
          :loading="loading"
          :placeholder="t('documents.uploadFolderPlaceholder')"
          @update:value="(v) => emit('update:folderId', v)"
        />
        <div v-if="canManageFolders" class="doc-upload-location__create">
          <template v-if="!showInlineCreate">
            <n-button
              text
              type="primary"
              size="small"
              @click="showInlineCreate = true"
            >
              {{ t("documents.uploadNewFolder") }}
            </n-button>
          </template>
          <template v-else>
            <n-space :size="10" align="center" style="width: 100%">
              <n-input
                v-model:value="newFolderName"
                size="small"
                :placeholder="t('documents.folderForm.namePlaceholder')"
                style="flex: 1"
                @keyup.enter="submitCreateFolder"
              />
              <n-button
                type="primary"
                size="small"
                :loading="creatingFolder"
                @click="submitCreateFolder"
              >
                {{ t("common.create") }}
              </n-button>
              <n-button
                size="small"
                :disabled="creatingFolder"
                @click="
                  showInlineCreate = false;
                  newFolderName = '';
                "
              >
                {{ t("common.cancel") }}
              </n-button>
            </n-space>
          </template>
        </div>
      </n-space>
    </n-form-item>
  </div>
</template>
