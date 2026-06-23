# Mermaid 语法速查

## 流程图 flowchart

```mermaid
flowchart TD
    Start([开始]) --> Input[填写申请]
    Input --> Review{主管审批}
    Review -->|通过| Finance[财务审核]
    Review -->|驳回| Input
    Finance --> Archive[(归档)]
    Archive --> End([结束])
```

常用形状：

| 语法 | 形状 |
|------|------|
| `A[矩形]` | 处理步骤 |
| `B(圆角)` | 一般活动 |
| `C{菱形}` | 判断 |
| `D([体育场])` | 开始/结束 |
| `E[(数据库)]` | 存储 |

方向：`TD` 上下、`LR` 左右、`BT` 下上、`RL` 右左。

## 时序图 sequenceDiagram

```mermaid
sequenceDiagram
    participant U as 用户
    participant S as 系统
    participant A as 审批人
    U->>S: 提交申请
    S->>A: 推送待办
    A-->>S: 审批通过
    S-->>U: 通知结果
```

## 状态图 stateDiagram-v2

```mermaid
stateDiagram-v2
    [*] --> 草稿
    草稿 --> 待审: 提交
    待审 --> 已通过: 同意
    待审 --> 已驳回: 拒绝
    已驳回 --> 草稿: 修改
    已通过 --> [*]
```

## 思维导图 mindmap

```mermaid
mindmap
  root((项目启动))
    目标
      范围界定
      里程碑
    资源
      人员
      预算
    风险
      进度
      合规
```

注意：mindmap 节点避免括号、引号等特殊符号。

## 甘特图 gantt（可选）

```mermaid
gantt
    title 项目实施计划
    dateFormat YYYY-MM-DD
    section 准备
    需求确认 :a1, 2025-01-01, 7d
    section 开发
    功能开发 :a2, after a1, 14d
    section 上线
    验收发布 :a3, after a2, 5d
```

## 常见错误

1. 节点 ID 含空格 — 使用 `step1` 而非 `step 1` 作为 ID。
2. 中文边标签 — 使用 `A -->|是| B` 格式。
3. 子图 — `subgraph 标题` … `end`，标题可用引号包裹特殊字符。
