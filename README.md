# 本析平台 (Benxi)

> 企业级 AI 知识库平台 — 入库 · 析清 · 用起来

[![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)]()
[![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D)]()

**本析平台**是一个全栈开源的企业级 AI 知识管理平台，将 PDF 翻译、知识库构建、智能检索、报告生成等能力整合为统一闭环。

- **在线体验**: [http://36.151.146.71:40005/ai/](http://36.151.146.71:40005/ai/)
- **GitHub**: [https://github.com/zhibinQiu/benxi](https://github.com/zhibinQiu/benxi)
- **文档站点**: [https://zhibinQiu.github.io/benxi/](https://zhibinQiu.github.io/benxi/)（标题：本析-企业级 AI 智能体平台）
- **版本**: v4.9.0（见根目录 `VERSION`）

---

## 👀 界面预览

<div align="center">
  <table>
    <tr>
      <td align="center"><img src="frontend/public/images/本析智能首页.png" alt="智能首页" width="360" /></td>
      <td align="center"><img src="frontend/public/images/功能列表.png" alt="功能列表" width="360" /></td>
    </tr>
    <tr>
      <td align="center"><strong>智能首页</strong> — 平台入口与概览</td>
      <td align="center"><strong>功能列表</strong> — 全功能导航</td>
    </tr>
    <tr>
      <td align="center"><img src="frontend/public/images/知识检索.png" alt="知识检索" width="360" /></td>
      <td align="center"><img src="frontend/public/images/本体图谱.png" alt="本体图谱" width="360" /></td>
    </tr>
    <tr>
      <td align="center"><strong>知识检索</strong> — 语义检索与智能问答</td>
      <td align="center"><strong>本体图谱</strong> — 领域知识图谱</td>
    </tr>
  </table>
</div>

> 更多截图与演示请访问 [在线体验](http://36.151.146.71:40005/ai/)

---

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 📄 **PDF 翻译** | 科学文献全格式翻译，保留排版 |
| 🧠 **AI 知识库** | 文档入库、语义检索、智能问答 |
| 🔗 **本体构建** | 自动抽取实体关系，构建领域知识图谱 |
| 🤖 **多智能体** <sup>[¹](#设计哲学)</sup> | 调度 / 专精 / 子智能体分层编排，Tool · Skill · HITL |
| 📊 **报告生成** | 基于知识库的自动报告与对比分析 |
| 🔐 **权限体系** | 组织架构 + 角色权限 + 字段级管控 |
| 🌐 **多语言** | 中英文界面，国际化支持 |

---

## 🏗 项目结构

```
pdf_trans/
├── backend/             # FastAPI 后端（API / 认证 / 文档 / 知识库 / Agent）
│   ├── app/agent/       # 可抽离智能体运行时（路由 · 编排 · AIP · 子智能体）
│   └── agent_md/        # Agent 指令 · 路由偏好 · 工具描述
├── frontend/            # Vue 3 + Naive UI 前端
├── data/                # DATA_ROOT（开发默认）；生产常为 /root/qzb/benxi/data
├── backups/             # stack.sh backup 产物
├── compose.yaml         # Docker Compose
└── VERSION              # 版本号
```

---

## 🚀 快速启动

### 前提条件

- Docker & Docker Compose
- 或 Python 3.12+ + Node.js 18+

### Docker 方式（推荐）

```bash
cp .env.stack.example .env
cp backend/.env.example backend/.env    # 按需编辑

# 启动全栈
./scripts/dev.sh docker --profile knowflow
```

| 模式 | Web | API |
|------|-----|-----|
| Docker 开发 | http://127.0.0.1:40005 | http://127.0.0.1:18000 |
| 本机开发 | http://127.0.0.1:40005 | http://127.0.0.1:8000 |

停止：`./scripts/dev.sh stop`

---

## 🔧 多智能体运行时 <sup>[¹](#设计哲学)</sup>

核心在 `backend/app/agent/`（可抽离库）+ `agent_tool_loop` 宿主六相循环；业务偏好在 `backend/agent_md/`。

> [Agent 架构](docs/zh/agent-architecture.md) · [设计哲学](docs/zh/agent-philosophy.md) · [通俗长文](my-agent-philosophy.md)

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [产品文档](https://zhibinQiu.github.io/benxi/) | 本析-企业级 AI 智能体平台 · 架构与运维 |
| [Agent 架构](docs/zh/agent-architecture.md) | 流程 · 分层 · 代码地图 |
| [组件与数据存储](docs/zh/operations/components-and-storage.md) | DATA_ROOT 与 backups/ |
| [运维部署指南](https://zhibinQiu.github.io/benxi/operations/README/) | 部署、配置、升级 |

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送 (`git push origin feature/amazing`)
5. 提交 Pull Request

## 📖 设计哲学

[¹](#设计哲学): 设计理念见 [我的智能体设计哲学](my-agent-philosophy.md) 与 [docs/zh/agent-philosophy.md](docs/zh/agent-philosophy.md)。

---

## 📄 许可

[AGPL v3](LICENSE) — 开源自由软件，请遵守协议条款。
