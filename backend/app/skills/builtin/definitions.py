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
        # ── 前端路由 Stub Skill（占位用，无真实编排） ────────────
        SkillDefinition(
            name="pdf-translate",
            title="PDF 翻译",
            description="用户提供 PDF 或明确要求翻译/双语版文档时使用。",
            source=SkillSource.BUILTIN,
            feature_id="pdf_translate",
            permission_code="feature.translate",
            readiness=SkillReadiness.STUB,
            route="/system/translate",
            catalog_visible=True,
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
            catalog_visible=True,
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
            catalog_visible=True,
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
            catalog_visible=True,
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
            catalog_visible=True,
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
            catalog_visible=True,
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
            title="表格分析",
            description="用户上传 Excel/CSV 并要求对表格进行统计、清洗、转换、可视化等处理时使用。",
            source=SkillSource.BUILTIN,
            feature_id="data_analysis",
            permission_code="feature.data_analysis",
            readiness=SkillReadiness.STUB,
            route="/system/data-analysis",
            catalog_visible=True,
            tools=(
                _stub_tool(
                    "process_table",
                    "对表格数据执行清洗、转换、统计、可视化等处理",
                    feature_title="表格分析",
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
            catalog_visible=True,
            tools=(
                _stub_tool(
                    "query",
                    "自然语言问数",
                    feature_title="智能问数",
                    route="/system/smart-data-query",
                ),
            ),
        ),
        # ── 免费网页 AI Skill（真正的多步编排工作流） ───────
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
            catalog_visible=True,
            catalog_tier="resident",
            use_when="需要免费 AI 对话、代码生成、文案、翻译、生图、识图等任务，且不想用付费 API",
            dont_use_when="企业内部知识库检索（用 invoke_context_subagent(kind=search)）、平台 CRUD、需联网获取最新信息（用 invoke_context_subagent(kind=search)）、需要精确构图或高分辨率出图（推荐用专业工具）、纯 OCR 提取（用 ocr feature）",
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
        # ── 股市分析 Skills ─────────────────────────────
        SkillDefinition(
            name="stock-deep-analysis",
            title="AI 深度解读",
            description=(
                "单只个股的基本面深度分析：从财务数据、估值水平、行业竞争格局、"
                "成长逻辑等维度进行全面解读，输出结构化分析报告。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="stock_deep_analysis",
            permission_code="feature.stock_deep_analysis",
            readiness=SkillReadiness.READY,
            catalog_visible=True,
            use_when="需要单只个股的基本面深度分析：财务数据解读、估值评估、行业竞争格局、成长逻辑验证",
            dont_use_when="需要多角色辩论或量价技术面分析（分别用 stock-roundtable / stock-volume-price）",
            output="结构化个股深度分析报告（含公司概览、财务/估值/行业/成长/风险五维分析）",
            tools=(
                SkillToolSpec(
                    name="analyze",
                    description="对指定个股进行 AI 深度基本面分析",
                    parameters={
                        "type": "object",
                        "required": ["stock"],
                        "properties": {
                            "stock": {
                                "type": "string",
                                "description": "股票代码或名称，如 603986.SH / 兆易创新",
                            },
                            "dimensions": {
                                "type": "string",
                                "description": "可选，指定分析维度，逗号分隔：财务,估值,行业,成长,风险。默认全部",
                            },
                        },
                    },
                    handler=h.handle_stock_deep_analysis,
                ),
            ),
        ),
        SkillDefinition(
            name="stock-roundtable-debate-fundamental",
            title="辩论圆桌 · 基本面",
            description=(
                "多角色对抗性辩论研究，聚焦基本面维度（财务/估值/行业格局）。"
                "9 位参与者（4 位研究分工角色 + 巴菲特/芒格/彼得林奇/索罗斯/"
                "霍华德·马克斯等虚构角色）对抗性辩论，主持人逐轮裁决，输出完整圆桌报告。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="stock_roundtable_debate_fundamental",
            permission_code="feature.stock_roundtable_debate_fundamental",
            readiness=SkillReadiness.READY,
            catalog_visible=True,
            use_when="需要多角色对抗性辩论研究，且聚焦基本面维度（财务数据、估值逻辑、行业格局）：平台信号研究员/基本面研究员/市场定价研究员/风险反方 + 巴菲特/芒格/彼得林奇/索罗斯/霍华德·马克斯等虚构角色",
            dont_use_when="短线技术面分析（用 stock-roundtable-debate-shortterm 或 stock-volume-price）、单只个股基本面问答（用 stock-deep-analysis）、无虚构角色研究（用 stock-roundtable-research-fundamental）",
            output="完整圆桌研究报告（辩论圆桌·基本面）：含证据加权总表、非平庸洞见、研究分层结论、后续验证清单",
            tools=(
                SkillToolSpec(
                    name="debate",
                    description="对指定个股发起辩论圆桌·基本面研究",
                    parameters={
                        "type": "object",
                        "required": ["stock"],
                        "properties": {
                            "stock": {
                                "type": "string",
                                "description": "股票代码或名称，如 603986.SH / 兆易创新",
                            },
                            "rounds": {
                                "type": "integer",
                                "description": "可选，辩论轮数 3-5，默认 4",
                                "minimum": 3,
                                "maximum": 5,
                                "default": 4,
                            },
                        },
                    },
                    handler=h.handle_stock_roundtable_debate_fundamental,
                ),
            ),
        ),
        SkillDefinition(
            name="stock-roundtable-debate-shortterm",
            title="辩论圆桌 · 短线",
            description=(
                "多角色对抗性辩论研究，聚焦短线维度（量价/资金/情绪）。"
                "9 位参与者（4 位研究分工角色 + 巴菲特/芒格/彼得林奇/索罗斯/"
                "霍华德·马克斯等虚构角色）对抗性辩论，主持人逐轮裁决，输出完整圆桌报告。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="stock_roundtable_debate_shortterm",
            permission_code="feature.stock_roundtable_debate_shortterm",
            readiness=SkillReadiness.READY,
            catalog_visible=True,
            use_when="需要多角色对抗性辩论研究，且聚焦短线维度（量价关系、资金流向、市场情绪）：平台信号研究员/基本面研究员/市场定价研究员/风险反方 + 巴菲特/芒格/彼得林奇/索罗斯/霍华德·马克斯等虚构角色",
            dont_use_when="基本面深度分析（用 stock-deep-analysis 或 stock-roundtable-debate-fundamental）、无虚构角色短线研究（用 stock-roundtable-research-shortterm）、简单技术面诊断（用 stock-volume-price）",
            output="完整圆桌研究报告（辩论圆桌·短线）：含证据加权总表、非平庸洞见、研究分层结论、后续验证清单",
            tools=(
                SkillToolSpec(
                    name="debate",
                    description="对指定个股发起辩论圆桌·短线研究",
                    parameters={
                        "type": "object",
                        "required": ["stock"],
                        "properties": {
                            "stock": {
                                "type": "string",
                                "description": "股票代码或名称，如 603986.SH / 兆易创新",
                            },
                            "rounds": {
                                "type": "integer",
                                "description": "可选，辩论轮数 3-5，默认 4",
                                "minimum": 3,
                                "maximum": 5,
                                "default": 4,
                            },
                        },
                    },
                    handler=h.handle_stock_roundtable_debate_shortterm,
                ),
            ),
        ),
        SkillDefinition(
            name="stock-roundtable-research-fundamental",
            title="专业研究 · 基本面",
            description=(
                "无虚构角色的系统性基本面研究。4 位专业研究角色（行业分析师/财务分析师/"
                "估值分析师/风险分析师）协作，输出结构化研究报告，不含对抗性辩论。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="stock_roundtable_research_fundamental",
            permission_code="feature.stock_roundtable_research_fundamental",
            readiness=SkillReadiness.READY,
            catalog_visible=True,
            use_when="需要系统性基本面研究，不需要虚构角色的对抗性辩论：行业分析师/财务分析师/估值分析师/风险分析师研究团队协作",
            dont_use_when="需要多角色对抗性辩论（用 stock-roundtable-debate-fundamental）、单只个股基本面问答（用 stock-deep-analysis）、短线研究方向（用 stock-roundtable-research-shortterm）",
            output="结构化研究报告（专业研究·基本面）：含行业与竞争定位、财务深度拆解、估值评估、关键假设验证、风险清单",
            tools=(
                SkillToolSpec(
                    name="research",
                    description="对指定个股进行专业研究·基本面分析",
                    parameters={
                        "type": "object",
                        "required": ["stock"],
                        "properties": {
                            "stock": {
                                "type": "string",
                                "description": "股票代码或名称，如 603986.SH / 兆易创新",
                            },
                            "rounds": {
                                "type": "integer",
                                "description": "可选，研究迭代深度 3-5，默认 4",
                                "minimum": 3,
                                "maximum": 5,
                                "default": 4,
                            },
                        },
                    },
                    handler=h.handle_stock_roundtable_research_fundamental,
                ),
            ),
        ),
        SkillDefinition(
            name="stock-roundtable-research-shortterm",
            title="专业研究 · 短线",
            description=(
                "无虚构角色的短线技术面研究。4 位专业研究角色（技术分析师/资金分析师/"
                "情绪分析师/风险分析师）协作，输出结构化短线评估报告，不含对抗性辩论。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="stock_roundtable_research_shortterm",
            permission_code="feature.stock_roundtable_research_shortterm",
            readiness=SkillReadiness.READY,
            catalog_visible=True,
            use_when="需要系统性短线技术面研究，不需要虚构角色的对抗性辩论：技术分析师/资金分析师/情绪分析师/风险分析师研究团队协作",
            dont_use_when="需要多角色对抗性短线辩论（用 stock-roundtable-debate-shortterm）、简单量价诊断（用 stock-volume-price）、基本面研究方向（用 stock-roundtable-research-fundamental）",
            output="结构化研究报告（专业研究·短线）：含量价结构分析、资金面分析、情绪面分析、技术指标信号、关键价位与风险",
            tools=(
                SkillToolSpec(
                    name="research",
                    description="对指定个股进行专业研究·短线分析",
                    parameters={
                        "type": "object",
                        "required": ["stock"],
                        "properties": {
                            "stock": {
                                "type": "string",
                                "description": "股票代码或名称，如 603986.SH / 兆易创新",
                            },
                            "rounds": {
                                "type": "integer",
                                "description": "可选，研究迭代深度 3-5，默认 4",
                                "minimum": 3,
                                "maximum": 5,
                                "default": 4,
                            },
                        },
                    },
                    handler=h.handle_stock_roundtable_research_shortterm,
                ),
            ),
        ),
        SkillDefinition(
            name="stock-volume-price",
            title="量价会诊",
            description=(
                "短线技术面诊断。围绕指标（强弱评分/量比/换手/资金流向/市场温度）、"
                "形态（K线结构/经典形态/放量缩量关键位置）、"
                "趋势（均线位置/近期涨跌幅/波段强度与背离风险）、"
                "决策（观察清单与风险边界）四层框架，输出可复核的短线检查单，不给买卖指令。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="stock_volume_price",
            permission_code="feature.stock_volume_price",
            readiness=SkillReadiness.READY,
            catalog_visible=True,
            use_when="需要短线技术面诊断：量价分析、技术指标判断、K线形态识别、趋势结构分析、风险边界评估",
            dont_use_when="基本面深度分析或多角色辩论（分别用 stock-deep-analysis / stock-roundtable）",
            output="短线检查单（含四层框架：指标→形态→趋势→决策，不给买卖指令）",
            tools=(
                SkillToolSpec(
                    name="diagnose",
                    description="对指定个股进行量价技术面诊断，输出四层框架检查单",
                    parameters={
                        "type": "object",
                        "required": ["stock"],
                        "properties": {
                            "stock": {
                                "type": "string",
                                "description": "股票代码或名称，如 603986.SH / 兆易创新",
                            },
                            "aspects": {
                                "type": "string",
                                "description": "可选，指定分析维度，逗号分隔：indicators(指标),patterns(形态),trend(趋势),decision(决策)。默认全部",
                            },
                        },
                    },
                    handler=h.handle_stock_volume_price,
                ),
            ),
        ),
        # ── 双碳问答 ─────────────────────────────────────
        SkillDefinition(
            name="carbon-qa",
            title="双碳问答",
            description=(
                "双碳领域专业问答：通过官方源原子工具获取碳价/政策/排放·CCER·国际·地方数据，"
                "综合回答碳市场、碳达峰碳中和、CCER、碳排放核算等问题。"
                "新闻资讯类引导浏览器查最新，禁止编造实时数据。"
            ),
            source=SkillSource.BUILTIN,
            feature_id="carbon_qa",
            permission_code="feature.carbon_qa",
            readiness=SkillReadiness.READY,
            catalog_visible=True,
            catalog_tier="resident",
            use_when=(
                "双碳领域问题：碳价行情、碳交易、碳达峰碳中和政策、CCER、碳排放核算、节能降碳等"
            ),
            dont_use_when="其他非双碳领域问题、简单常识问答（无需查官方源）",
            output="双碳领域专业分析结果与建议（含来源链接）；新闻类返回浏览器执行指引",
            tools=(
                SkillToolSpec(
                    name="ask",
                    description=(
                        "回答双碳领域问题：自动调用 carbon_price / carbon_policy / carbon_data；"
                        "新闻资讯类返回浏览器查最新的执行指引"
                    ),
                    parameters={
                        "type": "object",
                        "required": ["question"],
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "用户的双碳问题",
                            },
                        },
                    },
                    handler=h.handle_carbon_qa_ask,
                ),
            ),
        ),
    ]
    for spec in specs:
        register_skill(spec)
