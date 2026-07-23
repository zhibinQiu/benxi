/**
 * 本析智能体工作流状态管理
 *
 * 原则：
 * 1. 流式期原地更新：summary / liveThinking / parsingUrls 替换，不堆叠多行状态
 * 2. steps 仅供答后「思考过程」折叠面板累积
 * 3. 展示真实在做的事（搜索词、解析 URL、思考片段），避免固定「请稍候」
 */

export function emptyAgentWorkflow() {
  return {
    running: false,
    failed: false,
    /** 当前操作一行摘要（原地替换） */
    summary: "",
    /** 流式思考正文（原地增长/截断展示，不堆叠多块） */
    liveThinking: "",
    /** 正在/已解析的网页列表（全量 snapshot 替换） */
    parsingUrls: [],
    /** 思考过程 / 执行轨迹（折叠面板） */
    steps: [],
    taskPlan: [],
    detailSteps: [],
    pendingConfirmation: null,
    pendingChoice: null,
    suspended: false,
    checkpointId: null,
  };
}

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
const LIVE_THINKING_MAX = 2400;

export function sanitizeWorkflowDisplayText(text) {
  const value = String(text || "").trim();
  if (!value) return "";
  if (HIDDEN_TEXT_RES.some((re) => re.test(value))) return "";
  // 草稿答复（含完整 mermaid / 长篇终稿）不进思考区
  if (value.length > 400 && /```/.test(value)) return "";
  return value;
}

function safeText(text, fallback = "") {
  return sanitizeWorkflowDisplayText(text) || fallback;
}

function ensureSteps(state) {
  if (!Array.isArray(state.steps)) state.steps = [];
  return state.steps;
}

/**
 * 将思考片段写入 liveThinking 与 steps（答后「思考过程」面板）。
 * @param {{ stream?: boolean }} [opts] stream=true 时连续拼接（thinking_delta），不强制换行
 */
function appendThinking(state, chunk, opts = {}) {
  const raw = String(chunk || "");
  if (!raw) return;
  // 流式增量也过滤终稿草稿，避免「重试多次」把完整答案堆进思考过程
  if (/```\s*mermaid/i.test(raw) || (/flowchart\s+TD/i.test(raw) && raw.length > 40)) {
    return;
  }
  const text = opts.stream ? raw : sanitizeWorkflowDisplayText(raw);
  if (!opts.stream && !text) return;
  if (opts.stream && !raw.trim()) return;
  const steps = ensureSteps(state);
  let thinking = steps.find((s) => s.kind === "thinking");
  if (!thinking) {
    thinking = { kind: "thinking", title: "思考过程", detail: "" };
    steps.push(thinking);
  }
  const prev = String(thinking.detail || "");
  // 去重：与末段相同则跳过（规划事件常重复推送）
  if (!opts.stream) {
    const tail = prev.split("\n").filter(Boolean).slice(-1)[0] || "";
    if (tail && (tail === text || text.includes(tail) || tail.includes(text))) {
      return;
    }
  }
  const next = opts.stream
    ? `${prev}${raw}`
    : prev
      ? `${prev}${prev.endsWith("\n") ? "" : "\n"}${text}`
      : text;
  thinking.detail = next.length > 8000 ? next.slice(-8000) : next;
  const livePrev = String(state.liveThinking || "");
  const live = opts.stream
    ? `${livePrev}${raw}`
    : livePrev
      ? `${livePrev}${text.startsWith("\n") ? text : `\n${text}`}`
      : text.replace(/^\n+/, "");
  state.liveThinking =
    live.length > LIVE_THINKING_MAX ? live.slice(-LIVE_THINKING_MAX) : live;
}

function formatThinkingLine(title, detail) {
  const t = safeText(title);
  const d = safeText(detail);
  if (t && d && t !== d) return `${t}：${d}`;
  return d || t || "";
}

function appendExecStep(state, step) {
  const steps = ensureSteps(state);
  const title = safeText(step.title);
  if (!title && !step.detail) return;
  steps.push({
    kind: step.kind || "tool",
    title: title || "步骤",
    detail: step.detail || "",
  });
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
      const status = String(item.status || "pending").trim() || "pending";
      return { url, status };
    })
    .filter(Boolean);
}

function applyUrlParseSnapshot(state, ev) {
  const urls = normalizeUrlEntries(ev.urls);
  if (urls.length) {
    state.parsingUrls = urls;
  }
  const parsing = urls.find((u) => u.status === "parsing") || urls.find((u) => u.status === "pending");
  const title = safeText(ev.title || ev.detail);
  if (parsing?.url) {
    // 动作行展示当前正在解析的网址，不另开列表
    state.summary = `正在解析：${shortUrlForSummary(parsing.url)}`;
  } else if (title) {
    state.summary = title;
  } else if (urls.length) {
    const done =
      Number(ev.done) ||
      urls.filter((u) => u.status === "done" || u.status === "skipped").length;
    const total = Number(ev.total) || urls.length;
    if (done >= total && total > 0) {
      state.summary = `网页解析完成（${done}/${total}）`;
      state.parsingUrls = [];
    } else {
      state.summary = `正在解析网页（${done}/${total}）`;
    }
  }
}

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

/**
 * 从 tool_call 事件中提取对人类最有价值的操作描述。
 */
function extractToolSummary(ev) {
  const detail = safeText(ev.callDetail);
  if (detail) return detail;

  const title = safeText(ev.title);
  const tool = String(ev.tool || ev.tool_name || "").trim();

  if (tool.includes("web_search")) return title || "搜索";
  if (tool.includes("knowledge_retrieve")) return title || "知识库检索";
  if (tool.includes("kg_query") || tool.includes("kg.")) return title || "知识图谱";
  if (tool.startsWith("skill.")) return `技能：${tool.split(".").slice(-1)[0]}`;
  if (tool === "invoke_context_subagent") return title || "子智能体";
  if (tool === "request_orchestrator_assist") return title || "请求辅助";
  if (tool === "run_tool_batch") return title || "批量检索";
  if (tool === "deep_research") return title || "联网调研";

  return title || "";
}

/** 获取工作流失败时的错误文本。 */
export function getWorkflowLastError(workflow) {
  return workflow?.failed ? (workflow.summary || "") : "";
}

/**
 * @param {ReturnType<typeof emptyAgentWorkflow>} state
 * @param {object} ev
 */
export function applyAgentWorkflowEvent(state, ev) {
  if (!state) return emptyAgentWorkflow();
  const phase = ev?.phase;

  if (phase === "workflow_started") {
    state.running = true;
    state.failed = false;
    state.summary = "";
    state.liveThinking = "";
    state.parsingUrls = [];
    state.steps = [];
    state.taskPlan = [];
    state.detailSteps = [];
    return state;
  }

  if (phase === "plan_tasks") {
    state.running = true;
    const titles = (ev.tasks || [])
      .map((t) => String(t?.title || "").trim())
      .filter(Boolean);
    state.summary = titles.length === 1 ? titles[0] : titles.join(" → ");
    state.taskPlan = (ev.tasks || []).map((t) => ({
      title: String(t?.title || "").trim(),
      summary: String(t?.summary || "").trim(),
      substeps: Array.isArray(t?.substeps) ? t.substeps : [],
    }));
    return state;
  }

  if (phase === "agent_plan") {
    state.running = true;
    state.summary = safeText(ev.title, "制定计划");
    const lines = ev.detail ? String(ev.detail).split("\n").filter(Boolean) : [];
    state.detailSteps = lines;
    if (lines.length) {
      appendExecStep(state, {
        kind: "plan",
        title: safeText(ev.title, "执行计划"),
        detail: lines.map((line) => ({ text: line.replace(/^\s*\d+\.\s*/, "") })),
      });
      appendThinking(state, formatThinkingLine(ev.title || "执行计划", lines.join("；")));
    } else {
      const d = safeText(ev.detail || ev.title);
      if (d) appendThinking(state, formatThinkingLine(ev.title || "执行计划", d));
    }
    return state;
  }

  if (phase === "task_started") {
    state.running = true;
    state.summary = safeText(ev.title, "执行中");
    return state;
  }

  if (phase === "task_done") {
    if (!state.summary) state.summary = "完成";
    return state;
  }

  if (phase === "task_failed") {
    state.summary = safeText(ev.detail || ev.title, "失败");
    return state;
  }

  if (phase === "task_retry") {
    state.running = true;
    state.summary = `重试：${safeText(ev.title, "")}`;
    return state;
  }

  if (phase === "tool_call") {
    state.running = true;
    state.failed = false;
    const summary = extractToolSummary(ev) || "执行中";
    state.summary = summary;
    // 新工具开始时清空上一轮解析列表（除非同属网页类工具且带 urls）
    if (!Array.isArray(ev.urls) || !ev.urls.length) {
      const tool = String(ev.tool || ev.tool_name || "");
      if (!tool.includes("web_search") && tool !== "fetch_url_content") {
        state.parsingUrls = [];
      }
    }
    appendExecStep(state, {
      kind: "tool",
      title: summary,
      detail: safeText(ev.callDetail || ev.detail),
    });
    appendThinking(
      state,
      formatThinkingLine(summary, safeText(ev.callDetail || ev.detail)),
    );
    return state;
  }

  if (phase === "tool_result") {
    if (ev.status === "failed") {
      state.summary = safeText(ev.detail, "执行失败");
    } else if (ev.status === "rejected") {
      state.summary = "";
    }
    // 工具结束后保留解析列表片刻；下一 tool_call / 结束时清理
    return state;
  }

  if (phase === "url_parse_progress") {
    state.running = true;
    applyUrlParseSnapshot(state, ev);
    return state;
  }

  if (phase === "thinking_delta") {
    state.running = true;
    const delta = String(ev.delta || "");
    if (!delta) return state;
    // 流式增量须连续拼接；勿每段前插 \n，否则会变成「一字一行」
    appendThinking(state, delta, { stream: true });
    if (!state.summary) state.summary = "思考中";
    return state;
  }

  if (phase === "agent_thinking" || phase === "llm_thinking") {
    state.running = true;
    const d = safeText(ev.detail || ev.title);
    if (d) {
      state.summary = d;
      appendThinking(state, formatThinkingLine(ev.title, d));
    } else if (!state.summary) {
      state.summary = "思考中";
    }
    return state;
  }

  if (phase === "agent_thought") {
    const d = safeText(ev.detail || ev.title);
    if (d) {
      appendThinking(state, formatThinkingLine(ev.title, d));
    }
    if (!state.summary || state.summary === "思考中") {
      state.summary = ev.status === "failed"
        ? safeText(ev.detail || ev.title, "失败")
        : safeText(ev.detail || ev.title, "");
    }
    return state;
  }

  if (phase === "llm_decision") {
    const d = safeText(ev.detail || ev.title);
    if (d) {
      state.summary = d;
      appendThinking(state, formatThinkingLine(ev.title || "决策", d));
    } else if (state.summary === "思考中") {
      state.summary = "";
    }
    return state;
  }

  if (phase === "orchestrator_progress") {
    state.running = true;
    const d = safeText(ev.detail || ev.title);
    if (d) state.summary = d;
    if (Array.isArray(ev.urls) && ev.urls.length) {
      applyUrlParseSnapshot(state, ev);
    }
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
    state.summary = "";
    state.liveThinking = "";
    state.parsingUrls = [];
    state.pendingConfirmation = null;
    state.pendingChoice = null;
    state.checkpointId = null;
    if (ev.status === "suspended") {
      state.suspended = true;
      state.checkpointId = ev.checkpoint_id || null;
    } else {
      state.suspended = false;
    }
    return state;
  }

  if (phase === "workflow_resumed") {
    state.running = true;
    state.suspended = false;
    state.summary = safeText(ev.title, "恢复执行");
    return state;
  }

  return state;
}
