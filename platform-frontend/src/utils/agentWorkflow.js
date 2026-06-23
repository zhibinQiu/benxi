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
  if (tool?.startsWith("skill.")) {
    const name = tool.slice("skill.".length);
    if (name && name !== "create" && name !== "update" && name !== "delete") {
      return `Skill: ${name}`;
    }
  }
  const fallback = {
    planner: "规划",
    evaluator: "评估",
    retrieve: "知识库检索",
    kg_context: "本体图谱",
    web_search: "联网检索",
    version_metadata: "版本元数据",
    llm: "语言模型",
    "agent.tools": "智能体工具",
    "agent.memory": "Agent 记忆",
    "agent.tool": "工具",
    "skill.create": "创建 Skill",
    "skill.update": "更新 Skill",
    "skill.delete": "删除 Skill",
    load_uploaded_skill: "加载技能",
    create_uploaded_skill: "创建技能",
    web_search: "联网搜索",
    knowledge_retrieve: "知识库检索",
    kg_query: "本体图谱查询",
    update_uploaded_skill_file: "更新 Skill 文件",
    delete_uploaded_skill: "删除 Skill",
    read_agent_memory: "读取记忆",
    append_agent_memory: "写入记忆",
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

function finishRunningSteps(steps, { failed = false, kinds = null } = {}) {
  for (const s of steps) {
    if (s.status === "running" && (!kinds || kinds.includes(s.kind))) {
      s.status = failed ? "failed" : "done";
    }
  }
}

function findStep(steps, id) {
  if (!id) return null;
  return steps.find((s) => s.id === id) || null;
}

/** Skill 脚本运行失败等可恢复错误：展示详情但不标红整个流程。 */
function isSoftToolFailure(ev, failed) {
  if (!failed) return false;
  const toolName = String(ev?.tool_name || "");
  const tool = String(ev?.tool || "");
  if (toolName === "run_skill_script") return true;
  if (tool.startsWith("skill.run.")) return true;
  return false;
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

  if (phase === "thinking_delta") {
    state.running = true;
    state.failed = false;
    state.currentTitle = ev.title || toolName || "思考中";
    const id = ev.step_id || state.steps[state.steps.length - 1]?.id || nextStepId();
    const existing = findStep(state.steps, id);
    upsertStep(state.steps, {
      id,
      kind: "thinking",
      tool,
      title: ev.title || existing?.title || (toolName ? `${toolName}思考中` : "思考中"),
      detail: `${existing?.detail || ""}${ev.delta || ""}`,
      status: "running",
    });
    return state;
  }

  if (phase === "agent_thinking") {
    state.running = true;
    state.failed = false;
    state.currentTitle = ev.title || "思考中";
    finishRunningSteps(state.steps, { kinds: ["node"] });
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

  if (phase === "agent_thought") {
    state.running = true;
    const id = ev.step_id || state.steps[state.steps.length - 1]?.id || nextStepId();
    const failed = ev.status === "failed";
    const existing = findStep(state.steps, id);
    const nextDetail = ev.detail || "";
    const keepDetail =
      existing?.detail && existing.detail.length > nextDetail.length
        ? existing.detail
        : nextDetail || existing?.detail || "";
    upsertStep(state.steps, {
      id,
      kind: "thinking",
      tool,
      title: ev.title || existing?.title || toolName || "完成",
      detail: keepDetail,
      status: failed ? "failed" : "done",
    });
    state.currentTitle = ev.title || state.currentTitle;
    state.failed = failed;
    return state;
  }

  if (phase === "tool_result") {
    state.running = true;
    const id = ev.step_id || state.steps[state.steps.length - 1]?.id || nextStepId();
    const failed = ev.status === "failed";
    const softFailure = isSoftToolFailure(ev, failed);
    const existing = findStep(state.steps, id);
    upsertStep(state.steps, {
      id,
      kind: "tool",
      tool,
      title: ev.title || existing?.title || toolName || "工具返回",
      callDetail: existing?.callDetail || "",
      resultDetail: ev.detail || "",
      status: softFailure ? "done" : failed ? "failed" : "done",
    });
    state.currentTitle = ev.title || state.currentTitle;
    if (!softFailure) {
      state.failed = failed;
    }
    return state;
  }

  if (phase === "tool_call") {
    state.running = true;
    state.failed = false;
    finishRunningSteps(state.steps, { kinds: ["node"] });
    const id = ev.step_id || nextStepId();
    const title = ev.title || toolName || "工具调用";
    state.currentTitle = title;
    upsertStep(state.steps, {
      id,
      kind: "tool",
      tool,
      title,
      callDetail: ev.detail || "",
      resultDetail: "",
      status: "running",
    });
    return state;
  }

  if (phase === "node_started") {
    state.running = true;
    finishRunningSteps(state.steps, { kinds: ["node"] });
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
    } else {
      finishRunningSteps(state.steps, { kinds: ["node"] });
    }
    return state;
  }

  if (phase === "workflow_finished") {
    state.running = false;
    state.failed = false;
    state.currentTitle = "";
    finishRunningSteps(state.steps);
    return state;
  }

  return state;
}
