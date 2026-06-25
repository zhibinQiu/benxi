/** 智能体展示名：标题后统一追加 Agent 后缀 */
export function formatAgentDisplayName(title) {
  const base = String(title || "").trim();
  if (!base) return "Agent";
  if (/\bAgent$/i.test(base)) return base;
  return `${base} Agent`;
}
