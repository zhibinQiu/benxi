# Agent 架构设计

> 本文档描述本析平台 Agent 系统的架构设计、数据传输逻辑和方法调用逻辑。  
> 架构设计图请打开 [Canvas](/Users/qiuzhibin/.cursor/projects/Users-qiuzhibin-project-pdf-trans/canvases/agent-architecture.canvas.tsx) 查看（在 Cursor IDE 中打开）。

---

## 1. 系统分层

| 层 | 职责 | 关键技术 |
|---|------|---------|
| **表现层** | 用户交互、SPA 路由 | Vue 3 + Nginx |
| **Agent 层** | 规划、工具循环、HITL、编排 | `agent_tool_loop.py`, `agentkit-loop`, `agentkit-aip` |
| **Skill 层** | 内置/上传/MCP 技能执行 | `skill_script_executor.py`, `agentkit-skills`, `agentkit-mcp` |
| **Tool 层** | 工具注册、参数校验、结果压缩 | `agent_tool_context.py`, `agentkit-tools` |

---

## 2. Agent 循环流程

```
用户消息 → API → LLM 规划 → 工具调度 → 执行工具 → 观察 → 继续/退出
```

### 2.1 阶段说明

1. **规划**: LLM 生成 `AgentExecutionPlan`，确定意图（直接回答/原子工具/发展技能）。
2. **调度**: 根据规划类型 dispatch 到对应处理路径。
3. **执行**: 原子工具 → 注册表查找 → Pydantic 校验 → 执行 → 结果压缩。
   发展技能 → 沙箱容器执行 → JSON 结论提取。
4. **观察**: Tool 结果注入到下一轮 system prompt。
5. **退出**: LLM 判断用户目标是否达成，达则回复，未达则继续。

### 2.2 关键组件

| 组件 | 文件 | 职责 |
|------|------|------|
| Agent Loop | `backend/app/services/agent_tool_loop.py` | 主循环调度 |
| Tool Context | `backend/app/core/agent_tool_context.py` | 上下文注入、指纹去重、消息裁剪 |
| Skill Executor | `backend/app/integrations/skill_script_executor.py` | 沙箱调用 |
| Skill Runtime | `backend/app/integrations/skill_script_runtime.py` | `fetch_text`/`finish` 注入模块 |
| Skill Dev Playbook | `backend/app/core/skill_dev_playbook.py` | Skill 命名校验、脚手架、修复提示 |
| Config | `backend/app/config.py` | 全局配置（Agent/Skill/沙箱） |

---

## 3. 数据传输逻辑

### 3.1 用户消息 → Agent 循环

```
User Message
    ↓
agent_tool_loop.py::execute_tool_loop()
    ↓
[Plan Stage]
    agent_planning → AgentExecutionPlan
    ↓
[Tool Dispatch]
    agent_tool_context.py::inject_retrieval_context_message()
        ├── build_skill_explore_context_block()  ← 调研材料
        ├── build_skill_repair_context_block()   ← 修复指引
        ├── build_turn_executed_tools_context()  ← 已执行工具列表
        └── build_retrieval_context_block()      ← RAG 检索结果
    ↓
[Execute]
    Tool: execute_tool() → compress_tool_result()
    Skill: execute_skill_script() → sandbox POST /run → JSON conclusion
    ↓
[Observe]
    record_executed_tool_call() → fingerprint → cache
    ↓
[Trim]
    trim_agent_loop_messages() → fit_messages_to_total_budget()
    ↓
[Exit]
    LLM produces final reply → return to user
```

### 3.2 Skill 脚本执行

```
invoke_skill(skill-development, call, operation=run_skill_script)
    ↓
skill_script_executor.py::execute_skill_script()
    ├── resolve_entry_path(files)       # 找到 main.py
    ├── validate_skill_script(code)     # ast.parse 语法检查
    ├── _read_runtime_source()          # 读 skill_script_runtime.py
    ├── _build_sandbox_code(code, src)  # 内联 runtime + 去 import
    ├── base64 encode
    └── httpx.post(sandbox_url + "/run")
        ↓
KnowFlow Sandbox:
    executor_manager → security check → runc container
        ↓
    python -c "exec(decoded_code)" → main() → skill_runtime.finish()
        ↓
Returns JSON: {"status":"success","stdout":"...","stderr":"..."}
    ↓
agent_tool_context.py parses conclusion
```

---

## 4. 方法调用逻辑

### 4.1 Tool 指纹去重

```
tool_call_fingerprint(name, args)
    → normalize_tool_args_for_fingerprint(args)  # JSON 排序
    → hashlib.sha256(name + "\0" + sorted_json).hexdigest()[:16]
```

用途：相同参数的同名工具不重复执行。

### 4.2 Runtime 注入

```
_build_sandbox_code(code, runtime_src):
    1. strip `import skill_runtime` / `from skill_runtime import`
    2. prepend runtime_src (skill_script_runtime.py 全部源码)
    3. append mod_stub (sys.modules["skill_runtime"] + 变量绑定)
    4. append user code
    5. append `def main(): pass`
```

### 4.3 AIP Handoff

```
子智能体完成任务后:
    build_specialist_handoff_message(params)
        → AipMessage(senderRole="service", message_type=TASK_RESPONSE)
        → dataItems: [handoff_summary, tool_outcomes, skill_conclusion]
        → 发送到 orchestrator

调度器:
    best_reply_from_hops(hop_completes)
    merge_hop_citations(citation_lists)
```

---

## 5. 设计模式

| 模式 | 应用 | 说明 |
|------|------|------|
| **策略模式** | Agent 规划 | 不同规划策略（直接回答、原子工具、发展技能）可互换 |
| **注册表模式** | ToolRegistry / SkillRegistry | 工具和技能按名称注册，运行时通过名称查找 dispatch |
| **协议模式** | MCP ToolCaller / LoopEvidenceProvider | 宿主注入 Callable，本库依赖抽象不依赖具体实现 |
| **组合模式** | System prompt 构建 | `inject_retrieval_context_message` 组合多个上下文块 |
| **外观模式** | agentkit 包的 `__init__.py` | 封装内部模块，对外暴露简洁 API |

---

## 6. 部署模式

### 模式 A：本地 API + 基础服务

```
compose.yaml         # 核心服务（Postgres/Redis/Minio/API/Frontend）
compose.dev.yaml     # 热重载开发
compose.sandbox.yaml # Skill 沙箱
compose.mirror.yaml  # 镜像加速（可选）
deploy/knowflow.yml  # 知识库（profile: knowflow）
```

启动：`bash scripts/stack.sh dev-up`

### 模式 B：全部在服务器

```
compose.yaml         # 核心服务
compose.server.yaml  # 运行时镜像 + 挂载源码
compose.sandbox.yaml # Skill 沙箱
compose.mirror.yaml  # 镜像加速（可选）
deploy/knowflow.yml  # 知识库（profile: knowflow）
```

启动：`bash scripts/stack.sh server-up`

---

## 7. 关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `agent_skill_script_enabled` | True | 是否启用脚本型 Skill |
| `agent_skill_script_timeout_seconds` | 30 | 沙箱执行超时（秒） |
| `sandbox_base_url` | "" | 沙箱服务地址（需设置） |
| `agent_max_tool_rounds` | 40 | 单轮对话最大工具循环轮次 |
| `agent_planning_enabled` | True | 是否启用 LLM 规划阶段 |
| `hitl_confirm_tools` | "" | 需要人工确认的工具列表 |

---

## 8. 相关包

| 包 | 版本 | 说明 |
|----|------|------|
| `agentkit-tools` | 4.6.0 | 工具注册表、Schema 生成、校验、压缩 |
| `agentkit-skills` | 4.6.0 | Skill 注册表、搜索、执行、MCP 桥接 |
| `agentkit-mcp` | 4.6.0 | MCP 协议、HTTP/SSE 客户端 |
| `agentkit-loop` | 4.6.0 | 循环证据、退出提示构建 |
| `agentkit-aip` | 4.6.0 | AIP 身份码、Handoff、会话总线 |
| `agentkit-message` | 4.6.0 | 消息解析、过滤、上下文裁剪 |

---

## 9. Agent 设计哲学

### 9.1 三层路由模型

Agent 系统按**职责与可见性**分为三层，每层解决不同粒度的问题：

```
用户消息
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│  ① 编排器（Orchestrator）                                │
│     路由决策 + 通用对话                                   │
│     → 寒暄/简单问题：直接作答                             │
│     → 专精领域：路由到对应专精 Agent                     │
│     → 信息获取：tool loop 内自主决定用工具还是子 Agent    │
└───────────────────────┬──────────────────────────────────┘
                        │ 路由
                        ▼
┌──────────────────────────────────────────────────────────┐
│  ② 专精 Agent（Specialist）                              │
│     完整 tool loop，面向用户                             │
│     skill-dev / platform / report / rpa                   │
│     → 用户找它办事，它有自己的 system prompt 和工具集    │
│     → 结果直接呈现给用户                                 │
└───────────────────────┬──────────────────────────────────┘
                        │ 委托子任务
                        ▼
┌──────────────────────────────────────────────────────────┐
│  ③ 子 Agent（Subagent）                                  │
│     隔离 tool loop，面向父 Agent                         │
│     explore / browser_digest / deep_research             │
│     → 父 Agent 在流程中按需调用                          │
│     → 有自己的 LLM 循环，自主决策                        │
│     → 结果汇总回父 Agent 的上下文                        │
└──────────────────────────────────────────────────────────┘
```

### 9.2 设计原则

#### 原则一：路由看意图，专精看领域，子 Agent 看步骤

| 事件类型 | 路由目标 | 示例 |
|---------|---------|------|
| 信息获取（查数据、做调研） | 编排器自留，tool loop 内解决 | "查一下碳价格" → 编排器调 `web_search` |
| 深度信息获取（需多轮分析） | 编排器调子 Agent | "分析碳市场趋势和影响因素" → 编排器调 `deep_research` |
| 领域操作（写报告、创建 Skill、文档操作） | 专精 Agent | "帮我创建监控碳价的 Skill" → `skill-dev` |
| 专精工作流中的一环（调研→编码→测试） | 子 Agent | skill-dev 调研目标网站结构 → `browser_digest` |

#### 原则二：子 Agent ≠ 专精 Agent

| | 专精 Agent | 子 Agent |
|---|---|---|
| **谁调用的** | 编排器（路由） | 父 Agent（tool call） |
| **面向谁** | 用户 | 父 Agent |
| **生命周期** | 完整 tool loop，独立对话 | 子任务，执行完即返回结果 |
| **状态** | 独立 | 继承父状态 |
| **配置位置** | `agent_config.py`（`AgentProfileDef`） | `subagent.py`（`SubagentKindConfig`） |
| **LLM 决策** | 自己的 LLM | 自己的 LLM |

#### 原则三：子 Agent ≈ Skill + 自己的 LLM

```
Skill：
  ┌─────────────────────────────────┐
  │  SKILL.md（指令说明）            │
  │  main.py / 预设 actions          │
  │  ← 父 Agent 的 LLM 负责决策      │
  └─────────────────────────────────┘

子 Agent：
  ┌─────────────────────────────────┐
  │  system_contract（system prompt）│
  │  allowed_tools（白名单）         │
  │  max_rounds（独立循环轮次）       │
  │  ← 子 Agent 自己的 LLM 做决策    │
  └─────────────────────────────────┘
```

Skill 和子 Agent 都解决"父 Agent 委托子任务"的问题。区别在于：**子任务需要多步推理和自主决策时用子 Agent，子任务只执行预设操作时用 Skill。**

#### 原则四：无必要勿增实体

- 能直接调原子工具解决的，不劳烦子 Agent
- 能用子 Agent 解决的，不新增专精 Agent
- 能不新增专精 Agent 的，不改编排器路由

**新增一个专精 Agent 意味着：**
1. 在 `agent_config.py` 中定义 profile
2. 在 `agents.md` 中添加路由描述
3. 在编排器路由中增加意图判断
4. 处理独立的状态管理

**新增一个子 Agent 只需：**
1. 在 `subagent.py` 中增加一行 `SubagentKindConfig`
2. 在 `agent_tool_args.py` 的 `ContextSubagentKind` 中增加字面量

#### 原则五：子 Agent 结果是材料，不是终稿

子 Agent 的输出设计为"供父 Agent 使用的素材"，而非直接呈现给用户的终稿。这是子 Agent 与专精 Agent 的根本区别：

```
子 Agent 返回：  structured_report（research_summary、key_findings、数据对比、矛盾点、引用）
                      ↓
父 Agent 拿到后：  阅读研究报告 → 结合自己的知识库检索 → 组织最终回复 → 呈现给用户
```

### 9.3 决策矩阵

当需要判断某个能力应该放在哪一层时，使用以下决策树：

```
用户提了一个需求
       │
       ▼
这需求是整个对话的目的吗？
   ↓ 是                    ↓ 不是（父 Agent 正在处理中）
  走 专精 Agent               │
                              ▼
这需求是父 Agent 流程中的
一个子步骤/子任务吗？
   ↓ 是                    ↓ 不是
  走 子 Agent               │
                            ▼
父 Agent 自己就能搞定
直接调原子 tool 就行
```

或者从事件分类的角度：

```
① 事件是领域操作（写报告、创建 Skill、操作文档、浏览器自动化、定时任务）
   → 专精 Agent

② 事件是信息获取（查数据、做调研、找资料）
   → 编排器自留，tool loop 内决定：
       简单查 → 直接调原子工具（web_search）
       深度研究 → 委托子 Agent（invoke_context_subagent）

③ 事件是专精工作流中的一环（需要多步推理才能完成的中间步骤）
   → 子 Agent
```

### 9.4 代码映射

| 概念 | 位置 | 关键类型 |
|------|------|---------|
| 编排器 | `agent_config.py` / `agent_route_resolver.py` | `agent_id="orchestrator"` |
| 专精 Agent | `agent_config.py` / `agents.md` | `AgentProfileDef` |
| 原子工具 | `agent_tool_args.py` 的 `TOOL_DEFINITIONS` | `(description, Pydantic model)` |
| Skill | `skills/builtin/definitions.py` 的 `SKILL_DEFAULT_DEFINITIONS` | `SkillDefinition` |
| 子 Agent | `subagent.py` 的 `_PLATFORM_RUNTIME.kinds` | `SubagentKindConfig` |
