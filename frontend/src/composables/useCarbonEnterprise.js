import { ref, computed } from "vue";
import {
  listEnterprises,
  createEnterprise,
  updateEnterprise,
  deleteEnterprise,
  fetchComplianceMeta,
} from "../api/carbonCompliance";

/** 模块级缓存：离开页面再进入时复用，避免重复拉取 */
const enterprises = ref([]);
const selectedId = ref("");
const meta = ref({ industries: [], risk_profiles: [] });
const loading = ref(false);
let metaLoaded = false;
let enterprisesLoaded = false;

/** 设置缓存（跨组件实例复用，避免重复拉取） */
export const carbonPageCache = {
  settings: null,
};

export function clearCarbonEnterpriseCache() {
  enterprises.value = [];
  selectedId.value = "";
  meta.value = { industries: [], risk_profiles: [] };
  loading.value = false;
  metaLoaded = false;
  enterprisesLoaded = false;
  carbonPageCache.settings = null;
}

export function useCarbonEnterprise() {
  const selected = computed(() =>
    enterprises.value.find((e) => e.id === selectedId.value) || null
  );

  async function loadMeta({ force = false } = {}) {
    if (metaLoaded && !force) return;
    meta.value = (await fetchComplianceMeta()) || { industries: [], risk_profiles: [] };
    metaLoaded = true;
  }

  async function loadEnterprises({ force = false } = {}) {
    if (enterprisesLoaded && !force) return;
    loading.value = true;
    try {
      const rows = await listEnterprises();
      enterprises.value = Array.isArray(rows) ? rows : [];
      if (!selectedId.value && enterprises.value.length) {
        selectedId.value = enterprises.value[0].id;
      }
      if (
        selectedId.value &&
        !enterprises.value.some((e) => e.id === selectedId.value)
      ) {
        selectedId.value = enterprises.value[0]?.id || "";
      }
      enterprisesLoaded = true;
    } finally {
      loading.value = false;
    }
  }

  async function saveEnterprise(form, editingId) {
    if (editingId) {
      await updateEnterprise(editingId, form);
    } else {
      const created = await createEnterprise(form);
      selectedId.value = created?.id || selectedId.value;
    }
    enterprisesLoaded = false;
    await loadEnterprises({ force: true });
  }

  async function removeEnterprise(id) {
    await deleteEnterprise(id);
    if (selectedId.value === id) selectedId.value = "";
    enterprisesLoaded = false;
    await loadEnterprises({ force: true });
  }

  return {
    enterprises,
    selectedId,
    selected,
    meta,
    loading,
    loadMeta,
    loadEnterprises,
    saveEnterprise,
    removeEnterprise,
  };
}
