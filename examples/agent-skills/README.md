# Agent Skills 上传示例

本目录提供可上传到平台的 **上传型 Skill** 示例。多数 Skill 是给智能体看的 Markdown 说明；**web-page-insight** 还包含可在沙箱中执行的 Python 脚本。

## 基本概念

| 概念 | 说明 |
|------|------|
| **Tool（原子工具）** | 平台固定的 function calling 原语：`web_search`、`knowledge_retrieve`、`kg_query`、记忆、文档、浏览器等。**不可扩充**。 |
| **Skill（技能）** | 对工具的编排与选用说明，分两类：**内置技能**（平台预置）与**发展技能**（上传 / Agent 生成）。 |
| **内置技能** | 如「知识综合检索」编排 `knowledge_retrieve` + `kg_query` + `web_search`；「联网搜索」编排 `web_search`。 |
| **发展技能** | 管理员上传或 Agent 生成的 `SKILL.md` 包；可在正文中编排工具，也可纯指令。 |
| **SKILL.md** | 发展技能的核心文件 |
| **Discovery** | 技能名称与选用规则进入智能体目录 |
| **Activation** | 模型调用原子工具，或对发展技能 `load_uploaded_skill` |

## 示例：mermaid-diagram

用途：教模型在对话中输出 **Mermaid** 流程图、时序图等，由平台自动渲染。

### 目录结构

```
mermaid-diagram/
├── SKILL.md              # 必需
├── references/           # 可选参考
│   └── syntax-guide.md
└── templates/            # 可选模板
    └── examples.md
```

### 上传步骤

**方式一：ZIP（推荐）**

```bash
cd examples/agent-skills
zip -r mermaid-diagram.zip mermaid-diagram/
```

在 **系统设置 → Agent Skills → Skills** 中选择 `mermaid-diagram.zip`。

**方式二：文件夹**

在「选择文件夹」时选中 `mermaid-diagram` 目录（须含 `SKILL.md`）。

### 上传之后

1. 在列表中可查看文件、下载备份、启停 Skill  
2. 启用后进入智能体 **Discovery 目录**；模型在需要图表时会加载 `SKILL.md` 并按指令输出 ` ```mermaid ` 代码块  
3. 对话区自动渲染；用户可复制源码保存为 `.mmd` 文件  

## 示例：web-page-insight（可执行脚本）

用途：在沙箱中拉取 **公开 http(s) 网页**，在内存中分析标题/描述/结构，通过 `run_skill_script` **只返回 conclusion**，不保存 HTML。

### 目录结构

```
web-page-insight/
├── SKILL.md
├── main.py           # 入口（平台 run_skill_script 执行）
└── fetch_utils.py    # 辅助模块（演示多文件 import）
```

### 上传步骤

```bash
cd examples/agent-skills
zip -r web-page-insight.zip web-page-insight/
```

在 **系统设置 → Agent Skills → Skills** 中选择 `web-page-insight.zip` 并启用。

### 在本析智能中使用

用户：「分析一下 https://example.com 这个页面讲什么」

智能体应调用：

```text
run_skill_script(skill_name="web-page-insight", args=["https://example.com"])
```

根据返回的 `conclusion` 组织回答，勿复述整页 HTML。

### 能力边界

- ✅ 规定输出格式、引用权限内文档（配合内置检索）
- ✅ **Python 脚本沙箱**（`run_skill_script`）：多文件、内存分析、仅返回 `conclusion`
- ❌ 不持久化抓取/网页原文到服务器；脚本禁止写本地文件
- ❌ 不访问内网/本机 URL；不越权访问文档

### 脚本 Skill 通用约定

Skill 包内放 `main.py`（或 `run.py`），平台注入 `skill_runtime.py`：

```python
# main.py — 示例：拉取网页并只输出分析结论
import sys
import skill_runtime
from bs4 import BeautifulSoup

def main():
    url = sys.argv[1]
    html = skill_runtime.fetch_text(url)  # 内存中，不落盘
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string or "").strip() if soup.title else ""
    skill_runtime.finish(f"页面标题：{title}")

if __name__ == "__main__":
    main()
```

- 入口脚本最后一行须输出 JSON：`{"conclusion":"..."}`，或调用 `skill_runtime.finish(...)`
- 沙箱预装：`requests`、`httpx`、`beautifulsoup4`、`lxml`、`pandas`、`numpy` 等
- 禁止：`open()` 写文件、`subprocess`、数据库等

更多说明见 [Agent Skills 实现说明](../../docs/zh/implementation/agent-skills-implementation.md)。

## 示例：web-rpa-demo

用途：展示 **`browser_save_workflow`** 录制的 `workflow.json` 格式（非可执行脚本）。实际 RPA 由平台内置 `browser_*` 工具完成，见 [浏览器 RPA 实现说明](../../docs/zh/implementation/browser-rpa-implementation.md)。

```text
web-rpa-demo/
├── SKILL.md
└── workflow.json    # 录制步骤序列样例
```

启用 `AGENT_BROWSER_ENABLED=true` 后，在 AI 首页对话即可探索网页并保存流程，无需上传本示例。
