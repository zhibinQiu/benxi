# 功能实现说明（v4.8.6）

> **本文说明各功能如何运转**，含关键方法与提示词落点。  
> 架构分层见 [系统架构](architecture.md)；Agent Skills 详见 [Agent Skills 实现](../implementation/agent-skills-implementation.md)（含 §10 Prompt、§11 调用链）；子智能体模型见 [Agent 架构](../agent-architecture.md)。

---

## 阅读说明

| 章节 | 内容 |
|------|------|
| [§0](#0-知识沉淀闭环) | 文档从入库到问答的整体链路 |
| [§1](#1-总体原则) | 平台设计原则（含术语解释） |
| [§2–§3](#2-身份认证与会话) | 登录、权限、文档中心 |
| [§4](#4-knowflow--知识库) | 知识库、检索、图谱、AI 智能体 |
| [§5–§13](#5-pdf-翻译) | 翻译、对比、语音、任务等 |
| [§14](#14-agent-skills-管理) | Agent Skills 管理 |
| [§15](#15-aip-智能体互联v460) | AIP 智能体互联 |
| [§16](#16-postgresql-读写分离) | PostgreSQL 读写分离 |
| [§17](#17-理财助手与股市分析v486) | 理财助手、股市专精 Agent |
| [§18](#18-双碳助手v486) | 双碳助手看板与报告 |
| [§19](#19-工作笔记与提示词管理v486) | 笔记、提示词模板 |
| [§20](#20-公开分享share_tokenv486) | 文档/笔记/报告公开分享 |

**常见术语**：**JWT** = 登录后颁发的访问凭证；**RBAC** = 按角色分配功能权限；**MinIO** = 存文件的 object 存储；**Celery** = 后台异步任务 worker；**SSE** = 浏览器实时接收服务端推送（用于对话流式输出）。

---

## 0. 知识沉淀闭环

平台在同一权限口径下贯通以下链路，减少多系统拼装与数据搬运：

| 阶段 | 用户入口 | 后端要点 |
|------|----------|----------|
| 入库 | 文档中心上传 / 订阅导入 | MinIO 存储 + 可选 KnowFlow 同步 |
| 索引 | 自动 Job / 文档详情「重新索引」 | 上传默认 **naive** 向量分块；重索引默认 **PageIndex** 结构树 |
| 本体 | 本体图谱 · 本体设置 | LLM 从已索引文档抽取实体/关系；可手工编辑 |
| 检索 | 知识检索 | PageIndex 树 + 向量 **混合召回**；权限内白名单过滤 |
| 问答 | AI 智能体 / 知识检索 | 文档片段 + 图谱子图 **合并引用** |
| 成稿 | 报告生成 | Agent 多路召回 + 章节扩写；**思维导图** Tab 可导出 |

**检索策略**：长文档用 **PageIndex**（PDF/Word 章节目录树定位章节）+ 向量 **混合召回**；报告生成用 Agent 规划多轮子问题、分章节扩写。

---

## 1. 总体原则

| 原则 | 含义 | 这样设计的原因 |
|------|------|----------------|
| 平台是唯一控制面 | 用户、组织、文档信息、权限在 **PostgreSQL**；文件在 **MinIO** | 权限与元数据只维护一份，避免多系统数据不一致 |
| 重计算外置 | 翻译、向量检索、长任务交给独立服务或 Worker | API 保持轻量，交互不被大任务阻塞 |
| 功能插件化 | 每项业务能力注册为插件，统一出现在「系统功能」 | 新功能可插拔，菜单与权限自动对齐 |
| 权限先于能力 | 文档操作先校验 ACL，再调 KnowFlow | 防止「平台不让看但检索能搜到」 |
| 异步不阻塞 | 翻译、大删除、对比等走 **Job** + 轮询/SSE | 用户不必长时间等待 HTTP 响应 |
| 读写分离（可选） | 配置 `DATABASE_READ_URL` 后，只读 API 走副本 | 文档列表/详情、`/system/*` 读接口用 `get_read_db`；写操作仍走主库 |

---

## 2. 身份认证与会话

### 2.1 登录

1. 用户在前端提交手机号/姓名 + 密码。  
2. API 在 PostgreSQL 查用户、校验密码哈希与账号状态（`active`）。  
3. 成功后递增 `auth_token_version`，写入审计日志，签发 **JWT access_token + refresh_token**。  
4. 若启用 KnowFlow，登录时触发 **知识库预热**（后台 reconcile catalog，不阻塞响应）。  
5. 前端将 token 存入 localStorage，后续请求带 `Authorization: Bearer`。

### 2.2 会话与踢人

- 每个用户有 `auth_token_version`；JWT 内嵌版本号，API 校验不一致则 401。  
- 新设备登录会 bump 版本，旧 token 失效（「账号已在别处登录」）。  
- `GET /auth/me` 返回用户信息、权限码列表、是否系统管理员等。

### 2.3 权限模型（RBAC + 文档 ACL）

| 层级 | 作用 |
|------|------|
| 角色 | `sys_admin`、`member` 等，绑定权限码如 `doc.read`、`feature.pdf_translate` |
| 功能权限 | `require_feature("xxx")` 控制能否进入某系统功能页 |
| 文档 scope | `personal` / `department` / `team` / `company` 决定文档库 Tab 与默认可见范围 |
| 单文档 grant/deny | 分享给个人、禁止访问；与 scope 叠加计算最终 `can_read / can_query / can_modify` |

系统管理员拥有全部权限；普通用户按角色 + 文档 ACL 判定。

---

## 3. 文档中心

### 3.1 上传与版本

1. **创建文档记录**：前端 `POST /documents`，写入标题、scope、文件夹等元数据。  
2. **预签名上传**：`POST .../upload/prepare` 生成 MinIO `storage_key` 与 PUT 预签名 URL。  
3. **直传 MinIO**：浏览器将文件 PUT 到 MinIO，不经 API  body，支持大文件。  
4. **完成上传**：`POST .../upload/complete` 校验大小与 MIME，写入 `DocumentVersion`，设为当前版。  
5. **可选 Git 版本**：部分格式会同步写入 per-document Git 仓库，供版本对比与 diff 使用。  
6. **可选 KnowFlow 同步**：若 `sync_knowflow=true`，异步或同步将当前版上传到 RAGFlow dataset 并触发解析。

### 3.2 分级文档库

| scope | 界面 Tab | 组织绑定 | 可见规则（简述） |
|-------|----------|----------|------------------|
| personal | 个人级 | 不绑定组织 | 仅 owner；系统管理员可见全部 |
| team | 分部级 | depth=2 | 绑定节点子孙子树 + `doc.read` |
| department | 部门级 | depth=1 | 同上 |
| company | 公司级 | depth=0（根） | 同上 |
| （虚拟）分享 | 分享 | — | 他人 grant 且非 scope 默认可见的文档 |

完整对应关系（组织树、用户部门、RBAC、分享/deny、KnowFlow dataset）见 [权限模型与文档分级](../platform/permission-model.md)。

列表、详情、下载、移动、回收站均先查 ACL 再返回数据。

### 3.3 分享与禁止访问

- **分享给用户**：写入 `DocumentPermission`，级别如 visible / query / modify。  
- **禁止访问**：`DocumentDenial` 优先级高于 grant。  
- 变更分享后，若启用 KnowFlow，会 **同步 KB ACL** 与 **分享镜像**（被分享者在个人 dataset 中可见可检索副本）。

### 3.4 回收站与删除

- 软删：设 `deleted_at`，列表 `in_recycle=1` 可见。  
- 恢复：校验 `can_restore`。  
- 永久删除：创建 Celery 任务，清理 MinIO 对象、KnowFlow 链接、Git 仓库、版本块等。

### 3.5 知识索引状态

文档详情展示 **KnowFlow 索引状态**（未同步 / 解析中 / 已索引 / 失败）。  
用户可手动 **重新同步** 或 **重新解析**；管理员可配置默认解析器（DeepDOC / PaddleOCR 等）与分块策略。

---

## 4. KnowFlow / 知识库

### 4.1 账号映射

- 每个平台用户在 RAGFlow 侧有 **mapped 账号**（如 `zt-platform-{user_id}`），链接表存 `ragflow_user_id`、token 等。  
- 登录时确保 RAGFlow 账号存在；管理员有 bootstrap 租户管理能力。

### 4.2 Dataset 与 scope

| scope | RAGFlow dataset |
|-------|-----------------|
| personal | 用户个人 dataset |
| department / team | 按组织 scope_key 绑定共享 dataset |
| company | 公司级 dataset |

平台维护 `ragflow_scope_datasets` 注册表，避免重复创建。

### 4.3 文档同步流程

1. 从 MinIO 读取当前版二进制。  
2. HTML/Office 等经 **normalize** 转为 KnowFlow 可接受格式。  
3. 调用 RAGFlow API **upload_document**，写入 meta：`platform_document_id`、`platform_user_id`。  
4. 触发 **parse_documents**（切片、向量化）。  
5. 平台记录 `RagflowDocumentMirrorLink`（文档 id ↔ ragflow doc id ↔ dataset id）。

分享文档时，为被分享者在个人 dataset 创建 **镜像副本**，检索时仍校验平台 ACL。

### 4.4 嵌入 UI（iframe + SSO）

1. 前端请求 `GET /rag/embed-session` 获取 SSO token。  
2. iframe 加载 `/ragflow-ui/...`（生产经 Nginx 反代；开发经 API embed-proxy）。  
3. **embed-proxy** 反代 KnowFlow 静态与 API，注入 **platform-branding** CSS/JS，实现白标。  
4. SPA 内 `/v1/*` 请求同源走 embed-proxy，避免跨域。

### 4.5 知识检索（原生页）

- 与 iframe 解耦的 **原生问答页**：左侧 scope 文档树，右侧对话。  
- 检索前计算用户 **可 query 文档白名单**，再调用检索引擎，结果带 citation 回显。  
- 权限过滤在平台侧完成，不暴露未授权 chunk。

#### 检索引擎（区别于传统单向量 RAG）

| 引擎 | 适用文档 | 实现思路 |
|------|----------|----------|
| **PageIndex 树检索** | 已做结构索引（reindex 默认 pageindex） | LLM 在文档目录树中选 node_id，取对应章节正文；适合长 PDF/制度类文档的章节定位 |
| **KnowFlow 向量检索** | 已同步 KnowFlow 且栈可达 | hybrid 向量 + 关键词召回 chunk |
| **本地 fallback** | KnowFlow 不可达 | 平台侧轻量检索，保证基本可用 |

**问答实现**：`knowledge_qa_service.iter_knowledge_qa_stream` → 召回 → `build_aligned_qa_context_and_citations` → `_build_qa_llm_messages`（system 含引用规则，`temperature=0.2`）→ 流式生成。Agentic 模式见 `knowledge_agentic_service`（规划子问题 + 充足性评估）。详见 [知识库实现 §5](../implementation/knowledge-implementation.md)。

同一问题可对不同文档 **按引擎分区** 后合并 hits（`retrieve_hits_for_qa`），可选 Agentic 模式由 `knowledge_agentic_service.iter_gather_for_knowledge_qa` 规划子问题多轮检索。回答可切换 **思维导图** Tab（`generate_knowledge_mindmap`）。实现细节见 [知识库实现 §5](../implementation/knowledge-implementation.md)。

#### 与本体图谱联动

问答前若用户具备 `feature.kg`，会从问题中 **匹配实体 mention**，扩展 2 跳子图，将结构化关系追加到 LLM 上下文（引用编号与文档片段顺延）。

### 4.6 本体图谱

1. **本体建模**：管理员/用户配置实体类型（组织、人员、法规、项目等）与关系类型（包含、引用、约束…）。  
2. **自动抽取**：文档索引完成后，可选 LLM 从正文抽取实体/关系写入 PostgreSQL（`kg_entities` / `kg_relations`）。  
3. **工作台**：`KgView`（图探索）与 `OntologyView`（本体建模）双视图——实体查询、关系子图、详情编辑；支持按类型浏览、跳数控制子图范围。  
4. **下游消费**：知识检索、报告生成、**AI 智能体** 在回答前调用 `retrieve_kg_context_for_question`，将图谱事实与文档片段一并注入 prompt。

### 4.7 报告生成（区别于短答式 RAG）

| 维度 | 知识检索（短答） | 报告生成 |
|------|------------------|----------|
| 目标 | 单轮精准回答 + 引用 | 万字级长报告，分章节交付 |
| 召回 | 单次 top-k hits | Agent 规划多轮子问题，多路召回后去重合并 |
| 生成 | 一次 LLM 归纳 | 按章节 Agent 扩写，可联网补充（可选） |
| 输出 | 对话气泡 + 思维导图 Tab | 报告正文 Tab + **思维导图 Tab**，支持导出 Word / Markdown 大纲 / OPML（XMind） |

**实现入口**：`report_generation_service.iter_report_generation_stream()`。

| 环节 | 方法 | 说明 |
|------|------|------|
| 意图 | `classify_intent` | `initial` / `follow_up` / `format_adjust` |
| 主题 | `resolve_report_topic` | 正则从用户句抽取报告主题 |
| 多路召回 | `build_local_retrieval_queries` + `retrieve_local_hits_for_report` | 每查询 15 段，合并至多 28 段 |
| Agentic | `iter_gather_for_report` | LLM 规划 `local_queries` / `web_queries` |
| Prompt | `_build_messages` | `_REPORT_SYSTEM` + 意图指令 + 编号材料块 |
| 引用 | `build_aligned_report_sources` | 本地 [1..n] + 联网 [n+1..] 连续编号 |
| 思维导图 | `generate_report_mindmap` | 复用 QA mindmap LLM，失败本地回退 |

System 提示词、Agentic 规划 JSON、优化预设详见 [报告生成实现](../implementation/report-generation-implementation.md)。

### 4.8 AI 智能体（Agent Skills）

**入口**：`POST /api/v1/ai-chat/stream` → `ai_chat_service.iter_chat_with_ai_agent_stream()`。

**用户侧体验**：

1. 输入问题 → SSE 流式显示回答；  
2. 调用了检索时显示 workflow 步骤（`agent_thinking` / `tool_call` / `tool_result`）；  
3. 回答中带 `[1][2]` 引用，底部展示来源卡片。

**后端实现（v4.6.0）**：

| 环节 | 方法 / 模块 | 做法 |
|------|-------------|------|
| 意图预判 | `agent_intent.plan_agent_tools` | 寒暄/平台用法直接答；有附件则预读正文 |
| Prompt 组装 | `prompt_budget.build_bounded_chat_messages` | 常驻 system + Discovery 目录 + 历史 + 用户消息 |
| 常驻提示词 | `agent_resident.build_ai_home_resident_prompt` | 身份、引用格式、工具约定、禁止越权 |
| Discovery | `catalog.build_agent_catalog_prompt` | 注入 Skill 摘要与选用规则 |
| 工具循环 | `agent_tool_loop.iter_agent_tool_loop` | 多轮 LLM tool-calling，默认最多 40 轮 |
| 综合检索 | `skill_chat_service.resolve_combined_research_async` | `research` 工具内并行 KB + KG + Web |
| 上传 Skill | `execute_agent_tool` → `load_uploaded_skill` | 从 MinIO 读 `SKILL.md` 全文 |
| 记忆 | `maybe_write_user_memory` / `read_agent_memory` | 用户级 `MEMORY.md` |

详细提示词片段与调用链见 [Agent Skills 实现 §10–§11](../implementation/agent-skills-implementation.md)。

**浏览器自动化**：启用 `AGENT_BROWSER_ENABLED` 后，可用 `browser_*` 工具族；v4.8.6 起由父层通过 `invoke_context_subagent(kind=execute)` 委托执行（无独立 `rpa` 专精）。详见 [浏览器 RPA 实现](../implementation/browser-rpa-implementation.md)。

### 4.9 切片管理 / 编码管理

- **切片管理**：侧栏入口，iframe 或原生列表管理 chunk（管理员/有权限用户）。  
- **编码管理**：系统设置内 KnowFlow 编码规则配置（管理员）。

---

## 5. PDF 翻译

### 5.1 流程

1. 用户在上传文件或从文档库选择 PDF，配置源语言、目标语言、翻译引擎。  
2. API 将文件转发至 **pdf2zh-api** 创建远程 job，获得 `pdf2zh_job_id`。  
3. 平台创建 **Job** 记录（类型 `pdf_translate`，状态 running），并投递 Celery **`monitor_translate_job`**。  
4. Worker 周期性拉取 pdf2zh 进度，更新 Job 的 `progress`、`stage`、输出文件路径。  
5. 完成后用户下载译稿，或 **导入文档库**（写入 MinIO + DocumentVersion，可选 sync KnowFlow）。

### 5.2 状态与通知

- 前端任务面板 / 翻译页轮询 Job 状态。  
- 终态（done / failed / cancelled）写入通知（可选）。  
- pdf2zh 首次启动需 **BabelDOC warmup**（约数分钟）。

---

## 6. 文档对比

### 6.1 跨文档差异对比

1. 用户选择两份已有 **query 权限** 的文档（左右栏）。  
2. 创建 **compare job**（异步），后台抽取已解析正文。  
3. **LLM 对比**（`compare_llm_service`）或块级 diff 引擎归纳增删改，结果存 Job payload。  
4. 前端多栏预览 + 荧光高亮 + 侧栏差异列表联动滚动。  
5. **不触发建索引**：对比仅使用文档库已有解析/向量索引；须先完成上传与 KnowFlow 同步。

### 6.2 单文档版本对比

- 上传完成时后台预计算**相邻版本对** diff，前端经 `GET .../version-compare/adjacent` 只读加载。  
- 支持版本差异问答（基于入库 diff + LLM 总结）。

### 6.3 自然语言检索（对比内）

- 在已选文档范围内，用 NL 问句检索。  
- 平台先算 ACL 白名单 document_id 列表，再调 KnowFlow retrieval 或本地字段匹配。  
- 命中 chunk 在预览栏高亮（与 diff 色系区分）。

---

## 7. 语音转写

1. 用户上传音频或录音，请求 **speech-api**（FunASR）。  
2. 返回带时间轴的文本与说话人分离结果（视模型配置）。  
3. 可选调用 **DeepSeek** 生成会议摘要。  
4. 结果可保存为文档或订阅条目。

模型文件位于 `data/speech-models`（Docker 卷或宿主机目录）；首次启动自动下载，体积较大。

---

## 8. 订阅与内容导入

| 来源 | 实现要点 |
|------|----------|
| RSS / 网站 | 定时或手动抓取 → HTML → Markdown → `subscription_items` |
| 微信公众号 | 专用抓取与解析流程 |
| 导入文档库 | `buildImportToPersonalLibraryBody`：scope=personal，可选 sync KnowFlow |

导入后走与普通上传相同的 MinIO + 可选索引流程。

---

## 9. 异步任务与 Job 体系

| 类型 | 执行方式 | 说明 |
|------|----------|------|
| pdf_translate | Celery 监控 pdf2zh | `monitor_translate_job` |
| delete_document | Celery | 清理存储与索引 |
| compare | BackgroundTasks 或 Job 服务 | 大 diff 不阻塞 HTTP |
| KnowFlow catalog reconcile | 登录后后台 / 定时 | 对齐 dataset 与文档 |

**Redis** 作 Celery broker；Worker 与 API 共用 `platform/.env`。  
远程开发时：若 Redis 上已有 Worker 则不再本地启动；否则本机 Worker 连远程 Redis（见 `./dev.sh local`）。

Job 统一模型：`Job` 表存 type、status、progress、payload、error_message；前端 **JobsPanel** 与 SSE 事件推送进度。

---

## 10. 系统功能插件（前端入口）

后端 `platform/app/features/builtin/` 注册插件，前端 `SystemFunctionsView` 按 **文档 / 工具 / 智能** 分类展示。

| 功能 id | 用户可见能力 |
|---------|----------------|
| pdf_translate | PDF 科学翻译 |
| doc_compare | 文档对比 |
| knowledge_search | 知识检索 |
| ai_home | AI 智能体 |
| ontology | 本体图谱 |
| report_generation | 报告生成 |
| smart_data_query | 智能问数 |
| carbon_qa | 领域问答 |
| ocr | 文件内容提取 |
| speech_to_text | 会议转写 |
| data_analysis | 数据分析 Notebook |
| agent_skills | Agent Skills 管理（内置启停、上传包、记忆） |
| knowflow 相关 | 切片管理、编码管理等 |

未授权的功能码不在列表出现；路由层 `require_feature` 与菜单双重拦截。

---

## 11. 系统设置与说明文档

| 模块 | 实现 |
|------|------|
| 用户 / 部门 / 角色 | CRUD + RBAC 种子 |
| 模型与资源配置 | 在线配置 LLM、Embedding、Rerank、OCR、KnowFlow 地址；保存前可连通性测试 |
| 系统说明文档 | 读取仓库 `docs/` 与根目录《运维部署指南》；Markdown + **Mermaid** 渲染 |
| 操作审计 | 登录、文档、翻译等写 `audit_log` |
| 在线用户 | Redis 会话 + 心跳（若启用） |

公开配置 `GET /system/client-config` 供前端启动拉取主题、API 根路径等。

---

## 12. 前端架构要点

| 项 | 说明 |
|----|------|
| 路由 | Vue Router，`/ai/` base path |
| API | 域模块拆分（`documents.js`、`translate.js` 等）；开发态走 Vite 代理 `/ai/api` |
| 布局 | MainLayout + FeatureSubsystemShell；功能页统一顶栏与本地导航 |
| 状态 | composables（`useAuth`、`usePlatformUi` 等） |
| KnowFlow | iframe + embed-session；Vite 代理 `/ragflow-ui`、`/v1` |
| UI | Naive UI + Liquid Glass 主题；全局视频背景可选 |

保存前端文件后 **Vite HMR** 即时刷新；改 API 后 **uvicorn --reload** 自动重载（开发模式）。

---

## 13. 资源管理与语音合成

### 13.1 资源管理（管理员）

- 入口：**系统设置 → 资源管理**（需 `admin.user` 或系统管理员）。
- 配置项：语言模型、嵌入、VL、Rerank、OCR-VL、**语音合成**、语音识别、PDF 翻译、RAGFlow/KnowFlow、SearXNG 等。
- 数据存 `platform_model_settings` 单例 JSON；`.env` 中 `PLATFORM_*` 仅作首次引导，运行以页面保存为准。
- 保存后可对单项做 **连通性测试**（`POST /admin/model-settings/health/test`）。
- 普通成员侧栏不可见，API 无 `admin.user` 返回 403。

### 13.2 语音合成

- 功能页：**系统功能 → 语音合成**（`feature.text_to_speech`）。
- TTS 优先读资源管理 `tts_*`；未单独配置时从支持 `/audio/speech` 的兼容端点（如嵌入/VL）借用 URL/Key。
- 合成接口：`POST /api/v1/text-to-speech/synthesize`；元数据 `GET .../meta`。

### 13.3 远程代码同步

- 本机 `./dev.sh sync`：rsync `platform/app` 到服务器并 **重启 API / Worker**。
- `./dev.sh sync --frontend`：额外 build `dist` 并 nginx reload（挂载静态资源，不重建前端镜像）。

---

## 14. Agent Skills 管理

**面向谁**：系统管理员或有 `feature.agent_skills` 权限的用户。

| 能力 | 说明 |
|------|------|
| 内置 Skill | 14 项平台能力；4 项在对话中可执行（联网、文档、图谱、综合检索），其余引导去功能页 |
| 上传包 | ZIP 或文件夹，含 `SKILL.md`；存对象存储，全员共享（scope=system） |
| 启停 | 内置用 binding 表；上传包用 enabled 字段 |
| 用户记忆 | 每用户一份 `MEMORY.md`，对话中可「请记住…」或工具读写 |

**上传后如何生效**：启用 → `build_agent_catalog_prompt` 写入 Discovery 目录 → 模型在任务匹配时调用 `load_uploaded_skill`。

示例包：`examples/agent-skills/mermaid-diagram/`（教模型如何输出 Mermaid 图）。

---

## 15. AIP 智能体互联（v4.6.0）

**面向谁**：需与外部智能体互通的部署方；管理员配置 SK 密钥与外部智能体登记。

| 能力 | 说明 |
|------|------|
| 发现 | `GET /api/v1/aip/discover` — 列出内置专精与已登记外部智能体（ACDL） |
| 调用 | `POST /api/v1/aip/interact` / `interact/stream` — 同步或流式 handoff |
| SK 密钥 | `GET/POST/DELETE /api/v1/admin/aip/keys` — GB/Z 185.3 身份密钥 |
| 外部登记 | Agent Skills 管理页 — `/admin/agent-skills/external-agents` |
| 执行层 | `agent_aip_executor` — supervisor 调度内置 hop 或外部 HTTP |

配置项：`AIP_ENABLED`、`AIP_SERVICE_BASE_URL`、`AIP_EXTERNAL_AGENTS_JSON`（见 `platform/.env.example`）。

---

## 16. PostgreSQL 读写分离

平台在 `app/database.py` 实现可选读写分离：

| 组件 | 说明 |
|------|------|
| `DATABASE_URL` | 主库（读写） |
| `DATABASE_READ_URL` | 只读副本；**留空时读写均走主库** |
| `get_db()` | 写路径：创建/更新/删除、事务提交 |
| `get_read_db()` | 读路径：列表、详情等只读查询 |
| `read_session_factory()` | 有副本用副本 Session，否则回退 `SessionLocal` |
| `run_db_read_task()` | 异步线程池中执行只读 DB 任务（同 `get_read_db` 路由） |

**已接入 `get_read_db` 的 API**（节选）：

- `documents/listing.py` — 文档列表、文件夹树、回收站列表等  
- `documents/crud.py` — `GET` 文档详情  
- `system.py` — 客户端配置、功能列表等读接口  

Celery Worker、流式对话中的写操作（如 `platform_chat_store.append_turn`）仍使用主库 `SessionLocal`。

生产启用：在 `platform/.env` 配置 `DATABASE_READ_URL` 指向 PostgreSQL 只读副本（流复制或云厂商只读实例），连接池参数与主库共用 `DB_POOL_*`。

---

## 17. 理财助手与股市分析（v4.8.6）

**面向谁**：有理财助手功能权限的用户；对话中也可路由到 `stock` 专精智能体。

| 能力 | 说明 |
|------|------|
| 行情与自选 | A 股/基金/虚拟币行情；`finance_watchlist_items` 自选清单 |
| AI 报告 | 深度解读、多角色圆桌（辩论/专业 × 基本面/短线）、量价会诊；异步 Job 生成 |
| 原子工具 | `stock_quote` / `stock_kline` / `market_indices` / `finance_search` / `f10_data` |
| 专精 Agent | `stock`（`agents/instructions/stock.md`）；F10 底稿经 AKShare 结构化拉取 |
| 分享 | 报告支持 `share_token` 免登录 HTML 预览 |

入口：前端 `FinanceAssistantView`；API `app/api/finance.py`；服务 `finance_service` / `finance_f10` / `finance_factsheet`。

---

## 18. 双碳助手（v4.8.6）

**面向谁**：有双碳助手功能权限的用户；对话可路由到 `carbon` 专精智能体。

| 能力 | 说明 |
|------|------|
| 看板 | 碳交易快照、碳价/政策/多维数据查询 |
| AI 报告 | 碳交易简报、政策摘要、减碳策略；写入 `carbon_reports` |
| 原子工具 | `carbon_price` / `carbon_policy` / `carbon_data` |
| Skill | `carbon-consulting` 上传型/内置包与示例包同步 |

入口：前端 `CarbonAssistantView`；API `app/api/carbon_assistant.py`；服务 `carbon_assistant_service` / `carbon_service`。

---

## 19. 工作笔记与提示词管理（v4.8.6）

| 模块 | 能力 | 落点 |
|------|------|------|
| 工作笔记 | 文件夹、Markdown 编辑、图片粘贴、AI 润色、发布至文档库、待办子 Tab | `NoteView` · `note_service` · 表 `notes` / `note_folders` |
| 提示词管理 | 个人模板 CRUD、按类别筛选、一键复制 | `PromptManagementView` · `prompt_service` · 表 `prompt_templates` |

二者均注册为 builtin FeaturePlugin，菜单与权限由功能注册表驱动。

---

## 20. 公开分享（share_token，v4.8.6）

文档、笔记、理财报告、碳报告统一使用 `share_token`：

1. 登录用户在详情页/`ShareLinkModal` 生成或撤销链接。  
2. 免登录 `GET` 公开路由渲染 HTML 预览（`document_share_render` / `note_share_render` / 各报告 render）。  
3. Schema 迁移为各实体增加 `share_token` 列（唯一索引）。

---

## 21. 与外部系统关系

| 系统 | 关系 |
|------|------|
| pdf2zh_next / BabelDOC | 独立 HTTP 服务，平台只调 REST |
| KnowFlow / RAGFlow | 向量库 + 原厂 UI；平台 SSO + 同步 + ACL |
| DeepSeek 等 | 在线 LLM，API Key 在 `.env` 或资源管理 |
| AKShare | 金融 F10 / 行情结构化拉取（理财与股市 Agent） |
| 设计系统（:40001） | 智能问数等 iframe 外链，独立 upstream |
| Dify（若同机） | 端口 40001 预留，与平台栈分离 |

---

## 相关文档

- [系统架构](architecture.md)
- [权限与账户](permissions.md)
- [知识库实现](../implementation/knowledge-implementation.md)
- [报告生成实现](../implementation/report-generation-implementation.md)
- [Agent 架构](../agent-architecture.md)
- [设计哲学](../agent-philosophy.md)
- [Agent Skills 实现](../implementation/agent-skills-implementation.md)
- [文档对比产品设计](../platform/doc-compare-product-design.md)
