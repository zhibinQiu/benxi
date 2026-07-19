<script setup>
defineOptions({ name: "PromptManagementView" });
import { ref, computed, onMounted, watch } from "vue";
import {
  SearchOutline,
  AddOutline,
  CopyOutline,
  TrashOutline,
  FolderOpenOutline,
} from "@vicons/ionicons5";
import { useMessage, useDialog } from "naive-ui";
import { useI18n } from "../composables/useI18n";
import {
  fetchPrompts,
  fetchPromptCategories,
  createPrompt,
  updatePrompt,
  deletePrompt,
} from "../api/prompts";

const message = useMessage();
const dialog = useDialog();
const { t } = useI18n();

// ── 状态 ──
const prompts = ref([]);
const categories = ref([]);
const loading = ref(false);
const searchQuery = ref("");
const activeCategory = ref("");

// ── 新建/编辑弹窗 ──
const showModal = ref(false);
const editingId = ref(null);
const form = ref({ title: "", content: "", category: "" });
const saving = ref(false);

// ── 预定义类别选项 ──
const CATEGORY_OPTIONS = computed(() => [
  { label: t("promptManagement.catCoding"), value: "编程" },
  { label: t("promptManagement.catImageGen"), value: "生图" },
  { label: t("promptManagement.catOther"), value: "其他" },
]);

// ── 计算属性 ──
const filteredPrompts = computed(() => {
  let list = prompts.value;
  const q = searchQuery.value.trim().toLowerCase();
  if (q) {
    list = list.filter(
      (p) =>
        p.title.toLowerCase().includes(q) ||
        p.content.toLowerCase().includes(q)
    );
  }
  return list;
});

// ── 加载数据 ──
async function loadData() {
  loading.value = true;
  try {
    const [promptData, catData] = await Promise.all([
      fetchPrompts(),
      fetchPromptCategories(),
    ]);
    prompts.value = promptData || [];
    categories.value = catData || [];
  } catch {
    prompts.value = [];
    categories.value = [];
  } finally {
    loading.value = false;
  }
}

// ── 新建 ──
function openCreate() {
  editingId.value = null;
  form.value = { title: "", content: "", category: "生图" };
  showModal.value = true;
}

function openEdit(item) {
  editingId.value = item.id;
  form.value = {
    title: item.title,
    content: item.content,
    category: item.category,
  };
  showModal.value = true;
}

// ── 保存 ──
async function handleSave() {
  const { title, content } = form.value;
  if (!title.trim()) {
    message.warning(t("promptManagement.msgTitleRequired"));
    return;
  }
  if (!content.trim()) {
    message.warning(t("promptManagement.msgContentRequired"));
    return;
  }
  saving.value = true;
  try {
    if (editingId.value) {
      await updatePrompt(editingId.value, form.value);
      message.success(t("promptManagement.msgUpdated"));
    } else {
      await createPrompt(form.value);
      message.success(t("promptManagement.msgCreated"));
    }
    showModal.value = false;
    await loadData();
  } catch (e) {
    message.error(e?.message || t("promptManagement.msgOperationFailed"));
  } finally {
    saving.value = false;
  }
}

// ── 删除 ──
function handleDelete(item) {
  dialog.warning({
    title: t("promptManagement.deleteTitle"),
    content: t("promptManagement.deleteConfirm", { title: item.title }),
    positiveText: t("promptManagement.deleteOk"),
    negativeText: t("promptManagement.cancel"),
    onPositiveClick: async () => {
      try {
        await deletePrompt(item.id);
        message.success(t("promptManagement.msgDeleted"));
        await loadData();
      } catch (e) {
        message.error(e?.message || t("promptManagement.msgDeleteFailed"));
      }
    },
  });
}

// ── 复制 ──
async function copyContent(content) {
  try {
    await navigator.clipboard.writeText(content);
    message.success(t("promptManagement.msgCopied"));
  } catch {
    message.error(t("promptManagement.msgCopyFailed"));
  }
}

// ── 分类点击 ──
function toggleCategory(cat) {
  activeCategory.value = activeCategory.value === cat ? "" : cat;
}

// ── 搜索防抖 ──
let searchTimer = null;
watch(searchQuery, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    try {
      prompts.value =
        (await fetchPrompts({ search: searchQuery.value.trim() || undefined })) || [];
    } catch {
      prompts.value = [];
    }
  }, 300);
});

watch(activeCategory, async (cat) => {
  try {
    prompts.value =
      (await fetchPrompts({ category: cat || undefined })) || [];
  } catch {
    prompts.value = [];
  }
});

// ── 初始化 ──
onMounted(loadData);
</script>

<template>
  <div class="pm-page feature-page">
    <!-- 操作栏 -->
    <div class="pm-header">
      <div class="pm-header-actions">
        <div class="pm-search-box">
          <n-input
            v-model:value="searchQuery"
            size="small"
            clearable
            :placeholder="t('promptManagement.searchPlaceholder')"
            class="pm-search-input"
          >
            <template #prefix>
              <n-icon size="16" class="pm-search-icon">
                <search-outline />
              </n-icon>
            </template>
          </n-input>
        </div>
        <n-button @click="openCreate">
          <template #icon>
            <n-icon><add-outline /></n-icon>
          </template>
          {{ t("promptManagement.create") }}
        </n-button>
      </div>
    </div>

    <!-- 分类标签（筛选控件，不用主按钮） -->
    <div class="pm-categories">
      <n-button
        size="small"
        quaternary
        class="pm-cat-btn"
        :class="{ 'pm-cat-btn--active': activeCategory === '' }"
        @click="activeCategory = ''"
      >
        <template #icon>
          <n-icon size="14"><folder-open-outline /></n-icon>
        </template>
        {{ t("promptManagement.all") }}
      </n-button>
      <n-button
        v-for="cat in categories"
        :key="cat.category"
        size="small"
        quaternary
        class="pm-cat-btn"
        :class="{ 'pm-cat-btn--active': activeCategory === cat.category }"
        @click="toggleCategory(cat.category)"
      >
        {{ cat.category }}
      </n-button>
    </div>

    <!-- 内容区 -->
    <div class="pm-body">
      <n-spin :show="loading" class="pm-spin">
        <!-- 空状态 -->
        <n-empty
          v-if="!loading && filteredPrompts.length === 0"
          :description="searchQuery || activeCategory ? t('promptManagement.emptySearch') : t('promptManagement.emptyNoData')"
        />

        <!-- 卡片列表 -->
        <div v-else class="pm-grid">
          <div
            v-for="item in filteredPrompts"
            :key="item.id"
            class="pm-card"
            @click="openEdit(item)"
          >
            <div class="pm-card-top">
              <div class="pm-card-title-row">
                <h3 class="pm-card-title">{{ item.title }}</h3>
                <n-tag v-if="item.category" size="tiny" :bordered="false">{{ item.category }}</n-tag>
              </div>
            </div>
            <p class="pm-card-preview">{{ item.content }}</p>
            <div class="pm-card-footer">
              <span class="pm-card-time">{{ item.updated_at?.slice(0, 10) || "" }}</span>
              <div class="pm-card-footer-actions">
                <n-button size="small" quaternary @click.stop="copyContent(item.content)">
                  <template #icon>
                    <n-icon size="14"><copy-outline /></n-icon>
                  </template>
                  {{ t("promptManagement.copy") }}
                </n-button>
                <n-button size="small" quaternary @click.stop="handleDelete(item)">
                  <template #icon>
                    <n-icon size="14"><trash-outline /></n-icon>
                  </template>
                  {{ t("promptManagement.delete") }}
                </n-button>
              </div>
            </div>
          </div>
        </div>
      </n-spin>
    </div>

    <!-- 新建/编辑弹窗 -->
    <n-modal
      v-model:show="showModal"
      :mask-closable="false"
      preset="card"
      class="pm-modal"
      :title="editingId ? t('promptManagement.editModalTitle') : t('promptManagement.createModalTitle')"
      :style="{ maxWidth: '640px' }"
      :segmented="{ footer: true }"
    >
      <n-form label-placement="top" class="pm-form">
        <n-form-item :label="t('promptManagement.formTitle')">
          <n-input
            v-model:value="form.title"
            :placeholder="t('promptManagement.titlePlaceholder')"
            :maxlength="256"
          />
        </n-form-item>
        <n-form-item :label="t('promptManagement.formCategory')">
          <n-select
            v-model:value="form.category"
            :options="CATEGORY_OPTIONS"
            :placeholder="t('promptManagement.categoryPlaceholder')"
            clearable
          />
        </n-form-item>
        <n-form-item :label="t('promptManagement.formContent')">
          <n-input
            v-model:value="form.content"
            type="textarea"
            :placeholder="t('promptManagement.contentPlaceholder')"
            :rows="8"
            :maxlength="10000"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="pm-modal-footer">
          <n-button @click="showModal = false">{{ t("promptManagement.cancel") }}</n-button>
          <n-button
            type="primary"
            :loading="saving"
            :disabled="saving"
            @click="handleSave"
          >
            {{ t("promptManagement.save") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
/* ── 页面布局 ── */
.pm-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
}

/* ── 操作栏 ── */
.pm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  gap: 16px;
  flex-wrap: wrap;
}

.pm-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ── 搜索框 ── */
.pm-search-box {
  width: 280px;
}

.pm-search-icon {
  color: var(--platform-text-tertiary);
}

.pm-search-input {
  width: 100%;
}

/* ── 分类标签 ── */
.pm-categories {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex-shrink: 0;
}

.pm-cat-btn {
  border: 1px solid transparent;
  font-weight: 400;
  color: var(--platform-text-secondary);
}

.pm-cat-btn.pm-cat-btn--active {
  color: var(--platform-accent-pressed);
  font-weight: 600;
  background: var(--platform-accent-muted-strong);
  border-color: var(--platform-accent-border);
}

.pm-cat-btn.pm-cat-btn--active :deep(.n-button__content),
.pm-cat-btn.pm-cat-btn--active :deep(.n-icon) {
  color: inherit;
}

/* ── 主体 ── */
.pm-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.pm-spin {
  height: 100%;
}

/* ── 卡片网格 ── */
.pm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  padding-bottom: 24px;
}

.pm-card {
  background: var(--platform-card-bg, #fcfcfc);
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
}

.pm-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.pm-card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.pm-card-title {
  font-size: var(--platform-font-size-sm, 12px);
  font-weight: 500;
  margin: 0;
  color: var(--platform-text);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pm-card-preview {
  font-size: var(--platform-font-size-sm);
  line-height: 1.6;
  margin: 0;
  color: var(--platform-text-tertiary);
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.pm-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--platform-border-strong);
}

.pm-card-footer-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pm-card-time {
  font-size: var(--platform-font-size-sm, 12px);
  color: var(--platform-text-tertiary);
}

/* ── 弹窗 ── */
.pm-modal {
  border-radius: 12px;
}

.pm-form {
  margin-top: 4px;
}

.pm-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
