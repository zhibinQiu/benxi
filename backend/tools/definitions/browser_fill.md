---
name: browser_fill
---
按 fields 列表批量向多个表单字段写入值。每个字段需提供 snapshot ref 与 value。

## When to use
- 一次填写多个输入框（登录表、资料表等）
- 已 snapshot 且拿到各字段 ref

## When NOT to use
- 只填一个简单输入框（可用 browser_type）
- 没有有效 ref（先 browser_snapshot）

## Returns
- 批量填表结果摘要

## Parameters

### fields (required)
对象数组，每项含：
- ref：snapshot 元素引用
- value：要填入的值
最多 30 项。
