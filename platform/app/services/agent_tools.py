"""AI 智能体 OpenAI 兼容 tools 定义与执行（Skill 管理 / 记忆 / 加载 / 检索）。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.permissions import user_has_permission
from app.models.org import User
from app.services.agent_memory_service import (
    append_user_memory,
    clear_user_memory,
    read_user_memory,
)
from app.services.agent_skill_router import extract_memory_note
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_SKILL_MAP,
    ATOMIC_TOOL_WEB_SEARCH,
    kb_result_to_context,
    kg_result_to_context,
    web_result_to_context,
)
from app.skills.executor import invoke_skill_tool
from app.skills.types import SkillInvocationContext

_logger = logging.getLogger(__name__)

_ATOMIC_RETRIEVAL_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": ATOMIC_TOOL_WEB_SEARCH,
            "description": (
                "按关键词检索互联网公开信息摘要；用户问最新资讯、价格、新闻或明确要求联网时使用"
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问句"},
                    "max_items": {
                        "type": "integer",
                        "description": "最多返回条数",
                        "default": 8,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
            "description": (
                "在权限内企业文档库检索相关片段；回答内部制度、报告、项目文档等问题时使用"
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "检索问句"},
                    "doc_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "description": "限定文档 ID，省略则使用会话上下文",
                    },
                    "limit": {"type": "integer", "default": 8},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": ATOMIC_TOOL_KG_QUERY,
            "description": (
                "查询企业本体图谱中的实体与关系；适合概念关联、产业链、组织关系等问题"
            ),
            "parameters": {
                "type": "object",
                "required": ["question"],
                "properties": {
                    "question": {"type": "string", "description": "自然语言问题"},
                },
            },
        },
    },
]

_RUN_SKILL_SCRIPT_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_skill_script",
        "description": (
            "在沙箱中执行**上传型** Skill 包内的 Python 入口脚本（支持多文件 import）。"
            "脚本须在内存中完成抓取/分析，最后用 skill_runtime.finish(conclusion) 输出结论；"
            "平台不保存原始网页/抓取内容。仅当用户明确要求运行该 Skill 脚本时调用"
        ),
        "parameters": {
            "type": "object",
            "required": ["skill_name"],
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "上传 Skill 名称",
                },
                "entry": {
                    "type": "string",
                    "description": "入口 .py 相对路径，省略则尝试 main.py / run.py",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "传给入口脚本的命令行参数，如 URL",
                },
            },
        },
    },
}

_BROWSER_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": (
                "在隔离浏览器中打开 http/https 页面。JavaScript 页面、需点击/填表的交互任务"
                "必须使用 browser_* 工具，勿仅用 web_search 或 run_skill_script 拉静态 HTML"
            ),
            "parameters": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {"type": "string", "description": "目标 URL"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": (
                "获取当前页面的交互元素 ref 列表（无障碍树摘要）。"
                "每次 navigate/click/type 导致页面变化后必须重新 snapshot；"
                "click/type 只能使用**最近一次** snapshot 返回的 ref"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "按 ref 点击元素（ref 来自最近一次 browser_snapshot）",
            "parameters": {
                "type": "object",
                "required": ["ref"],
                "properties": {
                    "ref": {"type": "string", "description": "元素 ref，如 e3"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "向 ref 对应输入框填入文本，可选提交",
            "parameters": {
                "type": "object",
                "required": ["ref", "text"],
                "properties": {
                    "ref": {"type": "string"},
                    "text": {"type": "string"},
                    "submit": {
                        "type": "boolean",
                        "description": "填完后按 Enter",
                        "default": False,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "批量填表：[{ref, value}, ...]",
            "parameters": {
                "type": "object",
                "required": ["fields"],
                "properties": {
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["ref", "value"],
                            "properties": {
                                "ref": {"type": "string"},
                                "value": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": (
                "截取当前页面截图并返回 URL；在回复中用 Markdown 图片展示给用户"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "full_page": {
                        "type": "boolean",
                        "description": "是否全页截图",
                        "default": False,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_save_workflow",
            "description": (
                "将本会话已录制的浏览器操作步骤保存为上传型 Skill（含 workflow.json），"
                "便于后续重复执行"
            ),
            "parameters": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "description": "Skill 名称（slug）"},
                    "description": {"type": "string", "description": "Skill 描述"},
                    "parameters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可参数化的字段名，如 url、username",
                    },
                    "replace_existing": {
                        "type": "boolean",
                        "description": "同名 Skill 已存在时是否覆盖（默认 true，重新录制保存时通常应覆盖）",
                        "default": True,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close_session",
            "description": "关闭当前对话的浏览器会话并释放资源",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_replay_workflow",
            "description": (
                "回放含 workflow.json 的 RPA Skill（确定性重放录制的 navigate/click/type 步骤）"
            ),
            "parameters": {
                "type": "object",
                "required": ["skill_name"],
                "properties": {
                    "skill_name": {"type": "string", "description": "RPA Skill 名称"},
                    "parameters": {
                        "type": "object",
                        "description": "参数键值，如 url、custname",
                        "additionalProperties": {"type": "string"},
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_run_task",
            "description": (
                "自动探索模式：根据自然语言任务目标，由模型多步驱动 browser_* 操作"
                "（适合复杂但目标明确的网页任务；可配合 start_url）"
            ),
            "parameters": {
                "type": "object",
                "required": ["task"],
                "properties": {
                    "task": {"type": "string", "description": "要完成的目标描述"},
                    "start_url": {"type": "string", "description": "可选起始 URL"},
                    "max_steps": {
                        "type": "integer",
                        "description": "最多自动步数，省略则用平台默认",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_browser_workflow",
            "description": (
                "定时执行 RPA Skill 回放，完成后发送系统通知（含截图链接）"
            ),
            "parameters": {
                "type": "object",
                "required": ["skill_name"],
                "properties": {
                    "skill_name": {"type": "string"},
                    "parameters": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                    "delay_minutes": {"type": "integer", "description": "延迟分钟数"},
                    "scheduled_at": {
                        "type": "string",
                        "description": "ISO8601 绝对时间",
                    },
                },
            },
        },
    },
]

_DOCUMENT_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_library_documents",
            "description": (
                "列出平台文档库中用户可见的文档（只读查看）。"
                "用户问某文件夹/分级下有哪些文件、文档、收藏时调用；"
                "「网页收藏」是平台个人文档库系统文件夹（网站收藏/RSS 导入），不是浏览器书签。"
                "默认 scope=personal；可按 folder_name（如「网页收藏」）或 folder_id 筛选"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "description": "文档分级：personal、company、department、team，默认 personal",
                        "default": "personal",
                    },
                    "folder_name": {
                        "type": "string",
                        "description": "文件夹名称，如「网页收藏」「未分类」或自定义文件夹名",
                    },
                    "folder_id": {
                        "type": "string",
                        "description": "文件夹 UUID（与 folder_name 二选一）",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "按标题模糊筛选",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回条数，默认 30",
                        "default": 30,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_manageable_documents",
            "description": (
                "列出当前用户拥有可修改（完全管理）权限的文档，用于重命名、移动、删除或分享前定位 document_id"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "按标题模糊筛选，省略则返回最近可管理文档",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回条数，默认 20",
                        "default": 20,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_document_folders",
            "description": (
                "列出某分级下的平台文档库文件夹（含系统文件夹「网页收藏」「未分类」），"
                "用于定位 folder_id 或确认文件夹名称"
            ),
            "parameters": {
                "type": "object",
                "required": ["scope"],
                "properties": {
                    "scope": {
                        "type": "string",
                        "description": "文档分级：personal、company、department、team",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_document",
            "description": "重命名用户有完全管理权限的文档",
            "parameters": {
                "type": "object",
                "required": ["document_id", "new_title"],
                "properties": {
                    "document_id": {"type": "string", "description": "文档 UUID"},
                    "new_title": {"type": "string", "description": "新标题"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_document",
            "description": "将文档移动到同分级下的文件夹或未分类",
            "parameters": {
                "type": "object",
                "required": ["document_id"],
                "properties": {
                    "document_id": {"type": "string", "description": "文档 UUID"},
                    "folder_id": {
                        "type": "string",
                        "description": "目标文件夹 UUID；移到未分类时省略",
                    },
                    "folder_name": {
                        "type": "string",
                        "description": "目标文件夹名称（与 folder_id 二选一）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "share_document",
            "description": (
                "将文档分享给指定用户（需为创建人、管理员或已被授予可修改权限）"
            ),
            "parameters": {
                "type": "object",
                "required": ["document_id", "user_names"],
                "properties": {
                    "document_id": {"type": "string", "description": "文档 UUID"},
                    "user_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "被分享人姓名或账号，可多个",
                    },
                    "level": {
                        "type": "string",
                        "description": "权限级别：visible（仅查阅）、query（可检索）、modify（可修改）",
                        "default": "query",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_document",
            "description": "永久删除用户有完全管理权限的文档（不可恢复，需 confirm=true）",
            "parameters": {
                "type": "object",
                "required": ["document_id", "confirm"],
                "properties": {
                    "document_id": {"type": "string", "description": "文档 UUID"},
                    "confirm": {
                        "type": "boolean",
                        "description": "必须为 true 才执行删除",
                    },
                },
            },
        },
    },
]

_PLATFORM_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": "列出当前用户的待办事项；用户询问待办、任务清单或需确认已有待办时调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "pending（未完成）或 done（已完成），省略则返回全部",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_todo",
            "description": "为当前用户添加一条待办事项",
            "parameters": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string", "description": "待办标题"},
                    "note": {"type": "string", "description": "补充说明"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": "修改或完成待办；完成时设 status=done",
            "parameters": {
                "type": "object",
                "required": ["todo_id"],
                "properties": {
                    "todo_id": {"type": "string", "description": "待办 UUID"},
                    "title": {"type": "string", "description": "新标题"},
                    "note": {"type": "string", "description": "新备注"},
                    "status": {
                        "type": "string",
                        "description": "pending 或 done",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_todo",
            "description": "删除一条待办事项",
            "parameters": {
                "type": "object",
                "required": ["todo_id"],
                "properties": {
                    "todo_id": {"type": "string", "description": "待办 UUID"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "立即向当前用户发送一条系统通知（出现在通知中心）",
            "parameters": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string", "description": "通知标题"},
                    "body": {"type": "string", "description": "通知正文"},
                    "link": {
                        "type": "string",
                        "description": "可选跳转链接，如 /documents/{id}",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_notification",
            "description": (
                "在指定时间后向当前用户发送系统通知，用于提醒类请求"
                "（如「5 分钟后提醒我提交文档」）"
            ),
            "parameters": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string", "description": "通知标题"},
                    "body": {"type": "string", "description": "通知正文"},
                    "link": {"type": "string", "description": "可选跳转链接"},
                    "delay_minutes": {
                        "type": "integer",
                        "description": "多少分钟后提醒，如 5",
                    },
                    "delay_seconds": {
                        "type": "integer",
                        "description": "多少秒后提醒；与 delay_minutes 二选一",
                    },
                    "scheduled_at": {
                        "type": "string",
                        "description": "ISO8601 绝对时间，如 2026-06-22T15:30:00+08:00",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_scheduled_notifications",
            "description": "列出当前用户尚未发送的定时通知",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "最多返回条数，默认 20",
                        "default": 20,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_scheduled_notification",
            "description": "取消一条尚未发送的定时通知",
            "parameters": {
                "type": "object",
                "required": ["notification_id"],
                "properties": {
                    "notification_id": {
                        "type": "string",
                        "description": "定时通知 UUID",
                    },
                },
            },
        },
    },
]

AGENT_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "load_uploaded_skill",
            "description": (
                "加载**上传型** Skill 的 SKILL.md 完整说明。"
                "仅当用户任务明确对应该 Skill 且需按其流程执行时调用；"
                "创建新 Skill 请用 create_uploaded_skill；内置 Skill 禁止 load；"
                "勿在开篇、Skill 管理或与描述无关的任务中调用"
            ),
            "parameters": {
                "type": "object",
                "required": ["skill_name"],
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "skill 名称，如 mermaid-diagram",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_uploaded_skill",
            "description": (
                "创建组织共享的上传型 Skill（与 ZIP 上传格式一致，含 SKILL.md）。"
                "用户要求新建/编写 Skill 时使用；勿用 load_uploaded_skill 代替创建"
            ),
            "parameters": {
                "type": "object",
                "required": ["name", "description", "skill_md_body"],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "小写连字符 slug，如 my-workflow",
                    },
                    "description": {
                        "type": "string",
                        "description": "一句话描述，供 Discovery 使用",
                    },
                    "skill_md_body": {
                        "type": "string",
                        "description": "SKILL.md 正文（不含 frontmatter）",
                    },
                    "replace_existing": {
                        "type": "boolean",
                        "description": "同名时是否覆盖",
                        "default": False,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_uploaded_skill_file",
            "description": "更新已安装上传型 Skill 的文本文件内容",
            "parameters": {
                "type": "object",
                "required": ["skill_name", "file_path", "content"],
                "properties": {
                    "skill_name": {"type": "string"},
                    "file_path": {
                        "type": "string",
                        "description": "相对路径，如 SKILL.md",
                    },
                    "content": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_uploaded_skill",
            "description": "删除上传/智能体生成的 Skill；内置平台 Skill 不可删除",
            "parameters": {
                "type": "object",
                "required": ["skill_name"],
                "properties": {"skill_name": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_agent_memory",
            "description": "读取当前用户跨会话记忆 MEMORY.md",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_agent_memory",
            "description": "向当前用户 MEMORY.md 追加一条经验（不含密钥与本地路径）",
            "parameters": {
                "type": "object",
                "required": ["note"],
                "properties": {
                    "note": {"type": "string", "description": "要记住的简短事实"}
                },
            },
        },
    },
]


def build_agent_tool_specs(db: Session, user: User) -> list[dict[str, Any]]:
    """按用户权限与平台开关组装可用原子工具列表。"""
    from app.config import get_settings
    from app.services.searxng_service import is_enabled as web_search_enabled

    specs: list[dict[str, Any]] = []
    if user_has_permission(db, user, "feature.knowledge_search"):
        specs.append(_ATOMIC_RETRIEVAL_TOOL_SPECS[1])
    if user_has_permission(db, user, "feature.kg_palantir"):
        specs.append(_ATOMIC_RETRIEVAL_TOOL_SPECS[2])
    if web_search_enabled(db):
        specs.append(_ATOMIC_RETRIEVAL_TOOL_SPECS[0])
    specs.extend(AGENT_TOOL_SPECS)
    specs.extend(_DOCUMENT_TOOL_SPECS)
    specs.extend(_PLATFORM_TOOL_SPECS)
    if get_settings().agent_skill_script_enabled:
        specs.append(_RUN_SKILL_SCRIPT_SPEC)
    from app.integrations.browser_automation.browser_config import get_browser_rpa_config

    if get_browser_rpa_config(db).enabled:
        specs.extend(_BROWSER_TOOL_SPECS)
    return specs


def agent_tool_names() -> set[str]:
    from app.config import get_settings

    names = {
        spec["function"]["name"]
        for spec in AGENT_TOOL_SPECS
        if spec.get("function", {}).get("name")
    }
    names.update(
        spec["function"]["name"]
        for spec in _ATOMIC_RETRIEVAL_TOOL_SPECS
        if spec.get("function", {}).get("name")
    )
    run_name = _RUN_SKILL_SCRIPT_SPEC.get("function", {}).get("name")
    if run_name:
        names.add(run_name)
    if get_settings().agent_browser_enabled:
        names.update(
            spec["function"]["name"]
            for spec in _BROWSER_TOOL_SPECS
            if spec.get("function", {}).get("name")
        )
    names.update(
        spec["function"]["name"]
        for spec in _DOCUMENT_TOOL_SPECS
        if spec.get("function", {}).get("name")
    )
    names.update(
        spec["function"]["name"]
        for spec in _PLATFORM_TOOL_SPECS
        if spec.get("function", {}).get("name")
    )
    return names


def _tool_result(ok: bool, summary: str, data: Any = None) -> str:
    return json.dumps(
        {"ok": ok, "summary": summary, "data": data},
        ensure_ascii=False,
    )


def _citation_start(loop_state: dict[str, Any] | None) -> int:
    if not loop_state:
        return 1
    return len(loop_state.get("citations") or []) + 1


def _offset_context_citations(
    context: str,
    citations: list[dict],
    *,
    start: int,
) -> tuple[str, list[dict]]:
    if start <= 1 or not citations:
        return context, citations
    offset = start - 1
    shifted = [{**c, "index": int(c.get("index") or 0) + offset} for c in citations]

    def _repl(match: re.Match[str]) -> str:
        num = int(match.group(1)) + offset
        return f"[{num}]"

    shifted_context = re.sub(r"\[(\d+)\]", _repl, context or "")
    return shifted_context, shifted


def _record_retrieval(
    loop_state: dict[str, Any] | None,
    *,
    context: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    start = _citation_start(loop_state)
    context, citations = _offset_context_citations(
        context, citations, start=start
    )
    if loop_state is not None and citations:
        loop_state.setdefault("citations", []).extend(citations)
    return context, citations


async def _execute_atomic_retrieval_tool(
    ctx: SkillInvocationContext,
    *,
    tool_name: str,
    params: dict[str, Any],
    user_message: str,
    loop_state: dict[str, Any] | None,
) -> str | None:
    route = ATOMIC_TOOL_SKILL_MAP.get(tool_name)
    if not route:
        return None
    skill_name, internal_tool = route
    query = str(
        params.get("query")
        or params.get("question")
        or user_message
        or ""
    ).strip()
    if not query:
        return _tool_result(False, "缺少 query / question")
    cache_key = f"{tool_name}:{query.casefold()}"
    if loop_state is not None:
        done = loop_state.setdefault("atomic_retrieval_queries", set())
        if cache_key in done:
            return _tool_result(
                True,
                "本回合已执行相同检索，请复用先前工具结果",
                {"context": "", "deduplicated": True},
            )
    invoke_params = dict(params)
    if tool_name == ATOMIC_TOOL_WEB_SEARCH:
        invoke_params.setdefault("query", query)
    elif tool_name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        invoke_params.setdefault("query", query)
    elif tool_name == ATOMIC_TOOL_KG_QUERY:
        invoke_params.setdefault("question", query)
    result = await invoke_skill_tool(
        ctx,
        skill_name=skill_name,
        tool_name=internal_tool,
        params=invoke_params,
    )
    if not result.ok:
        return _tool_result(False, result.summary or f"{tool_name} 失败")
    citation_start = _citation_start(loop_state)
    if tool_name == ATOMIC_TOOL_WEB_SEARCH:
        context, citations = web_result_to_context(
            result, citation_start=citation_start
        )
    elif tool_name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        context, citations = kb_result_to_context(ctx.db, query, result)
    else:
        kg_ctx = kg_result_to_context(result)
        context, citations = "", []
        if kg_ctx and loop_state is not None:
            loop_state["kg_context"] = kg_ctx
        if kg_ctx and kg_ctx.context_text:
            context = kg_ctx.context_text
            citations = list(kg_ctx.citations or [])
    context, citations = _record_retrieval(
        loop_state, context=context, citations=citations
    )
    if loop_state is not None:
        loop_state.setdefault("atomic_retrieval_queries", set()).add(cache_key)
    return _tool_result(
        True,
        result.summary,
        {
            "context": context,
            "hit_count": len(citations),
            "tool": tool_name,
        },
    )


def _parse_uuid(value: Any, *, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无效的 {field}") from exc


def _execute_document_tool(
    db: Session,
    user: User,
    *,
    tool_name: str,
    params: dict[str, Any],
) -> str | None:
    from app.core.exceptions import AppError
    from app.services import agent_document_service as doc_svc

    handlers = {
        "list_library_documents": lambda: doc_svc.list_library_documents_for_agent(
            db,
            user,
            scope=str(params.get("scope") or "personal").strip(),
            folder_id=_parse_uuid(params["folder_id"], field="folder_id")
            if params.get("folder_id")
            else None,
            folder_name=str(params.get("folder_name") or "") or None,
            keyword=params.get("keyword"),
            limit=int(params.get("limit") or 30),
        ),
        "list_manageable_documents": lambda: doc_svc.list_manageable_documents(
            db,
            user,
            keyword=params.get("keyword"),
            folder_id=_parse_uuid(params["folder_id"], field="folder_id")
            if params.get("folder_id")
            else None,
            folder_name=str(params.get("folder_name") or "") or None,
            scope=str(params.get("scope") or "personal").strip(),
            limit=int(params.get("limit") or 20),
        ),
        "list_document_folders": lambda: doc_svc.list_document_folders_for_agent(
            db,
            user,
            scope=str(params.get("scope") or "").strip(),
        ),
        "rename_document": lambda: doc_svc.rename_document_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
            new_title=str(params.get("new_title") or ""),
        ),
        "move_document": lambda: doc_svc.move_document_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
            folder_id=_parse_uuid(params["folder_id"], field="folder_id")
            if params.get("folder_id")
            else None,
            folder_name=str(params.get("folder_name") or "") or None,
        ),
        "share_document": lambda: doc_svc.share_document_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
            user_names=list(params.get("user_names") or []),
            level=str(params.get("level") or "query"),
        ),
        "delete_document": lambda: doc_svc.delete_document_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
            confirm=bool(params.get("confirm")),
        ),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return None
    try:
        data = handler()
        if isinstance(data, dict) and data.get("message"):
            return _tool_result(True, str(data["message"]), data)
        if isinstance(data, list):
            return _tool_result(
                True,
                f"共 {len(data)} 条",
                {"items": data, "count": len(data)},
            )
        return _tool_result(True, "操作完成", data)
    except AppError as exc:
        detail = exc.detail
        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        return _tool_result(False, msg)
    except ValueError as exc:
        return _tool_result(False, str(exc))


def _execute_platform_tool(
    db: Session,
    user: User,
    *,
    tool_name: str,
    params: dict[str, Any],
) -> str | None:
    from app.core.exceptions import AppError
    from app.services import agent_platform_service as plat_svc

    handlers = {
        "list_todos": lambda: plat_svc.list_todos_for_agent(
            db,
            user,
            status=str(params["status"]).strip() if params.get("status") else None,
        ),
        "create_todo": lambda: plat_svc.create_todo_for_agent(
            db,
            user,
            title=str(params.get("title") or ""),
            note=str(params.get("note") or ""),
        ),
        "update_todo": lambda: plat_svc.update_todo_for_agent(
            db,
            user,
            todo_id=_parse_uuid(params.get("todo_id"), field="todo_id"),
            title=str(params["title"]).strip() if params.get("title") is not None else None,
            note=str(params["note"]).strip() if params.get("note") is not None else None,
            status=str(params["status"]).strip() if params.get("status") is not None else None,
        ),
        "delete_todo": lambda: plat_svc.delete_todo_for_agent(
            db,
            user,
            todo_id=_parse_uuid(params.get("todo_id"), field="todo_id"),
        ),
        "send_notification": lambda: plat_svc.send_notification_for_agent(
            db,
            user,
            title=str(params.get("title") or ""),
            body=str(params.get("body") or ""),
            link=str(params.get("link") or "") or None,
        ),
        "schedule_notification": lambda: plat_svc.schedule_notification_for_agent(
            db,
            user,
            title=str(params.get("title") or ""),
            body=str(params.get("body") or ""),
            link=str(params.get("link") or "") or None,
            delay_seconds=int(params["delay_seconds"])
            if params.get("delay_seconds") is not None
            else None,
            delay_minutes=int(params["delay_minutes"])
            if params.get("delay_minutes") is not None
            else None,
            scheduled_at=str(params.get("scheduled_at") or "") or None,
        ),
        "list_scheduled_notifications": lambda: plat_svc.list_scheduled_notifications_for_agent(
            db,
            user,
            limit=int(params.get("limit") or 20),
        ),
        "cancel_scheduled_notification": lambda: plat_svc.cancel_scheduled_notification_for_agent(
            db,
            user,
            notification_id=_parse_uuid(
                params.get("notification_id"), field="notification_id"
            ),
        ),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return None
    try:
        data = handler()
        if isinstance(data, dict) and data.get("message"):
            return _tool_result(True, str(data["message"]), data)
        if isinstance(data, list):
            return _tool_result(
                True,
                f"共 {len(data)} 条",
                {"items": data, "count": len(data)},
            )
        return _tool_result(True, "操作完成", data)
    except AppError as exc:
        detail = exc.detail
        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        return _tool_result(False, msg)
    except ValueError as exc:
        return _tool_result(False, str(exc))


async def _execute_browser_tool(
    db: Session,
    user: User,
    *,
    tool_name: str,
    params: dict[str, Any],
    conversation_id: str | None,
    loop_state: dict[str, Any] | None = None,
) -> str | None:
    from app.services import browser_rpa_service as rpa

    def _track_screenshot(data: dict[str, Any] | None) -> None:
        if not loop_state or not isinstance(data, dict):
            return
        api_path = str(data.get("screenshot_api_path") or "").strip()
        if not api_path:
            return
        loop_state.setdefault("stream_attachments", []).append(
            {
                "type": "image",
                "url": api_path,
                "title": str(data.get("title") or "浏览器截图"),
            }
        )

    handlers = {
        "browser_navigate": lambda: rpa.browser_navigate(
            db,
            user,
            conversation_id=conversation_id,
            url=str(params.get("url") or ""),
        ),
        "browser_snapshot": lambda: rpa.browser_snapshot(
            db, user, conversation_id=conversation_id
        ),
        "browser_click": lambda: rpa.browser_click(
            db,
            user,
            conversation_id=conversation_id,
            ref=str(params.get("ref") or ""),
        ),
        "browser_type": lambda: rpa.browser_type(
            db,
            user,
            conversation_id=conversation_id,
            ref=str(params.get("ref") or ""),
            text=str(params.get("text") or ""),
            submit=bool(params.get("submit")),
        ),
        "browser_fill": lambda: rpa.browser_fill(
            db,
            user,
            conversation_id=conversation_id,
            fields=list(params.get("fields") or []),
        ),
        "browser_screenshot": lambda: rpa.browser_screenshot(
            db,
            user,
            conversation_id=conversation_id,
            full_page=bool(params.get("full_page")),
        ),
        "browser_save_workflow": lambda: rpa.browser_save_workflow(
            db,
            user,
            conversation_id=conversation_id,
            name=str(params.get("name") or ""),
            description=str(params.get("description") or ""),
            parameters=list(params.get("parameters") or []),
            replace_existing=params.get("replace_existing", True),
        ),
        "browser_close_session": lambda: rpa.browser_close_session(
            user, conversation_id=conversation_id
        ),
        "browser_replay_workflow": lambda: rpa.browser_replay_workflow(
            db,
            user,
            skill_name=str(params.get("skill_name") or ""),
            parameters={
                str(k): str(v)
                for k, v in (params.get("parameters") or {}).items()
            }
            if isinstance(params.get("parameters"), dict)
            else {},
        ),
        "browser_run_task": lambda: rpa.browser_run_task(
            db,
            user,
            conversation_id=conversation_id,
            task=str(params.get("task") or ""),
            start_url=str(params.get("start_url") or ""),
            max_steps=int(params["max_steps"])
            if params.get("max_steps") is not None
            else None,
        ),
        "schedule_browser_workflow": lambda: rpa.schedule_browser_workflow(
            db,
            user,
            skill_name=str(params.get("skill_name") or ""),
            parameters={
                str(k): str(v)
                for k, v in (params.get("parameters") or {}).items()
            }
            if isinstance(params.get("parameters"), dict)
            else {},
            delay_minutes=int(params["delay_minutes"])
            if params.get("delay_minutes") is not None
            else None,
            scheduled_at=str(params.get("scheduled_at") or "") or None,
        ),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return None
    try:
        result = handler()
        import asyncio

        data = await result if asyncio.iscoroutine(result) else result
        if tool_name in {"browser_screenshot", "browser_replay_workflow", "browser_run_task"}:
            _track_screenshot(data if isinstance(data, dict) else None)
        if isinstance(data, dict) and data.get("message"):
            return _tool_result(True, str(data["message"]), data)
        if tool_name == "browser_snapshot":
            ref_count = len((data or {}).get("refs") or [])
            return _tool_result(
                True,
                f"页面快照：{(data or {}).get('title') or ''}（{ref_count} 个可交互元素）",
                data,
            )
        if tool_name == "browser_screenshot":
            api_path = str((data or {}).get("screenshot_api_path") or "")
            summary = "截图已生成"
            if api_path:
                summary = f"截图已生成：{api_path}"
            return _tool_result(True, summary, data)
        if tool_name == "browser_replay_workflow":
            conclusion = str((data or {}).get("conclusion") or "RPA 回放完成")
            return _tool_result(True, conclusion[:200], data)
        return _tool_result(True, "浏览器操作完成", data)
    except Exception as exc:
        return _tool_result(False, str(exc))


async def execute_agent_tool(
    db: Session,
    user: User,
    *,
    tool_name: str,
    arguments: dict[str, Any] | str | None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
    user_message: str = "",
    loop_state: dict[str, Any] | None = None,
) -> str:
    if isinstance(arguments, str):
        try:
            params = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            params = {}
    else:
        params = dict(arguments or {})

    ctx = SkillInvocationContext(
        db=db,
        user=user,
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
    )

    try:
        atomic = await _execute_atomic_retrieval_tool(
            ctx,
            tool_name=tool_name,
            params=params,
            user_message=user_message,
            loop_state=loop_state,
        )
        if atomic is not None:
            return atomic

        if tool_name == "load_uploaded_skill":
            skill_name = str(params.get("skill_name") or "").strip()
            if not skill_name:
                return _tool_result(False, "缺少 skill_name")
            from app.services.agent_skill_router import validate_uploaded_skill_load
            from app.skills.catalog import get_merged_skill_definition

            defn = get_merged_skill_definition(db, skill_name, user=user)
            if not defn:
                return _tool_result(False, f"Skill 不存在: {skill_name}")
            planned = None
            if loop_state:
                planned = str(loop_state.get("planned_uploaded_skill") or "").strip() or None
            ok, reason = validate_uploaded_skill_load(
                user_message=user_message,
                skill_name=skill_name,
                skill_description=defn.description,
                skill_source=defn.source,
                planned_skill=planned,
            )
            if not ok:
                return _tool_result(False, reason)
            result = await invoke_skill_tool(
                ctx, skill_name=skill_name, tool_name="load"
            )
            return _tool_result(result.ok, result.summary, result.data)

        if tool_name == "run_skill_script":
            skill_name = str(params.get("skill_name") or "").strip()
            if not skill_name:
                return _tool_result(False, "缺少 skill_name")
            entry = str(params.get("entry") or "").strip()
            raw_args = params.get("args")
            args: list[str] = []
            if isinstance(raw_args, list):
                args = [str(a) for a in raw_args]
            elif isinstance(raw_args, str) and raw_args.strip():
                args = [raw_args.strip()]
            from app.services import agent_skill_service as svc
            from app.services.agent_skill_service import load_skill_workspace_bytes, _skill_by_name

            skill = _skill_by_name(db, skill_name)
            files = load_skill_workspace_bytes(db, skill.id)
            if b"workflow.json" in files and (
                not entry or entry == "replay.py" or entry.endswith("replay.py")
            ):
                from app.services.browser_rpa_service import replay_skill_workflow_script

                payload = await replay_skill_workflow_script(
                    db, user, files=files, args=args
                )
            else:
                payload = svc.run_uploaded_skill_script(
                    db,
                    skill_name,
                    user=user,
                    entry=entry,
                    args=args,
                )
            conclusion = str(payload.get("conclusion") or "")
            extra: dict[str, Any] = {
                "conclusion": conclusion,
                "entry": payload.get("entry"),
                "hint": payload.get("hint"),
            }
            if payload.get("screenshot_api_path") and loop_state is not None:
                loop_state.setdefault("stream_attachments", []).append(
                    {
                        "type": "image",
                        "url": payload["screenshot_api_path"],
                        "title": "RPA 回放截图",
                    }
                )
                extra["screenshot_api_path"] = payload["screenshot_api_path"]
            return _tool_result(
                True,
                conclusion[:200] or "脚本执行完成",
                extra,
            )

        if tool_name == "create_uploaded_skill":
            from app.services import agent_skill_service as svc

            skill = svc.create_generated_skill(
                db,
                user,
                name=str(params.get("name") or ""),
                description=str(params.get("description") or ""),
                skill_md_body=str(params.get("skill_md_body") or ""),
                replace_existing=bool(params.get("replace_existing")),
            )
            return _tool_result(
                True,
                f"已创建 Skill `{skill.name}`",
                {
                    "skill_id": str(skill.id),
                    "name": skill.name,
                    "source_type": skill.source_type,
                },
            )

        if tool_name == "update_uploaded_skill_file":
            from app.services import agent_skill_service as svc

            skill_name = str(params.get("skill_name") or "")
            file_path = str(params.get("file_path") or "")
            summary = svc.update_skill_file_by_name(
                db,
                user,
                skill_name=skill_name,
                file_path=file_path,
                content=str(params.get("content") or ""),
            )
            return _tool_result(
                True,
                f"已更新 `{skill_name}` / {file_path}",
                {"skill_id": str(summary.id), "name": summary.name},
            )

        if tool_name == "delete_uploaded_skill":
            from app.services import agent_skill_service as svc

            svc.delete_skill_by_name(db, str(params.get("skill_name") or ""))
            return _tool_result(True, "已删除 Skill")

        if tool_name == "read_agent_memory":
            body = read_user_memory(user.id)
            return _tool_result(True, "已读取记忆", {"memory": body})

        if tool_name == "append_agent_memory":
            note = str(params.get("note") or "").strip()
            if not note:
                return _tool_result(False, "note 不能为空")
            ok = append_user_memory(user.id, extract_memory_note(note, max_len=500))
            return _tool_result(ok, "已写入记忆" if ok else "写入失败")

        doc_tool = _execute_document_tool(db, user, tool_name=tool_name, params=params)
        if doc_tool is not None:
            return doc_tool

        plat_tool = _execute_platform_tool(db, user, tool_name=tool_name, params=params)
        if plat_tool is not None:
            return plat_tool

        browser_tool = await _execute_browser_tool(
            db,
            user,
            tool_name=tool_name,
            params=params,
            conversation_id=conversation_id,
            loop_state=loop_state,
        )
        if browser_tool is not None:
            return browser_tool

        return _tool_result(False, f"未知工具: {tool_name}")
    except Exception as exc:
        _logger.warning("agent tool %s failed: %s", tool_name, exc)
        return _tool_result(False, str(exc))


def _parse_tool_args(raw: str | dict | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def tool_workflow_meta(tool_name: str, raw_args: str | dict | None) -> dict[str, str]:
    """生成 workflow UI 展示用标题与 tool 键。"""
    params = _parse_tool_args(raw_args)
    name = (tool_name or "").strip()

    if name == ATOMIC_TOOL_WEB_SEARCH:
        query = str(params.get("query") or "").strip() or "?"
        return {
            "title": "联网搜索",
            "result_title": "联网搜索完成",
            "detail": query[:120],
            "tool": ATOMIC_TOOL_WEB_SEARCH,
        }
    if name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        query = str(params.get("query") or "").strip() or "?"
        return {
            "title": "知识库检索",
            "result_title": "知识库检索完成",
            "detail": query[:120],
            "tool": ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
        }
    if name == ATOMIC_TOOL_KG_QUERY:
        question = str(params.get("question") or "").strip() or "?"
        return {
            "title": "本体图谱查询",
            "result_title": "图谱查询完成",
            "detail": question[:120],
            "tool": ATOMIC_TOOL_KG_QUERY,
        }
    if name == "load_uploaded_skill":
        skill = str(params.get("skill_name") or "").strip() or "?"
        return {
            "title": f"加载 Skill: {skill}",
            "result_title": f"Skill 已加载: {skill}",
            "failure_title": f"Skill 加载失败: {skill}",
            "detail": skill,
            "tool": f"skill.{skill}",
        }
    if name == "run_skill_script":
        skill = str(params.get("skill_name") or "").strip() or "?"
        entry = str(params.get("entry") or "").strip() or "auto"
        return {
            "title": f"运行 Skill 脚本: {skill}",
            "result_title": f"脚本执行完成: {skill}",
            "failure_title": f"脚本执行失败: {skill}",
            "detail": entry,
            "tool": f"skill.run.{skill}",
        }
    if name == "create_uploaded_skill":
        skill = str(params.get("name") or "").strip() or "?"
        return {
            "title": f"创建 Skill: {skill}",
            "result_title": f"Skill 已创建: {skill}",
            "detail": str(params.get("description") or "")[:120],
            "tool": "skill.create",
        }
    if name == "update_uploaded_skill_file":
        skill = str(params.get("skill_name") or "").strip() or "?"
        path = str(params.get("file_path") or "").strip() or "SKILL.md"
        return {
            "title": f"更新 Skill 文件: {skill}/{path}",
            "result_title": f"已更新: {skill}/{path}",
            "detail": path,
            "tool": "skill.update",
        }
    if name == "delete_uploaded_skill":
        skill = str(params.get("skill_name") or "").strip() or "?"
        return {
            "title": f"删除 Skill: {skill}",
            "result_title": f"Skill 已删除: {skill}",
            "detail": skill,
            "tool": "skill.delete",
        }
    if name == "read_agent_memory":
        return {
            "title": "读取 Agent 记忆",
            "result_title": "记忆已读取",
            "detail": "",
            "tool": "agent.memory",
        }
    if name == "append_agent_memory":
        note = str(params.get("note") or "").strip()[:80]
        return {
            "title": "写入 Agent 记忆",
            "result_title": "记忆已写入",
            "detail": note,
            "tool": "agent.memory",
        }
    if name == "list_library_documents":
        folder = str(params.get("folder_name") or params.get("folder_id") or "").strip()[:80]
        kw = str(params.get("keyword") or "").strip()[:80]
        detail = " / ".join(x for x in (folder, kw) if x)
        return {
            "title": "列出文档库文档",
            "result_title": "文档列表已获取",
            "detail": detail,
            "tool": "document.list",
        }
    if name == "list_manageable_documents":
        kw = str(params.get("keyword") or "").strip()[:80]
        return {
            "title": "列出可管理文档",
            "result_title": "文档列表已获取",
            "detail": kw,
            "tool": "document.list",
        }
    if name == "list_document_folders":
        scope = str(params.get("scope") or "").strip()
        return {
            "title": f"列出文件夹: {scope}",
            "result_title": "文件夹列表已获取",
            "detail": scope,
            "tool": "document.folders",
        }
    if name == "rename_document":
        title = str(params.get("new_title") or "").strip()[:80]
        return {
            "title": "重命名文档",
            "result_title": "文档已重命名",
            "detail": title,
            "tool": "document.rename",
        }
    if name == "move_document":
        folder = str(params.get("folder_name") or params.get("folder_id") or "未分类")[:80]
        return {
            "title": "移动文档",
            "result_title": "文档已移动",
            "detail": folder,
            "tool": "document.move",
        }
    if name == "share_document":
        names = params.get("user_names") or []
        detail = "、".join(str(x) for x in names[:3])[:80]
        return {
            "title": "分享文档",
            "result_title": "文档已分享",
            "detail": detail,
            "tool": "document.share",
        }
    if name == "delete_document":
        return {
            "title": "删除文档",
            "result_title": "文档已删除",
            "detail": str(params.get("document_id") or "")[:36],
            "tool": "document.delete",
        }
    if name == "list_todos":
        status = str(params.get("status") or "全部")
        return {
            "title": "列出待办",
            "result_title": "待办列表已获取",
            "detail": status,
            "tool": "platform.todos",
        }
    if name == "create_todo":
        title = str(params.get("title") or "").strip()[:80]
        return {
            "title": "添加待办",
            "result_title": "待办已添加",
            "detail": title,
            "tool": "platform.todos",
        }
    if name == "update_todo":
        title = str(params.get("title") or params.get("status") or "").strip()[:80]
        return {
            "title": "更新待办",
            "result_title": "待办已更新",
            "detail": title,
            "tool": "platform.todos",
        }
    if name == "delete_todo":
        return {
            "title": "删除待办",
            "result_title": "待办已删除",
            "detail": str(params.get("todo_id") or "")[:36],
            "tool": "platform.todos",
        }
    if name == "send_notification":
        title = str(params.get("title") or "").strip()[:80]
        return {
            "title": "发送系统通知",
            "result_title": "通知已发送",
            "detail": title,
            "tool": "platform.notification",
        }
    if name == "schedule_notification":
        delay = params.get("delay_minutes") or params.get("delay_seconds")
        title = str(params.get("title") or "").strip()[:80]
        boost_seconds = None
        if params.get("delay_seconds") is not None:
            boost_seconds = max(1, int(params["delay_seconds"]))
        elif params.get("delay_minutes") is not None:
            boost_seconds = max(60, int(params["delay_minutes"]) * 60)
        meta = {
            "title": "设置定时通知",
            "result_title": "定时通知已设置",
            "detail": f"{title} · {delay or params.get('scheduled_at', '')}"[:80],
            "tool": "platform.notification",
        }
        if boost_seconds is not None:
            meta["boost_seconds"] = str(boost_seconds)
        return meta
    if name == "list_scheduled_notifications":
        return {
            "title": "列出定时通知",
            "result_title": "定时通知列表已获取",
            "detail": "",
            "tool": "platform.notification",
        }
    if name == "cancel_scheduled_notification":
        return {
            "title": "取消定时通知",
            "result_title": "定时通知已取消",
            "detail": str(params.get("notification_id") or "")[:36],
            "tool": "platform.notification",
        }
    _browser_meta = {
        "browser_navigate": ("打开网页", "browser.navigate"),
        "browser_snapshot": ("读取页面结构", "browser.snapshot"),
        "browser_click": ("点击元素", "browser.click"),
        "browser_type": ("输入文本", "browser.type"),
        "browser_fill": ("批量填表", "browser.fill"),
        "browser_screenshot": ("页面截图", "browser.screenshot"),
        "browser_save_workflow": ("保存 RPA 流程", "browser.save_workflow"),
        "browser_close_session": ("关闭浏览器", "browser.close"),
        "browser_replay_workflow": ("回放 RPA 流程", "browser.replay"),
        "browser_run_task": ("自动探索网页", "browser.auto_task"),
        "schedule_browser_workflow": ("定时 RPA 任务", "browser.schedule"),
    }
    if name in _browser_meta:
        title, tool_key = _browser_meta[name]
        detail = ""
        if name == "browser_navigate":
            detail = str(params.get("url") or "")[:120]
        elif name in {"browser_click", "browser_type"}:
            detail = str(params.get("ref") or "")[:20]
        elif name == "browser_save_workflow":
            detail = str(params.get("name") or "")[:80]
        return {
            "title": title,
            "result_title": f"{title}完成",
            "detail": detail,
            "tool": tool_key,
        }
    return {
        "title": name or "工具调用",
        "result_title": name or "工具返回",
        "detail": "",
        "tool": name or "agent.tool",
    }
