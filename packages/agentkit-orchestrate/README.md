# agentkit-orchestrate

多专精任务编排引擎 — **无 DB / 无 LLM**，通过 Protocol 与规则 dataclass 注入宿主配置。

## 职责

- `OrchestratorTask` / `TaskExecutionResult` 领域模型
- 路由 → 任务清单（`tasks_from_routes`）
- 子任务规则验收（`verify_task_result` + `VerifyRules` / `VerifyHooks`）
- 调度协助与 skill-dev 升级（`AssistRules`）
- 用户诉求规则验收（`assess_answer_coverage_rule`）
- Workflow 事件构造（`workflow_plan_tasks` / `workflow_task_event`）
- 并行 worker 事件合并（`iter_parallel_task_events`）

## 留在宿主

- Agent profile 标题、DeepSeek 语义验收、用户 MEMORY 写入
- 浏览器截图 URL 解析（`/browser-rpa/screenshot`）
- 专精 hop 执行、终稿 LLM 合成

## 示例

```python
from agentkit_orchestrate import (
    AssistRules,
    VerifyHooks,
    VerifyRules,
    tasks_from_routes,
    verify_task_result,
)

rules = VerifyRules(action_agent_ids=frozenset({"platform"}))
hooks = VerifyHooks(
    is_substantive_deliverable=lambda t: len(t) > 20,
    reply_looks_like_denial=lambda t: "无法" in t,
)
tasks = tasks_from_routes(routes, title_fn=lambda a: a)
ok, summary, hint = verify_task_result(task, events, complete, rules=rules, hooks=hooks)
```

## 更多示例

见 [examples/orchestrate_tasks.py](../examples/orchestrate_tasks.py)
