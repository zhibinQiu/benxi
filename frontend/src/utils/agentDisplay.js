import { publicAsset } from "./appBase.js";

/** 智能体展示名：标题后统一追加 Agent 后缀 */
export function formatAgentDisplayName(title) {
  const base = String(title || "").trim();
  if (!base) return "Agent";
  if (/\bAgent$/i.test(base)) return base;
  return `${base} Agent`;
}

/** 内置智能体卡片封面图（按职责语义一一对应，不复用） */
const AGENT_CARD_BG_BY_ID = {
  orchestrator: "images/agents/orchestrator.jpg",
  platform: "images/agents/platform.jpg",
  report: "images/agents/report.jpg",
  "skill-dev": "images/agents/skill-dev.jpg",
  carbon: "images/agents/carbon.jpg",
  "power-economy": "images/agents/power-economy.jpg",
  stock: "images/agents/stock.jpg",
};

/** 封面图 URL；无专属图时返回空字符串 */
export function agentCardCoverUrl(agentId) {
  const rel = AGENT_CARD_BG_BY_ID[String(agentId || "").trim()];
  return rel ? publicAsset(rel) : "";
}

export function hasAgentCardBg(agentId) {
  return Boolean(AGENT_CARD_BG_BY_ID[String(agentId || "").trim()]);
}
