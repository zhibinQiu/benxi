# 功能实现说明（v4.0.7）

> **本文描述当前已实现功能的运行方式与数据流，不含代码。**  
> 架构分层见 [系统架构](architecture.md)；文档库细节见 [文档库实现](../implementation/documents-implementation.md)。

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

**与传统单向量 RAG 的差异**：长文档优先用 PageIndex 在目录树中定位章节，而非仅依赖 chunk  embedding 相似度；报告生成走多轮子问题规划，而非检索页的单轮短答。

---

## 1. 总体原则

| 原则 | 含义 |
|------|------|
| 平台是唯一控制面 | 用户、组织、文档元数据、权限、任务状态存在 **PostgreSQL**；二进制文件在 **MinIO** |
| 重计算外置 | PDF 翻译走 **pdf2zh-api**；向量检索与切片走 **KnowFlow/RAGFlow**；长时任务走 **Celery Worker** |
| 功能插件化 | 每个业务能力注册为 `FeaturePlugin`：挂载 API 路由、写入权限码、出现在「系统功能」列表 |
| 权限先于能力 | 所有文档相关操作先过 `can_*_document`；KnowFlow 侧通过 dataset / KB ACL 与平台 scope 对齐 |
| 异步不阻塞交互 | 翻译、大文档删除、对比 diff 等创建 **Job** 后轮询或 SSE；HTTP 请求快速返回 |

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
| team | 小组级 | depth=2 | 绑定节点子孙子树 + `doc.read` |
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

同一问题可对不同文档 **按引擎分区** 后合并 hits（`retrieve_hits_for_qa`），可选 Agentic 模式由 LLM 规划多轮子问题再检索。回答可切换 **思维导图** Tab（Mermaid），便于结构化浏览。

#### 与本体图谱联动

问答前若用户具备 `feature.kg_palantir`，会从问题中 **匹配实体 mention**，扩展 2 跳子图，将结构化关系追加到 LLM 上下文（引用编号与文档片段顺延）。

### 4.6 本体图谱

1. **本体建模**：管理员/用户配置实体类型（组织、人员、法规、项目等）与关系类型（包含、引用、约束…）。  
2. **自动抽取**：文档索引完成后，可选 LLM 从正文抽取实体/关系写入 PostgreSQL（`kg_entities` / `kg_relations`）。  
3. **工作台**：`KgPalantirView` 三栏——实体查询、关系子图、详情编辑；支持按类型浏览、跳数控制子图范围。  
4. **下游消费**：知识检索、报告生成、**AI 智能体** 在回答前调用 `retrieve_kg_context_for_question`，将图谱事实与文档片段一并注入 prompt。

### 4.7 报告生成（区别于短答式 RAG）

| 维度 | 知识检索（短答） | 报告生成 |
|------|------------------|----------|
| 目标 | 单轮精准回答 + 引用 | 万字级长报告，分章节交付 |
| 召回 | 单次 top-k hits | Agent 规划多轮子问题，多路召回后去重合并 |
| 生成 | 一次 LLM 归纳 | 按章节 Agent 扩写，可联网补充（可选） |
| 输出 | 对话气泡 + 思维导图 Tab | 报告正文 Tab + **思维导图 Tab**，支持导出 Word / Markdown 大纲 / OPML（XMind） |

实现：`report_generation_service` 复用 `retrieve_hits_for_qa` 与 `KnowledgeAgenticToolkit`；思维导图经 `generate_report_mindmap`（LLM 结构化或 Markdown 本地回退）。

### 4.8 AI 智能体

- 入口：默认首页 `/ai-home`，插件 `ai_home`。  
- 对话：`ai_chat_service` 调用 DeepSeek；流式 SSE 与引用卡片对齐知识检索页。  
- **增强上下文**（按用户权限自动启用）：  
  1. 有 `feature.knowledge_search`：在最多 20 份可 query 文档内调用 `retrieve_hits_for_qa`；  
  2. 有 `feature.kg_palantir`：解析问题实体并扩展子图；  
  3. 文档片段与图谱上下文 **合并编号** 后写入 system prompt。  
- 落地页快捷入口：**知识检索 → 报告生成 → 本体图谱**。

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

### 6.1 差异对比（Diff）

1. 用户选择 2–4 份已有 **query 权限** 的文档，指定基准版。  
2. 创建 **compare job**（异步），后台抽取文本层或 KnowFlow 解析文本。  
3. **版本块 diff 引擎** 计算增删改，结果存 Job payload。  
4. 前端多栏预览 + 荧光高亮 + 侧栏差异列表联动滚动。

### 6.2 自然语言检索（对比内）

- 在已选文档范围内，用 NL 问句检索。  
- 平台先算 ACL 白名单 document_id 列表，再调 KnowFlow retrieval。  
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
| kg_palantir | 本体图谱 |
| report_generation | 报告生成 |
| smart_data_query | 智能问数 |
| carbon_qa | 领域问答 |
| ocr | 文件内容提取 |
| speech_to_text | 会议转写 |
| assist_writing | 辅助写作 |
| data_analysis | 数据分析 Notebook |
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
- TTS 优先读资源管理 `tts_*`；未单独配置时从支持 `/audio/speech` 的兼容端点（如嵌入/VL）借用 URL/Key，**不会**回退 DeepSeek 等纯 LLM。
- 合成接口：`POST /api/v1/text-to-speech/synthesize`；元数据 `GET .../meta`。

### 13.3 远程代码同步

- 本机 `./dev.sh sync`：rsync `platform/app` 到服务器并 **重启 API / Worker**。
- `./dev.sh sync --frontend`：额外 build `dist` 并 nginx reload（挂载静态资源，不重建前端镜像）。

---

## 14. 与外部系统关系

| 系统 | 关系 |
|------|------|
| pdf2zh_next / BabelDOC | 独立 HTTP 服务，平台只调 REST |
| KnowFlow / RAGFlow | 向量库 + 原厂 UI；平台 SSO + 同步 + ACL |
| DeepSeek 等 | 在线 LLM，API Key 在 `.env` 或资源管理 |
| 设计系统（:40001） | 智能问数等 iframe 外链，独立 upstream |
| Dify（若同机） | 端口 40001 预留，与平台栈分离 |

---

## 相关文档

- [系统架构](architecture.md)
- [权限与账户](permissions.md)
- [知识库实现](../implementation/knowledge-implementation.md)（待补充细节时可读源码 `domains/knowledge/`）
- [文档对比产品设计](../platform/doc-compare-product-design.md)
