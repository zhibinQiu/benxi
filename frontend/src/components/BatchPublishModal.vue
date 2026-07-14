<script setup>
import { computed, ref, watch } from "vue";
import {
  NSpace,
  NButton,
  NRadio,
  NRadioGroup,
  NText,
  NProgress,
} from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import OrgDeptPickerTree from "./OrgDeptPickerTree.vue";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { updateDocument } from "../api/documents.js";
import { fetchDepartmentTree } from "../api/departments.js";
import { ORG_SCOPES } from "../constants/documentScope";

/** scope → 组织树层级深度（0=根/公司, 1=部门, 2=团队） */
const SCOPE_DEPTH = { company: 0, department: 1, team: 2 };

const props = defineProps({
  show: { type: Boolean, default: false },
  documentIds: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:show", "published"]);

const { t } = useI18n();
const ui = usePlatformUi();

const loading = ref(false);
const publishing = ref(false);

const departments = ref([]);
const publishTarget = ref("company");
const publishDeptIds = ref([]);
const batchProgress = ref({ done: 0, total: 0, failed: [] });

const documentCount = computed(() => props.documentIds.length);
const isBatch = computed(() => documentCount.value > 1);

/** 计算各部门在组织树中的深度。 */
function computeDeptDepthMap(depts) {
  const dp = new Map();
  function depthOf(id) {
    const key = String(id);
    if (dp.has(key)) return dp.get(key);
    const dept = depts.find((d) => String(d.id) === key);
    if (!dept || !dept.parent_id) {
      dp.set(key, 0);
      return 0;
    }
    const d = depthOf(dept.parent_id) + 1;
    dp.set(key, d);
    return d;
  }
  for (const d of depts) depthOf(d.id);
  return dp;
}

/** 仅展示当前 scope 对应深度的组织节点，避免用户选错层级。 */
const filteredDepartments = computed(() => {
  const depthMap = computeDeptDepthMap(departments.value);
  const targetDepth = SCOPE_DEPTH[publishTarget.value] ?? 0;
  return departments.value.filter(
    (d) => depthMap.get(String(d.id)) === targetDepth
  );
});

const hasDepts = computed(() => filteredDepartments.value.length > 0);

const canSubmit = computed(() => {
  if (!publishDeptIds.value.length) return false;
  if (!ORG_SCOPES.includes(publishTarget.value)) return false;
  return true;
});

const progressPercent = computed(() => {
  const p = batchProgress.value;
  if (!p.total) return 0;
  return Math.round((p.done / p.total) * 100);
});

async function loadDepartments() {
  if (!props.documentIds.length) return;
  loading.value = true;
  try {
    const depts = await fetchDepartmentTree();
    departments.value = Array.isArray(depts) ? depts : (depts.items || []);
  } catch {
    departments.value = [];
  } finally {
    loading.value = false;
  }
}

async function publishToLibrary() {
  if (!canSubmit.value) {
    ui.warning(t("documents.detail.selectPublishOrg"));
    return;
  }
  publishing.value = true;
  batchProgress.value = { done: 0, total: props.documentIds.length, failed: [] };
  try {
    const payload = {
      scope: publishTarget.value,
      dept_id: publishDeptIds.value[0],
    };
    for (const docId of props.documentIds) {
      try {
        await updateDocument(docId, payload);
        batchProgress.value.done++;
      } catch (e) {
        batchProgress.value.failed.push({ docId, reason: e.message });
        batchProgress.value.done++;
      }
    }
    const { done: success, failed } = batchProgress.value;
    if (success > 0 && failed.length === 0) {
      ui.success(t("documents.detail.publishedToLibrary"));
      emit("published");
    } else if (success > 0) {
      ui.warning(`已发布 ${success} 份文档，${failed.length} 份发布失败`);
      emit("published");
    } else {
      ui.error("发布失败");
    }
  } finally {
    publishing.value = false;
  }
}

function resetState() {
  publishTarget.value = "company";
  publishDeptIds.value = [];
  batchProgress.value = { done: 0, total: 0, failed: [] };
  departments.value = [];
}

watch(
  () => props.show,
  (val) => {
    if (val) {
      resetState();
      void loadDepartments();
    }
  },
  { immediate: true }
);

/** 切换发布目标时，之前选的部门 ID 已不匹配新层级，自动清空。 */
watch(publishTarget, () => {
  publishDeptIds.value = [];
});
</script>

<template>
  <AdminFormModal
    :show="show"
    :title="t('documents.detail.publishToLibrary')"
    :width="624"
    @update:show="$emit('update:show', $event)"
  >
    <template v-if="loading">
      <div class="batch-publish-loading">
        <n-text depth="3">{{ t("common.loading") }}</n-text>
      </div>
    </template>

    <template v-else>
      <div v-if="isBatch" class="batch-publish-summary">
        <n-tag type="info" size="small" :bordered="false">
          {{ t("batch.selected", { count: documentCount }) }}
        </n-tag>
      </div>

      <p class="batch-publish-hint">
        {{ t("documents.detail.publishHint") }}
      </p>

      <n-radio-group v-model:value="publishTarget" class="batch-publish-target">
        <n-space>
          <n-radio value="company">{{ t("scope.company") }}</n-radio>
          <n-radio value="department">{{ t("scope.department") }}</n-radio>
          <n-radio value="team">{{ t("scope.team") }}</n-radio>
        </n-space>
      </n-radio-group>

      <OrgDeptPickerTree
        v-if="hasDepts"
        :departments="filteredDepartments"
        v-model:department-ids="publishDeptIds"
        :max-height="336"
        style="margin-bottom: 14px"
      />

      <n-progress
        v-if="publishing && isBatch"
        type="line"
        :percentage="progressPercent"
        :show-indicator="false"
        class="batch-publish-progress"
      />
    </template>

    <template #footer>
      <n-space justify="end">
        <n-button :disabled="publishing" @click="$emit('update:show', false)">
          {{ t("common.cancel") }}
        </n-button>
        <n-button
          type="primary"
          :loading="publishing"
          :disabled="!canSubmit || !hasDepts"
          @click="publishToLibrary"
        >
          {{ t("documents.detail.publish") }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>
</template>

<style scoped>
.batch-publish-loading {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}

.batch-publish-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.batch-publish-hint {
  margin: 0 0 14px;
  color: var(--platform-text-secondary, #666);
  font-size: 16px;
  line-height: 1.55;
}

.batch-publish-target {
  display: block;
  margin-bottom: 14px;
}

.batch-publish-progress {
  margin-bottom: 14px;
}
</style>
