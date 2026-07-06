export const AGENT_SKILLS_TABS = new Set(["agents", "skills", "tools", "memory", "styles", "aip-keys"]);

export function resolveAgentSkillsTab(tab) {
  const name = String(tab || "");
  return AGENT_SKILLS_TABS.has(name) ? name : "agents";
}
