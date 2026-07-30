---
name: ask_user_choice
---
向用户提出方案选择，让用户从多个选项中挑选一个再继续执行。
当已有信息不足以做单一决策、存在多种合理方案时，必须使用此工具询问用户。

## When to use
- 存在多种合理方案需要用户决定
- 导出格式选择（PDF/Word/Markdown）
- 分析时间范围、报告风格偏好
- 多种数据可视化方案、多个执行路径
- 不要替用户做不确定的猜测——问清楚再继续

## When NOT to use
- 已有确定答案
- 只需告知用户结果
- 仅需用户确认/拒绝某个操作（这是 Human-in-the-Loop 确认流程，走确认机制）

## Returns
- 用户选择的选项

## Parameters

### question (required)
清晰描述需要用户决定什么。

### options (required)
2-6 个简洁明了的选项供用户选择。
