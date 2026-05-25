"""平台操作知识库 — 供智能客服注入系统提示词。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.permissions import user_has_permission
from app.features.registry import all_plugins, ensure_plugins_loaded
from app.models.org import User

_CATEGORY_LABELS = {
    "document": "文档类",
    "tools": "工具类",
    "carbon": "双碳类",
    "external": "外部链接",
}

_NAV_GUIDE = """
## 主导航（左侧菜单）
- **系统功能**：平台能力入口，按文档类 / 工具类 / 双碳类等分组展示卡片。
- **待办事项**：个人待办，支持勾选、拖拽排序、智能录入与调整（需配置 AI）。
- **文档库**：上传与管理文档，支持公司级 / 部门级 / 个人级分级；可分享授权、回收站恢复。
- **任务中心**：查看 PDF 翻译、文档删除等后台任务进度，可终止进行中的任务、清理历史记录。
- **系统设置**（管理员可见子菜单）：用户管理、部门管理、系统监控（操作日志与资源）、模型配置。

## 顶栏
- **消息**：任务完成等系统通知，未读角标提示。
- **用户名右侧**：消息入口与退出登录。

## 文档库要点
- 新建文档后版本历史默认有 v1 占位，上传文件即写入该版本。
- 按版本删除文件；删光全部版本后文档进入个人回收站（文档库右上角可进入回收站恢复）。
- 分享权限级别：可见（下载预览）、可查询（知识问答）、可编辑（上传/翻译/对比）、完全（含删除）。
- 分级：公司级、部门级、个人级，决定默认可见范围。

## 任务中心
- 状态：等待中、运行中、已完成、失败、已终止。
- 运行中任务可点「终止」；可清理已完成或清空非运行中记录。

## 常见问题路径
- PDF 翻译：系统功能 → PDF 翻译，或任务中心查看翻译任务。
- 知识问答：系统功能 → 知识问答（需 KnowFlow/RAG 服务就绪）。
- 文档对比：系统功能 → 文档对比，从文档库选择 PDF/Word 对照。
- 会议助手：系统功能 → 会议助手，录音转写与 AI 总结。
- 辅助写作：系统功能 → 辅助写作，Markdown 双栏编辑 + AI 改写。
- OCR：系统功能 → OCR 识别。
"""


def build_platform_knowledge(
    db: Session,
    user: User,
    *,
    page_hint: str | None = None,
) -> str:
    ensure_plugins_loaded()
    settings = get_settings()
    parts = [
        f"# {settings.app_name} 操作知识库",
        f"当前用户：{user.username}（{user.display_name or user.username}）",
    ]
    if page_hint:
        parts.append(f"用户当前页面：{page_hint}")

    parts.append(_NAV_GUIDE.strip())

    parts.append("\n## 系统功能清单（插件）")
    by_cat: dict[str, list] = {}
    for plugin in all_plugins():
        if not plugin.enabled:
            continue
        cat = plugin.category or "tools"
        by_cat.setdefault(cat, []).append(plugin)

    for cat, plugins in sorted(by_cat.items()):
        label = _CATEGORY_LABELS.get(cat, cat)
        parts.append(f"\n### {label}")
        for p in plugins:
            allowed = user_has_permission(db, user, p.permission_code)
            access = "可进入" if allowed else "无权限"
            route = p.route or p.external_url or p.embed_url or "—"
            parts.append(
                f"- **{p.title}**（{access}）：{p.description}；入口：{route}"
            )

    parts.append(
        "\n## 回答要求（给模型的约束，勿向用户复述本段）\n"
        "仅解答本平台的使用、菜单路径、权限与功能说明；不编造未列出的功能。"
        "涉及无权限的功能，说明需要管理员授权。语气简洁专业，适当用 Markdown 列表。"
    )
    return "\n".join(parts)
