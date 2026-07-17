"""内置平台能力 Skill 定义。"""

from __future__ import annotations

from app.core.tool_skill_taxonomy import (
    SKILL_BROWSER_AUTOMATION,
    SKILL_DEPT_ADMIN,
    SKILL_DOCUMENT_LIBRARY,
    SKILL_NOTIFICATION,
    SKILL_PLATFORM_OPS,
    SKILL_SKILL_DEV,
    SKILL_USER_ADMIN,
)
from app.skills.builtin import domain_handlers as dh
from app.skills.builtin import handlers as h
from app.skills.registry import register_skill
from app.skills.types import SkillDefinition, SkillReadiness, SkillSource, SkillToolSpec


def _stub_tool(
    name: str,
    description: str,
    *,
    feature_title: str,
    route: str,
    hint: str = "",
    extra_params: dict | None = None,
) -> SkillToolSpec:
    params = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    if extra_params:
        params["properties"] = extra_params
    return SkillToolSpec(
        name=name,
        description=description,
        parameters=params,
        handler=h.make_stub_handler(
            feature_title=feature_title, route=route, hint=hint
        ),
    )


def _domain_call_spec(
    *,
    description: str,
    allowed_hint: str,
    handler,
) -> SkillToolSpec:
    return SkillToolSpec(
        name="call",
        description=description,
        parameters={
            "type": "object",
            "required": ["operation"],
            "properties": {
                "operation": {
                    "type": "string",
                    "description": f"原子操作名。允许：{allowed_hint}",
                },
                "params": {
                    "type": "object",
                    "description": "传给该操作的参数（与原子 Tool schema 一致）",
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
        handler=handler,
    )


def register_builtin_skills() -> None:
    specs: list[SkillDefinition] = [
        # 以下为真正的技能（编排工作流 / 指令集），保留
        SkillDefinition(
            name="knowledge-research",
            title="知识综合检索",
            description=(
                "内置编排 Skill（非子 Agent）：指导 research 专精如何组合原子检索工具。"
                "做「组合取证」这一 playbook，不承担跨域调度。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="ai_home",
            permission_code=None,
            readiness=SkillReadiness.READY,
            route="/ai-home",
            catalog_visible=False,
            catalog_tier="resident",
            use_when=(
                "需组合图谱/联网/文档库取证；默认顺序图谱→联网→文档库，"
                "前序渠道有材料即停以提速；用户显式指定渠道时按其要求"
            ),
            dont_use_when="寒暄、平台系统操作、Skill 脚本执行、附件已含完整答案",
            output="带 [n] 引用的综合检索结论；事实优先级 图谱>联网>文档库>常识",
            orchestrated_tools=(
                "kg_query",
                "web_search",
                "knowledge_retrieve",
                "search_documents_by_name",
                "read_document_content",
            ),
            tools=(),
        ),
        SkillDefinition(
            name="deep-research",
            title="深度研究",
            description=(
                "对复杂课题进行多轮、多角度的互联网深度调研：分析问题、拆解子主题、"
                "生成多组搜索关键词、FireCrawl 读取网页全文、跨源交叉验证矛盾数据、"
                "输出带引用的结构化研究报告。适合需要深入调研的复杂问题。"
            ),
            source=SkillSource.BUILTIN,
            feature_id=None,
            readiness=SkillReadiness.READY,
            catalog_visible=True,
            catalog_tier="resident",
            use_when=(
                "需对复杂课题进行深度调研、多个角度交叉验证、"
                "获取最新数据和多方观点时使用"
            ),
            dont_use_when=(
                "简单知识查询（直接用 web_search / knowledge_retrieve）、"
                "内部知识库检索、浏览器自动化操作"
            ),
            output=(
                "带引用的结构化研究报告（含研究概述、关键发现、多源数据对比、矛盾说明）"
            ),
            tools=(
                SkillToolSpec(
                    name="call",
                    description=(
                        "对指定课题进行深度联网调研，委托子 Agent 执行多轮搜索与交叉验证"
                    ),
                    parameters={
                        "type": "object",
                        "required": ["task"],
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": "研究课题/问题描述，应包含足够的上下文和具体需求",
                            },
                        },
                    },
                    handler=h.handle_deep_research,
                ),
            ),
        ),
        SkillDefinition(
            name="pdf-translate",
            title="PDF 翻译",
            description="用户提供 PDF 或明确要求翻译/双语版文档时使用。",
            source=SkillSource.BUILTIN,
            feature_id="pdf_translate",
            permission_code="feature.translate",
            readiness=SkillReadiness.STUB,
            route="/system/translate",
            catalog_visible=False,
            tools=(
                _stub_tool(
                    "submit_job",
                    "提交 PDF 翻译后台任务",
                    feature_title="PDF 翻译",
                    route="/system/translate",
                    hint="完整流程需上传 PDF 文件，后续将支持 agent 直传。",
                    extra_params={
                        "document_id": {"type": "string", "description": "文档库 PDF ID"},
                        "target_lang": {"type": "string", "description": "目标语言，如 zh/en"},
                    },
                ),
            ),
        ),
        SkillDefinition(
            name="speech-to-text",
            title="语音转写",
            description="用户上传音频、提供视频链接、提及会议记录或要求转写总结时使用。",
            source=SkillSource.BUILTIN,
            feature_id="speech_to_text",
            permission_code="feature.speech_to_text",
            readiness=SkillReadiness.STUB,
            route="/system/speech",
            catalog_visible=False,
            tools=(
                _stub_tool(
                    "transcribe",
                    "转写音频/视频链接并生成会议纪要",
                    feature_title="语音转写",
                    route="/system/speech",
                    hint="可上传音频或粘贴公开视频链接转写。",
                ),
            ),
        ),
        SkillDefinition(
            name="text-to-speech",
            title="语音合成",
            description="用户要求朗读、播报或生成语音时使用。",
            source=SkillSource.BUILTIN,
            feature_id="text_to_speech",
            permission_code="feature.text_to_speech",
            readiness=SkillReadiness.STUB,
            route="/system/text-to-speech",
            catalog_visible=False,
            tools=(
                _stub_tool(
                    "synthesize",
                    "文本转语音",
                    feature_title="语音合成",
                    route="/system/text-to-speech",
                ),
            ),
        ),
        SkillDefinition(
            name="ocr",
            title="文件内容提取",
            description="用户上传图片/PDF 并要求提取文字或结构化内容时使用。",
            source=SkillSource.BUILTIN,
            feature_id="ocr",
            permission_code="feature.ocr",
            readiness=SkillReadiness.STUB,
            route="/system/ocr",
            catalog_visible=False,
            tools=(
                _stub_tool(
                    "extract",
                    "OCR 提取文件文本",
                    feature_title="文件内容提取",
                    route="/system/ocr",
                ),
            ),
        ),
        SkillDefinition(
            name="document-compare",
            title="文档对比",
            description="用户要对比两个文档版本差异时使用。",
            source=SkillSource.BUILTIN,
            feature_id="compare",
            permission_code="feature.compare",
            readiness=SkillReadiness.STUB,
            route="/system/compare",
            catalog_visible=False,
            tools=(
                _stub_tool(
                    "compare_versions",
                    "对比两个文档版本",
                    feature_title="文档对比",
                    route="/system/compare",
                ),
            ),
        ),
        SkillDefinition(
            name="report-generation",
            title="报告生成",
            description="用户要求生成长篇研究报告、章节扩写或导出思维导图时使用。",
            source=SkillSource.BUILTIN,
            feature_id="report_generation",
            permission_code="feature.report_generation",
            readiness=SkillReadiness.STUB,
            route="/knowledge/report",
            catalog_visible=False,
            tools=(
                _stub_tool(
                    "generate_outline",
                    "生成报告大纲并扩写",
                    feature_title="报告生成",
                    route="/knowledge/report",
                ),
            ),
        ),
        SkillDefinition(
            name="data-analysis",
            title="数据分析",
            description="用户上传 Excel/CSV 并要求统计分析或可视化时使用。",
            source=SkillSource.BUILTIN,
            feature_id="data_analysis",
            permission_code="feature.data_analysis",
            readiness=SkillReadiness.STUB,
            route="/system/data-analysis",
            catalog_visible=False,
            tools=(
                _stub_tool(
                    "analyze_dataset",
                    "对数据集执行统计分析",
                    feature_title="数据分析",
                    route="/system/data-analysis",
                ),
            ),
        ),
        SkillDefinition(
            name="smart-data-query",
            title="智能问数",
            description="用户用自然语言查询业务数据库或要看统计图表时使用。",
            source=SkillSource.BUILTIN,
            feature_id="smart_data_query",
            permission_code="feature.smart_data_query",
            readiness=SkillReadiness.STUB,
            route="/system/smart-data-query",
            catalog_visible=False,
            tools=(
                _stub_tool(
                    "query",
                    "自然语言问数",
                    feature_title="智能问数",
                    route="/system/smart-data-query",
                ),
            ),
        ),
        # --- 免费网页 AI Skill（真正的多步编排工作流） ---
        SkillDefinition(
            name="free-web-ai",
            title="免费 AI 工具",
            description=(
                "通过浏览器桥接免费网页 AI 执行文本对话、生图、识图问答等任务，无需付费 API key。"
                "支持手动选择平台，不指定时自动降级。支持连续对话（上下文记忆）。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="free_web_ai",
            permission_code="feature.free_web_ai",
            readiness=SkillReadiness.READY,
            route="/system/free-web-ai",
            catalog_visible=False,
            catalog_tier="resident",
            use_when="需要免费 AI 对话、代码生成、文案、翻译、生图、识图等任务，且不想用付费 API",
            dont_use_when="企业内部知识库检索（用 knowledge-search）、平台 CRUD、需联网获取最新信息（用 web_search）、需要精确构图或高分辨率出图（推荐用专业工具）、纯 OCR 提取（用 ocr feature）",
            output="AI 文本回复 / 图片 / 图片内容描述",
            tools=(
                SkillToolSpec(
                    name="chat",
                    description="向免费网页 AI 发送文本提示并获取回复（可指定 provider 选择平台）",
                    parameters={
                        "type": "object",
                        "required": ["prompt"],
                        "properties": {
                            "prompt": {"type": "string", "description": "提示词"},
                            "provider": {
                                "type": "string",
                                "description": "可选，指定 AI 平台: deepseek(代码/推理), doubao(通用), qwen(通用/生图)。不填则自动选择可用平台",
                                "enum": ["deepseek", "doubao", "qwen"],
                                "default": "",
                            },
                            "new_conversation": {
                                "type": "boolean",
                                "description": "是否强制新建对话（清空上下文）。默认为 false 沿用当前对话",
                                "default": False,
                            },
                        },
                    },
                    handler=h.handle_free_web_ai_chat,
                ),
                SkillToolSpec(
                    name="generate",
                    description="文字生成图片（支持豆包 doubao 或千问 qwen）",
                    parameters={
                        "type": "object",
                        "required": ["prompt"],
                        "properties": {
                            "prompt": {"type": "string", "description": "图片描述文字"},
                            "provider": {
                                "type": "string",
                                "description": "可选，指定生图平台: doubao(豆包), qwen(千问)。不填则自动选择",
                                "enum": ["doubao", "qwen"],
                                "default": "",
                            },
                            "new_conversation": {
                                "type": "boolean",
                                "description": "是否强制新建对话。默认为 false",
                                "default": False,
                            },
                        },
                    },
                    handler=h.handle_free_web_ai_image_gen,
                ),
                SkillToolSpec(
                    name="ask",
                    description="上传图片并提问（需提供服务器本地图片路径）",
                    parameters={
                        "type": "object",
                        "required": ["question", "image_path"],
                        "properties": {
                            "question": {"type": "string", "description": "关于图片的问题"},
                            "image_path": {"type": "string", "description": "图片文件在服务器上的路径"},
                            "provider": {
                                "type": "string",
                                "description": "可选，指定平台: doubao/qwen/deepseek。不填则自动选择",
                                "enum": ["doubao", "qwen", "deepseek"],
                                "default": "",
                            },
                            "new_conversation": {
                                "type": "boolean",
                                "description": "是否强制新建对话。默认为 false",
                                "default": False,
                            },
                        },
                    },
                    handler=h.handle_free_web_ai_image_ask,
                ),
            ),
        ),
        SkillDefinition(
            name=SKILL_SKILL_DEV,
            title="技能开发",
            description=(
                "上传型 Skill 生命周期：list/create/update/delete、run_skill_script 验证；"
                "经 invoke_skill(skill-development, call, {operation, params}) 调用。"
            ),
            source=SkillSource.BUILTIN,
            readiness=SkillReadiness.READY,
            catalog_visible=False,
            catalog_tier="resident",
            use_when=(
                "创建/修改/删除上传型 Skill 或 run_skill_script 取数验证；"
                "operation 如 create_skill、run_skill_script、list_agent_skills"
            ),
            dont_use_when=(
                "网页/联网调研（skill-dev 须 invoke_context_subagent 委托 browser-automation/web-search）、"
                "平台文档操作、撰写正式长报告"
            ),
            output="Skill 包变更或脚本执行输出",
            orchestrated_tools=(
                "list_agent_skills",
                "load_uploaded_skill",
                "run_skill_script",
                "create_skill",
                "update_uploaded_skill_file",
                "delete_uploaded_skill",
            ),
            tools=(
                _domain_call_spec(
                    description="执行技能管理操作",
                    allowed_hint=(
                        "list_agent_skills, create_skill, run_skill_script, "
                        "update_uploaded_skill_file, delete_uploaded_skill"
                    ),
                    handler=dh.handle_skill_development_call,
                ),
            ),
        ),
        # --- 浏览器自动化 ---
        SkillDefinition(
            name=SKILL_BROWSER_AUTOMATION,
            title="浏览器自动化",
            description=(
                "浏览器自动化操作（导航/点击/填表/截图/RPA 流程录制回放）；"
                "经 invoke_skill(browser-automation, call, {operation, params}) 调用。"
            ),
            source=SkillSource.BUILTIN,
            readiness=SkillReadiness.READY,
            catalog_visible=False,
            catalog_tier="resident",
            use_when=(
                "需要浏览器自动化操作：导航网页、点击元素、填表、截图、"
                "RPA 流程录制/回放、域名查询"
            ),
            dont_use_when="纯文本检索、平台文档操作、AI 对话、知识库检索",
            output="浏览器操作结果或截图",
            tools=(
                _domain_call_spec(
                    description="执行浏览器自动化操作",
                    allowed_hint=(
                        "browser_navigate, browser_snapshot, browser_click, "
                        "browser_type, browser_fill, browser_screenshot, "
                        "browser_save_workflow, browser_replay_workflow, "
                        "browser_run_task, browser_close_session, "
                        "schedule_browser_workflow"
                    ),
                    handler=dh.handle_browser_automation_call,
                ),
            ),
        ),
        # --- 文档库 ---
        SkillDefinition(
            name=SKILL_DOCUMENT_LIBRARY,
            title="文档库操作",
            description=(
                "文档库管理：搜索、读取、创建、移动、分享、删除文档与文件夹；"
                "经 invoke_skill(document-library, call, {operation, params}) 调用。"
            ),
            source=SkillSource.BUILTIN,
            readiness=SkillReadiness.READY,
            catalog_visible=False,
            catalog_tier="resident",
            use_when=(
                "需要操作文档库：搜索文档、读取内容、创建文档、移动/分享/删除文档、"
                "管理文件夹"
            ),
            dont_use_when=(
                "纯知识库语义检索（用 knowledge_retrieve）、"
                "浏览器自动化、AI 对话"
            ),
            output="文档操作结果",
            tools=(
                _domain_call_spec(
                    description="执行文档库操作",
                    allowed_hint=(
                        "search_documents_by_name, read_document_content, "
                        "list_library_documents, list_manageable_documents, "
                        "list_document_folders, create_kb_folder, "
                        "create_library_document, rename_document, "
                        "move_document, share_document, delete_document, "
                        "update_kb_folder, delete_kb_folder, "
                        "sync_document_knowledge, reindex_document"
                    ),
                    handler=dh.handle_document_library_call,
                ),
            ),
        ),
        # --- 平台操作 ---
        SkillDefinition(
            name=SKILL_PLATFORM_OPS,
            title="平台操作",
            description=(
                "待办事项管理；"
                "经 invoke_skill(platform-ops, call, {operation, params}) 调用。"
            ),
            source=SkillSource.BUILTIN,
            readiness=SkillReadiness.READY,
            catalog_visible=False,
            catalog_tier="resident",
            use_when="需要管理待办事项（创建/更新/删除/列出）",
            dont_use_when="浏览器操作、文档库操作、知识检索",
            output="操作结果",
            tools=(
                _domain_call_spec(
                    description="执行平台待办操作",
                    allowed_hint=(
                        "list_todos, create_todo, update_todo, delete_todo"
                    ),
                    handler=dh.handle_platform_ops_call,
                ),
            ),
        ),
        # --- 通知 ---
        SkillDefinition(
            name=SKILL_NOTIFICATION,
            title="通知管理",
            description=(
                "发送系统站内通知与定时提醒；"
                "经 invoke_skill(notification, call, {operation, params}) 调用。"
            ),
            source=SkillSource.BUILTIN,
            readiness=SkillReadiness.READY,
            catalog_visible=False,
            catalog_tier="resident",
            use_when=(
                "需要发送立即通知、设置定时提醒、查看已安排的定时通知、取消定时通知"
            ),
            dont_use_when="待办管理、文档库操作、浏览器操作",
            output="通知发送或操作结果",
            tools=(
                _domain_call_spec(
                    description="执行通知操作",
                    allowed_hint=(
                        "send_notification, schedule_notification, "
                        "list_scheduled_notifications, "
                        "cancel_scheduled_notification"
                    ),
                    handler=dh.handle_notification_call,
                ),
            ),
        ),
        # --- 用户管理 ---
        SkillDefinition(
            name=SKILL_USER_ADMIN,
            title="用户管理",
            description=(
                "平台用户管理：创建/更新/删除用户；"
                "经 invoke_skill(user-administration, call, {operation, params}) 调用。"
            ),
            source=SkillSource.BUILTIN,
            readiness=SkillReadiness.READY,
            catalog_visible=False,
            catalog_tier="resident",
            use_when="需要管理平台用户（创建/更新/删除）",
            dont_use_when="部门管理、文档操作、浏览器操作",
            output="用户管理操作结果",
            tools=(
                _domain_call_spec(
                    description="执行用户管理操作",
                    allowed_hint=(
                        "list_users, create_user, update_user, delete_user"
                    ),
                    handler=dh.handle_user_admin_call,
                ),
            ),
        ),
        # --- 部门管理 ---
        SkillDefinition(
            name=SKILL_DEPT_ADMIN,
            title="部门管理",
            description=(
                "平台部门管理：创建/更新/删除部门；"
                "经 invoke_skill(dept-administration, call, {operation, params}) 调用。"
            ),
            source=SkillSource.BUILTIN,
            readiness=SkillReadiness.READY,
            catalog_visible=False,
            catalog_tier="resident",
            use_when="需要管理平台部门（创建/更新/删除/列出）",
            dont_use_when="用户管理、文档操作、浏览器操作",
            output="部门管理操作结果",
            tools=(
                _domain_call_spec(
                    description="执行部门管理操作",
                    allowed_hint=(
                        "list_departments, create_department, "
                        "update_department, delete_department"
                    ),
                    handler=dh.handle_dept_admin_call,
                ),
            ),
        ),
    ]
    for spec in specs:
        register_skill(spec)
