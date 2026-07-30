import {
  GitNetworkOutline,
  HardwareChipOutline,
  DocumentTextOutline,
  ExtensionPuzzleOutline,
  LeafOutline,
  FlashOutline,
  TrendingUpOutline,
  GlobeOutline,
  SparklesOutline,
} from "@vicons/ionicons5";
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

/** 内置智能体语义色 + 图标（与封面职责对齐） */
const AGENT_CARD_VISUAL_BY_ID = Object.freeze({
  orchestrator: Object.freeze({
    accent: "#005A9E",
    soft: "rgba(0, 90, 158, 0.14)",
    icon: GitNetworkOutline,
  }),
  platform: Object.freeze({
    accent: "#1A7FD4",
    soft: "rgba(26, 127, 212, 0.14)",
    icon: HardwareChipOutline,
  }),
  report: Object.freeze({
    accent: "#0B6E99",
    soft: "rgba(11, 110, 153, 0.14)",
    icon: DocumentTextOutline,
  }),
  "skill-dev": Object.freeze({
    accent: "#3D6B9E",
    soft: "rgba(61, 107, 158, 0.14)",
    icon: ExtensionPuzzleOutline,
  }),
  carbon: Object.freeze({
    accent: "#0D8A6A",
    soft: "rgba(13, 138, 106, 0.14)",
    icon: LeafOutline,
  }),
  "power-economy": Object.freeze({
    accent: "#C47A12",
    soft: "rgba(196, 122, 18, 0.14)",
    icon: FlashOutline,
  }),
  stock: Object.freeze({
    accent: "#2A7A5C",
    soft: "rgba(42, 122, 92, 0.14)",
    icon: TrendingUpOutline,
  }),
});

const DEFAULT_VISUAL = Object.freeze({
  accent: "var(--platform-accent)",
  soft: "var(--platform-accent-soft)",
  icon: SparklesOutline,
});

const EXTERNAL_VISUAL = Object.freeze({
  accent: "#5B7A94",
  soft: "rgba(91, 122, 148, 0.14)",
  icon: GlobeOutline,
});

function visualOf(agentId) {
  return AGENT_CARD_VISUAL_BY_ID[String(agentId || "").trim()] || DEFAULT_VISUAL;
}

/** 封面图 URL；无专属图时返回空字符串 */
export function agentCardCoverUrl(agentId) {
  const rel = AGENT_CARD_BG_BY_ID[String(agentId || "").trim()];
  return rel ? publicAsset(rel) : "";
}

export function hasAgentCardBg(agentId) {
  return Boolean(AGENT_CARD_BG_BY_ID[String(agentId || "").trim()]);
}

/** 卡片 CSS 变量：--card-accent / --card-accent-soft */
export function agentCardAccentStyle(agentId, { external = false } = {}) {
  const entry = external ? EXTERNAL_VISUAL : visualOf(agentId);
  return {
    "--card-accent": entry.accent,
    "--card-accent-soft": entry.soft,
  };
}

export function resolveAgentCardIcon(agentId, { external = false } = {}) {
  if (external) return EXTERNAL_VISUAL.icon;
  return visualOf(agentId).icon;
}

/** 工作流徽标：调度 / 专精 */
export function agentRoleLabel(agentId) {
  return String(agentId || "").trim() === "orchestrator" ? "调度" : "专精";
}

/** 工作流徽标 CSS 变量（与卡片语义色一致） */
export function agentBadgeStyle(agentId, { external = false } = {}) {
  return agentCardAccentStyle(agentId, { external });
}
