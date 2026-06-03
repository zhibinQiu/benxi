# 测试

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
2. 登录 → 双碳智能体可对话
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
