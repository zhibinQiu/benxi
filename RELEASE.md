# 发布说明

## 4.0.3（v4.0.3）— 品牌统一、PageIndex 实验集成与知识检索增强

- **品牌与系统功能**：产品统一为「AI 办公系统」；系统功能说明精简，AI 助理与功能分类面向通用办公；移除智碳平台 V3、智碳 AI v1 等遗留外链插件
- **PageIndex（实验）**：自托管树形索引（`pageindex_version_links` + `PAGEINDEX_WORKSPACE_DIR` JSON）；与 KnowFlow 向量检索并存、按文档自动切换；支持 PDF/Markdown/Word/TXT；知识检索引用页级整页预览
- **知识检索**：`KnowledgeSearchPanel` 与引用卡片 UI（文件名、页码、类型标签）；智能回答与引用区宽度对齐；思维导图 Tab
- **报告生成 / 菜单设置 / 知识图谱**：内置报告生成、菜单配置、KG Palantir 等能力迭代
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
- **开发入口**：`./dev.sh` 为唯一入口（`local` / `docker` / `remote-dev` / `stack` / `deploy`）；移除 `zhitan.sh`、`start-local.sh` 等旧脚本
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
