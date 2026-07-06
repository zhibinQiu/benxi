export function normalizeBuiltinAgent(agent) {
  if (!agent) return agent;
  return {
    ...agent,
    service_enabled:
      agent.service_enabled === undefined || agent.service_enabled === null
        ? agent.enabled !== false
        : Boolean(agent.service_enabled),
  };
}

export function mergeBuiltinAgent(existing, updated) {
  return normalizeBuiltinAgent({ ...existing, ...updated });
}

export function isBuiltinSkill(row) {
  return row?.kind === "builtin" || row?.source === "builtin";
}
