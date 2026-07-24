# 测试

## v4.8.8 轻量化验证清单

本次版本聚焦图谱直答、Agent LLM 路由、工作时记忆、SSE 取消与免费网页 AI 下线。发布前建议：

| 层级 | 命令 / 检查 |
|------|-------------|
| 后端单元测试 | `cd backend && pytest tests/ -q` |
| 关键路由/取消单测 | `pytest tests/test_llm_agent_route.py tests/test_stream_cancel.py tests/test_agent_working_memory.py tests/test_kg_direct_and_plan_ui.py tests/test_subagent_loop_and_kg_skip.py -q` |
| 前端 lint + 构建 | `cd frontend && npm run lint && npm run build` |
| 图谱直答 | 点赞过的问答或图谱实体相关提问 → 无 tool loop 直接出字 |
| 流式取消 / 侧重试 | AI 对话生成中点停止或用户消息侧重试 → 后端协作中断 |
| 定时任务 | 编辑已有任务 → 立即执行 → 与 `/chat` 编排一致 |
| 文档库图标视图 | 文件夹内切换列表/图标，偏好可恢复 |
| AIP | `pytest tests/test_aip_*.py -q`；Agent Skills 管理页登记外部智能体 |

## 平台后端

```bash
cd platform
pip install -e ".[dev]"    # 或容器内
pytest tests/ -q
```

主要目录：`platform/tests/`

| 领域 | 示例文件 |
|------|----------|
| API / embed | `test_embed_proxy.py`, `test_knowflow_embed_proxy.py` |
| KnowFlow | `test_knowflow_catalog.py`, `test_ragflow_embed_fast_path.py` |
| 文档 scope | `test_content_import_scope.py` |
| 功能插件 | `test_feature_plugins.py` |
| 订阅 / HTML | `test_subscriptions_api.py`, `test_html_markdown.py` |

CI 建议：在 api 镜像 build 阶段或独立 job 运行 `pytest`。

## 冒烟清单（部署后）

1. `curl -sf http://127.0.0.1:18000/health` 或经 40005 登录页可开
2. 登录 → AI 智能体可对话（含文档检索 / 本体图谱引用，需相应功能权限）
3. 文档中心上传 / 下载
4. KnowFlow 启用时：
   - `curl -sf http://127.0.0.1:18000/v1/system/config`（容器内或开发机）
   - 切片管理页 iframe 无无限转圈
5. PDF 翻译提交任务 → worker 完成
6. 语音（若 profile speech）：`/api/v1/speech/meta` ok

## 前端

```bash
cd platform-frontend
npm install
npm run build    # 生产构建
```

暂无统一 E2E；关键路径依赖手工 + 上述 API 检查。

## pdf2zh 核心

根目录 `tests/config/` — 翻译配置相关，与平台栈独立。

## 性能关注点

- pdf2zh 首次 health：≤ 3min
- KnowFlow ES 冷启动：≤ 2min
- embed-session：应 < 10s（`sync=false`）
- 前端：Vite 生产构建 + Nginx gzip；Naive UI 按需加载

## 吞吐量 / 压力测试（v4.6.0）

脚本：`platform/scripts/stress_test_throughput.py`（依赖 `httpx`，随 platform 已安装）

| 场景 | 说明 |
|------|------|
| health burst | `/health`、`/health/ready` 高并发（无 DB） |
| mixed reads | 文档列表 / library / overview / monitor 混合读 |
| sustained reads | 持续 N 秒维持固定并发 |
| parse enqueue | 创建文档 → 上传 → 触发 reindex（解析入队） |

```bash
cd platform
# 常规负载（期望 100% 成功、无 503）
python scripts/stress_test_throughput.py --concurrency 40 --parse-jobs 50

# 单机生产档位 C 验收（compose 默认 6 worker × 12+8）
python scripts/stress_test_throughput.py --concurrency 80 --parse-jobs 80

# 极限探测（超出档位 C 时预期可见 503）
python scripts/stress_test_throughput.py --concurrency 200 --parse-jobs 200
```

测试文档标题前缀 `__stress_test__`，脚本结束时会 **batch-delete 自动清理**。可选环境变量：`STRESS_BASE_URL`、`STRESS_ACCOUNT`、`STRESS_PASSWORD`。

发布前建议：常规负载通过 + `pytest tests/ -q`（可 `--ignore=tests/test_knowflow_queue_service.py` 若本地无 KnowFlow MySQL）。
