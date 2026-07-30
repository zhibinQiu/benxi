/**
 * 本析智能体工作流状态管理
 *
 * 标准循环（与后端 protocol / OpenAI reasoning 对齐）:
 *   thinking → planning → executing →（再 thinking → …）
 * 并行执行：mode=parallel|dag 且多条 tasks.status=running。
 *
 * liveThinking：状态行下方的小字过程（流式推理 + 工具/技能自然语言行，不含代码）。
 */

export function emptyAgentWorkflow() {
  return {
    running: false,
    failed: false,
    /** thinking | planning | executing */
    stage: "",
    /** sequential | parallel | dag */
    planMode: "",
    summary: "",
    /** 当前执行智能体（调度/专精） */
    activeAgentId: "",
    activeAgentTitle: "",
    /** 流式过程正文（展示前经 scrub） */
    liveThinking: "",
    /** 答后「执行过程」快照（结束时从 liveThinking 固化，避免被清空） */
    processLog: "",
    parsingUrls: [],
    steps: [],
    /** 流式原始缓冲（含未闭合片段，渲染前 scrub） */
    _thinkingRaw: "",
    taskPlan: [],
    detailSteps: [],
    planEdges: [],
    pendingConfirmation: null,
    pendingChoice: null,
    suspended: false,
    checkpointId: null,
  };
}

const LIVE_THINKING_MAX = 12000;
/** 单条过程行最大字数，避免研究提纲整段刷屏并被截断 */
const PROCESS_LINE_MAX = 96;

const STATUS = {
  thinking: "思考中",
  planning: "正在规划",
  executing: "正在执行",
};

const HIDDEN_TEXT_RES = [
  /最多\s*\d+\s*轮/,
  /必须调用\s*mermaid/i,
  /匹配技能/,
  /```\s*mermaid/i,
  /flowchart\s+TD/i,
  /【系统警告】/,
  /【系统提示】你必须通过 tool_calls/,
  /【系统】必须调用/,
];

const TOOL_LABELS = {
  run_tool_batch: "批量并行检索",
  web_search: "联网搜索",
  knowledge_retrieve: "知识库检索",
  knowledge_folder_search: "文件夹检索",
  kg_query: "知识图谱查询",
  ontology_query: "本体语义理解",
  fetch_url_content: "读取网页",
  invoke_skill: "调用技能",
  find_skills: "查找技能",
  search_tools: "搜索工具",
  invoke_context_subagent: "启动子智能体",
  deep_research: "联网调研",
  describe_tool: "查看工具说明",
  load_uploaded_skill: "加载技能",
  list_agent_skills: "列出技能",
  read_agent_memory: "读取记忆",
  append_agent_memory: "写入记忆",
  "supervisor.plan": "任务规划",
  "supervisor.task": "子任务",
  "supervisor.route": "智能体路由",
  "supervisor.parallel": "并行调度",
  "supervisor.synthesize": "结果汇总",
  "agent.llm": "语言模型",
  "agent.execute": "执行分析",
  "agent.tools": "智能体工具",
  llm: "语言模型",
};

const AGENT_LABELS = {
  orchestrator: "小析",
  platform: "平台操作",
  report: "报告撰写",
  "skill-dev": "技能开发",
  carbon: "双碳",
  "power-economy": "电力经济",
  stock: "股市分析",
  research: "调研",
};

export function resolveAgentDisplayName(agentId, agentTitle = "") {
  const title = String(agentTitle || "").trim();
  if (title) return title;
  const id = String(agentId || "").trim();
  if (!id) return "";
  return AGENT_LABELS[id] || id;
}

/** 常见英文过程文案 → 中文 */
const THINKING_PHRASE_MAP = [
  [/\bPlan\b/g, "规划"],
  [/\bThinking\b/gi, "思考中"],
  [/\bthought complete\b/gi, "思考完成"],
  [/\bthinking complete\b/gi, "思考完成"],
  [/\bExecuting\b/gi, "正在执行"],
  [/\bExecution\b/gi, "执行"],
  [/\bCompleted\b/gi, "已完成"],
  [/\bFailed\b/gi, "失败"],
  [/\bRetry(?:ing)?\b/gi, "重试"],
  [/\bRunning\b/gi, "进行中"],
  [/\bPending\b/gi, "待执行"],
  [/\bDone\b/gi, "完成"],
  [/\bTool call\b/gi, "调用工具"],
  [/\bTool result\b/gi, "工具结果"],
  [/\borchestrator\b/gi, "小析"],
  [/\bsupervisor\.plan\b/gi, "任务规划"],
  [/\bsupervisor\.task\b/gi, "子任务"],
  [/OntologyHubService/gi, "本体语义中枢"],
  [/KgQueryService/gi, "知识图谱服务"],
  [/match[_\s]?entities/gi, "匹配实体"],
  [/execute[_\s]?plan/gi, "执行查询计划"],
];

const PROMPT_LEAK_RES = [
  /严格遵循\s*SKILL\.md/i,
  /请使用\s+.+\s*技能回答/,
  /第一人称身份/,
  /张雪峰式/,
  /Step\s*[123]/i,
  /工作流：先做/,
  /需获取：\s*1\)/,
  /我需要以下.+真实数据/,
];

const PHASE_TO_STAGE = {
  workflow_started: "thinking",
  agent_thinking: "thinking",
  llm_thinking: "thinking",
  thinking_delta: "thinking",
  agent_thought: "thinking",
  plan_tasks: "planning",
  agent_plan: "planning",
  llm_decision: "planning",
  task_started: "executing",
  task_retry: "executing",
  tool_call: "executing",
  url_parse_progress: "executing",
  orchestrator_progress: "executing",
  task_done: "executing",
  task_failed: "executing",
  tool_result: "executing",
};

function shortUrlForSummary(url) {
  const u = String(url || "").trim();
  if (!u) return "";
  try {
    const parsed = new URL(u);
    const path = `${parsed.hostname}${parsed.pathname || ""}`.replace(/\/$/, "");
    return path.length > 72 ? `${path.slice(0, 69)}…` : path;
  } catch {
    return u.length > 72 ? `${u.slice(0, 69)}…` : u;
  }
}

export function looksLikeToolCallPayload(text) {
  const value = String(text || "").trim();
  if (!value) return false;
  if (/^```(?:json|JSON)?\b/i.test(value)) return true;
  if (/"function"\s*:/.test(value) && /"params"\s*:/.test(value)) return true;
  if (/^\{\s*"(?:function|name|tool)"\s*:/.test(value)) return true;
  if (/"tool"\s*:/.test(value) && /"arguments"\s*:/.test(value)) return true;
  return false;
}

function naturalizeToolCallObject(obj) {
  if (!obj || typeof obj !== "object") return "";
  const fn = String(obj.function || obj.name || obj.tool || "").trim();
  if (!fn) return "";
  const params = obj.params || obj.arguments || obj.args || {};
  const label = TOOL_LABELS[fn] || fn.replace(/_/g, " ");
  if (fn === "run_tool_batch") {
    const steps = Array.isArray(params.steps) ? params.steps : [];
    if (steps.length) return `并行检索（${steps.length} 项）`;
    return label;
  }
  if (fn === "web_search" || fn === "knowledge_retrieve" || fn === "knowledge_folder_search") {
    const q = String(params.query || "").trim();
    return q ? `${label}「${q.slice(0, 40)}」` : label;
  }
  if (fn === "kg_query" || fn === "ontology_query") {
    const q = String(params.question || params.query || "").trim();
    return q ? `${label}「${q.slice(0, 40)}」` : label;
  }
  if (fn === "fetch_url_content") {
    const url = String(params.url || "").trim();
    return url ? `${label}：${shortUrlForSummary(url)}` : label;
  }
  return label;
}

export function scrubThinkingDisplayText(text) {
  let value = String(text || "");
  if (!value) return "";
  value = value.replace(/```(?:json|JSON)?\s*([\s\S]*?)```/gi, (_m, body) => {
    try {
      const line = naturalizeToolCallObject(JSON.parse(String(body || "").trim()));
      return line ? `\n${line}\n` : "";
    } catch {
      return "";
    }
  });
  const fenceIdx = value.lastIndexOf("```");
  if (fenceIdx !== -1) {
    const after = value.slice(fenceIdx + 3);
    if (/^\s*(json)?\s*[{\["]/i.test(after) || /^\s*(json)?\s*$/i.test(after)) {
      value = value.slice(0, fenceIdx);
    }
  }
  value = value.replace(
    /\{\s*"(?:function|name|tool)"\s*:\s*"[^"]+"[\s\S]*?\}\s*(?=\n|$)/g,
    (m) => {
      try {
        const line = naturalizeToolCallObject(JSON.parse(m));
        return line ? `${line}\n` : "";
      } catch {
        return looksLikeToolCallPayload(m) ? "" : m;
      }
    },
  );
  value = value.replace(/\{\s*"(?:function|name|tool)"\s*:[\s\S]*$/g, "");
  value = value
    .replace(/^\s*```(?:json|JSON)?\s*$/gim, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return localizeThinkingZh(value);
}

/** 过程展示尽量中文：工具名、智能体 id、常见英文状态词。 */
export function localizeThinkingZh(text) {
  let value = String(text || "");
  if (!value) return "";
  // skill.xxx / tool snake_case
  value = value.replace(
    /\b(?:skill\.)?([a-z][a-z0-9_]{2,}|[a-z]+(?:\.[a-z_]+)+)\b/gi,
    (m) => {
      const key = m.toLowerCase();
      if (TOOL_LABELS[key]) return TOOL_LABELS[key];
      if (TOOL_LABELS[key.replace(/^skill\./, "")]) {
        return TOOL_LABELS[key.replace(/^skill\./, "")];
      }
      if (AGENT_LABELS[key]) return AGENT_LABELS[key];
      // foo_bar → 保留可读；纯英文工具名用空格
      if (/_/.test(m) && !/[\u4e00-\u9fff]/.test(m)) {
        return m.replace(/_/g, " ");
      }
      return m;
    },
  );
  for (const [re, zh] of THINKING_PHRASE_MAP) {
    value = value.replace(re, zh);
  }
  return value;
}

export function sanitizeWorkflowDisplayText(text) {
  const scrubbed = scrubThinkingDisplayText(text);
  const value = String(scrubbed || "").trim();
  if (!value) return "";
  if (looksLikeToolCallPayload(value)) return "";
  if (HIDDEN_TEXT_RES.some((re) => re.test(value))) return "";
  if (value.length > 400 && /```/.test(value)) return "";
  return value;
}

function safeText(text, fallback = "") {
  return sanitizeWorkflowDisplayText(text) || fallback;
}

function resolveStage(ev) {
  const explicit = String(ev?.stage || "").trim();
  if (explicit === "thinking" || explicit === "planning" || explicit === "executing") {
    return explicit;
  }
  return PHASE_TO_STAGE[String(ev?.phase || "").trim()] || "";
}

function runningTasks(state) {
  return (state.taskPlan || []).filter((t) => t.status === "running");
}

function shortenProcessLine(text, max = PROCESS_LINE_MAX) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (!value) return "";
  if (value.length <= max) return value;
  return `${value.slice(0, Math.max(0, max - 1))}…`;
}

function looksLikePromptLeak(text) {
  const value = String(text || "");
  if (!value) return false;
  if (PROMPT_LEAK_RES.some((re) => re.test(value))) return true;
  // 长篇研究提纲 / 编号清单不当作过程行
  if (value.length > 160 && /(?:\d\)|\d\.)\s*.{0,20}(?:就业|薪资|招聘|录取)/.test(value)) {
    return true;
  }
  return false;
}

function lineFingerprint(text) {
  return String(text || "")
    .replace(/\s+/g, "")
    .replace(/[…。.!！?？,，;；:：]/g, "")
    .slice(0, 48);
}

function publishLiveThinking(state) {
  const scrubbed = scrubThinkingDisplayText(state._thinkingRaw || "");
  if (scrubbed.length > LIVE_THINKING_MAX) {
    // 从完整句子边界截取，避免末尾半截字
    let cut = scrubbed.slice(-(LIVE_THINKING_MAX - 1));
    const nl = cut.indexOf("\n");
    if (nl > 0 && nl < 80) cut = cut.slice(nl + 1);
    state.liveThinking = `…\n${cut}`;
  } else {
    state.liveThinking = scrubbed;
  }
}

function appendThinkingDelta(state, delta) {
  const chunk = String(delta || "");
  if (!chunk) return;
  // 不把提示词 / 研究提纲草稿流式刷进过程区
  if (looksLikePromptLeak(chunk)) return;
  if (looksLikePromptLeak(`${state._thinkingRaw || ""}${chunk}`.slice(-400))) {
    // 若缓冲尾部已像提示词泄漏，丢弃本段
    return;
  }
  // 流式 token 直接拼接，不要在每个 chunk 前插换行（否则会一字/一词一行）
  state._thinkingRaw = `${state._thinkingRaw || ""}${chunk}`;
  if (state._thinkingRaw.length > LIVE_THINKING_MAX * 2) {
    state._thinkingRaw = state._thinkingRaw.slice(-(LIVE_THINKING_MAX * 2));
  }
  publishLiveThinking(state);
}

function appendProcessLine(state, line) {
  let text = sanitizeWorkflowDisplayText(line);
  if (!text) return;
  if (looksLikePromptLeak(text)) {
    // 退化为短状态，不展示整段指令
    if (/技能/.test(text)) text = "按指定技能执行";
    else if (/就业|薪资|招聘/.test(text)) text = "整理就业数据要点";
    else return;
  }
  text = shortenProcessLine(text);
  if (!text) return;
  const raw = String(state._thinkingRaw || "").trimEnd();
  const fp = lineFingerprint(text);
  const lines = raw.split("\n").filter(Boolean);
  const last = lines[lines.length - 1] || "";
  if (last === text) return;
  if (fp && lineFingerprint(last) === fp) return;
  // 近重复：最近几行已出现过同类内容
  if (fp && lines.slice(-6).some((l) => lineFingerprint(l) === fp)) return;
  // 过程行以换行结尾，后续流式思考可直接拼接，不会黏在同一行
  state._thinkingRaw = raw ? `${raw}\n${text}\n` : `${text}\n`;
  if (state._thinkingRaw.length > LIVE_THINKING_MAX * 2) {
    state._thinkingRaw = state._thinkingRaw.slice(-(LIVE_THINKING_MAX * 2));
  }
  publishLiveThinking(state);
}

function setActiveAgent(state, ev, fallbackId = "") {
  const id = String(ev?.agent_id || fallbackId || "").trim();
  const title = resolveAgentDisplayName(id, ev?.agent_title);
  if (id) state.activeAgentId = id;
  if (title) state.activeAgentTitle = title;
  return title;
}

function setStage(state, stage, action = "") {
  state.stage = stage;
  if (stage === "thinking") {
    state.summary = STATUS.thinking;
    return;
  }
  if (stage === "planning") {
    state.summary = STATUS.planning;
    return;
  }
  const parallel =
    state.planMode === "parallel" ||
    state.planMode === "dag" ||
    runningTasks(state).length > 1;
  const active = runningTasks(state);
  if (parallel && active.length > 1) {
    const titles = active.map((t) => {
      const name = resolveAgentDisplayName(t.agentId, t.agentTitle);
      return name ? `${name}：${t.title}` : t.title;
    }).filter(Boolean);
    state.summary = `正在并行执行（${active.length}）：${titles.join(" ∥ ")}`;
    return;
  }
  const a = String(action || "").trim();
  if (a) {
    state.summary = a.startsWith("正在执行") ? a : `${STATUS.executing}：${a}`;
  } else if (active.length === 1) {
    const t = active[0];
    const name = resolveAgentDisplayName(t.agentId, t.agentTitle);
    if (name) {
      state.activeAgentId = t.agentId || state.activeAgentId;
      state.activeAgentTitle = name;
    }
    state.summary = `${STATUS.executing}：${t.title}`;
  } else {
    state.summary = STATUS.executing;
  }
}

function syncTasksFromEvent(state, ev) {
  if (!Array.isArray(ev?.tasks) || !ev.tasks.length) return;
  const byId = new Map((state.taskPlan || []).filter((t) => t.id).map((t) => [t.id, t]));
  for (const raw of ev.tasks) {
    const id = String(raw?.id || "").trim();
    const title = String(raw?.title || "").trim();
    const status = String(raw?.status || "pending").trim() || "pending";
    const agentId = String(raw?.agent_id || "").trim();
    const agentTitle = resolveAgentDisplayName(agentId, raw?.agent_title);
    const existing = id ? byId.get(id) : null;
    if (existing) {
      existing.status = status;
      if (raw.summary) existing.summary = String(raw.summary).slice(0, 120);
      if (title) existing.title = title;
      if (agentId) existing.agentId = agentId;
      if (agentTitle) existing.agentTitle = agentTitle;
    } else if (id || title) {
      const row = {
        id,
        title,
        summary: String(raw?.summary || "").trim(),
        status,
        agentId,
        agentTitle,
        substeps: Array.isArray(raw?.substeps) ? raw.substeps : [],
      };
      state.taskPlan.push(row);
      if (id) byId.set(id, row);
    }
  }
}

function updateTaskPlanStatus(state, ev, status) {
  if (!Array.isArray(state.taskPlan)) state.taskPlan = [];
  const taskId = String(ev?.task_id || "").trim();
  const title = String(ev?.title || "").trim();
  let task = taskId ? state.taskPlan.find((t) => t.id === taskId) : null;
  if (!task && title) task = state.taskPlan.find((t) => t.title === title);
  if (task) {
    task.status = status;
    const detail = String(ev?.detail || "").trim();
    if (detail) task.summary = detail.slice(0, 120);
  }
  syncTasksFromEvent(state, ev);
}

function nextPendingTaskTitle(state) {
  const pending = (state.taskPlan || []).find(
    (t) => !t.status || t.status === "pending",
  );
  return pending?.title || "";
}

function ensureSteps(state) {
  if (!Array.isArray(state.steps)) state.steps = [];
  return state.steps;
}

function appendExecStep(state, step) {
  const steps = ensureSteps(state);
  const title = safeText(step.title);
  if (!title) return;
  const last = steps[steps.length - 1];
  if (last && last.kind === step.kind && last.title === title) return;
  if (steps.length >= 24) steps.shift();
  steps.push({ kind: step.kind || "tool", title, detail: "" });
}

function normalizeUrlEntries(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (typeof item === "string") {
        const url = item.trim();
        return url ? { url, status: "parsing" } : null;
      }
      if (!item || typeof item !== "object") return null;
      const url = String(item.url || "").trim();
      if (!url) return null;
      return { url, status: String(item.status || "pending").trim() || "pending" };
    })
    .filter(Boolean);
}

function applyUrlParseSnapshot(state, ev) {
  const urls = normalizeUrlEntries(ev.urls);
  if (urls.length) state.parsingUrls = urls;
  const parsing =
    urls.find((u) => u.status === "parsing") ||
    urls.find((u) => u.status === "pending");
  if (parsing?.url) {
    setStage(state, "executing", `解析网页 ${shortUrlForSummary(parsing.url)}`);
  } else if (urls.length) {
    const done =
      Number(ev.done) ||
      urls.filter((u) => u.status === "done" || u.status === "skipped").length;
    const total = Number(ev.total) || urls.length;
    setStage(
      state,
      "executing",
      done >= total && total > 0
        ? `网页解析完成（${done}/${total}）`
        : `解析网页（${done}/${total}）`,
    );
  }
}

function extractToolSummary(ev) {
  const title = safeText(ev.title);
  // 优先短中文 title；不再把内部 callDetail（类名/长提纲）顶到前台
  if (title) return shortenProcessLine(title);
  const callDetail = safeText(ev.callDetail || ev.call_detail);
  if (
    callDetail &&
    callDetail.length <= PROCESS_LINE_MAX &&
    !/Service|match_entities|execute_plan/i.test(String(ev.callDetail || ev.call_detail || ""))
  ) {
    return callDetail;
  }
  const tool = String(ev.tool || ev.tool_name || "").trim();
  if (tool.includes("web_search")) return "联网搜索";
  if (tool.includes("knowledge_retrieve")) return "知识库检索";
  if (tool.includes("ontology_query") || tool.includes("ontology")) return "本体语义理解";
  if (tool.includes("kg_query") || tool.includes("kg.")) return "知识图谱查询";
  if (tool.startsWith("skill.")) return `技能：${tool.split(".").slice(-1)[0]}`;
  if (tool === "invoke_context_subagent") return "启动子智能体";
  if (tool === "request_orchestrator_assist") return "请求辅助";
  if (tool === "run_tool_batch") return "批量并行检索";
  if (tool === "deep_research") return "联网调研";
  if (tool === "invoke_skill") return "调用技能";
  if (TOOL_LABELS[tool]) return TOOL_LABELS[tool];
  return "";
}

export function finalizeWorkflowProcess(workflow) {
  if (!workflow) return workflow;
  const snap = scrubThinkingDisplayText(
    workflow.liveThinking || workflow._thinkingRaw || workflow.processLog || "",
  );
  if (snap) {
    workflow.processLog = snap;
    if (!(workflow.steps || []).length) {
      const lines = snap
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean);
      workflow.steps = lines.slice(-24).map((title) => ({
        kind: "tool",
        title,
        detail: "",
      }));
    }
  }
  workflow.liveThinking = "";
  workflow._thinkingRaw = "";
  workflow.running = false;
  return workflow;
}

export function getWorkflowLastError(workflow) {
  return workflow?.failed ? workflow.summary || "" : "";
}

export function workflowRunningTasks(workflow) {
  return (workflow?.taskPlan || []).filter((t) => t.status === "running");
}

export function applyAgentWorkflowEvent(state, ev) {
  if (!state) return emptyAgentWorkflow();
  const phase = ev?.phase;
  const stage = resolveStage(ev);

  if (phase === "workflow_started") {
    state.running = true;
    state.failed = false;
    state.parsingUrls = [];
    state.steps = [];
    state._thinkingRaw = "";
    state.liveThinking = "";
    state.processLog = "";
    state.taskPlan = [];
    state.detailSteps = [];
    state.planMode = "";
    state.planEdges = [];
    state.activeAgentId = "";
    state.activeAgentTitle = "";
    setActiveAgent(state, ev, "orchestrator");
    setStage(state, "thinking");
    return state;
  }

  if (phase === "plan_tasks") {
    state.running = true;
    state.planMode = String(ev.mode || "").trim() || "sequential";
    state.planEdges = Array.isArray(ev.edges) ? ev.edges : [];
    state.taskPlan = (ev.tasks || []).map((t) => {
      const agentId = String(t?.agent_id || "").trim();
      return {
        id: String(t?.id || "").trim(),
        title: String(t?.title || "").trim(),
        summary: String(t?.summary || "").trim(),
        status: String(t?.status || "pending").trim() || "pending",
        agentId,
        agentTitle: resolveAgentDisplayName(agentId, t?.agent_title),
        substeps: Array.isArray(t?.substeps) ? t.substeps : [],
      };
    });
    setActiveAgent(state, ev, "orchestrator");
    setStage(state, "planning");
    const titles = state.taskPlan.map((t) => {
      const name = t.agentTitle || resolveAgentDisplayName(t.agentId);
      return name && t.title ? `${name}：${t.title}` : t.title;
    }).filter(Boolean);
    if (titles.length) {
      const label =
        state.planMode === "parallel" || state.planMode === "dag"
          ? titles.join(" ∥ ")
          : titles.length === 1
            ? titles[0]
            : `计划 ${titles.length} 步`;
      appendExecStep(state, { kind: "plan", title: label });
      appendProcessLine(state, `规划：${label}`);
    }
    return state;
  }

  if (phase === "agent_plan") {
    state.running = true;
    setActiveAgent(state, ev);
    setStage(state, "planning");
    const planTitle = safeText(ev.title, "执行计划");
    appendExecStep(state, { kind: "plan", title: planTitle });
    appendProcessLine(state, `规划：${planTitle}`);
    return state;
  }

  if (phase === "task_started") {
    state.running = true;
    if (ev.mode) state.planMode = String(ev.mode).trim() || state.planMode;
    updateTaskPlanStatus(state, ev, "running");
    setActiveAgent(state, ev);
    const title = safeText(ev.title);
    setStage(state, "executing", title);
    const agent = state.activeAgentTitle;
    if (title) appendProcessLine(state, agent ? `${agent}：${title}` : `执行：${title}`);
    return state;
  }

  if (phase === "task_done") {
    updateTaskPlanStatus(state, ev, "done");
    const still = runningTasks(state);
    if (still.length > 1) setStage(state, "executing");
    else if (still.length === 1) setStage(state, "executing", still[0].title);
    else if (nextPendingTaskTitle(state)) setStage(state, "planning");
    else setStage(state, "thinking");
    return state;
  }

  if (phase === "task_failed") {
    updateTaskPlanStatus(state, ev, "failed");
    state.stage = "executing";
    state.summary = safeText(ev.detail || ev.title, "执行失败");
    return state;
  }

  if (phase === "task_retry") {
    state.running = true;
    setStage(state, "executing", `重试 ${safeText(ev.title)}`);
    return state;
  }

  if (phase === "tool_call") {
    state.running = true;
    state.failed = false;
    setActiveAgent(state, ev);
    const action = extractToolSummary(ev) || "工具";
    setStage(state, "executing", action);
    if (!Array.isArray(ev.urls) || !ev.urls.length) {
      const tool = String(ev.tool || ev.tool_name || "");
      if (!tool.includes("web_search") && tool !== "fetch_url_content") {
        state.parsingUrls = [];
      }
    }
    appendExecStep(state, { kind: "tool", title: action });
    const agent = state.activeAgentTitle;
    appendProcessLine(state, agent ? `${agent} · ${action}` : action);
    return state;
  }

  if (phase === "tool_result") {
    if (ev.status === "failed") {
      state.summary = safeText(ev.detail, "执行失败");
      appendProcessLine(state, `失败：${safeText(ev.detail || ev.title, "执行失败")}`);
    } else if (ev.status === "rejected") {
      setStage(state, "thinking");
      appendProcessLine(state, "已取消该操作");
    } else {
      // 完成行只保留短标题，避免把长 detail / 研究提纲刷进过程区
      const done = shortenProcessLine(safeText(ev.title) || "完成");
      if (done) appendProcessLine(state, `完成：${done}`);
      if (runningTasks(state).length) setStage(state, "executing");
      else setStage(state, "thinking");
    }
    return state;
  }

  if (phase === "url_parse_progress") {
    state.running = true;
    applyUrlParseSnapshot(state, ev);
    return state;
  }

  if (phase === "thinking_delta") {
    state.running = true;
    setActiveAgent(state, ev);
    if (state.stage !== "thinking") setStage(state, "thinking");
    appendThinkingDelta(state, ev.delta || ev.text || "");
    return state;
  }

  if (phase === "agent_thinking" || phase === "llm_thinking") {
    state.running = true;
    setActiveAgent(state, ev);
    setStage(state, "thinking");
    const hint = safeText(ev.detail || ev.title);
    if (hint && hint !== STATUS.thinking) appendProcessLine(state, hint);
    return state;
  }

  if (phase === "agent_thought") {
    if (ev.status === "failed") {
      state.summary = safeText(ev.detail || ev.title, "失败");
      appendProcessLine(state, state.summary);
    } else if (state.stage === "thinking") setStage(state, "planning");
    return state;
  }

  if (phase === "llm_decision") {
    setStage(state, stage || "planning");
    return state;
  }

  if (phase === "orchestrator_progress") {
    state.running = true;
    setStage(state, "executing", safeText(ev.detail || ev.title));
    if (Array.isArray(ev.urls) && ev.urls.length) applyUrlParseSnapshot(state, ev);
    return state;
  }

  if (phase === "confirmation_required") {
    state.running = true;
    state.summary = `等待确认：${safeText(ev.title) || ""}`;
    state.pendingConfirmation = {
      id: ev.confirmation_id || "",
      tool: ev.tool || "",
      toolName: ev.tool_name || "",
      title: ev.title || "",
      detail: ev.detail || "",
      status: "awaiting",
    };
    return state;
  }

  if (phase === "confirmation_heartbeat") return state;

  if (phase === "choice_required") {
    state.running = true;
    state.summary = `等待选择：${safeText(ev.question || ev.title) || ""}`;
    state.pendingChoice = {
      id: ev.choice_id || "",
      tool: ev.tool || "",
      toolName: ev.tool_name || "",
      title: ev.title || "",
      question: ev.question || "",
      options: Array.isArray(ev.options) ? ev.options : [],
      status: "awaiting",
    };
    return state;
  }

  if (phase === "choice_heartbeat") return state;

  if (phase === "workflow_finished") {
    state.running = false;
    state.failed = false;
    state.stage = "";
    state.summary = "";
    finalizeWorkflowProcess(state);
    state.parsingUrls = [];
    state.pendingConfirmation = null;
    state.pendingChoice = null;
    if (ev.status === "suspended") {
      state.suspended = true;
      state.checkpointId = ev.checkpoint_id || null;
    } else {
      state.suspended = false;
      state.checkpointId = null;
    }
    return state;
  }

  if (phase === "workflow_resumed") {
    state.running = true;
    state.suspended = false;
    setStage(state, "executing", safeText(ev.title, "恢复执行"));
    return state;
  }

  if (stage) setStage(state, stage, safeText(ev.title || ev.detail));
  return state;
}
