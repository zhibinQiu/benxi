<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
import { computed, onMounted, reactive, ref } from "vue";
import {
  NButton,
  NCard,
  NCheckbox,
  NDivider,
  NSpace,
  NSpin,
  NText,
} from "naive-ui";
import { fetchMenuSettings, updateMenuSettings } from "../../api/menuSettings.js";

const ui = usePlatformUi();
const loading = ref(false);
const saving = ref(false);
const items = ref([]);
const visibility = reactive({});

const mainItems = computed(() => items.value.filter((item) => item.group === "main"));
const settingsItems = computed(() =>
  items.value.filter((item) => item.group === "settings")
);

async function load() {
  loading.value = true;
  try {
    const data = await fetchMenuSettings();
    items.value = data?.items || [];
    for (const item of items.value) {
      visibility[item.key] = Boolean(data?.member_visible?.[item.key]);
    }
  } catch (e) {
    ui.error(e.message || "加载菜单配置失败");
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  try {
    const member_visible = Object.fromEntries(
      items.value.map((item) => [item.key, Boolean(visibility[item.key])])
    );
    await updateMenuSettings({ member_visible });
    ui.success("菜单配置已保存");
  } catch (e) {
    ui.error(e.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="menu-settings-page feature-page">
    <n-spin :show="loading">
      <n-card title="普通用户可见菜单" size="small">
        <n-text depth="3" class="page-hint">
          勾选后，普通成员登录时可在侧栏看到对应菜单；系统管理员始终可见全部菜单。
        </n-text>

        <section class="menu-group">
          <h3 class="menu-group__title">主导航</h3>
          <n-space vertical :size="10">
            <label
              v-for="item in mainItems"
              :key="item.key"
              class="menu-option"
            >
              <n-checkbox v-model:checked="visibility[item.key]" />
              <span class="menu-option__text">
                <strong>{{ item.label }}</strong>
                <n-text depth="3">{{ item.description }}</n-text>
              </span>
            </label>
          </n-space>
        </section>

        <n-divider />

        <section class="menu-group">
          <h3 class="menu-group__title">系统设置</h3>
          <n-space vertical :size="10">
            <label
              v-for="item in settingsItems"
              :key="item.key"
              class="menu-option"
            >
              <n-checkbox v-model:checked="visibility[item.key]" />
              <span class="menu-option__text">
                <strong>{{ item.label }}</strong>
                <n-text depth="3">{{ item.description }}</n-text>
              </span>
            </label>
          </n-space>
        </section>

        <template #action>
          <n-space>
            <n-button type="primary" :loading="saving" @click="save">保存</n-button>
            <n-button :disabled="saving || loading" @click="load">重新加载</n-button>
          </n-space>
        </template>
      </n-card>
    </n-spin>
  </div>
</template>

<style scoped>
.menu-settings-page {
  max-width: 720px;
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

.menu-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
}

.menu-option__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
</style>
