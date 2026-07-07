# 本析平台 (Benxi)

> 企业级 AI 知识库平台 — 入库 · 析清 · 用起来

[![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)]()
[![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D)]()

**本析平台**是一个全栈开源的企业级 AI 知识管理平台，将 PDF 翻译、知识库构建、智能检索、报告生成等能力整合为统一闭环。

- **GitHub**: [https://github.com/zhibinQiu/benxi](https://github.com/zhibinQiu/benxi)
- **AgentKit**: [https://github.com/zhibinQiu/Agentkit](https://github.com/zhibinQiu/Agentkit)
- **版本**: v4.6.0（见根目录 `VERSION`）

---

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 📄 **PDF 翻译** | 科学文献全格式翻译，保留排版 |
| 🧠 **AI 知识库** | 文档入库、语义检索、智能问答 |
| 🔗 **本体构建** | 自动抽取实体关系，构建领域知识图谱 |
| 🤖 **AgentKit** | 多智能体编排框架，支持工具注册与子 Agent |
| 📊 **报告生成** | 基于知识库的自动报告与对比分析 |
| 🔐 **权限体系** | 组织架构 + 角色权限 + 字段级管控 |
| 🌐 **多语言** | 中英文界面，国际化支持 |

---

## 🏗 项目结构

```
pdf_trans/
├── backend/             # FastAPI 后端（API / 认证 / 文档 / 知识库）
├── frontend/            # Vue 3 + Naive UI 前端
├── packages/
│   ├── agentkit/        # AgentKit 元包 — 多智能体框架
│   ├── agentkit-*/      # 子包（aip / loop / mcp / message / tools …）
│   └── ai-bridge/       # AI 网页操控桥接（Node.js）
├── pdf2zh_next/         # PDF 翻译核心
├── docs/                # 文档
├── scripts/             # 开发/运维脚本
├── deploy/              # 部署配置
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

### 远程依赖开发

```bash
REMOTE_HOST=你的服务器IP ./scripts/dev.sh remote-dev
bash scripts/verify-remote-deps.sh
./scripts/dev.sh local
```

---

## 🔧 AgentKit — 多智能体框架

AgentKit 是本析平台的多智能体架构 Python 工具包，提供从路由、编排、通信到执行的全链路组件。

```bash
# 安装全部组件
pip install -e packages/agentkit

# 或按需安装
pip install -e packages/agentkit-aip
pip install -e packages/agentkit-mcp
```

> 详细文档见 [AgentKit 仓库](https://github.com/zhibinQiu/Agentkit) 或 [AgentKit 开发者指南](https://zhibinQiu.github.io/benxi/)。

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [产品文档](https://zhibinQiu.github.io/benxi/) | 在线文档 — 使用指南与最佳实践 |
| [AgentKit 开发者指南](https://github.com/zhibinQiu/Agentkit) | AgentKit 开发文档 |
| [API 参考](https://github.com/zhibinQiu/benxi/tree/main/backend) | 后端 API 说明 |
| [运维部署指南](https://zhibinQiu.github.io/benxi/operations/README/) | 部署、配置、升级 |
| [脚本说明](https://github.com/zhibinQiu/benxi/tree/main/scripts) | dev / stack / deploy |

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送 (`git push origin feature/amazing`)
5. 提交 Pull Request

---

## ☕ 请开发者喝咖啡

本平台全部开源，开发不易。如果项目对你有帮助，欢迎打赏支持～

> 打赏 50 元以上，企业级部署享折扣 15%

<div align="center">
  <table>
    <tr>
      <td align="center">
        <img src="images/weixin.jpg" alt="微信收款码" width="200" />
        <br />
        <strong>微信</strong>
      </td>
      <td align="center">
        <img src="images/zhifubao.jpg" alt="支付宝收款码" width="200" />
        <br />
        <strong>支付宝</strong>
      </td>
    </tr>
  </table>
</div>

---

## 📄 许可

[AGPL v3](LICENSE) — 开源自由软件，请遵守协议条款。
