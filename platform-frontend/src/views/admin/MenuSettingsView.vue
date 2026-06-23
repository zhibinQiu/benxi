<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { computed, onMounted, reactive, ref } from "vue";
import {
  NButton,
  NCard,
  NDivider,
  NSelect,
  NSpace,
  NSpin,
  NText,
} from "naive-ui";
import { fetchMenuSettings, updateMenuSettings } from "../../api/menuSettings.js";
import { useMenuSettings } from "../../composables/useMenuSettings.js";
import ListRefreshButton from "../../components/ListRefreshButton.vue";

const ui = usePlatformUi();
const { t } = useI18n();
const { loadMenuSettings } = useMenuSettings();
const loading = ref(false);
const saving = ref(false);
const items = ref([]);
const visibility = reactive({});

const visibilityOptions = computed(() => [
  { value: "all", label: t("admin.menuSettings.visibility.all") },
  { value: "admin", label: t("admin.menuSettings.visibility.admin") },
  { value: "hidden", label: t("admin.menuSettings.visibility.hidden") },
]);

const mainItems = computed(() => items.value.filter((item) => item.group === "main"));
const settingsItems = computed(() =>
  items.value.filter((item) => item.group === "settings")
);

function resolveItemVisibility(data, key) {
  const level = data?.menu_visibility?.[key];
  if (level === "all" || level === "admin" || level === "hidden") return level;
  const legacy = data?.member_visible?.[key];
  if (legacy === true) return "all";
  if (legacy === false) return "admin";
  return "all";
}

function applySettings(data) {
  items.value = data?.items || [];
  for (const item of items.value) {
    visibility[item.key] = resolveItemVisibility(data, item.key);
  }
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchMenuSettings();
    applySettings(data);
  } catch (e) {
    ui.error(e.message || t("admin.menuSettings.loadFailed"));
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  try {
    const menu_visibility = Object.fromEntries(
      items.value.map((item) => [item.key, visibility[item.key] || "all"])
    );
    const member_visible = Object.fromEntries(
      items.value.map((item) => [
        item.key,
        (visibility[item.key] || "all") === "all",
      ])
    );
    const data = await updateMenuSettings({ menu_visibility, member_visible });
    applySettings(data);
    await loadMenuSettings(true);
    ui.success(t("admin.menuSettings.saved"));
  } catch (e) {
    ui.error(e.message || t("admin.menuSettings.saveFailed"));
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="menu-settings-page feature-page">
    <n-spin :show="loading">
      <n-card :title="t('admin.menuSettings.title')" size="small">
        <template #header-extra>
          <ListRefreshButton :loading="loading" @click="load" />
        </template>
        <n-text depth="3" class="page-hint">
          {{ t("admin.menuSettings.hint") }}
        </n-text>

        <section class="menu-group">
          <h3 class="menu-group__title">{{ t("admin.menuSettings.mainNav") }}</h3>
          <div class="menu-table">
            <div
              v-for="item in mainItems"
              :key="item.key"
              class="menu-row"
            >
              <div class="menu-row__info">
                <strong>{{ item.label }}</strong>
                <n-text depth="3">{{ item.description }}</n-text>
              </div>
              <n-select
                v-model:value="visibility[item.key]"
                class="menu-row__select"
                :options="visibilityOptions"
                size="small"
              />
            </div>
          </div>
        </section>

        <n-divider />

        <section class="menu-group">
          <h3 class="menu-group__title">{{ t("admin.menuSettings.systemSettings") }}</h3>
          <div class="menu-table">
            <div
              v-for="item in settingsItems"
              :key="item.key"
              class="menu-row"
            >
              <div class="menu-row__info">
                <strong>{{ item.label }}</strong>
                <n-text depth="3">{{ item.description }}</n-text>
              </div>
              <n-select
                v-model:value="visibility[item.key]"
                class="menu-row__select"
                :options="visibilityOptions"
                size="small"
              />
            </div>
          </div>
        </section>

        <template #action>
          <n-space>
            <n-button type="primary" :loading="saving" @click="save">
              {{ t("common.save") }}
            </n-button>
            <n-button :disabled="saving || loading" @click="load">
              {{ t("admin.menuSettings.reload") }}
            </n-button>
          </n-space>
        </template>
      </n-card>
    </n-spin>
  </div>
</template>

<style scoped>
.menu-settings-page {
  max-width: 820px;
}

.page-hint {
  display: block;
  margin-bottom: 16px;
  line-height: 1.6;
}

.menu-group__title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
}

.menu-table {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.menu-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--platform-surface-muted, rgba(0, 0, 0, 0.02));
}

.menu-row__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.menu-row__select {
  width: 168px;
  flex-shrink: 0;
}
</style>
