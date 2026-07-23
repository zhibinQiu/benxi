---
name: run_tool_batch
---
在一轮内批量执行多个只读/检索类原子工具（最多 6 步），减少往返。每步指定 tool 名与 arguments。

## When to use
- 需要并行或连续做多次检索/查询，且均为只读
- 已知各步工具名与参数

## When NOT to use
- 含写操作、浏览器交互、破坏性操作（应逐步调用）
- 单工具即可完成的任务
- 不确定工具参数时先 describe_tool / search_tools

## Returns
- 各步执行结果列表

## Parameters

### steps (required)
数组，每项含：
- tool：工具名
- arguments：参数对象
1–6 步。
