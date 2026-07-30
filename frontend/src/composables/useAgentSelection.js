import { computed, nextTick, ref } from "vue";
import { fetchAiChatSkillCatalog } from "../api/chat.js";
import { useChatCatalogCache } from "./useChatCatalogCache.js";
import { formatAgentDisplayName } from "../utils/agentDisplay.js";

/**
 * Agent / Skill / 模型选择弹层及报告 Skill 预设注入。
 */
export function useAgentSelection({ input, composerRef, ui, t }) {
  const agentPopoverShow = ref(false);
  const skillCatalog = ref([]);
  const skillCatalogLoading = ref(false);
  const skillPopoverShow = ref(false);
  const skillCatalogLoaded = ref(false);
  const modelPopoverShow = ref(false);
  const reportSkillPopoverShow = ref(false);
  const reportOptimizePopoverShow = ref(false);

  const {
    agentCatalog,
    agentCatalogLoading,
    agentCatalogLoaded,
    loadAgentCatalog: loadSharedAgentCatalog,
    modelOptions,
    modelSettingsLoading,
    modelOptionsLoaded,
    selectedModelProviderId,
    loadModelOptions,
    selectModel: selectSharedModel,
  } = useChatCatalogCache();

  async function loadAgentCatalog() {
    try {
      await loadSharedAgentCatalog();
    } catch (e) {
      ui.error(e.message || t("chat.agentSkills.loadFailed"));
    }
  }

  const currentModelLabel = computed(() => {
    for (const g of modelOptions.value) {
      const found = g.children?.find((c) => c.value === selectedModelProviderId.value);
      if (found) return found.label;
    }
    return "切换模型";
  });

  function selectModel(opt) {
    selectSharedModel(opt);
    modelPopoverShow.value = false;
  }

  async function onModelPopoverShowChange(show) {
    modelPopoverShow.value = show;
  }

  async function onAgentPopoverShowChange(show) {
    agentPopoverShow.value = show;
    if (show && !agentCatalogLoaded.value) {
      await loadAgentCatalog();
    }
  }

  function useAgent(agent) {
    const label = formatAgentDisplayName(agent.title);
    input.value = `请让 ${label}：`;
    agentPopoverShow.value = false;
    nextTick(() => composerRef.value?.focus?.());
  }

  async function loadSkillCatalog() {
    if (skillCatalogLoading.value) return;
    skillCatalogLoading.value = true;
    try {
      skillCatalog.value = (await fetchAiChatSkillCatalog()) || [];
      skillCatalogLoaded.value = true;
    } catch (e) {
      ui.error(e.message || t("chat.agentSkills.skillLoadFailed"));
    } finally {
      skillCatalogLoading.value = false;
    }
  }

  async function onSkillPopoverShowChange(show) {
    skillPopoverShow.value = show;
    if (show && !skillCatalogLoaded.value) {
      await loadSkillCatalog();
    }
  }

  function useSkill(skill) {
    // 注入稳定 skill name（slug），便于后端硬解析；无 name 时回退 title
    const label = (skill.name || skill.title || "").trim();
    if (!label) return;
    input.value = `请使用 ${label} 技能：`;
    skillPopoverShow.value = false;
    nextTick(() => composerRef.value?.focus?.());
  }

  function useReportOptimizePreset(preset) {
    const prompt = (preset?.prompt || preset?.description || preset?.label || "").trim();
    if (!prompt) return;
    input.value = prompt;
    reportOptimizePopoverShow.value = false;
    nextTick(() => composerRef.value?.focus?.());
  }

  function useReportAgentSkill(skill) {
    const prompt = String(skill?.sample_prompt || skill?.samplePrompt || "").trim();
    if (!prompt) return;
    input.value = prompt;
    reportSkillPopoverShow.value = false;
    nextTick(() => composerRef.value?.focus?.());
  }

  function closeSelectionPopovers() {
    agentPopoverShow.value = false;
    skillPopoverShow.value = false;
    reportSkillPopoverShow.value = false;
    reportOptimizePopoverShow.value = false;
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
    agentPopoverShow,
    skillCatalog,
    skillCatalogLoading,
    skillPopoverShow,
    skillCatalogLoaded,
    modelPopoverShow,
    reportSkillPopoverShow,
    reportOptimizePopoverShow,
    currentModelLabel,
    selectModel,
    onModelPopoverShowChange,
    onAgentPopoverShowChange,
    useAgent,
    loadSkillCatalog,
    onSkillPopoverShowChange,
    useSkill,
    useReportOptimizePreset,
    useReportAgentSkill,
    closeSelectionPopovers,
  };
}
