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
    executionMode: "",
    steps: [],
    taskPlan: [],
    planResult: "",
    lastError: "",
    pendingConfirmation: null,
    pendingChoice: null,
    suspended: false,
    checkpointId: null,
  };
}

function formatTaskPlanResult(tasks) {
  const titles = (tasks || []).map((task) => String(task?.title || "").trim()).filter(Boolean);
  if (!titles.length) return "";
  if (titles.length === 1) return `规划方案：${titles[0]}`;
  return `规划方案：${titles.join(" → ")}`;
}

function applyPlanResult(state, text) {
  const safe = sanitizeWorkflowDisplayText(text);
  if (safe) state.planResult = safe;
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
    kg_context: "知识图谱",
    version_metadata: "版本元数据",
    llm: "语言模型",
    "agent.tools": "智能体工具",
    "agent.memory": "Agent 记忆",
    "agent.tool": "工具",
    "skill.create": "创建 Skill",
    "skill.update": "更新 Skill",
    "skill.delete": "删除 Skill",
    load_uploaded_skill: "加载技能",
    create_skill: "创建技能",
    "supervisor.route": "智能体路由",
    "supervisor.parallel": "并行调度",
    "supervisor.synthesize": "结果汇总",
    "supervisor.plan": "任务规划",
    "supervisor.task": "子任务",
    web_search: "联网搜索",
    knowledge_retrieve: "知识库检索",
    kg_query: "知识图谱查询",
    update_uploaded_skill_file: "更新 Skill 文件",
    delete_uploaded_skill: "删除 Skill",
    read_agent_memory: "读取记忆",
    append_agent_memory: "写入记忆",
  };
  return fallback[tool] || "";
}

/**
 * 仅过滤纯内部文案，保留对用户有价值的信息（如检索结果数、工具调用参数）。
 * 类似 Cursor 的风格：展示更多实时细节，让用户看到智能体在做什么。
 */
const HIDDEN_WORKFLOW_DETAIL_RES = [
  /最多\s*\d+\s*轮/,
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

function upsertStep(steps, step) {
  const normalized = normalizeWorkflowStep(step);
  const idx = steps.findIndex((s) => s.id === normalized.id);
  if (idx >= 0) {
    steps[idx] = { ...steps[idx], ...normalized };
    return;
  }
  steps.push(normalized);
}

function normalizeWorkflowStep(step) {
  return {
    ...step,
    detail: sanitizeWorkflowDisplayText(step.detail),
    callDetail: sanitizeWorkflowDisplayText(step.callDetail),
    resultDetail: sanitizeWorkflowDisplayText(step.resultDetail),
  };
}

function mergeSegmentStep(prev, next) {
  return {
    ...prev,
    ...next,
    detail: next.detail || prev.detail,
    callDetail: next.callDetail || prev.callDetail,
    resultDetail: next.resultDetail || prev.resultDetail,
  };
}

/** 本析智能体：同一智能体连续操作合并为一段，不同智能体各保留一段（122233331 → 1231）。 */
function upsertAgentSegmentStep(steps, step) {
  const normalized = normalizeWorkflowStep(step);
  const agentId = String(normalized.agentId || "").trim();

  const byIdIdx = steps.findIndex((s) => s.id === normalized.id);
  if (byIdIdx >= 0) {
    const prev = steps[byIdIdx];
    const prevAgentId = String(prev.agentId || "").trim();
    if (agentId && prevAgentId && prevAgentId !== agentId) {
      steps.push(normalized);
      return;
    }
    steps[byIdIdx] = mergeSegmentStep(prev, normalized);
    return;
  }

  const last = steps[steps.length - 1];
  if (!last) {
    steps.push(normalized);
    return;
  }

  const lastAgentId = String(last.agentId || "").trim();
  const sameAgent = Boolean(agentId) && lastAgentId === agentId;

  if (sameAgent) {
    if (last.status === "running" || normalized.status === "running") {
      steps[steps.length - 1] = mergeSegmentStep(last, normalized);
      return;
    }
    if (last.status === "done" && normalized.status === "running") {
      steps.push(normalized);
      return;
    }
    steps[steps.length - 1] = mergeSegmentStep(last, normalized);
    return;
  }

  if (!agentId && !lastAgentId) {
    if (last.status === "running" || normalized.status === "running") {
      steps[steps.length - 1] = mergeSegmentStep(last, normalized);
      return;
    }
    steps.push(normalized);
    return;
  }

  steps.push(normalized);
}

/** 本析智能体：按执行顺序收集各智能体压缩段（不丢已完成子任务）。 */
export function resolveWorkflowDisplaySegments(workflow) {
  if (!workflow) return [];
  const tasks = workflow.taskPlan || [];
  if (!tasks.length) return [...(workflow.steps || [])];

  const segments = [];
  // 全局/调度步骤在前（chronologically first）
  segments.push(...(workflow.steps || []));
  // 子任务步骤在后
  for (const task of tasks) {
    segments.push(...(task.steps || []));
  }
  return segments;
}

/**
 * 获取步骤最具体的描述文本。
 * 类似 Cursor 风格：优先展示调用参数/查询内容，再展示结果，最后 fallback 到标题。
 */
export function getWorkflowSegmentContent(step) {
  if (!step) return "";
  const title = sanitizeWorkflowDisplayText(step.title);
  const detail = sanitizeWorkflowDisplayText(step.detail);
  const callDetail = sanitizeWorkflowDisplayText(step.callDetail);
  const resultDetail = sanitizeWorkflowDisplayText(step.resultDetail);

  // 失败时优先展示失败详情
  if (step.status === "failed" && resultDetail) {
    return resultDetail;
  }

  // 收集所有候选文本
  const candidates = [
    { text: callDetail, priority: 3 },  // 调用参数最具体
    { text: resultDetail, priority: 2 }, // 结果其次
    { text: detail, priority: 1 },
    { text: title, priority: 0 },
  ]
    .filter((c) => c.text)
    // 如果标题已包含某个字段，该字段不占优势
    .map((c) => {
      if (c.priority > 0 && title && title.includes(c.text)) {
        return { ...c, priority: Math.min(c.priority, 0) };
      }
      return c;
    });

  if (!candidates.length) return "";

  // 取优先级最高的非空文本
  const best = candidates.reduce((a, b) => (a.priority >= b.priority ? a : b));
  return best.text;
}

/** 从 workflow 中提取最后一次失败的可展示错误（compact 模式结束后步骤会被清空）。 */
export function getWorkflowLastError(workflow) {
  if (!workflow) return "";
  const cached = sanitizeWorkflowDisplayText(workflow.lastError);
  if (cached) return cached;
  const segments = resolveWorkflowDisplaySegments(workflow);
  for (let i = segments.length - 1; i >= 0; i -= 1) {
    const step = segments[i];
    if (step.status !== "failed") continue;
    const text = getWorkflowSegmentContent(step);
    if (text) return text;
  }
  return "";
}

export function getWorkflowDoneSegments(workflow) {
  return resolveWorkflowDisplaySegments(workflow).filter(
    (segment) => segment.status === "done" || segment.status === "failed"
  );
}

export function getWorkflowRunningSegment(workflow) {
  if (!workflow) return null;
  // 优先检查子任务步骤（包含实际智能体操作）
  for (const task of workflow.taskPlan || []) {
    const running = (task.steps || []).find((s) => s.status === "running");
    if (running) return running;
  }
  // 次检查全局步骤
  const global = (workflow.steps || []).find((s) => s.status === "running");
  if (global) return global;
  if (!workflow?.running) return null;
  const currentTitle = sanitizeWorkflowDisplayText(workflow.currentTitle);
  if (!currentTitle) return null;
  return {
    agentTitle: workflow.currentAgentTitle || "",
    title: currentTitle,
    status: "running",
  };
}

/**
 * 获取步骤的所有详情行（类似 Cursor 的详细输出风格）。
 * 返回 { callDetail, resultDetail, detail, title } 中非空的值。
 */
export function getWorkflowFullDetails(step) {
  if (!step) return { primary: "", secondary: "", tool: "" };
  const title = sanitizeWorkflowDisplayText(step.title) || "";
  const detail = sanitizeWorkflowDisplayText(step.detail) || "";
  const callDetail = sanitizeWorkflowDisplayText(step.callDetail) || "";
  const resultDetail = sanitizeWorkflowDisplayText(step.resultDetail) || "";
  const tool = step.tool || "";

  // 如果标题已经包含 callDetail 的内容，跳过重复展示
  const effectiveCall = callDetail && title.includes(callDetail) ? "" : callDetail;

  // 主要展示行：调用参数 > 详情 > 标题
  const primary = effectiveCall || detail || title;
  // 次要展示行：结果详情（与主要行不同时）
  const secondary = resultDetail && resultDetail !== primary ? resultDetail : "";
  return { primary, secondary, tool };
}

export function formatWorkflowDoneLine(step) {
  const agent = String(step?.agentTitle || "").trim();
  const content = getWorkflowSegmentContent(step);
  if (agent && content) return `${agent}：${content}`;
  return content || agent;
}

export function formatWorkflowRunningLine(workflow, step, executingLabel) {
  const agent = String(step?.agentTitle || workflow?.currentAgentTitle || "").trim();
  const title = sanitizeWorkflowDisplayText(step?.title);
  const content = getWorkflowSegmentContent(step) || sanitizeWorkflowDisplayText(workflow?.currentTitle);
  if (title && content && title !== content) {
    return [executingLabel, agent, `${title}：${content}`].filter(Boolean).join(" ");
  }
  return [executingLabel, agent, content].filter(Boolean).join(" ");
}

/** 从 workflow 状态中解析当前应展示的单一步骤。 */
export function resolveCurrentWorkflowStep(workflow) {
  if (!workflow) return null;

  for (const task of workflow.taskPlan || []) {
    for (const step of task.steps || []) {
      if (step.status === "running") return step;
    }
  }
  for (const step of workflow.steps || []) {
    if (step.status === "running") return step;
  }

  if (workflow.steps?.length) {
    return workflow.steps[workflow.steps.length - 1];
  }

  const runningTask = (workflow.taskPlan || []).find((task) => task.status === "running");
  if (runningTask?.steps?.length) {
    return runningTask.steps[runningTask.steps.length - 1];
  }

  for (let i = (workflow.taskPlan || []).length - 1; i >= 0; i -= 1) {
    const steps = workflow.taskPlan[i]?.steps || [];
    if (steps.length) return steps[steps.length - 1];
  }
  return null;
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

/** 同一智能体进行中的思考步骤（用于覆盖展示，避免堆叠多行）。 */
function findRunningThinkingStep(steps, agentId) {
  const id = String(agentId || "").trim();
  let fallback = null;
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const step = steps[i];
    if (step.kind !== "thinking" || step.status !== "running") continue;
    if (id && step.agentId === id) return step;
    if (!fallback) fallback = step;
  }
  return id ? null : fallback;
}

function resolveActiveThinkingStepId(steps, ev, state) {
  const agentId = ev.agent_id || state.currentAgentId || "";
  const running = findRunningThinkingStep(steps, agentId);
  if (running) return running.id;
  if (ev.step_id) return ev.step_id;
  return nextStepId();
}

function resolveThinkingStepIdForUpdate(steps, ev, state) {
  if (ev.step_id && findStep(steps, ev.step_id)) return ev.step_id;
  const agentId = ev.agent_id || state.currentAgentId || "";
  const running = findRunningThinkingStep(steps, agentId);
  if (running) return running.id;
  return ev.step_id || steps[steps.length - 1]?.id || nextStepId();
}

function normalizeTaskPlanItem(raw, prev = null) {
  if (!raw || typeof raw !== "object") return null;
  const id = String(raw.id || "").trim();
  if (!id) return null;
  return {
    id,
    title: String(raw.title || raw.agent_id || id).trim(),
    agentId: String(raw.agent_id || prev?.agentId || "").trim(),
    status: raw.status || prev?.status || "pending",
    summary: sanitizeWorkflowDisplayText(raw.summary) || prev?.summary || "",
    steps: Array.isArray(prev?.steps) ? prev.steps : [],
    attempts: raw.attempts || prev?.attempts || 0,
    maxAttempts: raw.maxAttempts || prev?.maxAttempts || 3,
    lastError: sanitizeWorkflowDisplayText(raw.lastError) || prev?.lastError || "",
  };
}

function applyTaskPlan(state, tasks) {
  if (!Array.isArray(tasks)) return;
  const prevById = Object.fromEntries(state.taskPlan.map((t) => [t.id, t]));
  state.taskPlan = tasks
    .map((raw) => normalizeTaskPlanItem(raw, prevById[raw?.id]))
    .filter(Boolean);
}

function upsertTaskPlanItem(state, taskId, patch = {}) {
  const id = String(taskId || "").trim();
  if (!id) return;
  let item = state.taskPlan.find((t) => t.id === id);
  if (!item) {
    item = { id, title: id, agentId: "", status: "pending", summary: "", steps: [], attempts: 0, maxAttempts: 3, lastError: "" };
    state.taskPlan.push(item);
  }
  if (patch.status) item.status = patch.status;
  if (patch.summary !== undefined) item.summary = sanitizeWorkflowDisplayText(patch.summary) || "";
  if (patch.title) item.title = String(patch.title).trim();
  if (patch.attempts !== undefined) item.attempts = patch.attempts;
  if (patch.maxAttempts !== undefined) item.maxAttempts = patch.maxAttempts;
  if (patch.lastError !== undefined) item.lastError = sanitizeWorkflowDisplayText(patch.lastError) || "";
  if (!Array.isArray(item.steps)) item.steps = [];
}

/** 有 task_id 时写入子任务步骤，否则写入全局步骤。 */
function resolveStepList(state, taskId) {
  const id = String(taskId || "").trim();
  if (id) {
    upsertTaskPlanItem(state, id);
    const task = state.taskPlan.find((t) => t.id === id);
    if (task) {
      if (!Array.isArray(task.steps)) task.steps = [];
      return task.steps;
    }
  }
  return state.steps;
}

/** 调度层可恢复失败：展示详情但不标红步骤。 */
function isSoftWorkflowFailure(ev, failed) {
  if (!failed) return false;
  const tool = String(ev?.tool || "");
  if (tool === "supervisor.assess") return true;
  if (tool === "agent.handoff") return true;
  return false;
}

/**
 * @param {ReturnType<typeof emptyAgentWorkflow>} state
 * @param {object} ev
 * @param {(key: string) => string} [t]
 * @param {{ currentStepOnly?: boolean }} [options]
 */
export function applyAgentWorkflowEvent(state, ev, t, options = {}) {
  if (!state) return emptyAgentWorkflow();
  const currentStepOnly = Boolean(options.currentStepOnly);
  const putStep = currentStepOnly ? upsertAgentSegmentStep : upsertStep;
  const phase = ev?.phase;
  const tool = ev?.tool || "";
  const toolName = toolLabel(tool, t);
  const taskId = ev?.task_id || "";
  const stepList = () => resolveStepList(state, taskId);
  applyAgentMeta(state, ev);

  function resolveThinkingStartId(steps) {
    if (currentStepOnly) return resolveActiveThinkingStepId(steps, ev, state);
    return ev.step_id || steps[steps.length - 1]?.id || nextStepId();
  }

  function resolveThinkingFinishId(steps) {
    if (currentStepOnly) return resolveThinkingStepIdForUpdate(steps, ev, state);
    return ev.step_id || steps[steps.length - 1]?.id || nextStepId();
  }

  function resolveAgentThinkingId(steps) {
    if (currentStepOnly) return resolveActiveThinkingStepId(steps, ev, state);
    return ev.step_id || nextStepId();
  }

  if (phase === "workflow_started") {
    state.running = true;
    state.failed = false;
    state.currentTitle = ev.title || "Agent 开始";
    state.currentAgentTitle = "";
    state.currentAgentId = "";
    state.executionMode = "";
    state.steps = [];
    state.taskPlan = [];
    return state;
  }

  if (phase === "plan_tasks") {
    state.running = true;
    state.failed = false;
    state.executionMode = ev.mode === "parallel" ? "parallel" : "sequential";
    applyTaskPlan(state, ev.tasks);
    applyPlanResult(state, formatTaskPlanResult(ev.tasks) || ev.detail || ev.title);
    setCurrentTitle(state, ev.title || "任务规划");
    return state;
  }

  if (phase === "task_started") {
    state.running = true;
    applyTaskPlan(state, ev.tasks);
    upsertTaskPlanItem(state, ev.task_id, { status: "running" });
    /* 专精任务开始，结束调度智能体的运行步骤（如果有） */
    finishRunningSteps(state.steps);
    setCurrentTitle(state, ev.title || "执行中");
    return state;
  }

  if (phase === "task_retry") {
    state.running = true;
    applyTaskPlan(state, ev.tasks);
    upsertTaskPlanItem(state, ev.task_id, { status: "running" });
    /* 专精重试，结束调度智能体的运行步骤 */
    finishRunningSteps(state.steps);
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
    const hasRunningTask = state.taskPlan.some((item) => item.status === "running");
    if (!hasRunningTask && !currentStepOnly) state.currentTitle = "";
    return state;
  }

  if (phase === "task_failed") {
    state.running = true;
    applyTaskPlan(state, ev.tasks);
    upsertTaskPlanItem(state, ev.task_id, {
      status: "failed",
      summary: sanitizeWorkflowDisplayText(ev.detail) || "",
    });
    return state;
  }

  if (phase === "orchestrator_progress") {
    /* 调度端进度心跳：子智能体后台执行中，调度持续发射进度事件。
       更新 currentTitle 并在步骤列表中创建一个正在运行的节点，
       让前端明确标注调度智能体正在工作而非等待。 */
    state.running = true;
    // 如果有更具体的子智能体步骤在运行，不覆盖显示
    const hasSpecificStep = state.taskPlan.some(
      (t) => (t.steps || []).some((s) => s.status === "running" && s.kind !== "node")
    );
    if (!hasSpecificStep) {
      setCurrentTitle(state, ev.detail || ev.title, "调度执行中");
    }
    const steps = stepList();
    const id = ev.step_id || "orch-progress";
    const existing = findStep(steps, id);
    putStep(steps, {
      id,
      kind: "node",
      tool: ev.tool || "supervisor.progress",
      title: ev.title || "调度执行中",
      detail: ev.detail || existing?.detail || "",
      status: "running",
      agentTitle: ev.agent_title || existing?.agentTitle || state.currentAgentTitle,
      agentId: ev.agent_id || existing?.agentId || state.currentAgentId,
    });
    return state;
  }

  if (phase === "thinking_delta") {
    state.running = true;
    state.failed = false;
    setCurrentTitle(state, ev.title || toolName, "思考中");
    const steps = stepList();
    const id = ev.step_id || resolveThinkingStartId(steps);
    const existing = findStep(steps, id);
    putStep(steps, {
      id,
      kind: "thinking",
      tool,
      title: ev.title || existing?.title || (toolName ? `${toolName}思考中` : "思考中"),
      detail: `${existing?.detail || ""}${ev.delta || ""}`,
      status: "running",
      agentTitle: ev.agent_title || existing?.agentTitle || state.currentAgentTitle,
      agentId: ev.agent_id || existing?.agentId || state.currentAgentId,
    });
    return state;
  }

  if (phase === "agent_thinking") {
    state.running = true;
    state.failed = false;
    const steps = stepList();
    finishRunningSteps(steps, { kinds: ["node"] });
    // 也清理全局步骤中的调度进度节点
    const globalSteps = resolveStepList(state, "");
    if (globalSteps !== steps) {
      finishRunningSteps(globalSteps, { kinds: ["node"] });
    }
    setCurrentTitle(state, ev.title, "思考中");
    const id = resolveAgentThinkingId(steps);
    const existing = findStep(steps, id);
    putStep(steps, {
      id,
      kind: "thinking",
      tool,
      title: ev.title || existing?.title || (toolName ? `${toolName}…` : "思考中"),
      detail: ev.detail || existing?.detail || "",
      status: "running",
      agentTitle: ev.agent_title || existing?.agentTitle || state.currentAgentTitle,
      agentId: ev.agent_id || existing?.agentId || state.currentAgentId,
    });
    return state;
  }

  if (phase === "agent_thought") {
    state.running = true;
    const steps = stepList();
    const id = resolveThinkingFinishId(steps);
    const failed = ev.status === "failed";
    const softFailure = isSoftWorkflowFailure(ev, failed);
    const existing = findStep(steps, id);
    const nextDetail = ev.detail || "";
    const keepDetail =
      existing?.detail && existing.detail.length > nextDetail.length
        ? existing.detail
        : nextDetail || existing?.detail || "";
    putStep(steps, {
      id,
      kind: "thinking",
      tool,
      title: ev.title || existing?.title || toolName || "完成",
      detail: keepDetail,
      status: softFailure ? "done" : failed ? "failed" : "done",
      agentTitle: ev.agent_title || existing?.agentTitle || state.currentAgentTitle,
      agentId: ev.agent_id || existing?.agentId || state.currentAgentId,
    });
    if (!failed) {
      const planLike =
        tool === "supervisor.plan" ||
        tool === "planner" ||
        /规划/.test(String(ev.title || ""));
      if (planLike) {
        applyPlanResult(
          state,
          keepDetail || ev.title || (tool === "supervisor.plan" ? formatTaskPlanResult(ev.tasks) : "")
        );
      }
    }
    if (failed && !softFailure) {
      const errText = keepDetail || ev.title || "";
      if (errText) state.lastError = errText;
      setCurrentTitle(state, ev.title, state.currentTitle);
    } else if (failed && softFailure) {
      setCurrentTitle(state, ev.title, state.currentTitle);
    } else if (!failed) {
      const allSteps = [...state.steps, ...state.taskPlan.flatMap((item) => item.steps || [])];
      const hasRunning = allSteps.some((s) => s.status === "running");
      if (currentStepOnly) {
        if (!hasRunning) {
          state.currentTitle = "";
        }
      } else {
        state.currentTitle = hasRunning ? state.currentTitle : "";
      }
    }
    return state;
  }

  if (phase === "tool_result") {
    state.running = true;
    const steps = stepList();
    const id = ev.step_id || steps[steps.length - 1]?.id || nextStepId();
    const failed = ev.status === "failed";
    const softFailure = isSoftWorkflowFailure(ev, failed);
    const existing = findStep(steps, id);
    const resultDetail = ev.detail || "";
    putStep(steps, {
      id,
      kind: "tool",
      tool,
      title: ev.title || existing?.title || toolName || "工具返回",
      callDetail: existing?.callDetail || "",
      resultDetail,
      status: softFailure ? "done" : failed ? "failed" : "done",
      agentTitle: ev.agent_title || existing?.agentTitle || state.currentAgentTitle,
      agentId: ev.agent_id || existing?.agentId || state.currentAgentId,
    });
    setCurrentTitle(state, ev.title, state.currentTitle);
    if (failed && resultDetail) state.lastError = resultDetail;
    return state;
  }

  if (phase === "tool_call") {
    state.running = true;
    state.failed = false;
    const steps = stepList();
    finishRunningSteps(steps, { kinds: ["node"] });
    // 也清理全局步骤中的调度进度节点
    const globalSteps = resolveStepList(state, "");
    if (globalSteps !== steps) {
      finishRunningSteps(globalSteps, { kinds: ["node"] });
    }
    const id = ev.step_id || nextStepId();
    const title = ev.title || toolName || "工具调用";
    setCurrentTitle(state, title);
    putStep(steps, {
      id,
      kind: "tool",
      tool,
      title,
      callDetail: ev.detail || "",
      resultDetail: "",
      status: "running",
      agentTitle: ev.agent_title || state.currentAgentTitle,
      agentId: ev.agent_id || state.currentAgentId,
    });
    return state;
  }

  if (phase === "node_started") {
    state.running = true;
    const steps = stepList();
    finishRunningSteps(steps, { kinds: ["node"] });
    // 也清理全局步骤中的调度进度节点
    const globalSteps = resolveStepList(state, "");
    if (globalSteps !== steps) {
      finishRunningSteps(globalSteps, { kinds: ["node"] });
    }
    setCurrentTitle(state, ev.title, "处理中");
    if (ev.title) {
      const id = ev.step_id || nextStepId();
      putStep(steps, {
        id,
        kind: "node",
        tool,
        title: ev.title,
        detail: ev.detail || "",
        status: "running",
        agentTitle: ev.agent_title || state.currentAgentTitle,
        agentId: ev.agent_id || state.currentAgentId,
      });
    }
    return state;
  }

  if (phase === "node_finished") {
    const failed = ev.status === "failed" || ev.status === "exception";
    const steps = stepList();
    // 更新正在完成节点步骤的标题（如"正在读取上下文"→"上下文就绪"）
    for (const s of steps) {
      if (s.status === "running" && s.kind === "node" && ev.title) {
        s.title = ev.title;
      }
    }
    if (failed) {
      setCurrentTitle(state, `${ev.title || "节点"}（失败）`);
      finishRunningSteps(steps, { failed: true });
    } else {
      finishRunningSteps(steps, { kinds: ["node"] });
      state.currentTitle = "";
    }
    return state;
  }

  if (phase === "confirmation_required") {
    state.running = true;
    state.pendingConfirmation = {
      id: ev.confirmation_id || "",
      tool: ev.tool || "",
      toolName: ev.tool_name || "",
      title: ev.title || "",
      detail: ev.detail || "",
      status: "awaiting",
    };
    setCurrentTitle(state, `等待确认：${ev.title || ""}`);
    return state;
  }

  if (phase === "confirmation_heartbeat") {
    /* 维持连接的心跳，无需 UI 更新 */
    return state;
  }

  if (phase === "choice_required") {
    state.running = true;
    state.pendingChoice = {
      id: ev.choice_id || "",
      tool: ev.tool || "",
      toolName: ev.tool_name || "",
      title: ev.title || "",
      question: ev.question || "",
      options: Array.isArray(ev.options) ? ev.options : [],
      status: "awaiting",
    };
    setCurrentTitle(state, `等待选择：${ev.question || ev.title || ""}`);
    return state;
  }

  if (phase === "choice_heartbeat") {
    /* 维持连接的心跳，无需 UI 更新 */
    return state;
  }

  if (phase === "workflow_finished") {
    state.running = false;
    state.failed = false;
    state.currentTitle = "";
    state.currentAgentTitle = "";
    state.currentAgentId = "";
    state.pendingConfirmation = null;
    state.pendingChoice = null;
    state.checkpointId = null;
    if (ev.status === "suspended") {
      // 进入暂停状态：恢复时需要保留 checkpoint 信息
      state.suspended = true;
      state.checkpointId = ev.checkpoint_id || null;
    } else {
      state.suspended = false;
    }
    if (currentStepOnly) {
      const preservedError = getWorkflowLastError(state);
      if (preservedError) state.lastError = preservedError;
      state.steps = [];
      for (const task of state.taskPlan) {
        task.steps = [];
      }
    } else {
      finishRunningSteps(state.steps);
      for (const task of state.taskPlan) {
        finishRunningSteps(task.steps || []);
      }
    }
    return state;
  }

  if (phase === "workflow_resumed") {
    // 从 checkpoint 恢复执行
    state.running = true;
    state.suspended = false;
    state.checkpointId = ev.checkpoint_id || null;
    setCurrentTitle(state, ev.title || "恢复执行");
    const steps = stepList();
    const resumedId = ev.step_id || nextStepId();
    putStep(steps, {
      id: resumedId,
      kind: "node",
      tool: "agent.resume",
      title: ev.title || "已恢复执行",
      detail: ev.detail || "",
      status: "running",
      agentTitle: ev.agent_title || state.currentAgentTitle,
      agentId: ev.agent_id || state.currentAgentId,
    });
    return state;
  }

  return state;
}
