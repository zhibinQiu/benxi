# 发布说明

## 4.6.0（v4.6.0）— AgentKit 包拆分、智能体开发套件与平台稳定增强

- **AgentKit 包拆分**：将多智能体核心组件拆分为 11 个独立 Python 包（agentkit-aip、agentkit-loop、agentkit-mcp、agentkit-message、agentkit-orchestrate、agentkit-route、agentkit-skills、agentkit-subagent、agentkit-tools、agentkit-interrupt、agentkit 元包），支持按需 pip 安装、独立版本管理与 PyPI 发布
- **AgentKit 文档**：新增各子包 README（含快速开始、API 概览与示例代码）、CHANGELOG（含版本演进追溯）与 py.typed 类型标记
- **循环工程（Loop Engineering）**：`LoopExitRequest` 规划器集成、`dict_evidence_provider` 工厂、`build_loop_exit_prompt_messages` 动态 Prompt 组装，替代传统静态提示词工程
- **AIP 协议层**：会话总线 `AipSessionBus` 支持顺序/并行 handoff、多 hop 编排辅助（`merge_hop_citations`、`best_reply_from_hops`）与外部智能体互操作
- **MCP 客户端**：轻量 HTTP/SSE 异步客户端（`McpClient`），零平台耦合，支持 token 压缩与自定义传输
- **Subagent 运行时**：隔离上下文子 Agent 并行 explore 与 tool 循环，Protocol 注入宿主能力（LLM、Tool、Skill）
- **Skill 插件框架**：统一注册表、MCP 桥接、关键词搜索与路由格式化
- **工具层**：声明式 `ToolRegistry`、Pydantic Schema 生成、参数校验与结果压缩
- **中断管理**：`InterruptStore` Protocol + HITL 响应盒，支持 Checkpoint 持久化与恢复
- **消息解析**：DSML 内嵌工具调用提取、流式过滤、多轮上下文裁剪与追问检测
- **平台稳定**：文档同步、架构说明、运维手册与版本号统一更新至 v4.6.0
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.6.0）

## 4.5.0（v4.5.0）— AIP 智能体互联、功能收敛与 UI 扁平化

- **AIP（GB/Z 185）**：发现 `/aip/discover`、ACDL 读取、同步/流式 `interact`；SK 密钥管理（`/admin/aip/keys`）；外部智能体登记（Agent Skills 管理页）；`agent_aip_executor` 统一内置专精 hop 与外部 HTTP 调用
- **报告类型 Skills**：6 种 `report-*` 示例包 + 启动种子，report 专精智能体在 AI 首页对话中选用
- **功能收敛**：移除碳资产行情、辅助写作独立页；公众号 Feed 合并至「网站收藏」订阅页；清理碳市场遗留表与孤儿 `feature.*` 权限
- **前端 UI**：ChatGPT 式 solid shell（`solid-shell.css` / `openai-style.css`）；结论区 `AssistantConclusionContent`；对话复制/分享；登录页独占视频背景
- **Agent 增强**：`agent_message_parse` DSML 净化与流式过滤；`AgentLoopSession` 短 DB 会话（延续 4.4.1）
- **代码收敛**：删除重复 `/admin/aip/external-agents` 路由（统一走 `/admin/agent-skills/external-agents`）；移除 TypewriterText、FeaturePageToolbar、ChatFloatingCitations 等废弃组件
- **文档同步**：架构、测试、部署与版本号统一更新至 v4.5.0
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.5.0）

## 4.4.1（v4.4.1）— 运行时瘦身与架构收敛

- **连接池**：对比任务 SSE 鉴权后立即归还请求级 DB 连接；启动引导改在线程池执行，避免阻塞 asyncio 事件循环
- **Agent 短会话**：`AgentLoopSession` 在 LLM/外部 I/O 前释放连接；`iter_agent_tool_loop` / `iter_supervised_agent_loop` 不再长占 `SessionLocal`；报告撰写流式路径对齐
- **路由信号**：`agent_routing_signals` 集中浏览器/调度/复合句等 regex，planner 与 supervisor 共用
- **Schema 修复**：补挂 `backfill_ragflow_version_links` 一次性回填补丁；全量迁移去除与 light 路径重复的索引 DDL；启动时清理未注册插件的孤儿 `feature.*` 权限
- **启动优化**：示例 Agent Skill 种子在全部已启用时跳过磁盘扫描；进程退出时释放 `last_seen` 线程池
- **死代码**：移除未使用的 `run_db_async_task`；清理已下线功能遗留配置（如碳市场同步 env）
- **前端内存**：知识检索/报告生成视图异步分包加载；KeepAlive 仅保留 1 个活跃面板；Header 飞层面板异步加载；对话面板失活时中止流式请求
- **前端请求**：知识库范围树改为进入知识功能路由后再预取；统一 Job SSE 订阅工厂；订阅页卸载时清理搜索 debounce 定时器
- **压测工具**：新增 `platform/scripts/stress_test_throughput.py`，覆盖读 API 并发、持续读压与文档解析入队；自动清理 `__stress_test__` 测试数据
- **容量说明**：文档补充连接池与 200 人在线/瞬时并发的规划建议（单 worker 约 40 连接上限）
- **文档同步**：架构、测试、部署与版本号统一更新至 v4.4.1
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.4.1）

## 4.4.0（v4.4.0）— 全栈轻量化与代码收敛

- **依赖精简**：移除未使用的 `alembic`、`passlib`、`requests`；密码哈希改为显式 `bcrypt` 依赖
- **死代码清理**：删除空服务/组件（`audit_display`、TypewriterText、FeaturePageToolbar 等 8 个文件）
- **API 复用**：知识检索流式问答改用 `createPlatformChatStream` 工厂，消除 ~70 行重复 SSE 解析
- **Locale 收敛**：移除已废弃的 `wechatMpFeed` / `wechatMpArticle` 国际化键（功能已合并至订阅页）
- **文档同步**：版本号、架构说明、测试指南、升级手册统一更新至 v4.4.0
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.4.0）

## 4.3.2（v4.3.2）— 智能体编排、流式体验与 Mermaid 加固

- **父智能体任务编排**：新增 `agent_orchestrator.py`，多路由复合任务默认顺序执行；workflow 推送 `plan_tasks` / `task_*` 事件；前端 checklist 展示子任务进度
- **提示词精简**：常驻/专精/规划器 system prompt 收敛为短约定；子任务 `task_mode` 只调工具、由调度层汇总最终回答
- **流式 UX**：中间 hop 不下发 `replace`；顺序 `workflow_finished` → `replace` → `done`；回答区仅展示最终结论
- **Agent 记忆**：`MEMORY.md` 每轮注入 system，「以记忆为准」覆盖默认自称
- **Mermaid 渲染加固**：语法自动清洗 + 三档重试；保留源码占位避免重挂载空白；视口内即时渲染
- **代码清理**：修复 `agentWorkflow.js` 任务清单处理；移除无效引用；富媒体 DOM 生命周期统一
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.3.2）

## 4.3.1（v4.3.1）— 知识检索模块化、功能收敛与 Agent 工具链增强

- **知识检索问答模块化**：`knowledge_qa_service` 拆分为 `knowledge_qa/` 子包（检索、生成、引用、预览、流式等），对外 API 保持不变
- **知识检索 UI 收敛**：移除独立 `KnowledgeQaView`，统一由 `KnowledgeSearchView` 承载问答与检索
- **移除系统文档模块**：删除 `system_docs` API/服务/管理页及前端 `SystemDocContent`
- **移除公众号资讯页**：删除 `WechatMpArticleView` / `WechatMpFeedView` 独立路由
- **Agent 工具链**：新增 `agent_tool_context`、`workflow_events`；tool loop 与技能路由增强
- **文档权限批量**：`documents/access_batch` 支持批量访问校验
- **列表页体验**：通用 `ListTableFooter`；订阅/用户/部门列表分页与页脚统一
- **API 请求作用域**：`requestScope.js` 统一请求上下文传递
- **代码收敛**：删除 `WebSearchResultDrawer`、`knowledge_qa` builtin feature 等冗余路径
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.3.1）

## 4.2.1（v4.2.1）— Agent Skills 架构升级与系统文档

- **Agent Skills 框架**：内置 14 项能力注册表（4 READY + 10 STUB）；上传型 Skill 包（ZIP/文件夹/`SKILL.md`）；Discovery 常驻目录 + Activation 按需 tool 调用
- **浏览器 RPA（Phase 1）**：Playwright 会话与 `browser_*` 工具族；对话探索录制 → Skill 固化；`INSTALL_BROWSER` / `AGENT_BROWSER_ENABLED` 可选启用
- **AI 智能体**：统一 `iter_agent_tool_loop`；`research` 综合 KB/KG/联网；对话历史预算与富内容生命周期优化
- **报告生成**：万字长报告流式生成；独立实现文档与 Agent 多路召回扩写链路
- **管理端**：`AgentSkillsView` — 内置启停、上传包、用户记忆；API `/admin/agent-skills`
- **版本更新弹窗**：登录后从 `RELEASE.md` 解析最新版本亮点，首次登录展示 `ReleaseHighlightsModal`
- **代码收敛**：删除未使用的 skill 路由、预检索 helper 与冗余 catalog 封装
- **系统文档**：新增 [Agent Skills](docs/zh/implementation/agent-skills-implementation.md)、[报告生成](docs/zh/implementation/report-generation-implementation.md)、[浏览器 RPA](docs/zh/implementation/browser-rpa-implementation.md) 实现说明；更新功能实现说明与架构总览
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.2.1）

## 4.1.1（v4.1.1）— 知识库去品牌化、索引增强与 AI 默认联网

- **产品去品牌化**：前台与资源管理文案统一为「知识库 API / 扩展后台 / MySQL」，去除 RAGFlow、KnowFlow 等对外展示名称
- **AI 智能体**：SearXNG 可用时默认联网检索；本地文档/图谱与联网摘要交叉验证；仅寒暄、平台操作说明等明确场景跳过联网
- **文档索引**：Word/Markdown/纯文本上传自动选用 Plain Text 版面；Office 转 PDF 失败时回退 Markdown 上传；版本索引元数据叠加 PageIndex 状态
- **用户管理**：用户列表 API 与前台分页（默认 20 条/页）
- **部署**：nginx 使用 Docker 内置 DNS 与变量 upstream，避免依赖容器未就绪时启动失败；`/ai/index.html` 禁用缓存
- **体验**：文档上传弹窗间距微调
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.1.1）

## 4.0.10（v4.0.10）— AI 智能体联网检索、Markdown 渲染与引用对齐

- **AI 智能体联网检索**：实时行情/价格类问题（如碳价）自动调用 SearXNG 联网搜索；本地知识库未命中时 fallback 联网补充；工作流展示 `web_search` 步骤并支持网页引用
- **Markdown / Mermaid**：统一 `markdown.js` 与 `mermaidRender.js` 渲染链路，对话与报告场景复用
- **引用对齐**：正文 `[n]` 与底部引用列表顺序重映射；无正文引用时不展示多余引用卡片
- **通知**：「全部已读」合并为清空通知列表，移除独立 clear 接口
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.10）

## 4.0.9（v4.0.9）— 测试修复、代码收敛与版本清理

- **测试基础设施**：新增 `test_support` 模块，修复 PyPI `tests` 包命名冲突导致的用例收集失败；补充 `llm_parse` / `text_utils` 单测
- **公共模块**：LLM JSON 解析与文本截断收敛至 `app/core/llm_parse.py`、`app/core/text_utils.py`，对比与 Agentic 检索复用
- **对比 API 精简**：移除废弃的 `sync_knowflow` 参数与 `version-compare/batch` 端点；前端删除未使用的对比 API 封装
- **前端清理**：删除 `roseLoader.js`、`featureDescriptions.js`、`useUiMessage.js` 等无引用模块
- **文档**：运维/架构文档版本号与 `dev.sh local` 命令表述统一
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.9）

## 4.0.8（v4.0.8）— 问题登记、KnowFlow 队列治理与知识闭环增强

- **问题登记**：新增问题登记模块（`/issue-reports`），成员可提交问题描述，管理员可标记已修复
- **KnowFlow 队列治理**：解析队列监控（MySQL task + Redis lag）、看门狗与入队前 parse 守卫，避免重复解析；系统监控页展示积压与重复文档概览；运维脚本 `knowflow-queue-reset.sh`、`knowflow-dedupe-documents.py` 与健康检查
- **本体图谱**：用户与部门组织树自动同步至知识图谱实体
- **文档上传**：上传时可选择目标库、文件夹与归属范围（`DocumentUploadLocationPicker`）
- **待办事项**：独立待办面板与页面（`TodosPanel` / `TodosView`）
- **登录体验**：登录后统一进入 AI 智能体首页，不再恢复退出前页面
- **订阅与资讯**：订阅条目管理、导入与 AI 摘要增强；菜单设置与系统监控迭代
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.8）

## 4.0.7（v4.0.7）— AI 智能体、本体图谱与知识闭环

- **AI 智能体**：原「AI 助理」更名为 AI 智能体；落地页快捷入口调整为知识检索 → 报告生成 → 本体图谱；回答时联合权限内文档检索与本体图谱上下文
- **本体图谱**：实体查询 / 本体设置选中态玻璃效果完整覆盖列表行；辅助写作归入工具分类
- **登录宣传**：强调本体图谱、知识沉淀闭环；补充 PageIndex + 向量混合检索 vs 传统 RAG、报告生成思维导图导出能力
- **系统文档**：功能实现说明补充知识闭环、检索引擎、图谱联动与 AI 智能体上下文合并
- **清理**：移除 third_party pageindex 构建产物；修正过时注释与默认版本引用
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.7）

## 4.0.6（v4.0.6）— 语音合成、资源管理权限与远程同步

- **语音合成**：内置文本转语音功能；资源管理独立「语音合成」配置项；TTS 凭证不再误回退 DeepSeek，可从嵌入/VL 等兼容端点自动借用；功能页不展示服务商品牌名
- **资源管理权限**：`GET/PUT /admin/model-settings` 及连通性探测需 `admin.user`；侧栏入口与用户/菜单管理同级，普通成员菜单中不可见
- **远程开发同步**：`./dev.sh sync` 默认重启服务器 API / Worker；`--frontend` 挂载 dist 构建后 nginx reload
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.6）

## 4.0.5（v4.0.5）— 品牌统一为「企业 AI 知识库平台」

- **产品命名**：前台、侧边栏、登录页、API 默认 `APP_NAME`、KnowFlow 白标、环境模板与文档统一为「**企业 AI 知识库平台**」
- **登录页**：宣传页 + 顶栏弹窗登录/注册；功能介绍全屏滚动；对比表客观描述市面方案差异
- **数据库迁移**：旧标题（含「AI 办公系统」「企业 AI 办公平台」等）自动迁移为当前产品名
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.5）

## 4.0.4（v4.0.4）— 架构收敛、PageIndex 默认重索引与实现文档

- **高内聚低耦合**：知识域统一经 `KnowledgeGateway`；解析器/索引栈规则收敛至 `knowledge_parser_service`；用户可见错误经 `user_messages`；后台 Job 调度经 `background_job_dispatch`
- **PageIndex**：保留结构索引、树检索与引用预览；移除系统功能页独立卡片（入口在文档详情「重新索引」）；重新索引默认分块为 PageIndex（与上传默认 naive 分离）
- **KnowFlow**：弃用前端 embed 与双份主题；保留 API、登录预热与原生知识检索页
- **性能**：CompareView 并行拉取、KnowledgeScopeTree 软刷新、Celery worker 调优、后台任务去重
- **LLM**：DeepSeek chat 统一封装，PageIndex / 知识问答复用
- **文档与注释**：重写知识服务、异步任务、前端结构实现说明；核心模块补充函数实现思路 docstring
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.4）

## 4.0.3（v4.0.3）— 品牌统一、PageIndex 实验集成与知识检索增强

- **品牌与系统功能**：产品统一为「AI 办公系统」；系统功能说明精简，AI 助理与功能分类面向通用办公；移除智碳平台 V3、智碳 AI v1 等遗留外链插件
- **PageIndex（实验）**：自托管树形索引（`pageindex_version_links` + `PAGEINDEX_WORKSPACE_DIR` JSON）；与 KnowFlow 向量检索并存、按文档自动切换；支持 PDF/Markdown/Word/TXT；知识检索引用页级整页预览
- **知识检索**：`KnowledgeSearchPanel` 与引用卡片 UI（文件名、页码、类型标签）；智能回答与引用区宽度对齐；思维导图 Tab
- **报告生成 / 菜单设置 / 知识图谱**：内置报告生成、菜单配置、本体与知识图谱等能力迭代
- **部署**：Gateway 模式（`compose.gateway.yaml`）；远程依赖暴露编排增强；Celery worker 并发调优
- **文档**：运维/架构文档同步现状，去除绿叶表述
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.3）

## 4.0.2（v4.0.2）— 文档存储一致性、OCR 与对比体验

- **文档存储**：上传完成前校验 MinIO 对象存在与大小；对账脚本新增 `missing_storage_versions` 扫描；`stack.sh restore` 在缺少 MinIO 备份时告警
- **重新索引**：默认不再全量 `resync`，在 KnowFlow 已有副本时仅切换解析器；MinIO 缺失时返回中文可读错误
- **OCR**：平台 OCR 服务与前端 `OcrView`、模型设置联动
- **文档对比**：PDF 预览与高亮（`ComparePdfPreview`）；对比检索与文本提取增强
- **知识库**：索引任务取消、解析等待与 scope 树缓存优化；系统功能开关（`useSystemFeatures`）
- **体验**：Liquid Glass 可选态样式、登录/鉴权错误提示、后台任务与文档中心 UI 迭代
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.2）

## 4.0.1（v4.0.1）— 品牌统一、开发入口精简与知识库一致性

- **品牌统一**：产品名统一为「绿叶 AI 办公系统」（前端标题、KnowFlow 白标、运维文档）
- **开发入口**：`./dev.sh` 为唯一入口（`local` / `docker` / `remote-dev` / `stack` / `deploy`）；移除 `benxi.sh`、`start-local.sh` 等旧脚本
- **知识库一致性**：新增 `knowledge_data_reconcile_service`（孤儿链接清理、MinIO 对账、增量复用）；文档库对齐修复个人级 `owner_id` 筛选
- **文档中心**：上传弹窗支持选错文件后重新选择（`FileDropZone` 替换受限 `n-upload`）；批量上传移除 max 禁用问题
- **模型与订阅**：模型设置与资源健康检测增强；订阅 API 与前端迭代
- **部署运维**：Compose 与远程依赖脚本更新；运维/架构文档同步现状
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.1）

## 4.0.0（v4.0.0）— 文档权限三档重构、知识库索引修复与全栈升级

**大版本**：权限体系重置、KnowFlow 登记可靠性、知识检索与部署架构全面升级。

- **文档权限三档**：统一为 **可见 / 可查 / 可修改**（`visible` / `query` / `modify`）；旧 `edit` / `full` / `use` / `delete` 别名归并至 `modify`；组织分级成员（公司/部门/小组/团队）默认可修改；上传人、管理员与显式授权用户为最高权限
- **知识库索引修复**：修复失效 KnowFlow 知识库 ID 登记导致的重新索引失败（「权限检查服务异常」）；新增实时存在性校验与 `repair_stale_scope_registries` 自动清理
- **知识检索**：问答整合为原生页（`KnowledgeSearchView` + `KnowledgeChatContent`），会话持久化、引用预览；移除旧 `RagQaView` / `rag` 内置特性
- **文档 API**：拆分为 `platform/app/api/documents/` 子模块（listing、upload、versions、folders、acl、sync 等）
- **后端架构**：Redis 客户端、请求级用户缓存、平台缓存层；`ragflow_scope_service` 与知识库同步增强
- **前端体验**：会话守卫、文档对比、版本预览、知识引用弹窗、Liquid Glass UI 与主题系统优化
- **部署运维**：合并 `compose.server-deps` 至主栈；`compose.expose-deps.yaml` 与 `setup-remote-dev-env.sh` 支持远程依赖开发；运维文档扩充（单服务器迁移、组件与存储等）
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（4.0.0）

## 3.9.3（v3.9.3）— 知识检索原生页、文档索引与 UI 体验

- **知识检索**：独立原生页（左分级文档树 + 右问答），与 KnowFlow 嵌入解耦；统一「知识检索」命名
- **文档中心**：恢复发布/分享合并卡片、知识索引与重新解析、列表/详情索引状态展示；解析器（DeepDOC/PaddleOCR 等）与分块方法可配置；顶栏操作区与系统顶栏融合（Teleport）
- **说明文档**：系统设置内 Markdown/Mermaid 说明文档（`/admin/docs`），后端 API 打包/挂载 `docs/` 与运维手册
- **体验**：全局视频背景 + Liquid Glass UI 统一（卡片/表格/输入/按钮）；网站收藏 Google SERP 式单列列表；主内容区纵向滚动修复；操作日志去掉资源类型/ID 列
- **部署**：服务器依赖 compose 与 `server-deps.sh`；前端 Docker 入口与 Nginx 模板；根目录《运维部署指南》
- **版本统一**：`VERSION` 同步 API / 前端 / Docker 镜像 tag（3.9.3）

## 3.9.2（v3.9.2）— 启动脚本整理、架构文档与稳定性

- **版本统一**：`VERSION` 为单一来源，同步 API / 前端 / Docker 镜像 tag（3.9.2）
- **启动脚本**：精简 `dev.sh`（移除废弃宿主机混合模式）；`stack.sh` 自动读取 `VERSION`；新增 `scripts/README.md`
- **文档**：恢复并更新运维手册、架构说明；根 `README.md` 重写；KnowFlow 白标脚本恢复
- **稳定性**：修复 `RagflowAccountLink` 与数据库 schema 不一致导致知识检索/嵌入 meta 500；资源管理支持保存前连通性测试
- **清理**：删除空占位运维脚本（`sync_resource_settings_from_env.py`、`reconcile_knowledge_data.py`）

## 3.8.0（v3.8.0）— KnowFlow 权限与同步、订阅与数据分析

- KnowFlow：普通用户 embed 仅用自己的 SSO 会话，不再借用 bootstrap 管理员身份；切片管理默认 `sync=false` 快路径，登录后后台 catalog 对账
- KnowFlow：知识库可见范围收紧为个人库 + 所属部门链；mapped 模式下个人/部门库在 bootstrap 租户创建并通过 KB ACL 授权；登录时刷新 `ragflow_user_id`
- KnowFlow：上传后后台同步至 KnowFlow；文档详情可手动同步；孤立「部门」库与脏 scope 注册表自动清理
- 订阅中心：统一订阅 API 与前端页面；网页/公众号文章抓取与 HTML→Markdown 导入
- 数据分析：内置插件与 Notebook 面板（pandas/matplotlib）
- 部署：根目录 `compose.yaml` + `deploy/` 统一栈；`scripts/stack.sh` / `scripts/deploy.sh stack`
- 知识检索插件、分享文档 KnowFlow 镜像同步；编码管理仅管理员可见

## 3.4.0（v3.4.0）— 统一容器栈

> 操作指南：[运维手册](docs/zh/operations/README.md) · [部署指南](docs/zh/operations/deployment.md)

- 仓库根 `compose.yaml` + `deploy/knowflow.yml`（profile），对外仅 `FRONTEND_PORT`
- `scripts/stack.sh`：build / up / dev-up / save / load / backup
- `scripts/deploy.sh stack`：rsync 镜像包+编排，**不 rsync 源码**
- `dev.sh` 默认走容器栈；`legacy` 保留宿主机开发模式
- `deploy/knowflow/` 打包 init.sql、settings、主题（服务器无需 third_party）
- 数据目录 `./data/` 绑定挂载，便于迁移

## 3.3.0（v3.3.0）

- 全局 UI：设计 tokens、深色/浅色主题、中英文 i18n；顶栏待办/任务/消息/主题/语言布局优化
- 文档中心：书签式分级 Tab；新建文件夹置末；提示改图标悬浮；「我的分享」列表修复
- 功能列表：卡片精简（去大类说明、虚线与「进入/外链」文案）；HintTooltip 统一提示
- 双碳智能体：「查看历史对话」仅保留图标 + 悬浮说明
- KnowFlow：中文用户名 RAGFlow 邮箱 ASCII 化与账号恢复；重复知识库自动去重；普通用户 SSO/切片管理修复
- 订阅：摘要服务与相关 API/测试；API 错误文案不再误报「知识服务不可用」

## 3.1.0（v3.1.0）

- 顶栏：后台任务与消息改为图标弹出面板；用户菜单整合信息维护与退出
- 信息维护：`/profile` 页面与 `PATCH /api/v1/auth/me`
- 列表批量删除：用户、部门、文档、任务、对话、订阅、待办等统一勾选 + 工具栏模式
- 文档中心：文件夹网格首位新建；「分享」改由「我的」下文件夹进入，Tab 栏移除「分享」
- 订阅中心：订阅 API 与前端页面
- 后端：文档服务分层、用户/部门核心模块、HTML/PDF 导出与格式识别
- 脚本：`dev.sh` / `deploy.sh` 统一本地启动与部署，精简旧脚本

## 3.0.0（v3.0.0）

- 知识中心：全文检索、知识订阅与 Feed 订阅入口
- 公众号资讯：跟踪列表、推文卡片、链接收录与导入文档库/KnowFlow
- 碳资产：交易演示、全国碳市场/CCER 实时行情与历史走势
- 文档库：文件夹组织与跨文件夹移动
- KnowFlow：嵌入代理、目录同步、登录预热与 RAGFlow 账号修复脚本
- 部署：`push_and_deploy` 并行后台部署、镜像 Compose、`deploy.target` 与 `CONFIG.md` 说明

## 2.7.1（v2.7.1）

- 公众号资讯：用户维护跟踪列表，卡片浏览推文，支持粘贴链接收录与导入文档库/KnowFlow
- KnowFlow：登录轻量预热（模型配置 + RBAC 建库权限），文档同步改在进入知识问答时执行
- KnowFlow：修复 mapped 用户无模型、无建库权限导致知识库与平台文档未同步
- 新增 `platform/scripts/repair_ragflow_users.py` 批量修复 RAGFlow 账号
- 碳资产交易演示、CCER 行情与历史数据等能力迭代

## 2.6.2（v2.6.2）

- 全场景历史对话：列表页、续聊与 Dify/平台双通道存储
- 登录页注册卡片翻转、对话首页左上角「查看历史对话」
- 智能客服与双碳智能体会话持久化

## 2.2.0（v2.2.0）

- 基本功能完毕：系统功能入口、悬浮智能客服、部署与 amd64 生产编排
- 前端独立 Docker 镜像、文档精简与部署脚本（`deploy_amd64`、`push_and_deploy` 等）
- 平台品牌与登录/文档库/AI 工具页体验优化

## 2.1.0（v2.1.0）

- 系统统一顶栏：全局返回 + 功能标题，功能说明独立一行
- 双碳智能体、智能问数 v2、双碳问答 v2（Dify 流式对话）
- 知识中心：文档库 + 知识图谱内嵌；知识问答启动动效
- 会议助手：录音转写、说话人时间线、会议记录与 DeepSeek 总结
- 文档权限四档、KnowFlow/RAGFlow 集成与同步
- 本地 FunASR 语音服务（`8765`）与平台启动脚本自动拉起

## 2.0.0（v2.0.0）

- 绿叶 AI 办公系统基线：文档库、PDF 翻译、对比、KnowFlow 知识问答等
