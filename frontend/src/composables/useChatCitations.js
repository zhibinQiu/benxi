import { ref } from "vue";
import { alignCitationsWithContent, splitCitedCitations } from "../utils/reportCitations.js";
import { openExternal } from "../utils/openExternal.js";

/**
 * 引用预览弹窗、引用对齐/分组及点击处理。
 */
export function useChatCitations({ messages, router, props, hasAssistantAnswer, hasAssistantAnswerText }) {
  const citationPreviewShow = ref(false);
  const citationPreviewTarget = ref(null);
  const citationPreviewQuestion = ref("");
  const citationPanelOpen = ref([]);
  const thinkingPanelOpen = ref(false);

  function reportCitationGroups(message) {
    const aligned = alignCitationsWithContent(message?.content, message?.citations || []);
    return splitCitedCitations(aligned.content, aligned.citations);
  }

  function messageCitationView(message) {
    return alignCitationsWithContent(message?.content, message?.citations || []);
  }

  function reportQuestionForMessage(index) {
    for (let i = index - 1; i >= 0; i -= 1) {
      if (messages.value[i]?.role === "user") {
        return messages.value[i].content || "";
      }
    }
    return "";
  }

  function onReportCitationClick(index, message, messageIndex) {
    const groups = reportCitationGroups(message);
    const all = [...groups.local, ...groups.web];
    openCitationPreview(index, all, reportQuestionForMessage(messageIndex));
  }

  function citationCount(message) {
    return Array.isArray(message?.citations) ? message.citations.length : 0;
  }

  /** 文档检索引用：在数据来源区用卡片展示截图，不把图塞进最终回答。 */
  function citationShowsDocumentSource(cit) {
    if (!cit || cit.source === "web") return false;
    if (String(cit.image_id || "").trim()) return true;
    if (Array.isArray(cit.inline_images) && cit.inline_images.some((img) => img?.url)) {
      return true;
    }
    if (cit.preview_available === true) return true;
    return Boolean(cit.document_id || cit.chunk_id);
  }

  function shouldShowFinalPanels(entry) {
    if (!hasAssistantAnswer(entry.message)) return false;
    if (props.showReportTools) return false;
    return true;
  }

  function assistantConclusionContent(message) {
    if (!message) return "";
    if (props.linkifyCitations && hasAssistantAnswerText(message)) {
      return messageCitationView(message).content;
    }
    return message.content || "";
  }

  function openCitationPreview(citationOrIndex, citations = [], question = "") {
    let citation = citationOrIndex;
    if (typeof citationOrIndex === "number") {
      citation = (citations || []).find((c) => Number(c.index) === citationOrIndex);
    }
    if (!citation) return;
    if (citation.source === "kg" && citation.entity_id) {
      router.push({
        name: "ontology",
        query: { tab: "graph", focusEntityId: citation.entity_id },
      });
      return;
    }
    if (citation.source === "web" && citation.url) {
      openExternal(citation.url);
      return;
    }
    citationPreviewQuestion.value = question || "";
    citationPreviewTarget.value = citation;
    citationPreviewShow.value = true;
  }

  function closeCitationPreview() {
    citationPreviewShow.value = false;
  }

  return {
    citationPreviewShow,
    citationPreviewTarget,
    citationPreviewQuestion,
    citationPanelOpen,
    thinkingPanelOpen,
    reportCitationGroups,
    messageCitationView,
    reportQuestionForMessage,
    onReportCitationClick,
    citationCount,
    citationShowsDocumentSource,
    shouldShowFinalPanels,
    assistantConclusionContent,
    openCitationPreview,
    closeCitationPreview,
  };
}
