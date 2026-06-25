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
    currentAgentTitle: "",
    currentAgentId: "",
    steps: [],
    taskPlan: [],
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
    "supervisor.route": "智能体路由",
    "supervisor.parallel": "并行调度",
    "supervisor.synthesize": "结果汇总",
    "supervisor.plan": "任务规划",
    "supervisor.task": "子任务",
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

/** 不向用户展示的内部 workflow 文案（轮次上限、规划摘要等）。 */
const HIDDEN_WORKFLOW_DETAIL_RES = [
  /最多\s*\d+\s*轮/,
  /^第\s*\d+\s*轮\s*[·]/,
  /按计划调用工具/,
  /命中问题缓存/,
  /直接回答，不调用工具/,
  /原子工具[：:]/,
  /推理完成，开始输出/,
  /^开始输出回答$/,
  /模型未返回正文/,
  /内置编排/,
  /发展技能\s*load/i,
  /检索子问题[：:]/,
  /建议补充检索[：:]/,
  /已召回\s*\d+\s*段/,
  /本地\s*\d+\s*段\s*[··]\s*联网/,
  /材料充足，可以/,
  /分析材料并生成回答/,
  /分析意图并拆解/,
  /拆解检索子问题/,
];

export function sanitizeWorkflowDisplayText(text) {
  const value = String(text || "").trim();
  if (!value) return "";
  if (HIDDEN_WORKFLOW_DETAIL_RES.some((re) => re.test(value))) return "";
  return value;
}

function setCurrentTitle(state, title, fallback = "") {
  const safe = sanitizeWorkflowDisplayText(title || fallback);
  if (safe) state.currentTitle = safe;
}

function applyAgentMeta(state, ev) {
  if (ev?.agent_title) state.currentAgentTitle = ev.agent_title;
  if (ev?.agent_id) state.currentAgentId = ev.agent_id;
}

function agentKey(agentId) {
  return agentId || "__default__";
}

/** 同一智能体只保留最新一步，避免工具调用反复堆叠。 */
function removePriorStepsForAgent(steps, agentId, keepId) {
  const key = agentKey(agentId);
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const step = steps[i];
    if (step.id === keepId) continue;
    if (agentKey(step.agentId) === key) {
      steps.splice(i, 1);
    }
  }
}

function upsertStep(steps, step, { replaceSameAgent = false } = {}) {
  const normalized = {
    ...step,
    detail: sanitizeWorkflowDisplayText(step.detail),
    callDetail: sanitizeWorkflowDisplayText(step.callDetail),
    resultDetail: sanitizeWorkflowDisplayText(step.resultDetail),
  };
  const idx = steps.findIndex((s) => s.id === normalized.id);
  if (idx >= 0) {
    steps[idx] = { ...steps[idx], ...normalized };
    return;
  }
  if (replaceSameAgent) {
    removePriorStepsForAgent(steps, normalized.agentId, normalized.id);
  }
  steps.push(normalized);
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

function normalizeTaskPlanItem(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = String(raw.id || "").trim();
  if (!id) return null;
  return {
    id,
    title: String(raw.title || raw.agent_id || id).trim(),
    agentId: String(raw.agent_id || "").trim(),
    status: raw.status || "pending",
    summary: sanitizeWorkflowDisplayText(raw.summary) || "",
  };
}

function applyTaskPlan(state, tasks) {
  if (!Array.isArray(tasks)) return;
  state.taskPlan = tasks.map(normalizeTaskPlanItem).filter(Boolean);
}

function upsertTaskPlanItem(state, taskId, patch = {}) {
  const id = String(taskId || "").trim();
  if (!id) return;
  let item = state.taskPlan.find((t) => t.id === id);
  if (!item) {
    item = { id, title: id, agentId: "", status: "pending", summary: "" };
    state.taskPlan.push(item);
  }
  if (patch.status) item.status = patch.status;
  if (patch.summary !== undefined) item.summary = sanitizeWorkflowDisplayText(patch.summary) || "";
  if (patch.title) item.title = String(patch.title).trim();
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
  applyAgentMeta(state, ev);

  if (phase === "workflow_started") {
    state.running = true;
    state.failed = false;
    state.currentTitle = ev.title || "Agent 开始";
    state.currentAgentTitle = "";
    state.currentAgentId = "";
    state.steps = [];
    state.taskPlan = [];
    return state;
  }

  if (phase === "plan_tasks") {
    state.running = true;
    state.failed = false;
    applyTaskPlan(state, ev.tasks);
    setCurrentTitle(state, ev.title || "任务规划");
    return state;
  }

  if (phase === "task_started") {
    state.running = true;
    applyTaskPlan(state, ev.tasks);
    upsertTaskPlanItem(state, ev.task_id, { status: "running" });
    setCurrentTitle(state, ev.title || "执行中");
    return state;
  }

  if (phase === "task_retry") {
    state.running = true;
    applyTaskPlan(state, ev.tasks);
    upsertTaskPlanItem(state, ev.task_id, { status: "running" });
    setCurrentTitle(state, `重试：${ev.title || ""}`);
    return state;
  }

  if (phase === "task_done") {
    state.running = true;
    applyTaskPlan(state, ev.tasks);
    upsertTaskPlanItem(state, ev.task_id, {
      status: "done",
      summary: sanitizeWorkflowDisplayText(ev.detail) || "",
    });
    const hasRunningTask = state.taskPlan.some((t) => t.status === "running");
    if (!hasRunningTask) state.currentTitle = "";
    return state;
  }

  if (phase === "task_failed") {
    state.running = true;
    state.failed = true;
    applyTaskPlan(state, ev.tasks);
    upsertTaskPlanItem(state, ev.task_id, {
      status: "failed",
      summary: sanitizeWorkflowDisplayText(ev.detail) || "",
    });
    return state;
  }

  if (phase === "thinking_delta") {
    state.running = true;
    state.failed = false;
    setCurrentTitle(state, ev.title || toolName, "思考中");
    const id = ev.step_id || state.steps[state.steps.length - 1]?.id || nextStepId();
    const existing = findStep(state.steps, id);
    upsertStep(
      state.steps,
      {
        id,
        kind: "thinking",
        tool,
        title: ev.title || existing?.title || (toolName ? `${toolName}思考中` : "思考中"),
        detail: `${existing?.detail || ""}${ev.delta || ""}`,
        status: "running",
        agentTitle: ev.agent_title || existing?.agentTitle || state.currentAgentTitle,
        agentId: ev.agent_id || existing?.agentId || state.currentAgentId,
      },
      { replaceSameAgent: !existing }
    );
    return state;
  }

  if (phase === "agent_thinking") {
    state.running = true;
    state.failed = false;
    setCurrentTitle(state, ev.title, "思考中");
    finishRunningSteps(state.steps, { kinds: ["node"] });
    const id = ev.step_id || nextStepId();
    upsertStep(
      state.steps,
      {
        id,
        kind: "thinking",
        tool,
        title: ev.title || (toolName ? `${toolName}…` : "思考中"),
        detail: ev.detail || "",
        status: "running",
        agentTitle: ev.agent_title || state.currentAgentTitle,
        agentId: ev.agent_id || state.currentAgentId,
      },
      { replaceSameAgent: true }
    );
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
      agentTitle: ev.agent_title || existing?.agentTitle || state.currentAgentTitle,
      agentId: ev.agent_id || existing?.agentId || state.currentAgentId,
    });
    if (failed) {
      setCurrentTitle(state, ev.title, state.currentTitle);
    } else {
      const hasRunning = state.steps.some((s) => s.status === "running");
      state.currentTitle = hasRunning ? state.currentTitle : "";
    }
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
      agentTitle: ev.agent_title || existing?.agentTitle || state.currentAgentTitle,
      agentId: ev.agent_id || existing?.agentId || state.currentAgentId,
    });
    setCurrentTitle(state, ev.title, state.currentTitle);
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
    setCurrentTitle(state, title);
    upsertStep(
      state.steps,
      {
        id,
        kind: "tool",
        tool,
        title,
        callDetail: ev.detail || "",
        resultDetail: "",
        status: "running",
        agentTitle: ev.agent_title || state.currentAgentTitle,
        agentId: ev.agent_id || state.currentAgentId,
      },
      { replaceSameAgent: true }
    );
    return state;
  }

  if (phase === "node_started") {
    state.running = true;
    finishRunningSteps(state.steps, { kinds: ["node"] });
    setCurrentTitle(state, ev.title, "处理中");
    if (ev.title) {
      const id = ev.step_id || nextStepId();
      upsertStep(
        state.steps,
        {
          id,
          kind: "node",
          tool,
          title: ev.title,
          detail: ev.detail || "",
          status: "running",
          agentTitle: ev.agent_title || state.currentAgentTitle,
          agentId: ev.agent_id || state.currentAgentId,
        },
        { replaceSameAgent: true }
      );
    }
    return state;
  }

  if (phase === "node_finished") {
    const failed = ev.status === "failed" || ev.status === "exception";
    if (failed) {
      state.failed = true;
      setCurrentTitle(state, `${ev.title || "节点"}（失败）`);
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
    state.currentAgentTitle = "";
    state.currentAgentId = "";
    finishRunningSteps(state.steps);
    return state;
  }

  return state;
}
