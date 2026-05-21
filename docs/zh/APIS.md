# API 说明

## 当前推荐

| 类型 | 文档 | 说明 |
|------|------|------|
| **REST + SSE**（Vue / 外部前端） | [development/rest-api.md](./development/rest-api.md) | `pdf2zh_next --api`，默认 `http://127.0.0.1:7861` |
| **Python 异步流** | [advanced/API/python.md](./advanced/API/python.md) | `do_translate_async_stream`，自建 UI 或集成 |
| **本地开发总览** | [development/local-development.md](./development/local-development.md) | 环境、资源、Gradio + Vue 并行运行 |

启动 REST API：

```bash
pdf2zh_next --api
# 可选：--api-port 7861
```

交互式文档：<http://127.0.0.1:7861/docs>

---

## 已废弃：HTTP（Flask / Celery / Redis）

> [!CAUTION]
>
> 以下内容为 **pdf2zh 1.x / 旧后端** 方案，**当前 pdf2zh_next 仓库不再维护**，请勿在新项目中使用。

旧流程依赖 `pdf2zh_next[backend]`、`--flask`、`--celery worker` 与 Redis，端点为 `http://localhost:11008/v1/translate` 等。若你在维护遗留部署，请参考历史提交或上游旧版文档。

---

## Python 模块调用（简述）

在已安装 `pdf2zh-next` 的 Python 环境中，推荐通过配置模型 + 高层 API 调用，详见 [Python API](./advanced/API/python.md)。

```python
from pdf2zh_next.high_level import do_translate_async_stream
# 配合 ConfigManager / SettingsModel 使用
```

旧文档中的 `from pdf2zh import translate` 属于 **1.x**，与当前包名 `pdf2zh_next` 不同。
