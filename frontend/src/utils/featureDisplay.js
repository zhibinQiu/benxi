import { publicAsset } from "./appBase.js";

/** 功能卡片左侧配图（按功能语义一一对应，不复用） */
const FEATURE_CARD_IMG_BY_ID = {
  pdf_translate: "images/features/pdf_translate.jpg",
  speech_to_text: "images/features/speech_to_text.jpg",
  text_to_speech: "images/features/text_to_speech.jpg",
  report_generation: "images/features/report_generation.jpg",
  ocr: "images/features/ocr.jpg",
  ontology: "images/features/ontology.jpg",
  kg: "images/features/kg.jpg",
  doc_compare: "images/features/doc_compare.jpg",
  knowledge_search: "images/features/knowledge_search.jpg",
  ai_tools: "images/features/ai_tools.jpg",
  notes: "images/features/notes.jpg",
  subscriptions: "images/features/subscriptions.jpg",
  carbon_assistant: "images/features/carbon_assistant.jpg",
  smart_data_query: "images/features/smart_data_query.jpg",
  data_analysis: "images/features/data_analysis.jpg",
  carbon_qa: "images/features/carbon_qa.jpg",
  smart_forecast: "images/features/smart_forecast.jpg",
  todos: "images/features/todos.jpg",
  finance_assistant: "images/features/finance_assistant.jpg",
  prompt_management: "images/features/prompt_management.jpg",
  carbon_ai_v1: "images/features/carbon_ai_v1.jpg",
};

/** 功能卡片配图 URL；无专属图时返回空字符串 */
export function featureCardImageUrl(featureId) {
  const rel = FEATURE_CARD_IMG_BY_ID[String(featureId || "").trim()];
  return rel ? publicAsset(rel) : "";
}

export function hasFeatureCardImage(featureId) {
  return Boolean(FEATURE_CARD_IMG_BY_ID[String(featureId || "").trim()]);
}
