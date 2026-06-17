/** Agent workflow SSE 事件 → 可展示步骤时间线 */

let _stepSeq = 0;

function nextStepId() {
  _stepSeq += 1;
  return `agent-step-${_stepSeq}`;
}

export function emptyAgentWorkflow() {
  return {
    running: false,
    failed: false,
    currentTitle: "",
    steps: [],
  };
}

function toolLabel(tool, t) {
  const key = tool ? `agentWorkflow.tools.${tool}` : "";
  if (key && t) {
    const label = t(key);
    if (label && label !== key) return label;
  }
  const fallback = {
    planner: "规划",
    evaluator: "评估",
    retrieve: "知识库检索",
    kg_context: "知识图谱",
    web_search: "联网检索",
    version_metadata: "版本元数据",
  };
  return fallback[tool] || "";
}

function upsertStep(steps, step) {
  const idx = steps.findIndex((s) => s.id === step.id);
  if (idx >= 0) {
    steps[idx] = { ...steps[idx], ...step };
    return;
  }
  steps.push(step);
}

function finishRunningSteps(steps, { failed = false } = {}) {
  for (const s of steps) {
    if (s.status === "running") {
      s.status = failed ? "failed" : "done";
    }
  }
}

/**
 * @param {ReturnType<typeof emptyAgentWorkflow>} state
 * @param {object} ev
 * @param {(key: string) => string} [t]
 */
export function applyAgentWorkflowEvent(state, ev, t) {
  if (!state) return emptyAgentWorkflow();
  const phase = ev?.phase;
  const tool = ev?.tool || "";
  const toolName = toolLabel(tool, t);

  if (phase === "workflow_started") {
    state.running = true;
    state.failed = false;
    state.currentTitle = ev.title || "Agent 开始";
    state.steps = [];
    return state;
  }

  if (phase === "agent_thinking") {
    state.running = true;
    state.failed = false;
    state.currentTitle = ev.title || "思考中";
    const id = ev.step_id || nextStepId();
    upsertStep(state.steps, {
      id,
      kind: "thinking",
      tool,
      title: ev.title || (toolName ? `${toolName}…` : "思考中"),
      detail: ev.detail || "",
      status: "running",
    });
    return state;
  }

  if (phase === "agent_thought" || phase === "tool_result") {
    state.running = true;
    const id = ev.step_id || state.steps[state.steps.length - 1]?.id || nextStepId();
    const failed = ev.status === "failed";
    upsertStep(state.steps, {
      id,
      kind: phase === "agent_thought" ? "thinking" : "tool",
      tool,
      title: ev.title || toolName || "完成",
      detail: ev.detail || "",
      status: failed ? "failed" : "done",
    });
    state.currentTitle = ev.title || state.currentTitle;
    state.failed = state.failed || failed;
    return state;
  }

  if (phase === "tool_call") {
    state.running = true;
    state.failed = false;
    const id = ev.step_id || nextStepId();
    const title = ev.title || toolName || "工具调用";
    state.currentTitle = title;
    upsertStep(state.steps, {
      id,
      kind: "tool",
      tool,
      title,
      detail: ev.detail || "",
      status: "running",
    });
    return state;
  }

  if (phase === "node_started") {
    state.running = true;
    state.currentTitle = ev.title || "处理中";
    if (ev.title) {
      upsertStep(state.steps, {
        id: ev.step_id || nextStepId(),
        kind: "node",
        tool,
        title: ev.title,
        detail: ev.detail || "",
        status: "running",
      });
    }
    return state;
  }

  if (phase === "node_finished") {
    const failed = ev.status === "failed" || ev.status === "exception";
    if (failed) {
      state.failed = true;
      state.currentTitle = `${ev.title || "节点"}（失败）`;
      finishRunningSteps(state.steps, { failed: true });
    }
    return state;
  }

  if (phase === "workflow_finished") {
    state.running = false;
    state.currentTitle = "";
    finishRunningSteps(state.steps);
    return state;
  }

  return state;
}
