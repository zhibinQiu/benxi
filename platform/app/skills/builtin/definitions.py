"""内置平台能力 Skill 定义。"""

from __future__ import annotations

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


def register_builtin_skills() -> None:
    specs: list[SkillDefinition] = [
        SkillDefinition(
            name="web-search",
            title="联网搜索",
            description="搜索互联网实时信息、政策动态、市场行情与公开数据。用户问最新资讯、价格、新闻或明确要求联网时使用。",
            source=SkillSource.BUILTIN,
            feature_id="ai_home",
            permission_code=None,
            readiness=SkillReadiness.READY,
            route="/ai-home",
            catalog_visible=False,
            orchestrated_tools=("web_search",),
            tools=(
                SkillToolSpec(
                    name="search",
                    description="按关键词检索互联网摘要",
                    parameters={
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
                    handler=h.handle_web_search,
                ),
            ),
        ),
        SkillDefinition(
            name="knowledge-search",
            title="知识库检索",
            description="从用户权限内的企业文档库检索片段，回答内部资料、制度、报告、项目文档等问题。",
            source=SkillSource.BUILTIN,
            feature_id="knowledge_search",
            permission_code="feature.knowledge_search",
            readiness=SkillReadiness.READY,
            route="/knowledge/search",
            catalog_visible=False,
            orchestrated_tools=("knowledge_retrieve",),
            tools=(
                SkillToolSpec(
                    name="retrieve",
                    description="在权限内文档中检索相关片段",
                    parameters={
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
                    handler=h.handle_knowledge_retrieve,
                ),
            ),
        ),
        SkillDefinition(
            name="kg-palantir",
            title="本体图谱",
            description="查询企业知识图谱中的实体、关系与子图，适合概念关联、产业链、组织关系等问题。",
            source=SkillSource.BUILTIN,
            feature_id="kg_palantir",
            permission_code="feature.kg_palantir",
            readiness=SkillReadiness.READY,
            route="/system/kg-palantir",
            catalog_visible=False,
            orchestrated_tools=("kg_query",),
            tools=(
                SkillToolSpec(
                    name="query_entities",
                    description="根据问题检索图谱实体与关系上下文",
                    parameters={
                        "type": "object",
                        "required": ["question"],
                        "properties": {
                            "question": {"type": "string", "description": "自然语言问题"},
                        },
                    },
                    handler=h.handle_kg_query,
                ),
            ),
        ),
        SkillDefinition(
            name="knowledge-research",
            title="知识综合检索",
            description=(
                "面向知识问答与资料检索：按需组合权限内文档检索、本体图谱与联网搜索，"
                "一次任务内合并上下文；闲聊或无需外部资料时可不调用。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="ai_home",
            permission_code=None,
            readiness=SkillReadiness.READY,
            route="/ai-home",
            orchestrated_tools=("knowledge_retrieve", "kg_query", "web_search"),
            tools=(),
        ),
        SkillDefinition(
            name="pdf-translate",
            title="PDF 翻译",
            description="提交 PDF 双语翻译任务，保留版式，支持术语表。用户提供 PDF 或要求翻译文档时使用。",
            source=SkillSource.BUILTIN,
            feature_id="pdf_translate",
            permission_code="feature.translate",
            readiness=SkillReadiness.STUB,
            route="/system/translate",
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
            title="会议助手",
            description="会议录音转写、说话人区分与智能总结。用户上传音频或提及会议记录时使用。",
            source=SkillSource.BUILTIN,
            feature_id="speech_to_text",
            permission_code="feature.speech_to_text",
            readiness=SkillReadiness.STUB,
            route="/system/speech",
            tools=(
                _stub_tool(
                    "transcribe",
                    "转写音频并生成会议纪要",
                    feature_title="会议助手",
                    route="/system/speech",
                    hint="需上传音频文件，后续将支持 agent 附件直传转写。",
                ),
            ),
        ),
        SkillDefinition(
            name="text-to-speech",
            title="语音合成",
            description="将文本合成为语音，适合播报、无障碍朗读场景。",
            source=SkillSource.BUILTIN,
            feature_id="text_to_speech",
            permission_code="feature.text_to_speech",
            readiness=SkillReadiness.STUB,
            route="/system/text-to-speech",
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
            description="从图片或 PDF 中提取文字与结构化内容。",
            source=SkillSource.BUILTIN,
            feature_id="ocr",
            permission_code="feature.ocr",
            readiness=SkillReadiness.STUB,
            route="/system/ocr",
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
            description="对比两个文档版本的差异，支持 PDF/Word。",
            source=SkillSource.BUILTIN,
            feature_id="compare",
            permission_code="feature.compare",
            readiness=SkillReadiness.STUB,
            route="/system/compare",
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
            description="基于知识库多路召回，按章节扩写生成长报告，可导出思维导图。",
            source=SkillSource.BUILTIN,
            feature_id="report_generation",
            permission_code="feature.report_generation",
            readiness=SkillReadiness.STUB,
            route="/knowledge/report",
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
            description="上传 Excel/CSV，对话生成 pandas 统计与可视化代码。",
            source=SkillSource.BUILTIN,
            feature_id="data_analysis",
            permission_code="feature.data_analysis",
            readiness=SkillReadiness.STUB,
            route="/system/data-analysis",
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
            name="assist-writing",
            title="辅助写作",
            description="润色、扩写、改写与结构化写作辅助。",
            source=SkillSource.BUILTIN,
            feature_id="assist_writing",
            permission_code="feature.assist_writing",
            readiness=SkillReadiness.STUB,
            route="/system/assist-writing",
            tools=(
                _stub_tool(
                    "rewrite",
                    "润色或改写文本",
                    feature_title="辅助写作",
                    route="/system/assist-writing",
                ),
            ),
        ),
        SkillDefinition(
            name="smart-data-query",
            title="智能问数",
            description="对结构化业务数据自然语言问数与图表分析。",
            source=SkillSource.BUILTIN,
            feature_id="smart_data_query",
            permission_code="feature.smart_data_query",
            readiness=SkillReadiness.STUB,
            route="/system/smart-data-query",
            tools=(
                _stub_tool(
                    "query",
                    "自然语言问数",
                    feature_title="智能问数",
                    route="/system/smart-data-query",
                ),
            ),
        ),
        SkillDefinition(
            name="carbon-qa",
            title="双碳问答",
            description="双碳政策、碳市场与减排领域专业问答。",
            source=SkillSource.BUILTIN,
            feature_id="carbon_qa",
            permission_code="feature.carbon_qa",
            readiness=SkillReadiness.STUB,
            route="/system/carbon-qa",
            tools=(
                _stub_tool(
                    "ask",
                    "双碳领域问答",
                    feature_title="双碳问答",
                    route="/system/carbon-qa",
                ),
            ),
        ),
    ]
    for spec in specs:
        register_skill(spec)
