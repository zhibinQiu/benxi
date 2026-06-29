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
            description="用户问最新资讯、价格、新闻或明确要求联网时使用。",
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
            description="用户问企业内部资料、制度、报告或项目文档，且需从权限内文档库检索时使用。",
            source=SkillSource.BUILTIN,
            feature_id="knowledge_search",
            permission_code="feature.knowledge_search",
            readiness=SkillReadiness.READY,
            route="/knowledge/search",
            catalog_visible=False,
            orchestrated_tools=("knowledge_retrieve", "search_documents_by_name"),
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
            description="用户问实体关联、产业链、组织关系或需从本体图谱查概念时使用。",
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
            description="组合文档/图谱/联网检索回答企业问题。",
            source=SkillSource.BUILTIN,
            feature_id="ai_home",
            permission_code=None,
            readiness=SkillReadiness.READY,
            route="/ai-home",
            catalog_tier="resident",
            use_when="需从文档库/图谱/联网组合取证答问，且非纯寒暄",
            dont_use_when="闲聊、平台用法、附件已含答案、单源检索够用",
            output="带 [n] 引用的检索结论",
            orchestrated_tools=(
                "knowledge_retrieve",
                "kg_query",
                "web_search",
                "search_documents_by_name",
            ),
            tools=(),
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
            description="用户上传音频、提及会议记录或要求转写总结时使用。",
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
            description="用户要求朗读、播报或生成语音时使用。",
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
            description="用户上传图片/PDF 并要求提取文字或结构化内容时使用。",
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
            description="用户要对比两个文档版本差异时使用。",
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
            description="用户要求生成长篇研究报告、章节扩写或导出思维导图时使用。",
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
            description="用户上传 Excel/CSV 并要求统计分析或可视化时使用。",
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
            name="smart-data-query",
            title="智能问数",
            description="用户用自然语言查询业务数据库或要看统计图表时使用。",
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
            description="用户询问双碳政策、碳市场或减排相关问题时使用。",
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
