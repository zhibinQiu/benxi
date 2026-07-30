import { ref } from "vue";
import { fetchAiChatAgentCatalog, fetchAiChatModelProviders } from "../api/chat.js";

const MODEL_CACHE_KEY = "ai_chat_model_options";
const MODEL_CACHE_TS_KEY = "ai_chat_model_options_ts";
const MODEL_SELECTED_KEY = "ai_chat_model_provider_id";
const MODEL_CACHE_TTL_MS = 5 * 60 * 1000;

const agentCatalog = ref([]);
const agentCatalogLoading = ref(false);
const agentCatalogLoaded = ref(false);
let agentCatalogPromise = null;

const modelOptions = ref([]);
const modelSettingsLoading = ref(false);
const modelOptionsLoaded = ref(false);
const selectedModelProviderId = ref(localStorage.getItem(MODEL_SELECTED_KEY) || "");
let modelOptionsPromise = null;

function loadModelCache() {
  const raw = localStorage.getItem(MODEL_CACHE_KEY);
  const ts = Number(localStorage.getItem(MODEL_CACHE_TS_KEY) || "0");
  if (raw && Date.now() - ts < MODEL_CACHE_TTL_MS) {
    try {
      return JSON.parse(raw);
    } catch {
      /* ignore */
    }
  }
  return null;
}

function saveModelCache(groups) {
  localStorage.setItem(MODEL_CACHE_KEY, JSON.stringify(groups));
  localStorage.setItem(MODEL_CACHE_TS_KEY, String(Date.now()));
}

function buildGroups(items) {
  const groups = [];
  let llmGroup = null;
  let mmGroup = null;

  for (const item of items || []) {
    const label = item.model_name || item.label || "模型";
    const entry = { label, value: item.id };
    if (item.description) entry.desc = item.description;
    if (item.resource_type === "multimodal") {
      if (!mmGroup) {
        mmGroup = { type: "group", label: "多模态模型", key: "multimodal", children: [] };
        groups.push(mmGroup);
      }
      mmGroup.children.push(entry);
    } else {
      if (!llmGroup) {
        llmGroup = { type: "group", label: "语言模型", key: "llm", children: [] };
        groups.push(llmGroup);
      }
      llmGroup.children.push(entry);
    }
  }
  return groups;
}

function ensureSelectedValid() {
  if (!selectedModelProviderId.value) {
    const first = modelOptions.value?.[0]?.children?.[0];
    if (first) {
      selectedModelProviderId.value = first.value;
      localStorage.setItem(MODEL_SELECTED_KEY, first.value);
    }
    return;
  }
  const allValues = new Set();
  for (const g of modelOptions.value) {
    for (const c of g.children || []) {
      allValues.add(c.value);
    }
  }
  if (!allValues.has(selectedModelProviderId.value)) {
    const first = modelOptions.value?.[0]?.children?.[0];
    selectedModelProviderId.value = first?.value || "";
  }
}

async function doFetchModelOptions() {
  const items = await fetchAiChatModelProviders();
  const groups = buildGroups(items);
  modelOptions.value = groups;
  if (groups.length) {
    saveModelCache(groups);
  }
  ensureSelectedValid();
  modelOptionsLoaded.value = true;
}

async function refreshModelOptionsSilently() {
  try {
    const items = await fetchAiChatModelProviders();
    const groups = buildGroups(items);
    if (groups.length) {
      modelOptions.value = groups;
      saveModelCache(groups);
    }
    ensureSelectedValid();
  } catch {
    /* keep cache */
  }
}

/**
 * 跨 AiChatPanel 实例共享的 agent catalog / model options 单例缓存。
 */
export function useChatCatalogCache() {
  async function loadAgentCatalog(force = false) {
    if (agentCatalogLoaded.value && !force) return agentCatalog.value;
    if (agentCatalogPromise && !force) return agentCatalogPromise;

    agentCatalogLoading.value = true;
    agentCatalogPromise = (async () => {
      try {
        agentCatalog.value = (await fetchAiChatAgentCatalog()) || [];
        agentCatalogLoaded.value = true;
        return agentCatalog.value;
      } finally {
        agentCatalogLoading.value = false;
        agentCatalogPromise = null;
      }
    })();
    return agentCatalogPromise;
  }

  async function loadModelOptions(force = false) {
    if (modelOptionsLoaded.value && !force && modelOptions.value.length) {
      return modelOptions.value;
    }
    if (modelOptionsPromise && !force) return modelOptionsPromise;

    const cached = loadModelCache();
    if (cached && !force) {
      modelOptions.value = cached;
      modelOptionsLoaded.value = true;
      ensureSelectedValid();
      refreshModelOptionsSilently();
      return modelOptions.value;
    }

    modelSettingsLoading.value = true;
    modelOptionsPromise = (async () => {
      try {
        await doFetchModelOptions();
        return modelOptions.value;
      } finally {
        modelSettingsLoading.value = false;
        modelOptionsPromise = null;
      }
    })();
    return modelOptionsPromise;
  }

  function selectModel(opt) {
    selectedModelProviderId.value = opt.value;
    localStorage.setItem(MODEL_SELECTED_KEY, opt.value);
  }

  return {
    agentCatalog,
    agentCatalogLoading,
    agentCatalogLoaded,
    loadAgentCatalog,
    modelOptions,
    modelSettingsLoading,
    modelOptionsLoaded,
    selectedModelProviderId,
    loadModelOptions,
    selectModel,
  };
}
