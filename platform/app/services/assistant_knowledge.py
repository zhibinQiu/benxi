"""平台操作知识库 — 供智能客服注入系统提示词。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.permissions import user_has_permission
from app.features.registry import all_plugins, ensure_plugins_loaded
from app.models.org import User

_CATEGORY_LABELS = {
    "document": "文档",
    "tools": "工具",
    "ai": "双碳",
    "carbon": "双碳",
    "external": "双碳",
}

_NAV_GUIDE = """
## 主导航（左侧菜单）
- **功能列表**：平台能力入口，按文档 / 工具 / 双碳分组展示。
- **待办事项**：个人待办，支持勾选、拖拽排序与 AI 辅助录入。
- **知识中心 · 文档库**：上传与管理文档（公司/部门/分部/个人分级）；分享授权、回收站恢复。
- **知识中心 · 切片库**：知识库与文档切片管理（需知识服务就绪）。
- **后台任务**：PDF 翻译、文档删除等异步任务进度，可终止或清理历史。
- **系统设置**（管理员）：用户、部门、系统监控、模型配置。

## 核心能力路径
- PDF 翻译：功能列表 → PDF 翻译；进度在后台任务查看。
- 知识检索：功能列表 → 知识检索（需知识服务就绪）；支持 PageIndex 树 + 向量混合召回；由小析基于所选文档作答。
- 报告生成：功能列表 → 报告生成；小析多路召回 + 章节扩写，成稿可导出思维导图。
- 本体图谱：功能列表 → 本体图谱；实体关系查询、子图探索，检索/问答/小析可联动。
- 本析智能：功能列表 → 工具 → 本析智能；或左侧菜单直达；小析联合文档检索与本体图谱回答。
- 智能问数 / 双碳问答：功能列表 → 对应卡片，小析多轮对话与引用溯源。
- 文档对比：功能列表 → 文档对比，从文档库选择 PDF/Word。
- 会议助手 / 语音合成 / 文件内容提取：功能列表 → 对应卡片。
- 资讯收录：知识中心 → 网站收藏（粘贴文章链接 / 微信公众号）。
- 本析平台客服：顶栏消息图标旁，小析解答平台使用与菜单路径问题。
"""

_PLATFORM_USAGE_GUIDE = """
## 文档上传与管理
- 入口：知识中心 → 文档库；或各功能页「从文档库选择」。
- 上传：拖拽/选择文件，选择归属范围（公司/部门/分部/个人）与目标文件夹。
- **网页收藏**：个人文档库系统文件夹，名称「网页收藏」；通过网站收藏粘贴链接或公众号导入的文档自动归入。小析可用文档库工具列出其中文件，与浏览器书签无关。
- 版本：同一文档可上传新版本；详情页可查看版本历史、对比与下载。
- 回收站：删除后可在回收站恢复（需对应修改权限或归属权限）。

## 文档权限（三档）
- **可见**：仅查看元数据，不可检索内容。
- **可查询**：可被知识检索、小析问答召回。
- **可修改**：编辑、删除、分享授权、上传新版本。
- 分享：文档详情 → 权限，按用户或部门授权；无权限功能需联系管理员开通。

## PDF 翻译
- 入口：功能列表 → PDF 翻译。
- 从本地上传或文档库选择 PDF；可配置语言对、术语表（pdf2zh）。
- 提交后在顶栏「后台任务」查看进度；完成后下载双语 PDF。

## 后台任务与通知
- 顶栏「后台任务」：翻译、文档索引、对比等异步任务；可终止运行中任务。
- 顶栏「消息」：任务完成、系统通知。
- 长任务可离开页面，稍后回来查看结果。

## 知识服务与索引
- 文档上传后需完成解析与索引方可检索；详情页可查看索引状态并触发重建。
- 知识检索 / 小析问答：左侧勾选**已索引**文档后再提问。
- 切片库、检索依赖 KnowFlow/RAG 就绪，异常时查看系统监控或联系管理员。

## 账号与个性化
- 顶栏用户菜单：个人资料、浅色/深色主题、中英文切换、退出登录。
- 侧栏收藏：在功能列表将常用功能收藏到侧栏快捷入口。

## 常见问题
- 检索无结果：确认文档已索引、权限为「可查询」、已勾选正确文档范围。
- 功能灰色或无入口：当前账号无权限，请管理员在角色管理中开通。
- 小析回答平台问题时：依据本知识库作答，不确定时建议联系系统管理员。
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
    parts.append(_PLATFORM_USAGE_GUIDE.strip())

    parts.append("\n## 功能列表（插件）")
    by_cat: dict[str, list] = {}
    for plugin in all_plugins():
        if not plugin.enabled:
            continue
        cat = plugin.category or "tools"
        if cat in ("carbon", "external", "ai"):
            cat = "ai"
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
        "你是小析，本析平台官方 AI 助手；自我介绍或提及助手时统一使用名称「小析」。\n"
        "仅解答本平台的使用、菜单路径、权限与功能说明；不编造未列出的功能。"
        "涉及无权限的功能，说明需要管理员授权。语气简洁专业，适当用 Markdown 列表。"
    )
    return "\n".join(parts)
