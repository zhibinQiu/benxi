---
name: web-page-insight
description: 在沙箱中拉取公开网页并在内存中分析标题、摘要与结构要点；通过 run_skill_script 执行，仅返回 conclusion，不保存原始 HTML。
---

# 网页快速洞察（可执行脚本 Skill）

## 适用场景

当用户提出以下需求时，使用工具 **`run_skill_script`** 执行本 Skill（**不要**只用 `load_uploaded_skill` 读说明就结束）：

- 抓取某个 **http/https 公开 URL** 并总结页面主题
- 查看页面标题、描述、主要标题层级、链接数量等**结构化结论**
- 对比两个公开页面的基本信息（分两次调用，每次一个 URL）

不适用：

- **网页截图、保存为图片文件**（请用平台内置 `browser_navigate` + `browser_screenshot`，需管理员启用浏览器 RPA）
- 需要登录、Cookie、验证码的页面
- 内网地址、本机地址（平台 SSRF 防护会拒绝）
- 需要把网页原文保存到服务器或知识库

## 执行方式

```text
run_skill_script(
  skill_name="web-page-insight",
  entry="main.py",          # 可省略，默认 main.py
  args=["https://example.com"]
)
```

平台在**临时目录**运行 `main.py`，注入 `skill_runtime.py`；执行结束后删除临时文件，**仅把 JSON conclusion 返回给模型**。

## 脚本结构

```text
web-page-insight/
├── SKILL.md
├── main.py           # 入口
└── fetch_utils.py    # 可 import 的辅助模块（示例多文件）
```

## 输出约定

`main.py` 须调用 `skill_runtime.finish(conclusion)`。`conclusion` 应为**中文分析摘要**，例如：

> 页面标题：Example Domain；描述：…；共 3 个 h1/h2 标题；外链约 12 个；正文摘要：…

**禁止**在 `conclusion` 中粘贴整页 HTML 或超长原文。

## 与智能体协作

| 步骤 | 工具 |
|------|------|
| 用户给出 URL，要求分析 | `run_skill_script` |
| 用户问「这个 Skill 怎么用」 | `load_uploaded_skill` 读本文 |
| 需要企业文档内容 | 改用内置 `research`，勿用本 Skill |

## 示例对话

用户：「帮我看一下 https://example.com 这个页面讲什么」

1. 调用 `run_skill_script(skill_name="web-page-insight", args=["https://example.com"])`
2. 根据返回的 `conclusion` 用自然语言回复用户
3. 若抓取失败，说明 URL 不可达或受平台安全策略限制

用户：「创建一个能拉网页的 Skill」

应使用 `create_uploaded_skill` 新建包，或告知本示例已存在；**不要**对本 Skill 盲目 `load_uploaded_skill`。

## 安全边界

- 仅允许 `http`/`https`，禁止内网 IP
- 脚本禁止 `open()` 写文件、`subprocess` 等（平台静态校验）
- 原始网页内容只在沙箱内存中短暂存在，**不会**写入数据库或对象存储
